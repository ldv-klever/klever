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


class SingleFile:
    def __init__(self, logger, clade, conf, specified_modules):
        self._logger = logger
        self._clade = clade
        self._conf = conf

    def divide(self):
        dependencies = util.build_dependencies(self._clade)[0]
        build_graph = self._clade.get_command_graph().load()
        modules = {}
        for file in dependencies.keys():
            try:
                desc = self._clade.get_cc().load_json_by_in(file)
            except FileNotFoundError:
                continue
            modules.update(util.create_module(self._clade, str(desc['id']), build_graph))

        return modules
