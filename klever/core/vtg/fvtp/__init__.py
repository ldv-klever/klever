#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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

import klever.core.vtg.plugins
from klever.core.vtg.fvtp.basic import BasicGenerationStrategy


class FVTP(klever.core.vtg.plugins.Plugin):

    def final_task_preparation(self):
        """
        Main routine of the component. It prepares a number of verification tasks and submit them to Bridge and the VRP
        component.

        :return: None
        """

        s = BasicGenerationStrategy(self.logger, self.conf, self.abstract_task_desc)

        self.logger.info('Begin task generating')
        task_description = s.generate_verification_task()

        self.dump_if_necessary("task.json", task_description, "verification task description")

        # Prepare final abstract verification task
        self.abstract_task_desc['verifier'] = self.conf['verifier']['name']
        self.abstract_task_desc["result processing"] = {'code coverage details': self.conf['code coverage details']}
        self.abstract_task_desc["task description"] = task_description
        self.abstract_task_desc['task archive'] = os.path.join(os.getcwd(), 'task files.zip')

        # Specific requirement specification settings can complement or/and overwrite common ones.
        if 'result processing' in self.conf:
            self.abstract_task_desc["result processing"].update(self.conf["result processing"])

    main = final_task_preparation
