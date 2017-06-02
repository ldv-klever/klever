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
import re
import zipfile
import sys
import signal
import traceback
from xml.etree import ElementTree
from xml.dom import minidom
from server.bridge import Server
from client.executils import execute


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
        logger.info("Exiting with exit code {}".format(exit_code))
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

    if "benchexec location" not in conf["client"]:
        raise KeyError("Provide configuration option 'client''benchexec location' as path to benchexec sources")
    if "resource limits" not in conf:
        raise KeyError("Configuration section 'resource limits' has not been provided")

    # Import runexec from BenchExec
    # todo: make it if the option is set otherwise import the package from pip
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
        from benchexec.benchexec import BenchExec
        executor = BenchExec()

        # Add verifiers path
        tool = conf['verifier']['name']
        version = conf['verifier']['version']
        path = conf['client']['verification tools'][tool][version]
        logger.debug("Add {!r} of version {!r} bin location {!r} to PATH".format(tool, version, path))
        os.environ["PATH"] = "{}:{}".format(path, os.environ["PATH"])
    set_signal_handler(executor)

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
    if "number of CPU cores" not in conf["resource limits"] or not not conf["resource limits"]["number of CPU cores"]:
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

        logger.debug("Prepare benchmark")
        benchmark = ElementTree.Element("benchmark", {
            "tool": conf["verifier"]["name"].lower(),
            "timelimit": str(round(conf["resource limits"]["CPU time"] / 1000)),
            "memlimit": str(conf["resource limits"]["memory size"]) + "B",
        })
        rundefinition = ElementTree.SubElement(benchmark, "rundefinition")
        for opt in conf["verifier"]["options"]:
            for name in opt:
                ElementTree.SubElement(rundefinition, "option", {"name": name}).text = opt[name]
        # Property file may not be specified.
        if "property file" in conf:
            ElementTree.SubElement(benchmark, "propertyfile").text = conf["property file"]
        if "extra benchexec options" in conf['client']:
            additional_opts = conf['client']["extra benchexec options"]
        else:
            additional_opts = []

        tasks = ElementTree.SubElement(benchmark, "tasks")
        # TODO: in this case verifier is invoked per each such file rather than per all of them.
        for file in conf["files"]:
            ElementTree.SubElement(tasks, "include").text = file
        with open("benchmark.xml", "w", encoding="utf8") as fp:
            fp.write(minidom.parseString(ElementTree.tostring(benchmark)).toprettyxml(indent="    "))

        os.makedirs("output".encode("utf8"))

        # This is done because of CPAchecker is not clever enough to search for its configuration and specification
        #  files around its binary.
        os.symlink(os.path.join(path, os.pardir, 'config'), 'config')

        # todo: set container mode
        args = ["--no-compress-results", "--outputpath", "./output/", "--container"]
        # todo: BenchExec cannot get identifiers, so setting particular cores is inefficient
        #if conf["resource limits"]["number of CPU cores"]:
        #    args.extend(["--limitCores", conf["resource limits"]["number of CPU cores"]])
        # todo: without container mode it is not working
        #if conf["resource limits"]["disk memory size"]:
        #    args.extend(["--filesSizeLimit", conf["resource limits"]["disk memory size"]])

        args = ['benchexec'] + args + additional_opts + ["benchmark.xml"]
        logger.info("Start task execution with the following options: {}".format(str(args)))
        exit_code = execute(logger, args)
        logger.info("Task solution has finished with exit code {}".format(exit_code))

        logger.debug("Translate benchexec output into our results format")
        decision_results = {
            "resources": {}
        }
        # Actually there is the only output file, but benchexec is quite clever to add current date to its name.
        solutions = glob.glob(os.path.join("output", "benchmark*results.xml"))
        if len(solutions) == 0:
            raise FileNotFoundError("Cannot find any solution generated by BenchExec")

        for benexec_output in solutions:
            with open(benexec_output, encoding="utf8") as fp:
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
                    elif name == "memUsage":
                        decision_results["resources"]["memory size"] = int(value)
                    elif name == "exitcode":
                        decision_results["exit code"] = int(value)

        with open("decision results.json", "w", encoding="utf8") as fp:
            json.dump(decision_results, fp, ensure_ascii=False, sort_keys=True, indent=4)

        with zipfile.ZipFile('decision result files.zip', mode='w') as zfp:
            zfp.write("decision results.json")
            for dirpath, dirnames, filenames in os.walk("output"):
                for filename in filenames:
                    zfp.write(os.path.join(dirpath, filename))
            if conf["upload input files of static verifiers"]:
                zfp.write("benchmark.xml")

        server.submit_solution(conf["identifier"], decision_results, "decision result files.zip")

    return exit_code


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


def set_signal_handler(executor):
    """
    Set custom sigterm handler in order to terminate job/task execution with all process group.

    :param executor: Object which corresponds RunExec or BenchExec. Should have method stop().
    :return: None
    """
    def handler(a, b):
        executor.stop()
        os._exit(-1)

    # Set custom handler
    signal.signal(signal.SIGTERM, handler)


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
