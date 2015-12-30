import logging
import uuid
import re
import os
import json


def extract_description(solution_dir, description_file):
    """
    Get directory with BenchExec output and extract results from there saving them to JSON file according to provided
    path.
    :param solution_dir: Path with BenchExec output.
    :param description_file:  Path to the description JSON file to save.
    :return: Identifier string of the solution.
    """
    identifier = str(uuid.uuid4())
    description = {
        "id": identifier,
        "resources": {},
        "comp": {}
    }
    limits = {}

    # Import general information
    general_file = os.path.join(solution_dir, "runInformation.txt")
    logging.debug("Import general information from the file {}".format(general_file))
    number = re.compile("(\d.*\d)")
    if os.path.isfile(general_file):
        with open(general_file, "r") as gi:
            for line in gi:
                key, value = line.strip().split("=", maxsplit=1)
                if key == "command":
                    description["comp"]["command"] = value
                elif key == "exitsignal":
                    description["signal num"] = int(value)
                elif key == "exitcode":
                    description["exit code"] = int(value)
                elif key == "walltime":
                    sec = number.match(value).group(1)
                    if sec:
                        description["resources"]["wall time"] = int(float(sec) * 1000)
                    else:
                        logging.warning("Cannot properly extract wall time from {}".format(general_file))
                elif key == "cputime":
                    sec = number.match(value).group(1)
                    if sec:
                        description["resources"]["CPU time"] = int(float(sec) * 1000)
                    else:
                        logging.warning("Cannot properly extract CPU time from {}".format(general_file))
                elif key == "memory":
                    mem_bytes = number.match(value).group(1)
                    if mem_bytes:
                        description["resources"]["maximum memory size"] = int(mem_bytes)
                    else:
                        logging.warning("Cannot properly extract exhausted memory from {}".format(general_file))
                elif key == "timeLimit":
                    # TODO: What kind of limit is it ?
                    sec = number.match(value).group(1)
                    if sec:
                        limits["max time"] = int(float(sec) * 1000)
                    else:
                        logging.warning("Cannot properly extract time limit from {}".format(general_file))
                elif key == "memoryLimit":
                    mem_bytes = number.match(value).group(1)
                    if mem_bytes:
                        limits["maximum memory size"] = int(mem_bytes)
                    else:
                        logging.warning("Cannot properly extract memory limit from {}".format(general_file))
    else:
        raise FileNotFoundError("There is no solution file {}".format(general_file))

    # Set final status
    # TODO: Test it more carefully
    if "signal num" in description:
        # According to documentation remove it from there in case of killing
        del description["exit code"]

        # Set status as killed by signal
        description["status"] = "killed by signal"

        # TODO: Determine reasons more carefully
        if limits["max time"] > 0.99 * description["resources"]["wall time"]:
            description["status"] = "wall time exhausted"
        elif limits["max time"] > 0.99 * description["resources"]["cpu time"]:
            description["status"] = "CPU time exhausted"
        elif limits["maximum memory size"] > 0.99 * description["resources"]["maximum memory size"]:
            description["status"] = "memory exhausted"
    elif "exit code" in description and description["exit code"] == 0:
        description["status"] = "normal exit"
    else:
        raise ValueError("Cannot determine termination reason according to the file {}".format(general_file))

    # Import Host information
    host_file = os.path.join(solution_dir, "hostInformation.txt")
    logging.debug("Import host information from the file {}".format(host_file))
    lv_re = re.compile("Linux\s(\d.*)")
    if os.path.isfile(host_file):
        with open(host_file, "r") as hi:
            for line in hi:
                key, value = line.strip().split("=", maxsplit=1)
                if key == "name":
                    description["comp"]["node name"] = value
                elif key == "os":
                    version = lv_re.match(value).group(1)
                    if version:
                        description["comp"]["Linux kernel version"] = version
                    else:
                        logging.warning("Cannot properly extract Linux kernel version from {}".format(host_file))
                elif key == "memory":
                    description["comp"]["mem size"] = value
                elif key == "cpuModel":
                    description["comp"]["CPU model"] = value
                elif key == "cores":
                    description["comp"]["number of CPU cores"] = value
    else:
        raise FileNotFoundError("There is no solution file {}".format(host_file))

    # Save description
    logging.debug("Save solution description to the file {}".format(description_file))
    with open(description_file, "w") as df:
        df.write(json.dumps(description, sort_keys=True, indent=4))

    return identifier, description

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
