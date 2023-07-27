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

import os
import json
import signal
import subprocess
import sys

from klever.scheduler import utils


def prepare_node_info(node_info):
    """
    Check that required values have been provided and add general node information.
    :param node_info: Dictionary with "node configuration" part of the configuration.
    :return: Updated dictionary.
    """
    system_info = utils.extract_system_information()
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
        result["available RAM memory"] = utils.memory_units_converter(result["available RAM memory"], '')[0]
    if result["available RAM memory"] < 1000 ** 3:
        result["available RAM memory"] = 1000 ** 3
    elif result["available RAM memory"] > result["RAM memory"]:
        result["available RAM memory"] = result["RAM memory"]
    if isinstance(result["available disk memory"], float):
        result["available disk memory"] = int(result["disk memory"] * result["available disk memory"])
    elif isinstance(result["available disk memory"], str):
        result["available disk memory"] = utils.memory_units_converter(result["available disk memory"], '')[0]
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


def setup_consul(conf, logger):
    """
    Setup consul working directory and configuration files.
    :param conf: Configuration dictionary.
    """
    consul_work_dir = os.path.join(os.path.abspath(os.path.curdir), "consul-dir")
    logger.info("Setup consul working directory {}".format(consul_work_dir))
    # Make consul working directory
    os.makedirs(consul_work_dir.encode("utf-8"))

    # Prepare node info
    conf["node configuration"] = prepare_node_info(conf["node configuration"])

    # TODO: Create main config
    consul_config = {"checks": []}

    # Move checks to to consul dir
    if "script checks" in conf["client-controller"]:
        logger.info("Add following checks fo consul to track:")
        for check in [check for check in conf["client-controller"]["script checks"]
                      if check["active"]]:
            check_file = os.path.join(os.path.dirname(sys.executable), check["name"])
            if not os.path.isfile(check_file):
                raise ValueError("Cannot find check {}, expect check script there {}".format(check["name"],
                                                                                             check_file))

            check_desc = {
                "id": "{} {}".format(conf["node configuration"]["node name"], check["name"]),
                "name": check["name"],
                "args": [check_file],
                "interval": check["interval"]
            }
            consul_config["checks"].append(check_desc)

    # Add JSON service check descriptions
    if "service checks" in conf["client-controller"]:
        for check in conf["client-controller"]["service checks"]:
            consul_config["checks"].append(check)

    # Add additional configuration options
    if "consul additional configuration" in conf["client-controller"]:
        for key in conf["client-controller"]["consul additional configuration"]:
            consul_config[key] = conf["client-controller"]["consul additional configuration"][key]

    consul_config_file = os.path.join(consul_work_dir, "config.json")
    logger.info("Save consul configuration file {}".format(consul_config_file))
    with open(consul_config_file, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(consul_config, ensure_ascii=False, sort_keys=True, indent=4))

    logger.debug("Extract system information and add it to the node information")
    node_configuration = os.path.join(os.path.abspath(os.path.curdir), "node configuration.json")

    logger.info("Save node configuration file {}".format(node_configuration))
    data = {
        "node configuration": conf["node configuration"],
        "Klever Bridge": conf["Klever Bridge"]
    }
    with open(node_configuration, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=4))

    # Add as an environment variable
    logger.info("Set environment variable {} as {}".
                 format("CONTROLLER_NODE_CONFIG", os.path.abspath(node_configuration)))
    os.environ["CONTROLLER_NODE_CONFIG"] = os.path.abspath(node_configuration)

    logger.info("Consul setup has been finished")

    return consul_work_dir, consul_config_file


def run_consul(conf, logger, work_dir, config_file):
    """
    Run consul with provided options.
    :param conf: Configuration dictionary.
    :param work_dir: Consul working directory.
    :param config_file: Consul configuration file
    """
    # Add script name
    args = [conf["client-controller"]["consul"], "agent"]

    # Add address
    args.append("-bind={}".format(conf["node configuration"]["bind address"]))

    # Add name if it is given
    if "node name" in conf["node configuration"]:
        args.append("-node={}".format(conf["node configuration"]["node name"]))

    # Add config file
    args.append("-config-file={}".format(config_file))

    # Add data dir
    args.append("-data-dir={}".format(os.path.join(work_dir, "data")))

    # Setup GUI
    if "setup GUI" in conf["client-controller"] and conf["client-controller"]["setup GUI"]:
        args.append("-ui")

    # Add other commands
    if "consul additional opts" in conf["client-controller"]:
        args.extend(conf["client-controller"]["consul additional opts"])

    command = " ".join(args)
    logger.info("Run: '{}'".format(command))

    process = None

    def handler(signum, frame):  # pylint:disable=unused-argument
        if process:
            process.send_signal(signum)

    signal.signal(signal.SIGTERM, handler)

    process = subprocess.Popen(args)

    process.wait()
