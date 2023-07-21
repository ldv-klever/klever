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

import json
import os

import klever.core.components
import klever.core.utils


class Plugin(klever.core.components.Component):
    depend_on_requirement = True

    def run(self):
        in_abstract_task_desc_file = os.path.relpath(
            os.path.join(self.conf['main working directory'], self.conf['in abstract task desc file']))
        with open(in_abstract_task_desc_file, encoding='utf-8') as fp:
            self.abstract_task_desc = json.load(fp)
        super().run()
        out_abstract_task_desc_file = os.path.relpath(
            os.path.join(self.conf['main working directory'], self.conf['out abstract task desc file']))
        self.logger.info(
            'Put modified abstract verification task description to file "%s"', out_abstract_task_desc_file)
        with open(out_abstract_task_desc_file, 'w', encoding='utf-8') as fp:
            klever.core.utils.json_dump(self.abstract_task_desc, fp, self.conf['keep intermediate files'])
        self.logger.info('Plugin has finished')
