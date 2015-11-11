#!/usr/bin/env python3
import argparse
import os
import json
import logging.config
import shutil
import subprocess

import Cloud.utils as utils

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

    # Check feasibility of limits
    if result["available RAM memory"] > result["RAM memory"]:
        raise ValueError("Node has {} bytes of RAM memory but {} is attempted to reserve".
                         format(result["RAM memory"], result["available RAM memory"]))
    if result["available disk memory"] > result["disk memory"]:
        raise ValueError("Node has {} bytes of disk memory but {} is attempted to reserve".
                         format(result["disk memory"], result["available disk memory"]))
    if result["available CPU number"] >= result["CPU number"]:
        raise ValueError("Node has {} CPU cores but {} is attempted to reserve".
                         format(result["CPU number"], result["available CPU number"]))

    return result

def setup_consul(conf):
    """
    Setup consul working directory and configuration files.
    :param conf: Configuration dictionary.
    """
    consul_work_dir = os.path.join(os.path.abspath(os.path.curdir), "consul-dir")
    logging.info("Setup consul working directory {}".format(consul_work_dir))
    # Make consul work dir
    os.makedirs(consul_work_dir)

    # Prepare ndde info
    conf["node configuration"] = prepare_node_info(conf["node configuration"])

    # TODO: Create main config
    consul_config = {"checks": []}

    # Move checks to to consul dir
    if "checks" not in conf["client-controller"]:
        raise KeyError("Provide configuration property 'client-controller''checks'")
    logging.info("Add following checks fo consul to track:")
    for check in [check for check in conf["client-controller"]["checks"]
                  if check["active"]]:
        check_file = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                  "../controller/checks", check["name"] + ".py")
        if not os.path.isfile(check_file):
            raise ValueError("Cannot find check {}, expect check script there {}".format(check["name"],
                                                                                         check_file))
        logging.info("Add check {} to {}".format(check_file, os.path.abspath(os.path.curdir)))
        shutil.copy(check_file, os.path.abspath(os.path.curdir))

        new_check_path = os.path.join(os.path.abspath(os.path.curdir), check["name"] + ".py")
        check_desc = {
            "id": "{} {}".format(conf["node configuration"]["node name"], check["name"]),
            "name": check["name"],
            "script": new_check_path,
            "interval": check["interval"]
        }
        consul_config["checks"].append(check_desc)

    consul_config_file = os.path.join(consul_work_dir, "config.json")
    logging.info("Save consul configuration file {}".format(consul_config_file))
    with open(consul_config_file, "w") as fh:
        fh.write(json.dumps(consul_config, sort_keys=True, indent=4))

    logging.debug("Extract system information and add it to the node information")
    node_configuration = os.path.join(os.path.abspath(os.path.curdir), "node configuration.json")
    logging.info("Save node configuration file {}".format(node_configuration))
    with open(node_configuration, "w") as fh:
        fh.write(json.dumps(conf["node configuration"], sort_keys=True, indent=4))

    logging.info("Consul setup has been finished")

    return consul_work_dir, consul_config_file

def run_consul(conf, work_dir, config_file):
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
        args.append("-ui-dir={}".
                       format(os.path.join(os.path.dirname(conf["client-controller"]["consul"]), "dist")))

    # Add other commands
    if "consul additional opts" in conf["client-controller"]:
        args.extend(conf["client-controller"]["consul additional opts"])

    command = " ".join(args)
    logging.info("Run: '{}'".format(command))
    subprocess.call(args)


def main():
    """Start execution of the corresponding cloud tool."""

    # Parse configuration
    parser = \
        argparse.ArgumentParser(description='Start client-controller according to the provided configuration.')
    parser.add_argument('config', metavar="CONF", help='Path to the cloud configuration file.')
    args = parser.parse_args()

    # Read configuration from file.
    with open(args.config) as fp:
        conf = json.load(fp)

    # Check common configuration
    if "common" not in conf:
        raise KeyError("Provide configuration property 'common' as an JSON-object")

    # Prepare working directory
    if "work dir" not in conf["common"]:
        raise KeyError("Provide configuration property 'common''work dir'")
    if "keep work dir" in conf["common"] and conf["common"]["keep work dir"]:
        logging.info("Keep working directory from the previous run")
    else:
        logging.debug("Clean working dir: {0}".format(conf["common"]['work dir']))
        shutil.rmtree(conf["common"]['work dir'], True)

    logging.debug("Create working dir: {0}".format(conf["common"]['work dir']))
    os.makedirs(conf["common"]['work dir'], exist_ok=True)

    # Go to the workdir to avoid creating files elsewhere
    os.chdir(conf["common"]['work dir'])

    # Start logging
    if "logging" not in conf["common"]:
        raise KeyError("Provide configuration property 'common''logging' according to Python logging specs")
    logging.config.dictConfig(conf["common"]['logging'])

    # Check config
    if "client-controller" not in conf:
        raise KeyError("Provide configuration property 'client-controller' as a JSON-object")
    if "node configuration" not in conf:
        raise KeyError("Provide configuration property 'node configuration' as a JSON-object")

    # Setup consul
    consul_work_dir, consul_config_file = setup_consul(conf)

    # Run consul
    run_consul(conf, consul_work_dir, consul_config_file)

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
if __name__ == "__main__":
    main()
