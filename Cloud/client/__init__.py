import os
import logging
import sys
import json

import Cloud.utils as utils


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

    # Determine psi script path
    if "psi path" not in conf["client"]:
        logging.debug("There is no configuration option 'client''psi path'")
        bin = os.path.join(os.path.dirname(os.path.realpath(__file__)), "../../Psi/bin/psi")
    else:
        bin = conf["client"]["psi path"]

    # Check existence of the file
    logging.info("Going to use psi from {}".format(bin))
    if not os.path.isfile(bin):
        raise FileExistsError("There is no psi execution script {}".format(bin))

    # Save psi configuration file
    psi_config_file = "psi configuration.json"
    with open(psi_config_file, "w") as fh:
        fh.write(json.dumps(conf["psi configuration"]))

    # Import RunExec
    executor = RunExecutor()

    # Run psi within runexec
    # TODO: How to choose proper CPU core numbers?
    result = executor.execute_run(args=[bin, psi_config_file], output_filename="output.log",
                                  softtimelimit=conf["resource limits"]["CPU time"],
                                  walltimelimit=conf["resource limits"]["wall time"],
                                  memlimit=conf["resource limits"]["max mem size"])

    return result


def execute_run(self, args, output_filename, stdin=None,
               hardtimelimit=None, softtimelimit=None, walltimelimit=None,
               cores=None, memlimit=None, memory_nodes=None,
               environments={}, workingDir=None, maxLogfileSize=None):
    return


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
