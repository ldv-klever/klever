#!/usr/bin/env python3
import argparse
import os
import json
import logging.config
import shutil

import Cloud.scheduler.requests.testgenerator as testgenerator
import Cloud.scheduler.requests.omega as omega
import Cloud.scheduler.docker as docker
import Cloud.scheduler.native as native
import Cloud.scheduler.verifiercloud as verifiercloud


def get_gateway(conf, work_dir):
    """
    Check which implementation of Session object to choose to get tasks
    :param conf: Configuration dictionary.
    :param work_dir: Path to the working directory.
    :return: Return object of the implementation of Session abstract class.
    """
    #if "user" not in conf:
    #    raise KeyError("Please provide scheduler username 'Omega''user' to authorize at verification gateway")
    #elif "password" not in conf:
    #    raise KeyError("Please provide scheduler password 'Omega''passwd' to authorize at verification gateway")

    if "debug with testgenerator" in conf["scheduler"]:
        return testgenerator.Server(conf["testgenerator"], work_dir)
    else:
        return omega.Server(conf["Omega"], work_dir)


def get_scheduler(conf, work_dir, session):
    """
    Check which scheduler to run according to conf dictionary.
    :param conf: Configuration dictionary.
    :param work_dir: Path to the working directory.
    :param session: Verification gateway object.
    :return: Return object of implementation of abstract class TaskScheduler.
    """
    if conf["type"] == "verifiercloud":
        return verifiercloud.Scheduler(conf, work_dir, session)
    elif conf["type"] == "docker":
        return docker.Scheduler(conf, work_dir, session)
    elif conf["type"] == "native":
        return native.Scheduler(conf, work_dir, session)
    else:
        raise ValueError("Scheduler type is not given in the configuration (scheduler->type) or it is not supported "
                         "(supported are 'native', 'docker' or 'verifiercloud')")


def main():
    """Start execution of the corresponding cloud tool."""

    # Parse configuration
    parser = argparse.ArgumentParser(description='Start cloud scheduler according to the provided configuration.')
    parser.add_argument('config', metavar="CONF", help='Path to the cloud configuration file.')
    args = parser.parse_args()

    # Read configuration from file.
    with open(args.config) as fp:
        conf = json.load(fp)

    # TODO: Do we need use version of the scheduler further?
    # TODO: Do we need any checks of exclusive execution?

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

    if "scheduler" not in conf:
        raise KeyError("Provide configuration property 'scheduler' as an JSON-object")
    if "Omega" not in conf:
        raise KeyError("Provide configuration property 'scheduler' as an JSON-object")

    session = get_gateway(conf, conf["common"]["work dir"] + "/requests/")
    scheduler_impl = get_scheduler(conf["scheduler"], conf["common"]["work dir"] + "/scheduler/", session)
    scheduler_impl.launch()


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
if __name__ == "__main__":
    main()
