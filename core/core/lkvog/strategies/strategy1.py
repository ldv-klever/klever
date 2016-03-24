from core.lkvog.strategies.module import Module
from core.lkvog.strategies.module import Graph


class Strategy1:
    def __init__(self, logger, deps, user_deps=None, params=None, export_func=None, module_sizes=None):
        if module_sizes is None:
            module_sizes = {}
        if export_func is None:
            export_func = []
        if params is None:
            params = {}
        if user_deps is None:
            user_deps = {}
        self.logger = logger

        # Going to read params
        self.koef = params.get('koef', 5)
        self.max_g_for_m = params.get('max_g_for_m', 5)
        self.minimize_groups_for_module = params.get('minimize_groups_for_module', True)
        self.priority_on_module_size = params.get('priority_on_module_size', True) and bool(module_sizes)
        self.division_type = params.get('division_type', 'Library')
        if self.division_type not in ('Library', 'Module', 'All'):
            raise ValueError("Division type {} doesn't exist".format(self.division_type))
        self.analyze_all_export_function = \
            params.get('analyze_all_export_function', self.division_type != 'Module') and bool(export_func)
        self.analyze_all_calls = \
            params.get('analyze_all_calls', self.division_type != 'Library') and bool(export_func)
        self.priority_on_export_function = \
            params.get('priority_on_export_function', self.division_type != 'Module') and bool(export_func)
        self.priority_on_calls = \
            params.get('priority_on_calls', self.division_type != 'Library') and bool(export_func)
        self.maximize_subsystems = params.get('maximize_subsystems', True)
        self.user_deps = user_deps

        # Creating modules dict
        self.modules = {}
        for module, m_deps in deps.items():
            self.modules.setdefault(module, Module(module))
            for m_dep in m_deps:
                self.modules.setdefault(m_dep, Module(m_dep))
                self.modules[module].add_predecessor(self.modules[m_dep])

            self.modules[module].size = module_sizes.get(module, 0)

        # Creating export/call functions
        self.not_checked_export_f = {}
        self.not_checked_call_f = {}
        for module_pred, func, module_succ in export_func:
            if module_pred not in self.modules or module_succ not in self.modules:
                continue
            self.modules[module_succ].export_functions.setdefault(func, [])
            self.modules[module_succ].export_functions[func].append(self.modules[module_pred])
            self.modules[module_pred].call_functions.setdefault(func, [])
            self.modules[module_pred].call_functions[func].append(self.modules[module_succ])

        for module in self.modules.values():
            self.not_checked_export_f[module] = set(module.export_functions.keys())
            self.not_checked_call_f[module] = set(module.call_functions.keys())

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

        return False

    def export_weight(self, module_pred, module_succ):
        # Count export functions, that successor calls from predecessor (this module)
        if not self.priority_on_export_function:
            return 0
        ret = 0
        for ex_f in self.not_checked_export_f.get(module_pred, set()):
            if module_succ in module_pred.export_functions[ex_f]:
                ret += 1
        return 3 * ret

    def call_weight(self, module_succ, module_pred):
        # Count functions, that successor (this module) calls from predecessor
        if not self.priority_on_calls:
            return 0
        ret = 0
        for call in self.not_checked_call_f.get(module_succ, set()):
            if module_pred in module_succ.call_functions[call]:
                ret += 1
        return 3 * ret

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
        return 3 * len(module.export_functions)

    def call_provided_weight(self, module, unused):
        # Count functions, that predecessor provides
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
        return int(10 * (self.max_g_for_m - self.count_groups_for_m.get(module, 0)) / self.max_g_for_m)

    def all_call_weight(self, module, process):
        # Returns count of functions, that module can call from process
        # If process doesn't provide export functions, but is an successor,
        # assume, he provide 1 export functions
        checked = set()
        ret = 0
        for process_module in process:
            for values in process_module.call_functions.values():
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
        return 2 * ret

    def measure_successor(self, module_pred, module_succ, process):
        weights = (self.export_weight, self.size_weight, self.export_provided_weight,
                   self.remoteness_weight, self.count_already_weight)
        return sum([weight_function(module_pred, module_succ) for weight_function in weights]) \
               + self.all_call_weight(module_succ, process)

    def measure_predecessor(self, module_pred, module_succ, process=set()):
        weights = (self.call_weight, self.size_weight, self.call_provided_weight,
                   self.remoteness_weight, self.count_already_weight)
        return sum([weight_function(module_succ, module_pred) for weight_function in weights]) \
               + self.all_call_weight(module_pred, process)

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

    def divide(self, module_name):
        if module_name not in self.modules:
            # This module has no dependencies
            self.logger.debug('Module {} has no dependencies'.format(module_name))
            return [[Module(module_name)]]

        main_module = self.modules[module_name]
        if self.is_fully_checked(main_module):
            self.logger.debug('Module {} reachs max group'.format(main_module.id))
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
                for module in process:
                    if self.division_type != 'Module':
                        # Search best candidate from successors
                        for succ in filter(lambda module: module not in process and module not in checked and
                                not self.count_groups_for_m.get(module.id, 0) > self.max_g_for_m
                                and len(process) + len(self.get_user_deps(module)) < self.koef, module.successors):
                            cur_measure = self.measure_successor(module, succ, process)
                            if cur_measure > 0 and cur_measure > max_measuring:
                                max_measuring = cur_measure
                                best_candidate = succ
                    if self.division_type != 'Library':
                        # Search best candidate from predecessors
                        for pred in self.topolog_sort(main_module, list(filter(lambda module: module not in process and
                                not self.count_groups_for_m.get(module.id, 0) > self.max_g_for_m and
                                module not in checked, module.predecessors))):
                            cur_measure = self.measure_predecessor(module, pred, process)
                            if cur_measure > 0 and cur_measure > max_measuring:
                                max_measuring = cur_measure
                                best_candidate = pred

                if best_candidate:
                    process.add(best_candidate)
                    process.update(self.get_user_deps(best_candidate))
                    checked.update(self.get_user_deps(best_candidate))
                    checked.add(best_candidate)

                    # Update not checked export functions and not checked call functions
                    for pred in filter(lambda module: module in process, best_candidate.predecessors):
                        self.not_checked_export_f.setdefault(pred, set()).difference_update \
                            ([functions for functions, module in pred.export_functions.items()
                                if best_candidate in module])
                    for succ in filter(lambda module: module in process, best_candidate.successors):
                        self.not_checked_export_f.setdefault(best_candidate, set()).difference_update \
                            ([function for function, modules in best_candidate.export_functions.items()
                                if succ in modules])

                    for pred in filter(lambda module: module in process, best_candidate.predecessors):
                        self.not_checked_call_f.setdefault(pred, set()).difference_update \
                            ([function for function, modules in pred.call_functions.items()
                                if best_candidate in modules])
                    for succ in filter(lambda module: module in process, best_candidate.successors):
                        self.not_checked_call_f.setdefault(best_candidate, set()).difference_update \
                            ([function for function, modules in best_candidate.call_functions.items()
                                if succ in modules])
                else:
                    break
            else:
                if process in clusters:
                    pass#break
                clusters.add(frozenset(process))
                for module in process:
                    self.checked_modules.add(module)
                    self.count_groups_for_m.setdefault(module, 0)
                    self.count_groups_for_m[module] += 1
                continue
            if len(process) > 1:
                clusters.add(frozenset(process))
            for module in process:
                self.checked_modules.add(module)
                self.count_groups_for_m.setdefault(module, 0)
                self.count_groups_for_m[module] += 1
            break

        ret = set()
        for cluster in clusters:
            modules = [x.id for x in cluster]
            ret.add(Graph(modules))
        return ret
