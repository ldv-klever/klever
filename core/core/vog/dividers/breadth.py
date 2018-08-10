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

from core.vog.dividers.abstract import AbstractDivider


class Breadth(AbstractDivider):

    def __init__(self, logger, conf):
        super(Breadth, self).__init__(logger, conf)
        self._cluster_size = conf['VOG divider'].get('module size', 3)
        self._max_locs = conf['VOG divider'].get('max locs')

    def divide(self):
        dependencies, root_files = self._build_dependencies()
        processed = set()
        modules = {}
        current_module_desc_files = set()
        current_module_in_files = set()
        current_locs = 0

        for root_file in sorted(root_files):
            process = [root_file]
            while process:
                cur = process.pop(0)
                if cur in processed:
                    continue

                processed.add(cur)

                if cur in self._cmd_graph_ccs:
                    current_module_desc_files.add(self._cmd_graph_ccs[cur]['id'])
                    current_module_in_files.update(self._cmd_graph_ccs[cur]['in'])
                    for file in self._cmd_graph_ccs[cur]['in']:
                        current_locs += self._get_locs(file)
                    if len(current_module_in_files) == self._cluster_size \
                            or (self._max_locs and current_locs >= self._max_locs):
                        self.logger.debug('Create module with {0} in files'.format(list(current_module_in_files)))
                        modules.update(self._create_module_by_desc(current_module_desc_files, current_module_in_files))
                        current_locs = 0

                process.extend(sorted(dependencies.get(cur, {}).keys()))

            if current_module_in_files:
                    self.logger.debug('Create module with {0} in files'.format(list(current_module_in_files)))
                    modules.update(self._create_module_by_desc(current_module_desc_files, current_module_in_files))

        return modules
