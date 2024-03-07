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

import klever.core.components
import klever.core.utils


class Plugin(klever.core.components.Component):
    def __init__(self, conf, logger, parent_id, callbacks, mqs, vals, abstract_task_desc=None, cur_id=None,
                 work_dir=None, attrs=None, include_child_resources=False):
        super().__init__(conf, logger, parent_id, callbacks, mqs, vals, cur_id, work_dir, attrs, True,
                         include_child_resources)
        self.abstract_task_desc = abstract_task_desc

    def run(self):
        super().run()
        self.logger.info('Plugin has finished')
