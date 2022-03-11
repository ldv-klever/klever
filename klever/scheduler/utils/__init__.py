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
import queue
import threading
import time
import signal
import zipfile
import re
import glob
import multiprocessing
import sys
import consul
from xml.etree import ElementTree

# This should prevent rumbling of urllib3
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("consul").setLevel(logging.WARNING)


class StreamQueue:
    """
    Implements queue to work with output stream to catch stderr or stdout.
    """

    def __init__(self, stream, stream_name, collect_all_output=False):
        self.stream = stream
        self.stream_name = stream_name
        self.collect_all_output = collect_all_output
        self.queue = queue.Queue()
        self.finished = False
        self.traceback = None
        self.thread = threading.Thread(target=self.__put_lines_from_stream_to_queue)
        self.output = []

    def get(self):
        try:
            return self.queue.get_nowait()
        except queue.Empty:
            return None

    def join(self):
        self.thread.join()

    def start(self):
        self.thread.start()

    def __put_lines_from_stream_to_queue(self):
        try:
            # This will put lines from stream to queue until stream will be closed. For instance it will happen when
            # execution of command will be completed.
            for line in self.stream:
                line = line.decode('utf-8').rstrip()
                self.queue.put(line)
                if self.collect_all_output:
                    self.output.append(line)

            # Nothing will be put to queue from now.
            self.finished = True
        except Exception:
            import traceback
            self.traceback = traceback.format_exc().rstrip()


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
    else:
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
        logger.debug("Clean working dir: {0}".format(conf["common"]['working directory']))
        logger.debug("Create working dir: {0}".format(conf["common"]['working directory']))
    else:
        logger.info("Keep working directory from the previous run")

    def handle_exception(exc_type, exc_value, exc_traceback):
        logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

    return conf, logger


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
    system_conf = dict()
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
    elif priority == "LOW":
        return 1
    elif priority == "HIGH":
        return 2
    elif priority == "URGENT":
        return 3
    else:
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
    else:
        return one_priority >= two_priority


def dir_size(dir):
    """
    Measure size of the given directory.

    :param dir: Path string.
    :return: integer size in Bytes.
    """
    if not os.path.isdir(dir):
        raise ValueError('Expect existing directory but it is not: {}'.format(dir))
    output = get_output('du -bs {} | cut -f1'.format(dir))
    try:
        res = int(output)
    except ValueError as e:
        # One of the files inside the dir has been removed. We should delete the warning message.
        splts = output.split('\n')
        if len(splts) < 2:
            # Can not delete the warning message
            raise e
        else:
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
        else:
            return True

    def handler(arg1, arg2):
        def terminate():
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
                terminate()
            restore_handlers()

            try:
                # Try to wait - it helps if a process is waiting for something, we need to check its status
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                print('{}: Process {} is still alive ...'.format(os.getpid(), pid))
                # Lets try it again
                time.sleep(10)

        terminate()

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
        else:
            return None

    set_handlers()
    cmd = args[0]
    if logger:
        logger.debug('Execute:\n{0}{1}{2}'.format(cmd,
                                                  '' if len(args) == 1 else ' ',
                                                  ' '.join('"{0}"'.format(arg) for arg in args[1:])))

        p = subprocess.Popen(args, env=env, stderr=subprocess.PIPE, cwd=cwd, preexec_fn=os.setsid)
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
        p = subprocess.Popen(args, env=env, cwd=cwd, preexec_fn=os.setsid, stderr=stderr, stdout=stdout)
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


def submit_task_results(logger, server, scheduler_type, identifier, decision_results, solution_path, speculative=False):
    """
    Pack output directory prepared by BenchExec and prepare report archive with decision results and
    upload it to the server.

    :param logger: Logger object.
    :param server: server.AbstractServer object.
    :param scheduler_type: Scheduler type.
    :param identifier: Task identifier.
    :param decision_results: Dictionary with decision results and measured resources.
    :param solution_path: Path to the directory with solution files.
    :param speculative: Do not upload solution to Bridge.
    :return: None
    """

    results_file = os.path.join(solution_path, "decision results.json")
    logger.debug("Save decision results to the disk: {}".format(os.path.abspath(results_file)))
    with open(results_file, "w", encoding="utf-8") as fp:
        json.dump(decision_results, fp, ensure_ascii=False, sort_keys=True, indent=4)

    results_archive = os.path.join(solution_path, 'decision result files.zip')
    logger.debug("Save decision results and files to the archive: {}".format(os.path.abspath(results_archive)))
    with open(results_archive, mode='w+b', buffering=0) as fp:
        with zipfile.ZipFile(fp, mode='w', compression=zipfile.ZIP_DEFLATED) as zfp:
            zfp.write(os.path.join(solution_path, "decision results.json"), "decision results.json")
            for dirpath, dirnames, filenames in os.walk(os.path.join(solution_path, "output")):
                for filename in filenames:
                    zfp.write(os.path.join(dirpath, filename),
                              os.path.join(os.path.relpath(dirpath, solution_path), filename))
            os.fsync(zfp.fp)

    if not speculative:
        server.submit_solution(identifier, decision_results, results_archive)
    else:
        logger.info("Do not upload speculative solution")

    kv_upload_solution(logger, identifier, scheduler_type, decision_results)


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


def __converter(value, table, kind, outunit):
    """
    Converts units to units.

    :param value: Given value as an integer, float or a string with units or without them.
    :param table: Table to translate units.
    :param kind: Time of units to print errors.
    :param outunit: Desired output unit, '' - means base.
    :return: Return the obtained value and the string of the value with units.
    """
    if isinstance(value, str):
        regex = re.compile("([0-9.]+)([a-zA-Z]*)$")
        if not regex.search(value):
            raise ValueError("Cannot parse string to extract the value and units: {!r}".format(value))
        else:
            value, inunit = regex.search(value).groups()
    else:
        inunit = ''
    # Check values
    for v in (inunit, outunit):
        if v not in table:
            raise ValueError("Get unknown {} unit {!r}".format(kind, v))

    # Get number and get bytes
    value_in_base = float(value) * table[inunit]

    # Than convert bytes into desired value
    value_in_out = value_in_base / table[outunit]

    # Align if necessary
    if outunit != '':
        fvalue = round(float(value_in_out), 2)
        ivalue = int(round(float(value_in_out), 0))
        if abs(fvalue - ivalue) < 0.1:
            value_in_out = ivalue
        else:
            value_in_out = fvalue
    else:
        value_in_out = int(value_in_out)

    return value_in_out, "{}{}".format(value_in_out, outunit)


def memory_units_converter(num, outunit=''):
    """
    Translate memory units.

    :param num: Given value as an integer, float or a string with units or without them.
    :param outunit: Desired output unit, '' - means Bytes.
    :return: Return the obtained value and the string of the value with units.
    """
    units_in_bytes = {
        '': 1,
        "B": 1,
        "KB": 10 ** 3,
        "MB": 10 ** 6,
        "GB": 10 ** 9,
        "TB": 10 ** 12,
        "KiB": 2 ** 10,
        "MiB": 2 ** 20,
        "GiB": 2 ** 30,
        "TiB": 2 ** 40,
    }

    return __converter(num, units_in_bytes, 'memory', outunit)


def time_units_converter(num, outunit=''):
    """
    Translate time units.

    :param num: Given value as an integer, float or a string with units or without them.
    :param outunit: Desired output unit, '' - means seconds.
    :return: Return the obtained value and the string of the value with units.
    """
    units_in_seconds = {
        '': 1,
        "s": 1,
        "min": 60,
        "h": 60 ** 2
    }

    return __converter(num, units_in_seconds, 'time', outunit)


def kv_upload_solution(logger, identifier, scheduler_type, dataset):
    """
    Upload data to controller storage.

    :param logger: Logger object.
    :param identifier: Task identifier.
    :param scheduler_type: Scheduler type.
    :param dataset: Data to save about the solution. This should be dictionary.
    :return: None
    """
    key = 'solutions/{}/{}'.format(scheduler_type, identifier)
    consul_client = consul.Consul()
    try:
        consul_client.kv.put(key, json.dumps(dataset))
        return
    except (AttributeError, KeyError):
        logger.warning("Cannot save key {!r} to key-value storage".format(key))


def kv_get_solution(logger, scheduler_type, identifier):
    """
    Upload data to controller storage.

    :param logger: Logger object.
    :param scheduler_type: Type of the scheduler to avoid races.
    :param identifier: Task identifier.
    :return: None
    """
    key = 'solutions/{}/{}'.format(scheduler_type, identifier)
    consul_client = consul.Consul()
    try:
        index, data = consul_client.kv.get(key)
        return json.loads(data['Value'])
    except (AttributeError, KeyError) as err:
        logger.warning("Cannot obtain key {!r} from key-value storage: {!r}".format(key, err))


def kv_clear_solutions(logger, scheduler_type, identifier=None):
    """
    Upload data to controller storage.

    :param logger: Logger object.
    :param scheduler_type: Type of the scheduler to avoid races.
    :param identifier: Task identifier.
    :return: None
    """
    try:
        consul_client = consul.Consul()
        if isinstance(identifier, str):
            consul_client.kv.delete('solutions/{}/{}'.format(scheduler_type, identifier), recurse=True)
        else:
            consul_client.kv.delete('solutions/{}'.format(scheduler_type), recurse=True)
    except (AttributeError, KeyError):
        logger.warning("Key-value storage is inaccessible")
