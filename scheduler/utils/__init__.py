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

import subprocess
import logging
import logging.config
import argparse
import os
import json
import shutil


def common_initialization(tool, conf=None):
    """
    Start execution of the corresponding cloud tool.

    :param tool: Tool name string.
    :return: Configuration dictionary.
    """

    if not conf:
        # Parse configuration
        parser = argparse.ArgumentParser(description='Start cloud {} according to the provided configuration.'.
                                         format(tool))
        parser.add_argument('config', metavar="CONF", help='Path to the cloud configuration file.')
        args = parser.parse_args()

        # Read configuration from file.
        with open(args.config, encoding="utf8") as fp:
            conf = json.load(fp)

    # TODO: Do we need use version of the scheduler further?
    # TODO: Do we need any checks of exclusive execution?

    # Check common configuration
    if "common" not in conf:
        raise KeyError("Provide configuration property 'common' as an JSON-object")

    # Prepare working directory
    if "working directory" not in conf["common"]:
        raise KeyError("Provide configuration property 'common''working directory'")
    if "keep working directory" in conf["common"] and conf["common"]["keep working directory"]:
        logging.info("Keep working directory from the previous run")
    else:
        logging.debug("Clean working dir: {0}".format(conf["common"]['working directory']))
        shutil.rmtree(conf["common"]['working directory'], True)

    logging.debug("Create working dir: {0}".format(conf["common"]['working directory']))
    os.makedirs(conf["common"]['working directory'], exist_ok=True)

    # Go to the working directory to avoid creating files elsewhere
    os.chdir(conf["common"]['working directory'])

    # Start logging
    if "logging" not in conf["common"]:
        raise KeyError("Provide configuration property 'common''logging' according to Python logging specs")
    logging.config.dictConfig(conf["common"]['logging'])

    return conf


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


def get_output(command):
    """
    Return STDOUT of the command.
    :param command: a command to be executed to get an entity value.
    """
    val = subprocess.getoutput(command)
    if not val:
        raise ValueError('Cannot get anything executing {}'.format(command))

    return val


def extract_system_information():
    """
    Extract information about the system and return it as a dictionary.
    :return: dictionary with system info,
    """
    system_conf = {}
    system_conf["node name"] = get_output('uname -n')
    system_conf["CPU model"] = get_output('cat /proc/cpuinfo | grep -m1 "model name" | sed -r "s/^.*: //"')
    system_conf["CPU number"] = int(get_output('cat /proc/cpuinfo | grep processor | wc -l'))
    system_conf["RAM memory"] = \
        int(get_output('cat /proc/meminfo | grep "MemTotal" | sed -r "s/^.*: *([0-9]+).*/1024 * \\1/" | bc'))
    system_conf["disk memory"] = 1024 * int(get_output('df ./ | grep / | awk \'{ print $4 }\''))
    system_conf["Linux kernel version"] = get_output('uname -r')
    system_conf["arch"] = get_output('uname -m')
    return system_conf

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'