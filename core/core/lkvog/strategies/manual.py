#
# Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
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

import re

from core.lkvog.strategies.strategy_utils import Module, Graph
from core.lkvog.strategies.abstract_strategy import AbstractStrategy


class Manual(AbstractStrategy):
    def __init__(self, logger, strategy_params, params):
        super().__init__(logger)
        self.groups = {}
        for key, value in params.get('groups', {}).items():
            self.groups[key] = []
            for module_list in value:
                if not isinstance(module_list, tuple) \
                        and not isinstance(module_list, list):
                    raise ValueError('You should specify a list of lists for modules for manual strategy\n'
                                     'For example "{0}: [{1}]" instead of "{0}: {1}"'.format(key,
                                                                                             value))
                self.groups[key].append(module_list)

    def _divide(self, module_name):
        ret = []

        if module_name == 'all':
            for module in self.groups.keys():
                ret.extend(self.divide(module))
            return ret
        elif not module_name.endswith('.ko'):
            # This is subsystem
            for module in self.groups.keys():
                if module.startswith(module_name):
                    ret.extend(self.divide(module))
            return ret

        if module_name.startswith('ext-modules/'):
            is_external = True
            module_name = module_name[12:]
        else:
            is_external = False

        if module_name in self.groups:
            for group in self.groups[module_name]:
                group_modules = []
                for module in group:
                    if is_external:
                        group_modules.append(Module('ext-modules/' + module))
                    else:
                        group_modules.append(Module(module))
                    for pred_module in group_modules[:-1]:
                        pred_module.add_successor(group_modules[-1])
                # Make module_name to root of the Graph
                root_module_pos = [module.id for module in group_modules].index(module_name if not is_external
                                                                                else 'ext-modules/' + module_name)
                group_modules[0], group_modules[root_module_pos] = group_modules[root_module_pos], group_modules[0]

                ret.append(Graph(group_modules))
        else:
            if is_external:
                ret.append(Graph([Module('ext-modules/' + module_name)]))
            else:
                ret.append(Graph([Module(module_name)]))

        return ret

    def get_to_build(self, modules):
        ret = set()
        for groups in self.groups.values():
            for group in groups:
                ret.update(group)

        return list(ret), False
