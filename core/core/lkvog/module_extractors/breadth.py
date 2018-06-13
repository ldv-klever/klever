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

from core.lkvog.module_extractors import util
import os


class Breadth:
    def __init__(self, logger, clade, conf, specified_modules):
        self.logger = logger
        self.clade = clade
        self._cluster_size = conf.get('module size', 3)
        self._max_locs = conf.get('max locs')
        self._cc_modules = {}
        self._dependencies = {}
        self._cc_modules = util.extract_cc(self.clade)
        self._dependencies, self._root_files = util.build_dependencies(self.clade)

    def _get_locs(self, file):
        desc = self.clade.get_cc().load_json_by_in(file)
        try:
            for in_file in desc['in']:
                with open(self.clade.get_file(os.path.join(desc['cwd'], in_file))) as fp:
                    return sum(1 for _ in fp)
        except:
            return 0

    def divide(self):
        processed = set()
        modules = {}
        current_module_desc_files = set()
        current_module_in_files = set()
        current_locs = 0

        for root_file in sorted(self._root_files):
            process = [root_file]
            while process:
                cur = process.pop(0)
                if cur in processed:
                    continue

                processed.add(cur)

                if cur in self._cc_modules:
                    current_module_desc_files.add(self._cc_modules[cur]['id'])
                    current_module_in_files.update(self._cc_modules[cur]['in'])
                    for file in self._cc_modules[cur]['in']:
                        current_locs += self._get_locs(file)
                    if len(current_module_in_files) == self._cluster_size \
                            or (self._max_locs and current_locs >= self._max_locs):
                        self.logger.debug('Create module with {0} in files'.format(list(current_module_in_files)))
                        modules.update(util.create_module(current_module_desc_files, current_module_in_files))
                        current_locs = 0

                process.extend(sorted(self._dependencies.get(cur, {}).keys()))

            if current_module_in_files:
                    self.logger.debug('Create module with {0} in files'.format(list(current_module_in_files)))
                    modules.update(util.create_module(current_module_desc_files, current_module_in_files))

        return modules
