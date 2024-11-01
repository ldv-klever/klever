#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import logging
import logging.config
import argparse
import os
import json
import shutil
import subprocess
import time
import signal
import zipfile
import re
import glob
import multiprocessing
import sys
from xml.etree import ElementTree

from klever.scheduler.utils import consul
from klever.core.utils import memory_units_converter, StreamQueue

# This should prevent rumbling of urllib3
logging.getLogger("urllib3").setLevel(logging.WARNING)


def common_initialization(tool, conf=None):
    """
    Start execution of the corresponding cloud tool.

    :param tool: Tool name string.
    :param conf: Configuration dictionary.
    :return: Configuration dictionary.
    """

    if not conf:
        # Parse configuration
        parser = argparse.ArgumentParser(description='Start cloud {} according to the provided configuration.'.
                                         format(tool))
        parser.add_argument('config', metavar="CONF", help='Path to the cloud configuration file.')
        args = parser.parse_args()

        # Read configuration from file.
        with open(args.config, encoding="utf-8") as fp:
            conf = json.load(fp)

    if "Klever Bridge" not in conf:
        raise KeyError("Provide configuration property 'Klever Bridge' as an JSON-object")

    if tool != "Client controller":
        if "scheduler" not in conf:
            raise KeyError("Provide configuration property 'scheduler' as an JSON-object")

        if "Klever jobs and tasks queue" not in conf:
            raise KeyError("Provide configuration property 'Klever jobs and tasks queue' as an JSON-object")

    # Check common configuration
    if "common" not in conf:
        raise KeyError("Provide configuration property 'common' as an JSON-object")

    # Prepare working directory
    if "working directory" not in conf["common"]:
        raise KeyError("Provide configuration property 'common''working directory'")

    conf["common"]['working directory'] = os.path.abspath(conf["common"]['working directory'])

    clean_dir = False
    if os.path.isdir(conf["common"]['working directory']) and not conf["common"].get("keep working directory", False):
        clean_dir = True
        shutil.rmtree(conf["common"]['working directory'], True)
    os.makedirs(conf["common"]['working directory'].encode("utf-8"), exist_ok=True)
    os.chdir(conf["common"]['working directory'])

    # Configure logging
    if "logging" not in conf["common"]:
        raise KeyError("Provide configuration property 'common''logging' according to Python logging specs")
    logging.config.dictConfig(conf["common"]['logging'])
    logger = logging.getLogger()

    # Report about the dir
    if clean_dir:
        # Go to the working directory to avoid creating files elsewhere
        logger.debug("Clean working dir: %s", conf['common']['working directory'])
        logger.debug("Create working dir: %s", conf['common']['working directory'])
    else:
        logger.info("Keep working directory from the previous run")

    def handle_exception(exc_type, exc_value, exc_traceback):
        logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

    return conf, logger


def prepare_node_info(node_info):
    """
    Check that required values have been provided and add general node information.
    :param node_info: Dictionary with "node configuration" part of the configuration.
    :return: Updated dictionary.
    """
    system_info = extract_system_information()
    result = node_info.copy()
    result.update(system_info)

    # Check required data
    if "CPU number" not in result:
        raise KeyError("Provide configuration property 'node configuration''CPU number'")
    if "available RAM memory" not in result:
        raise KeyError("Provide configuration property 'node configuration''available RAM memory'")
    if "available disk memory" not in result:
        raise KeyError("Provide configuration property 'node configuration''available disk memory'")
    if "available for jobs" not in result:
        raise KeyError("Provide configuration property 'node configuration''available for jobs'")
    if "available for tasks" not in result:
        raise KeyError("Provide configuration property 'node configuration''available for tasks'")

    # TODO: extract this to the common library. Add debug printing in particular warn if specified values are out of bounds. Try to use some mathematical functions like min and max.
    # Do magic transformations like in get_parallel_threads_num() from klever.core/utils.py to dynamically adjust available
    # resources if they are specified as decimals.
    if isinstance(result["available CPU number"], float):
        result["available CPU number"] = int(result["CPU number"] * result["available CPU number"])
    elif result["available CPU number"] > result["CPU number"]:
        result["available CPU number"] = result["CPU number"]
    if isinstance(result["available RAM memory"], float):
        result["available RAM memory"] = int(result["RAM memory"] * result["available RAM memory"])
    elif isinstance(result["available RAM memory"], str):
        result["available RAM memory"] = memory_units_converter(result["available RAM memory"], '')[0]
    if result["available RAM memory"] < 1000 ** 3:
        result["available RAM memory"] = 1000 ** 3
    elif result["available RAM memory"] > result["RAM memory"]:
        result["available RAM memory"] = result["RAM memory"]
    if isinstance(result["available disk memory"], float):
        result["available disk memory"] = int(result["disk memory"] * result["available disk memory"])
    elif isinstance(result["available disk memory"], str):
        result["available disk memory"] = memory_units_converter(result["available disk memory"], '')[0]
    if result["available disk memory"] < 1000 ** 3:
        result["available disk memory"] = 1000 ** 3
    elif result["available disk memory"] > result["disk memory"] - 1000 ** 3:
        result["available disk memory"] = result["disk memory"] - 1000 ** 3

    # Check feasibility of limits
    if result["available RAM memory"] > result["RAM memory"]:
        raise ValueError("Node has {} bytes of RAM memory but {} is attempted to reserve".
                         format(result["RAM memory"], result["available RAM memory"]))
    if result["available disk memory"] > result["disk memory"]:
        raise ValueError("Node has {} bytes of disk memory but {} is attempted to reserve".
                         format(result["disk memory"], result["available disk memory"]))
    if result["available CPU number"] > result["CPU number"]:
        raise ValueError("Node has {} CPU cores but {} is attempted to reserve".
                         format(result["CPU number"], result["available CPU number"]))

    return result


def split_archive_name(path):
    """
    Split archive name into file name and extension. The difference with is.path.splitext is that this function can
    properly parse double zipped archive names like myname.tar.gz providing "myname" and ".tar.gz". Would not work
    properly with names which contain dots.
    :param path: File path or file name.
    :return: tuple with file name at the first position and extension within the second one.
    """
    name = path
    extension = ""
    while "." in name:
        split = os.path.splitext(name)
        name = split[0]
        extension = split[1] + extension

    return name, extension


def get_output(command):
    """
    Return STDOUT of the command.
    :param command: a command to be executed to get an entity value.
    """
    val = subprocess.getoutput(command)
    if not val:
        raise ValueError('Cannot get anything executing {}'.format(command))

    return val


def extract_system_information():
    """
    Extract information about the system and return it as a dictionary.
    :return: dictionary with system info,
    """
    system_conf = {}
    system_conf["node name"] = get_output('uname -n')
    system_conf["CPU model"] = get_output('cat /proc/cpuinfo | grep -m1 "model name" | sed -r "s/^.*: //"')
    system_conf["CPU number"] = len(extract_cpu_cores_info().keys())
    system_conf["RAM memory"] = \
        int(get_output('cat /proc/meminfo | grep "MemTotal" | sed -r "s/^.*: *([0-9]+).*/1024 * \\1/" | bc'))
    system_conf["disk memory"] = 1024 * int(get_output('df ./ | grep / | awk \'{ print $4 }\''))
    system_conf["Linux kernel version"] = get_output('uname -r')
    system_conf["arch"] = get_output('uname -m')
    return system_conf


def sort_priority(priority):
    """
    Use the function to sort tasks by their priorities. For higher priority return higher integer.
    :param priority: String.
    :return: 3, 2, 1, 0
    """
    if priority == "IDLE":
        return 0
    if priority == "LOW":
        return 1
    if priority == "HIGH":
        return 2
    if priority == "URGENT":
        return 3

    raise ValueError("Unknown priority: {}".format(priority))


def higher_priority(one, two, strictly=False):
    """
    Compare that one priority is higher than second priority. If the third argument is True (False by default) than
    comparison is strict.

    :param one: 'IDLE', 'LOW', 'HIGH' or 'URGENT'
    :param two: 'IDLE', 'LOW', 'HIGH' or 'URGENT'
    :param strictly: False or True
    :return: one > two or one >= two (default)
    """

    one_priority = sort_priority(one)
    two_priority = sort_priority(two)

    if strictly:
        return one_priority > two_priority

    return one_priority >= two_priority


def dir_size(dir_path):
    """
    Measure size of the given directory.

    :param dir_path: Path string.
    :return: integer size in Bytes.
    """
    if not os.path.isdir(dir_path):
        raise ValueError('Expect existing directory but it is not: {}'.format(dir_path))
    # TODO: this measurement requires too much overheads
    # Currently we suggest to turn on options "runexec measure disk" and "benchexec measure disk" to prevent
    # measurements with du commands.
    output = get_output('du -bs {} | cut -f1'.format(dir_path))
    try:
        res = int(output)
    except ValueError as e:
        # One of the files inside the dir has been removed. We should delete the warning message.
        splts = output.split('\n')
        if len(splts) < 2:
            # Can not delete the warning message
            raise e

        res = int(splts[-1])
    return res


def execute(args, env=None, cwd=None, timeout=0.5, logger=None, stderr=sys.stderr, stdout=sys.stdout,
            disk_limitation=None, disk_checking_period=30):
    """
    Execute given command in a separate process catching its stderr if necessary.

    :param args: Command arguments.
    :param env: Environment variables.
    :param cwd: Current working directory to run the command.
    :param timeout: Timeout for the command.
    :param logger: Logger object.
    :param stderr: Pipe or file descriptor to redirect output. Use it if logger is not provided.
    :param stderr: Pipe or file descriptor to redirect output. Use it if logger is not provided.
    :param disk_limitation: Allowed integer size of disk memory in Bytes of current working directory.
    :param disk_checking_period: Integer number of seconds for the disk space measuring interval.
    :return: subprocess.Popen.returncode.
    """
    original_sigint_handler = signal.getsignal(signal.SIGINT)
    original_sigtrm_handler = signal.getsignal(signal.SIGTERM)

    def restore_handlers():
        signal.signal(signal.SIGTERM, original_sigtrm_handler)
        signal.signal(signal.SIGINT, original_sigint_handler)

    def process_alive(pid):
        try:
            os.kill(pid, 0)
        except OSError:
            return False

        return True

    def handler(arg1, arg2):  # pylint:disable=unused-argument
        def terminate(pid):
            print("{}: Cancellation of {} is successful, exiting".format(os.getpid(), pid))
            os._exit(-1)

        # Repeat until it dies
        if p and p.pid:
            pid = p.pid
            print("{}: Cancelling process {}".format(os.getpid(), pid))
            # Sent initial signals
            try:
                os.kill(pid, signal.SIGINT)
            except ProcessLookupError:
                terminate(pid)
            restore_handlers()

            try:
                # Try to wait - it helps if a process is waiting for something, we need to check its status
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                print('{}: Process {} is still alive ...'.format(os.getpid(), pid))
                # Lets try it again
                time.sleep(10)

        terminate(None)

    def set_handlers():
        signal.signal(signal.SIGTERM, handler)
        signal.signal(signal.SIGINT, handler)

    def disk_controller(pid, limitation, period):
        while process_alive(pid):
            s = dir_size("./")
            if s > limitation:
                # Kill the process
                print("Reached disk memory limit of {}GB, killing process {}"
                      .format(memory_units_converter(limitation, 'GB')[0], pid))

                with open('termination-reason.txt', 'w', encoding='utf-8') as fp:
                    fp.write(
                        "Process was terminated since it consumed {}GB of disk space while only {}GB is allowed {}"
                        .format(memory_units_converter(s, 'GB')[0], memory_units_converter(limitation, 'GB')[0],
                                "(you may need to adjust job solution settings)")
                    )
                    fp.flush()

                os.kill(pid, signal.SIGINT)

            time.sleep(period)

        os._exit(0)

    def activate_disk_limitation(pid, limitation):
        if limitation:
            checker = multiprocessing.Process(target=disk_controller, args=(pid, limitation, disk_checking_period))
            checker.start()
            return checker

        return None

    set_handlers()
    cmd = args[0]
    if logger:
        logger.debug('Execute:\n{0}{1}{2}'.format(cmd,
                                                  '' if len(args) == 1 else ' ',
                                                  ' '.join('"{0}"'.format(arg) for arg in args[1:])))

        p = subprocess.Popen(args, env=env, stderr=subprocess.PIPE, cwd=cwd, preexec_fn=os.setsid)  # pylint:disable=subprocess-popen-preexec-fn
        disk_checker = activate_disk_limitation(p.pid, disk_limitation)

        err_q = StreamQueue(p.stderr, 'STDERR', True)
        err_q.start()

        # Print to logs everything that is printed to STDOUT and STDERR each timeout seconds. Last try is required to
        # print last messages queued before command finishes.
        last_try = True
        while not err_q.finished or last_try:
            if err_q.traceback:
                raise RuntimeError(
                    'STDERR reader thread failed with the following traceback:\n{0}'.format(err_q.traceback))
            last_try = not err_q.finished
            time.sleep(timeout)

            output = []
            while True:
                line = err_q.get()
                if line is None:
                    break
                output.append(line)
            if output:
                m = '"{0}" outputted to {1}:\n{2}'.format(cmd, err_q.stream_name, '\n'.join(output))
                logger.warning(m)

        err_q.join()
    else:
        p = subprocess.Popen(args, env=env, cwd=cwd, preexec_fn=os.setsid, # pylint:disable=subprocess-popen-preexec-fn
                             stderr=stderr, stdout=stdout)  # pylint: disable=consider-using-with
        disk_checker = activate_disk_limitation(p.pid, disk_limitation)

    p.wait()
    if disk_checker:
        disk_checker.terminate()
        disk_checker.join()
    restore_handlers()

    return p.returncode


def process_task_results(logger):
    """
    Expect working directory after BenchExec finished its work. Then parse its generated files and read spent resources.

    :param logger: Logger object.
    :return:
    """
    logger.debug("Translate benchexec output into our results format")
    decision_results = {
        "resources": {}
    }
    # Actually there is the only output file, but benchexec is quite clever to add current date to its name.
    solutions = glob.glob(os.path.join("output", "benchmark*results.xml"))
    if len(solutions) == 0:
        raise FileNotFoundError("Cannot find any solution generated by BenchExec")

    for benexec_output in solutions:
        with open(benexec_output, encoding="utf-8") as fp:
            result = ElementTree.parse(fp).getroot()
            decision_results["desc"] = '{0}\n{1} {2}'.format(result.attrib.get('generator'),
                                                             result.attrib.get('tool'),
                                                             result.attrib.get('version'))
            run = result.findall("run")[0]
            for column in run.iter("column"):
                name, value = [column.attrib.get(name) for name in ("title", "value")]
                if name == "cputime":
                    match = re.search(r"^(\d+\.\d+)s$", value)
                    if match:
                        decision_results["resources"]["CPU time"] = int(float(match.groups()[0]) * 1000)
                elif name == "walltime":
                    match = re.search(r"^(\d+\.\d+)s$", value)
                    if match:
                        decision_results["resources"]["wall time"] = int(float(match.groups()[0]) * 1000)
                elif name == "memory":
                    decision_results["resources"]["memory size"] = int(value[:-1])
                elif name == "returnvalue":
                    decision_results["exit code"] = int(value)
                elif name == "status":
                    decision_results["status"] = str(value)

    return decision_results


def submit_task_results(logger, server, identifier, decision_results, solution_path, speculative=False, local_run=False):
    """
    Pack output directory prepared by BenchExec and prepare report archive with decision results and
    upload it to the server.

    :param logger: Logger object.
    :param server: server.AbstractServer object.
    :param identifier: Task identifier.
    :param decision_results: Dictionary with decision results and measured resources.
    :param solution_path: Path to the directory with solution files.
    :param speculative: Do not upload solution to Bridge.
    :param local_run: if the run is local, no need to transfer decision results via Bridge.
    :return: None
    """

    results_file = os.path.join(solution_path, "decision results.json")
    logger.debug("Save decision results to the disk: {}".format(os.path.abspath(results_file)))
    if local_run:
        decision_results['output dir'] = os.path.abspath(os.path.join(solution_path, "output"))
    with open(results_file, "w", encoding="utf-8") as fp:
        json.dump(decision_results, fp, ensure_ascii=False, sort_keys=True, indent=4)

    results_archive = os.path.join(solution_path, 'decision result files.zip')
    logger.debug("Save decision results and files to the archive: {}".format(os.path.abspath(results_archive)))
    with open(results_archive, mode='w+b', buffering=0) as fp:
        with zipfile.ZipFile(fp, mode='w', compression=zipfile.ZIP_DEFLATED) as zfp:
            zfp.write(os.path.join(solution_path, "decision results.json"), "decision results.json")
            if local_run:
                # Prepare a small archive, as Bridge requires it
                # the other files will be accessed directly via file system
                pass
            else:
                for dirpath, _, filenames in os.walk(os.path.join(solution_path, "output")):
                    for filename in filenames:
                        zfp.write(os.path.join(dirpath, filename),
                                  os.path.join(os.path.relpath(dirpath, solution_path), filename))
            os.fsync(zfp.fp)

    if not speculative:
        server.submit_solution(identifier, decision_results, results_archive)
    else:
        logger.info("Do not upload speculative solution")


def extract_cpu_cores_info():
    """
    Read /proc/cpuinfo to get information about cores and virtual cores.

    :return: {int(core id) -> int(virtual core id)}
    """
    data = {}
    with open('/proc/cpuinfo', encoding='utf-8') as fp:
        current_vc = None
        for line in fp.readlines():
            vc = re.match(r'processor\s*:\s*(\d+)', line)
            pc = re.match(r'core\sid\s*:\s*(\d+)', line)

            if vc:
                current_vc = int(vc.group(1))
            if pc:
                pc = int(pc.group(1))
                if pc in data:
                    data[pc].append(current_vc)
                else:
                    data[pc] = [current_vc]

    return data
