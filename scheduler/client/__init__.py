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
from xml.etree import ElementTree
from xml.dom import minidom


def solve(logger, conf, job=True, server=None):
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
    bench_exec_location = os.path.join(conf["client"]["benchexec location"])
    sys.path.append(bench_exec_location)

    # Import RunExec
    if job:
        from benchexec.runexecutor import RunExecutor
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
    # TODO: How to choose proper CPU core numbers?

    # Last preparations before run
    if job:
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
                                      files_size_limit=conf["resource limits"]["disk memory size"])
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

        logger.info("Start task execution")
        exit_code = executor.start(["--debug", "--no-container", "--no-compress-results", "--outputpath", "output",
                                    "benchmark.xml"])
        logger.info("Task solution has finished with exit code {}".format(exit_code))

        logger.debug("Translate benchexec output into our results format")
        decision_results = {
            "resources": {}
        }
        # Well known statuses of CPAchecker. First two statuses are likely appropriate for all verifiers.
        statuses_map = {
            'false(reach)': 'unsafe',
            'false(unreach-call)': 'unsafe',
            'false(valid-free)': 'unsafe',
            'false(valid-deref)': 'unsafe',
            'false(valid-memtrack)': 'unsafe',
            'true': 'safe',
            'EXCEPTION': 'error',
            'ERROR': 'error',
            'TIMEOUT': 'CPU time exhausted',
            'OUT OF MEMORY': 'memory exhausted'
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
                    elif name == "status":
                        # Either get our status if so or use status as is.
                        if value in statuses_map:
                            decision_results["status"] = statuses_map[value]
                        else:
                            decision_results["status"] = value
        # TODO: how to find exit code and signal number? decision_results["exit code"] = exit_code
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
        exit(-1)

    # Set custom handler
    signal.signal(signal.SIGTERM, handler)


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
