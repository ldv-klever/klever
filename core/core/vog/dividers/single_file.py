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


class SingleFile(AbstractDivider):

    def divide(self):
        dependencies = self._build_dependencies()[0]
        modules = {}
        for file in dependencies.keys():
            try:
                # todo: This should be corrected
                desc = self._clade.get_cc().load_json_by_in(file)
            except FileNotFoundError:
                continue
            modules.update(self._create_module(desc['id']))

        return modules
