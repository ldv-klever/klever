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
from core.lkvog.strategies.strategy_utils import Module, Graph
from core.lkvog.strategies.abstract_strategy import AbstractStrategy


class Manual(AbstractStrategy):
    def __init__(self, logger, strategy_params, params):
        super().__init__(logger)
        self.groups = {}
        self._need_dependencies = False
        self.group_params = params.get('groups', {})
        self._already_in_modules = set()
        for key, value in params.get('groups', {}).items():
            if not self._is_module(key) and not self.is_subsystem(key):
                self._need_dependencies = True
                self.groups = {}
                return
            self.groups[key] = []
            for module_list in value:
                if not isinstance(module_list, tuple) \
                        and not isinstance(module_list, list):
                    raise ValueError('You should specify a list of lists for modules for manual strategy\n'
                                     'For example "{0}: [{1}]" instead of "{0}: {1}"'.format(key,
                                                                                             value))
                for module in module_list:
                    if not self._is_module(module) and not self.is_subsystem(module):
                        self._need_dependencies = True
                        self.groups = {}
                        return
                self.groups[key].append(module_list)

    def _divide(self, module_name):
        ret = []

        if module_name == 'all':
            for module in self.groups.keys():
                ret.extend(self.divide(module))
            return ret
        elif self.is_subsystem(module_name):
            # This is subsystem
            for module in self.groups.keys():
                if module.startswith(module_name) and module != module_name:
                    ret.extend(self.divide(module))
            return ret

        if module_name.startswith('ext-modules/'):
            is_external = True
            module_name = module_name[12:]
        else:
            is_external = False

        for group_init_module in self.groups:
            if group_init_module == module_name \
                    or group_init_module.startswith(module_name) \
                    or module_name.startswith(group_init_module):

                for group in self.groups[group_init_module]:
                    group_modules = []
                    for module in group:
                        process = []
                        if self._is_module(module):
                            process.append(module)
                        elif self.is_subsystem(module):
                            process.extend(self.get_modules_for_subsystem(module))
                        else:
                            process.extend(self.get_modules_by_func(module))

                        for m in process:
                            if is_external:
                                group_modules.append(Module('ext-modules/' + m))
                            else:
                                group_modules.append(Module(m))
                            for pred_module in group_modules[:-1]:
                                pred_module.add_successor(group_modules[-1])
                    # Make module_name to root of the Graph
                    root_module_pos = [module.id for module in group_modules].index(module_name if not is_external
                                                                                    else 'ext-modules/' + module_name)
                    group_modules[0], group_modules[root_module_pos] = group_modules[root_module_pos], group_modules[0]

                    ret.append(Graph(group_modules))
                break
        else:
            if module_name not in self._already_in_modules:
                if is_external:
                    ret.append(Graph([Module('ext-modules/' + module_name)]))
                else:
                    ret.append(Graph([Module(module_name)]))

        for graph in ret:
            self._already_in_modules.update([module.id for module in graph.modules])

        return ret

    def _set_dependencies(self, deps, sizes):
        for key, value in self.group_params.items():
            if not self._is_module(key) and not self.is_subsystem(key):
                key = self.get_modules_by_func(key)[0]
            self.groups[key] = []
            for module_list in value:
                if not isinstance(module_list, tuple) \
                        and not isinstance(module_list, list):
                    raise ValueError('You should specify a list of lists for modules for manual strategy\n'
                                     'For example "{0}: [{1}]" instead of "{0}: {1}"'.format(key, value))
                modules = []
                for module in module_list:
                    if self._is_module(module) or self.is_subsystem(module):
                        modules.append(module)
                    else:
                        modules.extend(self.get_modules_by_func(module))
                self.groups[key].append(modules)
        self.logger.debug("Groups are {0}".format(str(self.groups)))

    def need_dependencies(self):
        return self._need_dependencies

    def get_modules_to_build(self, modules):
        ret = set(modules)
        for groups in self.groups.values():
            for group in groups:
                ret.update(group)
                for module in group:
                    if not self._is_module(module) and not self.is_subsystem(module):
                        return [], True

        return list(ret), False
