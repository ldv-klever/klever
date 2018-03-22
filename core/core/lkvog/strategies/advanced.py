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
from operator import itemgetter

from core.lkvog.strategies.strategy_utils import Module, Graph
from core.lkvog.strategies.abstract_strategy import AbstractStrategy


class Advanced(AbstractStrategy):
    def __init__(self, logger, strategy_params, params):
        super().__init__(logger)
        module_sizes = strategy_params.get('module_sizes', {})

        # Going to read params
        self.logger = logger
        self.koef = params.get('cluster size', 5)
        self.max_g_for_m = params.get('max group for module', 5)
        self.minimize_groups_for_module = params.get('minimize groups for module', True)
        self.priority_on_module_size = params.get('priority on module size', True)

        self.user_deps = {}
        for module, dep_modules in params.get('user deps', {}).items():
            module = re.subn('.ko$', '.o', module)[0]
            self.user_deps[module] = [re.subn('.ko$', '.o', dep_module)[0] for dep_module in dep_modules]

        self.division_type = params.get('division type', 'All')
        if self.division_type not in ('Library', 'Module', 'All'):
            raise ValueError("Division type {} doesn't exist".format(self.division_type))
        self.analyze_all_export_function = \
            params.get('analyze all export function', self.division_type != 'Module')
        self.analyze_all_calls = \
            params.get('analyze all calls', self.division_type != 'Library')
        self.priority_on_export_function = \
            params.get('priority on export function', self.division_type != 'Module')
        self.priority_on_calls = \
            params.get('priority on calls', self.division_type != 'Library')
        self.maximize_subsystems = params.get('maximize subsystems', True)

    def _set_dependencies(self, deps, sizes):
        # Creating modules dict
        if sizes is None:
            self.priority_on_module_size = False
            sizes = {}

        self.modules = {}
        for succ, _, module in sorted(deps):
            self.modules.setdefault(module, Module(module))
            self.modules.setdefault(succ, Module(succ))
            self.modules[module].add_successor(self.modules[succ])

            self.modules[module].size = sizes.get(module, 0)
            self.modules[succ].size = sizes.get(succ, 0)

        # Creating export/call functions
        self.not_checked_export_f = {}
        self.not_checked_call_f = {}
        for module_succ, func, module_pred in deps:
            if module_pred not in self.modules or module_succ not in self.modules:
                continue
            self.modules[module_succ].export_functions.setdefault(func, [])
            self.modules[module_succ].export_functions[func].append(self.modules[module_pred])
            self.modules[module_pred].call_functions.setdefault(func, [])
            self.modules[module_pred].call_functions[func].append(self.modules[module_succ])

        for module in self.modules.values():
            self.not_checked_export_f[module] = set(module.export_functions.keys())
            self.not_checked_call_f[module] = set(module.call_functions.keys())

        self.not_checked_export_f_backup = {k: set(v) for k, v in self.not_checked_export_f.items()}
        self.not_checked_call_f_backup = {k: set(v) for k, v in self.not_checked_call_f.items()}

        self.not_checked_preds = {}
        self.not_checked_succs = {}
        for module in self.modules.values():
            self.not_checked_preds[module] = set(module.predecessors)
            self.not_checked_succs[module] = set(module.successors)

        self.checked_clusters = set()
        self.checked_modules = set()
        self.count_groups_for_m = {}

    def is_fully_checked(self, module):
        if module not in self.checked_modules:
            # Not checked even once
            return False

        if self.analyze_all_export_function and self.not_checked_export_f.get(module, {}):
            # Not checked all export functions, but must
            return False

        if self.analyze_all_calls and self.not_checked_call_f.get(module, {}):
            # Not checked all calls, but must
            return False

        if not self.analyze_all_export_function and not self.analyze_all_calls and \
                                                self.count_groups_for_m.get(module, 0) > self.max_g_for_m:
            # All export functions has checked and the max gropus for the module has reached
            return True

        if self.analyze_all_export_function and not self.not_checked_export_f.get(module, {}) \
                and not self.analyze_all_calls and self.minimize_groups_for_module:
            # Should check all export functions once
            return True

        if self.analyze_all_calls and not self.not_checked_call_f.get(module, {}) \
                and not self.analyze_all_export_function and self.minimize_groups_for_module:
            # All calls has checked and the max gropus for the module has reached
            return True

        if self.analyze_all_calls and not self.analyze_all_export_function \
                and not self.not_checked_export_f.get(module, {}) and self.minimize_groups_for_module:
            # Should check all calls once
            return True

        if not self.not_checked_call_f.get(module, {}) \
                and not self.not_checked_export_f.get(module, {}) and self.minimize_groups_for_module:
            return True

        if self.count_groups_for_m.get(module, 0) > self.max_g_for_m:
            return True
        if not self.not_checked_succs[module] and not self.not_checked_preds[module]:
            return True

        return False

    def export_weight(self, module_pred, module_succ):
        # Count export functions, that predecessor calls from successor (this module)
        if not self.priority_on_export_function:
            return 0
        ret = 0
        for ex_f in self.not_checked_export_f.get(module_succ, set()):
            if module_pred in module_succ.export_functions[ex_f]:
                ret += 1
        return ret

    def call_weight(self, module_succ, module_pred):
        # Count functions, that predecessor (this module) calls from successor
        if not self.priority_on_calls:
            return 0
        ret = 0
        for call in self.not_checked_call_f.get(module_pred, set()):
            if module_succ in module_pred.call_functions[call]:
                ret += 1
        return ret

    def size_weight(self, module, unused):
        # Weight based on module size
        if not self.priority_on_module_size:
            return 0
        if module.size < 256 * 1024:
            return 2
        elif module.size < 1024 * 1024:
            return 1
        return 0

    def export_provided_weight(self, module, unused):
        # Count functions, that successor provides
        if not self.priority_on_export_function:
            return 0
        return len(module.export_functions)

    def call_provided_weight(self, module, unused):
        # Count functions, that predecessor provides
        if not self.priority_on_calls:
            return 0
        return len(module.call_functions)

    def remoteness_weight(self, module1, module2):
        # Returns non-zero if modules from difference subsystems
        if not self.maximize_subsystems:
            return 0
        subsystem1 = module1.id[:module1.id.rfind('/')]
        subsystem2 = module2.id[:module2.id.rfind('/')]
        return 0 if subsystem1.startswith(subsystem2) or subsystem2.startswith(subsystem1) else 1

    def count_already_weight(self, module, unused):
        # Returns weight based on counts groups for module
        return -1 - self.count_groups_for_m.get(module, 0)

    def more_difference(self, ret, process, module):
        if not ret or not process:
            return self.koef
        return self.koef - max(map(lambda group: len(set(process).union([module]).intersection(group)), ret))

    def all_call_weight(self, module, process):
        # Returns count of functions, that module can call from process
        # If process doesn't provide export functions, but is an successor,
        # assume, he provide 1 export functions
        checked = set()
        ret = 0
        for process_module in process:
            for values in sorted(process_module.call_functions.values()):
                if module.id in values:
                    ret += 1
                    checked.add(process_module)
            for call_functions in module.call_functions.values():
                if process_module in call_functions:
                    checked.add(process_module)
                    ret += 1
        for process_module in set(process).difference(checked):
            if process_module in module.successors or process_module in module.predecessors:
                ret += 1
        return ret

    def measure_predecessor(self, module_pred, module_succ, process, ret):
        weight_funcs = [self.count_already_weight, self.size_weight, self.export_provided_weight,
                        self.remoteness_weight]
        if self.analyze_all_export_function:
            weight_funcs.insert(0, self.export_weight)
        else:
            weight_funcs.insert(1, self.export_weight)
        weights = [weight(module_pred, module_succ) for weight in weight_funcs]
        weights.insert(2, self.more_difference(ret, process, module_pred))
        return weights

    def measure_successor(self, module_pred, module_succ, process, ret):
        weight_funcs = [self.count_already_weight, self.size_weight, self.call_provided_weight,
                        self.remoteness_weight]
        if self.analyze_all_calls:
            weight_funcs.insert(0, self.call_weight)
        else:
            weight_funcs.insert(1, self.call_weight)
        weights = [weight(module_succ, module_pred) for weight in weight_funcs]
        weights.insert(2, self.more_difference(ret, process, module_succ))
        return weights

    def get_user_deps(self, module):
        # Returns set of modules, that depends from given module
        # Depends extracts from user spec.
        ret = set()
        process = [self.user_deps.get(module.id, [])]
        while process:
            process_list_modules = process.pop(0)
            for process_module in process_list_modules:
                if process_module not in self.modules:
                    continue
                ret.add(self.modules[process_module])
                if process_module in self.user_deps:
                    process.append(self.user_deps[process_module])
        return ret

    def topolog_sort(self, main_module, modules):
        ret = {}
        process = [(1, module) for module in main_module.predecessors]
        while process:
            i, module = process.pop()
            if module not in modules:
                continue
            ret.setdefault(module, i)
            ret[module] = max(ret[module], i)
            process.extend([(i + 1, x) for x in module.predecessors])

        return map(lambda item2: item2[0], sorted(ret.items(), key=lambda item1: item1[1]))

    def get_best_candidate(self, modules):
        if not modules:
            return None
        process = sorted(modules)
        for i in range(len(modules[0][1])):
            max_value = max(process, key=lambda module: module[1][i])[1][i]
            if max_value == 0:
                continue
            process = list(sorted(filter(lambda module: module[1][i] / max_value >= 0.5 if max_value > 0 else
                                         max_value / module[1][i] >= 0.5, process)))
        return list(sorted(process, key=itemgetter(1), reverse=True))[0][0]

    def clean(self):
        self.count_groups_for_m = {}
        self.not_checked_call_f = {k: set(v) for k, v in self.not_checked_call_f_backup.items()}
        self.not_checked_export_f = {k: set(v) for k, v in self.not_checked_export_f_backup.items()}

    def _divide(self, module_name):
        self.clean()

        if module_name == 'all':
            ret = set()
            for module in sorted(self.modules.keys()):
                ret.update(self.divide(module))
            return ret
        elif not module_name.endswith('.ko'):
            # This is subsystem
            ret = set()
            for module in sorted(self.modules.keys()):
                if module.startswith(module_name):
                    ret.update(self.divide(module))
            return ret

        if module_name not in self.modules:
            # This module has no dependencies
            self.logger.debug('Module {0} has no dependencies'.format(module_name))
            return [Graph([Module(module_name)])]

        main_module = self.modules[module_name]
        if self.is_fully_checked(main_module):
            self.logger.debug('Module {0} reachs max group'.format(main_module.id))
            return []

        clusters = set()
        checked = set()
        while not self.is_fully_checked(main_module):
            # Any iteration starts with appending objective module and his user dependencies
            process = set()
            process.add(main_module)
            process.update(self.get_user_deps(main_module))
            checked.update(self.get_user_deps(main_module))

            # Appending while size of group less koef
            while len(process) < self.koef:
                max_measuring = 0
                best_candidate = None
                candidate_list = []
                for module in process:
                    if self.division_type != 'Module':
                        # Search best candidate from successors
                        candidate_list += list(map(lambda module_pred: (
                            module_pred, self.measure_predecessor(module_pred, module, process, clusters)),
                                                   filter(lambda module: module not in process, module.predecessors)))

                    if self.division_type != 'Library':
                        # Search best candidate from predecessors
                        candidate_list += list(map(lambda module_succ: (
                            module_succ, self.measure_successor(module, module_succ, process, clusters)),
                                                   filter(lambda module: module not in process, module.successors)))
                best_candidate = self.get_best_candidate(candidate_list)
                if best_candidate:
                    process.add(best_candidate)
                    process.update(self.get_user_deps(best_candidate))
                    checked.update(self.get_user_deps(best_candidate))
                    checked.add(best_candidate)
                    self.count_groups_for_m.setdefault(best_candidate, 0)
                    self.count_groups_for_m[best_candidate] += 1

                    # Update not checked export functions and not checked call functions
                    for succ in filter(lambda module: module in process, best_candidate.successors):
                        self.not_checked_export_f.setdefault(succ, set()).difference_update \
                            ([functions for functions, modules in succ.export_functions.items()
                              if best_candidate in modules])
                    for pred in filter(lambda module: module in process, best_candidate.predecessors):
                        self.not_checked_export_f.setdefault(best_candidate, set()).difference_update \
                            ([function for function, modules in best_candidate.export_functions.items()
                              if pred in modules])

                    for succ in filter(lambda module: module in process, best_candidate.successors):
                        self.not_checked_call_f.setdefault(best_candidate, set()).difference_update \
                            ([function for function, modules in best_candidate.call_functions.items()
                              if succ in modules])
                    for pred in filter(lambda module: module in process, best_candidate.predecessors):
                        self.not_checked_call_f.setdefault(pred, set()).difference_update \
                            ([function for function, modules in pred.call_functions.items()
                              if best_candidate in modules])

                    for module in process:
                        self.not_checked_succs[module].discard(best_candidate)
                        self.not_checked_preds[module].discard(best_candidate)
                else:
                    break
            else:
                if process in clusters:
                    break
                if process not in self.checked_clusters:
                    self.logger.debug('Append cluster: {0}'.format([module.id for module in process]))
                    clusters.add(frozenset(process))
                    self.checked_clusters.add(frozenset(process))
                for module in process:
                    self.checked_modules.add(module)
                    self.count_groups_for_m.setdefault(module, 0)
                    self.count_groups_for_m[module] += 1
                continue
            if len(process) > 1 or (len(process) == 1 and not clusters):
                if process not in self.checked_clusters:
                    self.logger.debug('Append cluster: {0}'.format([module.id for module in process]))
                    clusters.add(frozenset(process))
                    self.checked_clusters.add(frozenset(process))
            for module in process:
                self.checked_modules.add(module)
            break

        ret = set()
        for cluster in clusters:
            modules = {}
            for module in cluster:
                modules.setdefault(module.id, Module(module.id))
            for module in modules.values():
                if module.id in self.modules:
                    for dep in self.modules[module.id].successors:
                        if dep.id in modules:
                            module.add_predecessor(modules[dep.id])
            cluster2 = Graph(list(modules.values()))
            cluster2.root = [module for module in cluster2.modules if module.id == main_module.id][0]
            if cluster2 not in self.checked_clusters:
                self.checked_modules.add(cluster2)
                ret.add(cluster2)
        if self.not_checked_call_f[main_module]:
            print('Not checked all call', main_module.id, len(self.not_checked_call_f[main_module]))
        if self.not_checked_export_f[main_module]:
            print('Not checked all export', main_module.id, len(self.not_checked_export_f[main_module]))

        return ret

    def get_modules_to_build(self, modules):
        if self.is_deps is None:
            return [], True
        else:
            return self._collect_to_build(modules), False

    def need_dependencies(self):
        return True
