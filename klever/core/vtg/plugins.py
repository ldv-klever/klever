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

import klever.core.components
import klever.core.utils


class Plugin(klever.core.components.Component):
    def __init__(self, conf, logger, parent_id, mqs, vals, abstract_task_desc, cur_id, include_child_resources=False):

        work_dir = cur_id.lower()
        super().__init__(conf, logger, parent_id, mqs, vals, cur_id, work_dir, None, True,
                         include_child_resources)

        if not os.path.isdir(work_dir):
            self.logger.info(
                'Create working directory "%s" for component "%s"', work_dir, cur_id)
            os.makedirs(work_dir.encode('utf-8'))
        self.abstract_task_desc = abstract_task_desc

    def run(self):
        super().run()
        self.logger.info('Plugin has finished')

        out_abstract_task_desc_file = '{0} abstract task.json'.format(self.name)
        out_abstract_task_desc_file = os.path.relpath(
            os.path.join(os.path.pardir, out_abstract_task_desc_file))

        self.dump_if_necessary(out_abstract_task_desc_file, self.abstract_task_desc,
                               "modified abstract verification task description")
        return self.abstract_task_desc
