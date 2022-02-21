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

import glob
import json
import os
import sys
import traceback
import zipfile
import shutil
import re

from klever.scheduler.server import Server
from klever.scheduler.utils import execute, process_task_results, submit_task_results, memory_units_converter, time_units_converter
from klever.scheduler.client.options import adjust_options


def run_benchexec(mode, file=None, configuration=None):
    """
    This is the main routine of the native scheduler client that runs locally BenchExec for given job or task and upload
    results to Bridge.

    :param mode: Either "job" or "task".
    :param file: File with the configuration. Do not set the option alongside with the configuration one.
    :param configuration: The configuration dictionary. Do not set the option alongside with the file one.
    :return: It always exits at the end.
    """
    import logging

    if configuration and file:
        raise ValueError('Provide either file or configuration string')
    elif file:
        with open(file, encoding="utf-8") as fh:
            conf = json.loads(fh.read())
    else:
        conf = configuration

    # Check common configuration
    if "common" not in conf:
        raise KeyError("Provide configuration property 'common' as an JSON-object")

    # Prepare working directory
    if "working directory" not in conf["common"]:
        raise KeyError("Provide configuration property 'common''working directory'")

    # Go to the working directory to avoid creating files elsewhere
    os.chdir(conf["common"]['working directory'])

    # Initialize logger
    # create logger
    root_logger = logging.getLogger('')
    root_logger.setLevel(logging.DEBUG)

    # create console handler and set level to debug
    ch = logging.StreamHandler(sys.stdout)
    fh = logging.FileHandler("client-log.log", mode='w', encoding='utf-8')
    eh = logging.FileHandler("client-critical.log", mode='w', encoding='utf-8')

    ch.setLevel(logging.INFO)
    fh.setLevel(logging.DEBUG)
    eh.setLevel(logging.WARNING)

    # create formatter
    cf_formatter = logging.Formatter('%(asctime)s %(name)s %(levelname)5s> %(message)s')
    fh_formatter = logging.Formatter('%(asctime)s (%(filename)s:%(lineno)03d) %(name)s %(levelname)5s> %(message)s')
    eh_formatter = logging.Formatter('%(message)s')

    # add formatter to ch
    ch.setFormatter(cf_formatter)
    fh.setFormatter(fh_formatter)
    eh.setFormatter(eh_formatter)

    # add ch to logger
    root_logger.addHandler(ch)
    root_logger.addHandler(fh)
    root_logger.addHandler(eh)

    logger = logging.getLogger('SchedulerClient')

    # Try to report single short line message to error log to forward it to Bridge
    srv = None
    exit_code = 0
    try:
        logger.info("Going to solve a verification {} with identifier {}".format(mode, conf['identifier']))
        if mode == "task":
            srv = Server(logger, conf["Klever Bridge"], os.curdir)
            srv.register()
        elif mode not in ('job', 'task'):
            NotImplementedError("Provided mode {} is not supported by the client".format(mode))

        exit_code = solve(logger, conf, mode, srv)
    except:
        logger.warning(traceback.format_exc().rstrip())
        exit_code = 1
    finally:
        if not isinstance(exit_code, int):
            exit_code = 1
        logger.info("Exiting with exit code {}".format(str(exit_code)))
        os._exit(exit_code)


def solve(logger, conf, mode='job', srv=None):
    """
    Read configuration and either start job or task.

    :param logger: Logger object.
    :param conf: Configuration dictionary.
    :param mode: "job" or "task".
    :param srv: Server object.
    :return: Exit code of BenchExec or RunExec.
    """
    logger.debug("Create configuration file \"conf.json\"")
    with open("conf.json", "w", encoding="utf-8") as fp:
        json.dump(conf, fp, ensure_ascii=False, sort_keys=True, indent=4)

    if "resource limits" not in conf:
        raise KeyError("Configuration section 'resource limits' has not been provided")

    if mode == 'job':
        return solve_job(logger, conf)
    else:
        return solve_task(logger, conf, srv)


def solve_task(logger, conf, srv):
    """
    Perform preparation of task run and start it using BenchExec in either container or no-container mode.

    :param logger: Logger object.
    :param conf: Configuration dictionary.
    :param srv: Server object.
    :return: BenchExec exit code.
    """

    # Add verifiers path
    tool = conf['verifier']['name']
    version = conf['verifier']['version']
    path = conf['client']['verification tools'][tool][version]
    logger.debug("Add {!r} of version {!r} bin location {!r} to PATH".format(tool, version, path))
    os.environ["PATH"] = "{}:{}".format(path, os.environ["PATH"])

    if os.path.isdir('output'):
        shutil.rmtree('output', ignore_errors=True)

    logger.debug("Download task")
    ret = srv.pull_task(conf["identifier"], "task files.zip")
    if not ret:
        logger.info("Seems that the task data cannot be downloaded because of a respected reason, "
                    "so we have nothing to do there")
        os._exit(1)

    with zipfile.ZipFile('task files.zip') as zfp:
        zfp.extractall()

    os.makedirs("output".encode("utf-8"), exist_ok=True)

    # Replace benchmark.xml
    adjust_options('benchmark.xml', conf)

    args = prepare_task_arguments(logger, conf)
    exit_code = run(logger, args, conf, logger=logger)
    logger.info("Task solution has finished with exit code {}".format(exit_code))

    if exit_code != 0:
        # To keep the last warning exit without any exception
        if not isinstance(exit_code, int):
            exit_code = 1
        os._exit(exit_code)

    # Move tasks collected in container mode to expected place
    if "benchexec container mode" in conf['client'] and conf['client']["benchexec container mode"]:
        for entry in glob.glob(os.path.join('output', '*.files', 'cil.i', '*', '*')):
            shutil.move(entry, 'output')

    decision_results = process_task_results(logger)
    decision_results['resource limits'] = conf["resource limits"]
    logger.info("The speculative flag is: {}".format(conf.get('speculative')))
    logger.info("The solution status is: {}".format(decision_results.get('status', True)))
    if conf.get('speculative', False) and \
            decision_results.get('status', True) in ('OUT OF JAVA MEMORY', 'OUT OF MEMORY', 'TIMEOUT',
                                                     'SEGMENTATION FAULT', 'TIMEOUT (OUT OF JAVA MEMORY)') and \
            decision_results["resources"]["memory size"] >= 0.7 * decision_results['resource limits']['memory size']:
        logger.info("Do not upload solution since limits are reduced and we got: {!r}".
                    format(decision_results['status']))
        decision_results['uploaded'] = False
        speculative = True
    else:
        speculative = False
        decision_results['uploaded'] = True

    submit_task_results(logger, srv, "Klever", conf["identifier"], decision_results, os.path.curdir,
                        speculative=speculative)

    return exit_code


def solve_job(logger, conf):
    """
    Perfrom preparation of job run and start it using RunExec in either container or no-container mode.

    :param logger: Logger object.
    :param conf: Configuration dictionary.
    :return: RunExec exit code.
    """

    # Do this for deterministic python in job
    os.environ['PYTHONHASHSEED'] = "0"
    os.environ['PYTHONIOENCODING'] = "utf-8"
    os.environ['LC_LANG'] = "en_US"
    os.environ['LC_ALL'] = "en_US.UTF8"
    os.environ['LC_C'] = "en_US.UTF8"

    args = prepare_job_arguments(logger, conf)

    exit_code = run(logger, args, conf)
    logger.info("Job solution has finished with exit code {}".format(exit_code))

    return exit_code


def prepare_task_arguments(logger, conf):
    """
    Prepare arguments for solution of a verification task with BenchExec.

    :param conf: Configuration dictionary.
    :return: List with options.
    """

    # BenchExec arguments
    benchexec_bin = os.path.join(os.path.dirname(sys.executable), 'benchexec')
    args = [benchexec_bin]

    if "CPU cores" in conf["resource limits"] and conf["resource limits"]["CPU cores"]:
        args.extend(["--limitCores", str(conf["resource limits"]["number of CPU cores"])])
        args.append("--allowedCores")
        args.append(','.join(list(map(str, conf["resource limits"]["CPU cores"]))))

    if conf["resource limits"]["disk memory size"] and "benchexec measure disk" in conf['client'] and\
            conf['client']["benchexec measure disk"]:
        args.extend(["--filesSizeLimit", memory_units_converter(conf["resource limits"]["disk memory size"], 'MB')[1]])

    if 'memory size' in conf["resource limits"] and conf["resource limits"]['memory size']:
        numerical, string = memory_units_converter(conf["resource limits"]['memory size'], 'MB')
        # We do not need using precision more than one MB but the function can return float which can confuse BenchExec
        args.extend(['--memorylimit', '{}MB'.format(int(numerical))])

    if not conf["resource limits"].get('CPU time', 0) and not conf["resource limits"].get('soft CPU time', 0):
        # Disable explicitly time limitations
        args.extend(['--timelimit', '-1'])
    if conf["resource limits"].get('wall time', 0):
        args.extend(['--walltimelimit', time_units_converter(conf["resource limits"]["wall time"], "s")[1]])
    else:
        # As we cannot just disable the limit set a very large value
        args.extend(['--walltimelimit', str(60 * 60 * 24 * 365 * 100)])

    # Check container mode
    if "benchexec container mode" in conf['client'] and conf['client']["benchexec container mode"]:
        args.append('--container')

        if "benchexec container mode options" in conf['client']:
            args.extend(conf['client']["benchexec container mode options"])
    else:
        args.append('--no-container')

    args.extend(["--no-compress-results", "--outputpath", "./output/"])

    args.append("benchmark.xml")

    add_extra_paths(logger, conf)

    return args


def add_extra_paths(logger, conf):
    if "addon binaries" in conf["client"]:
        logger.debug("Add bin locations to {!r}: {!r}".format("PATH", ':'.join(conf["client"]["addon binaries"])))
        os.environ["PATH"] = "{}:{}".format(':'.join(conf["client"]["addon binaries"]), os.environ["PATH"])
        logger.debug("Current {!r} content is {!r}".format("PATH", os.environ["PATH"]))


def prepare_job_arguments(logger, conf):
    # RunExec arguments
    runexec_bin = os.path.join(os.path.dirname(sys.executable), 'runexec')
    args = [runexec_bin]

    if "CPU cores" in conf["resource limits"] and conf["resource limits"]["CPU cores"]:
        args.append("--cores")
        args.append(','.join(list(map(str, conf["resource limits"]["CPU cores"]))))

    if conf["resource limits"]["disk memory size"] and "runexec measure disk" in conf['client'] and \
            conf['client']["runexec measure disk"]:
        args.extend(["--filesSizeLimit", memory_units_converter(conf["resource limits"]["disk memory size"], "MB")[1]])

    if 'memory size' in conf["resource limits"] and conf["resource limits"]['memory size']:
        args.extend(['--memlimit', memory_units_converter(conf["resource limits"]['memory size'], "MB")[1]])

    # Check container mode
    if "runexec container mode" in conf['client'] and conf['client']["runexec container mode"]:
        args.append('--container')

        if "runexec container mode options" in conf['client']:
            args.extend(conf['client']["runexec container mode options"])
    else:
        args.append('--no-container')

    # Determine Klever Core script path
    if "Klever Core path" in conf["client"]:
        cmd = conf["client"]["Klever Core path"]
    else:
        cmd = os.path.join(os.path.dirname(sys.executable), "klever-core")

    # Add CIF path
    pythonpaths = conf["client"].setdefault("addon python packages", [])
    pythonpaths.append(os.path.join(os.path.dirname(cmd), os.path.pardir))
    add_extra_paths(logger, conf)

    # Check existence of the file
    args.append(cmd)

    return args


def run(selflogger, args, conf, logger=None):
    """
    Run given command with or without disk space limitations.

    :param selflogger: Logger to print log of this function.
    :param args: Command arguments.
    :param conf: Configuration dictionary of the client.
    :param logger: Logger object to print log of BenchExec or RunExec.
    :return: Exit code.
    """

    if conf["resource limits"]["disk memory size"] and not \
            (("runexec measure disk" in conf['client'] and conf['client']["runexec measure disk"]) or
             ("benchexec measure disk" in conf['client'] and conf['client']["benchexec measure disk"])):
        dl = conf["resource limits"]["disk memory size"]
        if "disk checking period" not in conf['client']:
            dcp = 60
        else:
            dcp = conf['client']['disk checking period']
    else:
        dcp = None
        dl = None

    if logger:
        ec = execute(args, logger=logger, disk_limitation=dl, disk_checking_period=dcp)
        if ec != 0:
            selflogger.info("Executor exited with non-zero exit code {}".format(ec))
        return ec
    else:
        with open('client-log.log', 'a', encoding="utf-8") as ste, \
                open('runexec stdout.log', 'w', encoding="utf-8") as sto:
            ec = execute(args, logger=logger, disk_limitation=dl, disk_checking_period=dcp, stderr=ste, stdout=sto)

        # Runexec prints its warnings and ordinary log to STDERR, thus lets try to find warnings there and move them
        # to critical log file
        if os.path.isfile('client-log.log'):
            with open('client-log.log', encoding="utf-8") as log:
                for line in log.readlines():
                    # Warnings can be added to the file only from RunExec
                    if re.search(r'WARNING - (.*)', line):
                        selflogger.warning(line.strip())
                    elif re.search(r'runexec: error: .*', line):
                        selflogger.error(line.strip())

        job_exit = None
        if ec == 0 and os.path.isfile('runexec stdout.log'):
            reason = None
            selflogger.info("Get return code of the job since runexec successfully exited")
            with open('runexec stdout.log', 'r', encoding="utf-8") as fp:
                for line in fp.readlines():
                    key, value = line.split('=')
                    if key and value and key == 'returnvalue':
                        job_exit = int(value)
                        if job_exit > 255:
                            # Be cool as Unix is
                            job_exit = job_exit >> 8
                    elif key and value and key == 'terminationreason':
                        reason = str(value).rstrip()
            if reason:
                selflogger.warning("RunExec set termination reason {!r}".format(reason))
                # Do not overwrite termination reason from disk space controller.
                if not os.path.exists('termination-reason.txt'):
                    with open('termination-reason.txt', 'w', encoding='utf-8') as fp:
                        if reason in ('cputime', 'memory'):
                            fp.write("Process was terminated since it ran out of {} {}"
                                     .format(reason, "(you may need to adjust job solution settings)"))
                        else:
                            fp.write("Process termination reason is: {}".format(reason))
                        fp.flush()
        if not os.path.isfile('runexec stdout.log') or job_exit is None:
            selflogger.info("Runexec exited successfully but it is not possible to read job exit code, aborting")
            ec = 1
        else:
            ec = job_exit

        return ec
