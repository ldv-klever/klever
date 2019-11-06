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


from core.utils import report
from core.vtg.plugins import Plugin
from core.vtg.emg.common import get_or_die
from core.vtg.emg.generators import generate_processes
from core.vtg.emg.common.process import ProcessCollection
from core.vtg.emg.translation import translate_intermediate_model
from core.vtg.emg.common.c.source import create_source_representation


class EMG(Plugin):
    """
    EMG plugin for environment model generators. The plugin generates an environment model on the base of manually
    written specifications using various generators and translation. Generated environment model contains C files and
    aspect files for merging with the original sources. As input, the plugin requires also results of source analysis.
    """
    depend_on_requirement = False

    def generate_environment(self):
        """
        Main function of EMG plugin.

        Plugin generates an environment model for the verification task.

        :return: None
        """
        self.logger.info("Start environment model generator {}".format(self.id))

        # Initialization of EMG
        self.logger.info("Import results of source analysis")
        sa = create_source_representation(self.logger, self.conf, self.abstract_task_desc)

        # Generate processes
        self.logger.info("Generate processes of an environment model")
        collection = ProcessCollection()
        reports = generate_processes(self.logger, self.conf, collection, self.abstract_task_desc, sa)

        # Send data to the server
        self.logger.info("Send data about generated instances to the server")

        report(self.logger, 'patch', {'identifier': self.id, 'data': reports}, self.mqs['report files'],
               self.vals['report id'], get_or_die(self.conf, "main working directory"))
        self.logger.info("An intermediate environment model has been prepared")

        # Import additional aspect files
        translate_intermediate_model(self.logger, self.conf, self.abstract_task_desc, sa, collection)
        self.logger.info("An environment model has been generated successfully")

    main = generate_environment
