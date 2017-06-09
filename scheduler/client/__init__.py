#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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

from utils import execute, process_task_results, submit_task_results
from server.bridge import Server


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
        with open(file, encoding="utf8") as fh:
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
    fh = logging.FileHandler("client-log.log", mode='w', encoding='utf8')
    eh = logging.FileHandler("client-critical.log", mode='w', encoding='utf8')

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
    server = None
    exit_code = 0
    try:
        logger.info("Going to solve a verification {}".format(mode))
        if mode == "task":
            server = Server(logger, conf["Klever Bridge"], os.curdir)
            server.register()
        elif mode not in ('job', 'task'):
            NotImplementedError("Provided mode {} is not supported by the client".format(mode))

        exit_code = solve(logger, conf, mode, server)
        logger.info("Exiting with exit code {}".format(str(exit_code)))
    except:
        logger.warning(traceback.format_exc().rstrip())
        exit_code = -1
    finally:
        if server:
            server.stop()
        os._exit(int(exit_code))


def solve(logger, conf, mode='job', server=None):
    logger.debug("Create configuration file \"conf.json\"")
    with open("conf.json", "w", encoding="utf8") as fp:
        json.dump(conf, fp, ensure_ascii=False, sort_keys=True, indent=4)

    # Check configuration
    logger.debug("Check configuration consistency")

    # todo: remove
    if "benchexec location" not in conf["client"]:
        raise KeyError("Provide configuration option 'client''benchexec location' as path to benchexec sources")
    if "resource limits" not in conf:
        raise KeyError("Configuration section 'resource limits' has not been provided")

    # Import runexec from BenchExec
    # todo: make it if the option is set otherwise import the package from pip
    # todo: just remove
    bench_exec_location = os.path.join(conf["client"]["benchexec location"])
    sys.path.append(bench_exec_location)

    # Import RunExec
    if mode == 'job':
        from benchexec.runexecutor import RunExecutor
        # todo: implement support of container mode
        # todo: switch to benchexec
        #executor = RunExecutor(use_namespaces=True)
        executor = RunExecutor()
        # Add CIF path
        if "cif location" in conf["client"]:
            logger.debug("Add CIF bin location to path {}".format(conf["client"]["cif location"]))
            os.environ["PATH"] = "{}:{}".format(conf["client"]["cif location"], os.environ["PATH"])
            logger.debug("Current PATH content is {}".format(os.environ["PATH"]))

        # Add CIL path
        if "cil location" in conf["client"]:
            logger.debug("Add CIL bin location to path {}".format(conf["client"]["cil location"]))
            os.environ["PATH"] = "{}:{}".format(conf["client"]["cil location"], os.environ["PATH"])
            logger.debug("Current PATH content is {}".format(os.environ["PATH"]))

        # Determine Klever Core script path
        if "Klever Core path" not in conf["client"]:
            logger.debug("There is no configuration option 'client''Klever Core path'")
            bin = os.path.join(os.path.dirname(os.path.realpath(__file__)), "../../core/bin/klever-core")
            os.environ['PYTHONPATH'] = os.path.join(os.path.dirname(bin), os.path.pardir)
        else:
            bin = conf["client"]["Klever Core path"]

        # Do it to make it possible to use runexec inside Klever
        os.environ['PYTHONPATH'] = "{}:{}".format(os.environ['PYTHONPATH'], bench_exec_location)

        # Check existence of the file
        logger.debug("Going to use Klever Core from {}".format(bin))
        if not os.path.isfile(bin):
            raise FileExistsError("There is no Klever Core executable script {}".format(bin))

        # Save Klever Core configuration to default configuration file
        with open("core.json", "w", encoding="utf8") as fh:
            json.dump(conf["Klever Core conf"], fh, ensure_ascii=False, sort_keys=True, indent=4)
    else:
        # Add verifiers path
        tool = conf['verifier']['name']
        version = conf['verifier']['version']
        path = conf['client']['verification tools'][tool][version]
        logger.debug("Add {!r} of version {!r} bin location {!r} to PATH".format(tool, version, path))
        os.environ["PATH"] = "{}:{}".format(path, os.environ["PATH"])

    # Check resource limitations
    if "CPU time" not in conf["resource limits"] or not conf["resource limits"]["CPU time"]:
        conf["resource limits"]["CPU time"] = None
        logger.debug("CPU time limit will not be set")
    else:
        logger.debug("CPU time limit: {} ms".format(conf["resource limits"]["CPU time"]))
    if "wall time" not in conf["resource limits"] or not conf["resource limits"]["wall time"]:
        conf["resource limits"]["wall time"] = None
        logger.debug("Wall time limit will not be set")
    else:
        logger.debug("Wall time limit: {} ms".format(conf["resource limits"]["wall time"]))
    if "memory size" not in conf["resource limits"] or not conf["resource limits"]["memory size"]:
        conf["resource limits"]["memory size"] = None
        logger.debug("Memory limit will not be set")
    else:
        logger.debug("Memory limit: {} bytes".format(conf["resource limits"]["memory size"]))
    if "CPU cores" not in conf["resource limits"] or not conf["resource limits"]["CPU cores"]:
        conf["resource limits"]["CPU cores"] = None
        logger.debug("CPU cores limit will not be set")
    if "number of CPU cores" not in conf["resource limits"] or not conf["resource limits"]["number of CPU cores"]:
        conf["resource limits"]["number of CPU cores"] = None
        logger.debug("CPU cores limit will not be set")

    # Last preparations before run
    if mode == 'job':
        # Do this for deterministic python in job
        os.environ['PYTHONHASHSEED'] = "0"
        os.environ['PYTHONIOENCODING'] = "utf8"
        os.environ['LC_LANG'] = "en_US"
        os.environ['LC_ALL'] = "en_US.UTF8"
        os.environ['LC_C'] = "en_US.UTF8"

        logger.info("Start job execution")
        result = executor.execute_run(args=[sys.executable, bin],
                                      output_filename="output.log",
                                      softtimelimit=conf["resource limits"]["CPU time"],
                                      walltimelimit=conf["resource limits"]["wall time"],
                                      memlimit=conf["resource limits"]["memory size"],
        # todo: does not work without container mode
        #                             files_size_limit=conf["resource limits"]["disk memory size"],
        # todo: do not set the option until both runexec and benchexec accepts both virtual CPU identifiers
        #                             cores=conf["resource limits"]["CPU cores"]
                                      )
        exit_code = int(result["exitcode"]) % 255
        logger.info("Job solution has finished with exit code {}".format(exit_code))
    else:
        logger.debug("Download task")
        server.pull_task(conf["identifier"], "task files.zip")
        with zipfile.ZipFile('task files.zip') as zfp:
            zfp.extractall()

        os.makedirs("output".encode("utf8"))

        args = prepare_task_arguments(logger, conf)

        logger.info("Start task execution with the following options: {}".format(' '.join(args)))
        exit_code = execute(args, logger=logger)
        logger.info("Task solution has finished with exit code {}".format(exit_code))
        if exit_code != 0:
            # To keep the last warning exit without any exception
            server.stop()
            os._exit(int(exit_code))

        # Move tasks collected in container mode to expected place
        if "benchexec container mode" in conf['client'] and conf['client']["benchexec container mode"]:
            for entry in glob.glob(os.path.join('output', '*.files', 'cil.i', '*', '*')):
                shutil.move(entry, 'output')

        decision_results = process_task_results(logger)
        submit_task_results(logger, server, conf["identifier"], decision_results)

    return exit_code


def prepare_task_arguments(logger, conf):
    """
    Prepare arguments for solution of a verification task with BenchExec.

    :param logger: Logger.
    :param conf: Configuration dictionary.
    :return: List with options.
    """

    # BenchExec arguments
    if "benchexec location" in conf["client"]:
        args = [os.path.join(conf["client"]["benchexec location"], 'benchexec')]
    else:
        args = ['benchexec']

    if "CPU cores" in conf["resource limits"]:
        logger.debug('Going to set CPU cores limit')
        args.extend(["--limitCores", str(conf["resource limits"]["number of CPU cores"])])
        args.append("--allowedCores")
        args.extend(list(map(str, conf["resource limits"]["CPU cores"])))

    if conf["resource limits"]["disk memory size"] and "benchexec measure disk" in conf['client'] and\
            conf['client']["benchexec measure disk"]:
        logger.debug('Going to set disk memory cores limit')
        args.extend(["--filesSizeLimit", str(conf["resource limits"]["disk memory size"]) + 'B'])

    logger.debug('Going to set memory and time limits')
    args.extend(['--memorylimit', str(conf["resource limits"]['memory size']) + 'B'])
    args.extend(['--timelimit', str(conf["resource limits"]['CPU time'])])

    # Check container mode
    if "benchexec container mode" in conf['client'] and conf['client']["benchexec container mode"]:
        logger.debug('Turn on container mode')
        args.append('--container')

        if "benchexec container mode options" in conf['client']:
            args.extend(conf['client']["benchexec container mode options"])
    else:
        logger.debug('Turn off container mode')
        args.append('--no-container')

    args.extend(["--no-compress-results", "--outputpath", "./output/"])

    args.append("benchmark.xml")

    return args

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
