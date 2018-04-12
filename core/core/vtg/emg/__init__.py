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

import os

import core.vtg.plugins

import core.utils
from core.vtg.emg.common import check_or_set_conf_property, get_necessary_conf_property, get_conf_property
from core.vtg.emg.common.c.source import Source
from core.vtg.emg.processGenerator import generate_processes
from core.vtg.emg.modelTranslator import translate_intermediate_model


class EMG(core.vtg.plugins.Plugin):
    """
    EMG plugin for environment model generation. The plugin generates an environment model on the base of manually
    written specifications using various generators and translators. Generated environment model contains C files and
    aspect files for merging with the original sources. As input, the plugin requires also results of source analysis.
    """
    depend_on_rule = False

    def generate_environment(self):
        """
        Main function of EMG plugin.

        Plugin generates an environment model for the verification task.

        :return: None
        """
        self.logger.info("Start environment model generator {}".format(self.id))

        # Initialization of EMG
        # Todo: refactor this
        self.logger.info("Import results of source analysis")
        sa = Source(self.logger, self.conf, self.abstract_task_desc)

        # Generate processes
        self.logger.info("Generate processes of an environment model")
        processes = generate_processes(self, sa)

        # Import additional aspect files
        translate_intermediate_model(self.logger, self.conf, self.abstract_task_desc, sa, processes)
        self.logger.info("An environment model has been generated successfully")

    main = generate_environment
