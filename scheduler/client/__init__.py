import glob
import json
import logging
import os
import re
import sys
import tarfile
from xml.etree import ElementTree
from xml.dom import minidom

import server.bridge as bridge
import utils as utils


def solve_job(conf):
    # Initialize execution
    conf = utils.common_initialization("Job executor client", conf)

    # Check configuration
    logging.info("Check configuration consistency")
    if "benchexec location" not in conf["client"]:
        raise KeyError("Provide configuration option 'client''benchexec location' as path to benchexec sources")
    if "resource limits" not in conf:
        raise KeyError("Configuration section 'resource limits' has not been provided")

    # Import runexec from BenchExec
    bench_exec_location = os.path.join(conf["client"]["benchexec location"])
    logging.debug("Add to PATH BenchExec location {0}".format(bench_exec_location))
    sys.path.append(bench_exec_location)
    from benchexec.runexecutor import RunExecutor

    # Add CIF path
    if "cif location" in conf["client"]:
        logging.info("Add CIF bin location to path {}".format(conf["client"]["cif location"]))
        os.environ["PATH"] = "{}:{}".format(conf["client"]["cif location"], os.environ["PATH"])
        logging.debug("Current PATH content is {}".format(os.environ["PATH"]))

    # Add CIL path
    if "cil location" in conf["client"]:
        logging.info("Add CIL bin location to path {}".format(conf["client"]["cil location"]))
        os.environ["PATH"] = "{}:{}".format(conf["client"]["cil location"], os.environ["PATH"])
        logging.debug("Current PATH content is {}".format(os.environ["PATH"]))

    # Determine Klever Core script path
    if "Klever Core path" not in conf["client"]:
        logging.debug("There is no configuration option 'client''Klever Core path'")
        bin = os.path.join(os.path.dirname(os.path.realpath(__file__)), "../../core/bin/klever-core")
    else:
        bin = conf["client"]["Klever Core path"]

    # Check existence of the file
    logging.info("Going to use Klever Core from {}".format(bin))
    if not os.path.isfile(bin):
        raise FileExistsError("There is no Klever Core executable script {}".format(bin))

    # Save Klever Core configuration to default configuration file
    with open("core.json", "w") as fh:
        json.dump(conf["Klever Core conf"], fh, sort_keys=True, indent=4)

    # Import RunExec
    executor = RunExecutor()

    # Check resource limitations
    if not conf["resource limits"]["CPU time"]:
        conf["resource limits"]["CPU time"] = None
        logging.info("CPU time limit will not be set")
    else:
        logging.info("CPU time limit: {}s".format(conf["resource limits"]["CPU time"]))
    if not conf["resource limits"]["wall time"]:
        conf["resource limits"]["wall time"] = None
        logging.info("Wall time limit will not be set")
    else:
        logging.info("Wall time limit: {}s".format(conf["resource limits"]["wall time"]))
    if not conf["resource limits"]["memory size"]:
        conf["resource limits"]["memory size"] = None
        logging.info("Memory limit will not be set")
    else:
        logging.info("Memory limit: {} bytes".format(conf["resource limits"]["memory size"]))

    # Run Klever Core within runexec
    # TODO: How to choose proper CPU core numbers?

    logging.info("Run Klever Core {}".format(bin))
    result = executor.execute_run(args=[bin],
                                  output_filename="output.log",
                                  softtimelimit=conf["resource limits"]["CPU time"],
                                  walltimelimit=conf["resource limits"]["wall time"],
                                  memlimit=conf["resource limits"]["memory size"])
    # TODO: Mmmmagic
    exit_code = int(result["exitcode"]) % 255
    logging.info("Job solution has finished with exit code {}".format(exit_code))
    return exit_code


# TODO: this function has too much similar code with solve_job(). Why don't merge them?
def solve_task(conf):
    # Initialize execution
    conf = utils.common_initialization("Task executor client", conf)

    # Check configuration
    logging.info("Check configuration consistency")
    if "benchexec location" not in conf["client"]:
        raise KeyError("Provide configuration option 'client''benchexec location' as path to benchexec sources")
    if "resource limits" not in conf:
        raise KeyError("Configuration section 'resource limits' has not been provided")

    bench_exec_location = os.path.join(conf["client"]["benchexec location"])
    logging.debug("Add to PATH BenchExec location {0}".format(bench_exec_location))
    sys.path.append(bench_exec_location)
    from benchexec.benchexec import BenchExec

    # Add CPAchecker path
    if "cpachecker location" in conf["client"]:
        logging.info("Add CPAchecker bin location to path {}".format(conf["client"]["cpachecker location"]))
        os.environ["PATH"] = "{}:{}".format(conf["client"]["cpachecker location"], os.environ["PATH"])
        logging.debug("Current PATH content is {}".format(os.environ["PATH"]))
    else:
        raise KeyError("Provide configuration option 'client''cpachecker location' as path to CPAchecker executables")

    benchexec = BenchExec()

    # Check resource limitations
    if "CPU time" not in conf["resource limits"]:
        conf["resource limits"]["CPU time"] = -1000
        logging.info("CPU time limit will not be set")
    logging.info("CPU time limit: {}s".format(conf["resource limits"]["CPU time"]))
    if "wall time" not in conf["resource limits"]:
        conf["resource limits"]["wall time"] = -1000
        logging.info("Wall time limit will not be set")
    logging.info("Wall time limit: {}s".format(conf["resource limits"]["wall time"]))
    if "memory size" not in conf["resource limits"]:
        conf["resource limits"]["memory size"] = -(1000 ** 2)
        logging.info("Memory limit will not be set")
    logging.info("Memory limit: {} bytes".format(conf["resource limits"]["memory size"]))

    logging.info("Download task")
    server = bridge.Server(conf["Klever Bridge"], os.curdir)
    server.register()
    server.pull_task(conf["identifier"], "task files.tar.gz")
    tar = tarfile.open("task files.tar.gz")
    tar.extractall()
    tar.close()

    logging.info("Prepare benchmark")
    benchmark = ElementTree.Element("benchmark", {
        "tool": conf["verifier"]["name"].lower(),
        "timelimit": str(round(conf["resource limits"]["CPU time"] / 1000)),
        "memlimit": str(round(conf["resource limits"]["memory size"] / (1000 ** 2))),
    })
    rundefinition = ElementTree.SubElement(benchmark, "rundefinition")
    for opt in conf["verifier"]["options"] + [
        {"-setprop": "parser.readLineDirectives=true"},
        {"-setprop": "cpa.arg.errorPath.graphml=witness.graphml"}
    ]:
        for name in opt:
            ElementTree.SubElement(rundefinition, "option", {"name": name}).text = opt[name]
    ElementTree.SubElement(benchmark, "propertyfile").text = conf["property file"]
    tasks = ElementTree.SubElement(benchmark, "tasks")
    # TODO: in this case verifier is invoked per each such file rather than per all of them.
    for file in conf["files"]:
        ElementTree.SubElement(tasks, "include").text = file
    with open("benchmark.xml", "w") as fp:
        fp.write(minidom.parseString(ElementTree.tostring(benchmark)).toprettyxml(indent="    "))

    os.makedirs("output")

    # This is done because of CPAchecker is not clever enough to search for its configuration and specification files
    # around its binary.
    os.symlink(os.path.join(conf["client"]["cpachecker location"], os.pardir, 'config'), 'config')

    logging.info("Run verifier {} using benchmark benchmark.xml".format(conf["verifier"]["name"]))

    exit_code = benchexec.start(["--debug", "--outputpath", "output", "benchmark.xml"])

    logging.info("Task solution has finished with exit code {}".format(exit_code))

    logging.info("Translate benchexec output into our results format")
    decision_results = {
        "resources": {}
    }
    # Actually there is the only output file, but benchexec is quite clever to add current date to its name.
    statuses_map = {
        'false(reach)': 'unsafe',
        'true': 'safe',
        'EXCEPTION': 'error',
        'ERROR': 'error',
        'TIMEOUT': 'CPU time exhausted',
        'OUT OF MEMORY': 'memory exhausted'
    }
    for benexec_output in glob.glob(os.path.join("output", "benchmark*results.xml")):
        with open(benexec_output) as fp:
            result = ElementTree.parse(fp).getroot()
            decision_results["desc"] = '{0}\n{1} {2}'.format(result.attrib.get('generator'), result.attrib.get('tool'),
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
                    decision_results["status"] = statuses_map[value]
    # TODO: how to find exit code and signal number? decision_results["exit code"] = exit_code
    with open("decision results.json", "w") as fp:
        json.dump(decision_results, fp, sort_keys=True, indent=4)

    with tarfile.open("decision result files.tar.gz", "w:gz") as tar:
        tar.add("decision results.json")
        if decision_results["status"] == 'unsafe':
            tar.add("output/witness.graphml", 'witness.graphml')
        for file in glob.glob(os.path.join("output", "benchmark*logfiles/*")):
            tar.add(file, os.path.basename(file))

    server.submit_solution(conf["identifier"], decision_results, "decision result files.tar.gz")

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


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
