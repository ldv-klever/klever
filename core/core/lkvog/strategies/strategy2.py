import os

from core.lkvog.strategies.module import Module
from core.lkvog.strategies.module import Graph


class Strategy2:
    def __init__(self, logger, deps, user_deps={}, params={}, export_func={}, module_sizes={}):
        self.logger = logger
        self.koef = params.get('koef', 5)
        self.max_g_for_m = params.get('max_g_for_m', 5)
        self.user_deps = user_deps
        self.group_size_non_const = params.get('group_size_non_const', True)
        self.minimize_groups_for_module = params.get('minimize_groups_for_module', True)
        self.analyze_all_calls = params.get('analyze_all_calls', True) and bool(export_func)
        self.priority_on_module_size = params.get('priority_on_module_size', True) and bool(module_sizes)
        self.priority_on_calls = params.get('priority_on_calls', True) and bool(export_func)
        self.maximize_subsystems = params.get('maximize_subsystems', True)

        self.modules = {}
        self.not_checked_calls = {}
        for module, m_deps in deps.items():
            self.modules.setdefault(module, Module(module))
            for m_dep in m_deps:
                self.modules.setdefault(m_dep, Module(m_dep))
                self.modules[module].add_predecessor(self.modules[m_dep])

            self.modules[module].size = module_sizes.get(module, 0)

        call_func = {}
        for module, export_funcs in export_func.items():
            if module not in self.modules:
                continue
            for ex_func, m2s in export_funcs.items():
                for m2 in m2s:
                    if m2 not in self.modules:
                        continue
                    call_func.setdefault(m2, {})
                    call_func[m2].setdefault(ex_func, set())
                    call_func[m2][ex_func].add(module)

        for module in call_func:
            if module not in self.modules:
                continue
            self.modules[module].call_functions = call_func[module]
            self.not_checked_calls[module] = set(self.modules[module].call_functions.keys())

        self.checked_clusters = set()
        self.checked_modules = set()
        self.count_groups_for_m = {}

    def is_fully_checked(self, module):
        if module not in self.checked_modules:
            return False

        if self.analyze_all_calls and self.not_checked_calls.get(module.id, {}):
            return False

        if not self.analyze_all_calls and self.count_groups_for_m.get(module, 0) > self.max_g_for_m:
            return True

        if self.analyze_all_calls and not self.not_checked_calls.get(module.id, {}) \
                and self.minimize_groups_for_module:
            return True

        return False

    def user_weight(self, module1, module2):
        if (module1 in self.user_deps and module2 in self.user_deps[module1]) \
                or (module2 in self.user_deps and module1 in self.user_deps[module2]):
            return 1
        else:
            return 0

    def call_weight(self, module_pred, module_succ):
        if not self.priority_on_calls:
            return 0
        ret = 0
        for call in self.not_checked_calls.get(module_succ.id, set()):
            if module_pred.id in module_succ.call_functions[call]:
                ret += 1
        return 3*ret

    def size_weight(self, module, unused_module):
        if not self.priority_on_module_size:
            return 0
        if module.size < 256 * 1024:
            return 2
        elif module.size < 1024 * 1024:
            return 1
        return 0

    def provided_weight(self, module, unused):
        return len(module.call_functions)

    def remoteness_weight(self, module1, module2):
        if not self.maximize_subsystems:
            return 0
        subsystem1 = module1.id[:module1.id.rfind('/')]
        subsystem2 = module2.id[:module2.id.rfind('/')]
        return 1 if subsystem1.startswith(subsystem2) or subsystem2.startswith(subsystem1) else 0

    def count_already_weight(self, module, unused_module):
        return int((self.max_g_for_m-self.count_groups_for_m.get(module, 0))/self.max_g_for_m)

    def all_call_weight(self, module, process):
        checked = set()
        ret = 0
        for m in process:
            for values in m.call_functions.values():
                if module.id in values:
                    ret += 1
                    checked.add(m)
            for v in module.call_functions.values():
                if m in v:
                    checked.add(m)
                    ret += 1
        for m in set(process).difference(checked):
            if m in module.successors or m in module.predecessors:
                ret += 1
        return 2*ret

    def measure(self, module_succ, module_pred, process):
        weights = (self.call_weight, self.size_weight,
                   self.provided_weight, self.remoteness_weight, self.count_already_weight)
        ret = sum([x(module_pred, module_succ) for x in weights]) + self.all_call_weight(module_pred, process)
        return ret

    def topolog_sort(self, main_module, modules):
        ret = {}
        process = [(1, x) for x in main_module.predecessors]
        while process:
            i, module = process.pop()
            if module not in modules:
                continue
            ret.setdefault(module, i)
            ret[module] = max(ret[module], i)
            process.extend([(i + 1, x) for x in module.predecessors])

        return map(lambda x: x[0], sorted(ret.items(), key=lambda x: x[1]))

    def divide(self, module_name):
        if module_name not in self.modules:
            # This module has no dependencies
            self.logger.debug('Module {} has no dependencies'.format(module_name))
            return [[Module(module_name)]]

        main_module = self.modules[module_name]
        if self.is_fully_checked(main_module):
            self.logger.debug('Module {} reachs max group'.format(main_module.id))
            return []

        ret = []
        checked = set()
        while not self.is_fully_checked(main_module):

            process = set()
            process.add(main_module)
            while len(process) < self.koef:
                max_measuring = 0
                best_pred = None
                succ_best_pred = None
                for module in process:
                    for pred in self.topolog_sort(main_module, list(filter(lambda x: x not in process and
                            not self.count_groups_for_m.get(x.id, 0) > self.max_g_for_m and x not in checked,
                                       module.predecessors))):
                        cur_measure = self.measure(module, pred, process)
                        if cur_measure > 0 and cur_measure > max_measuring:
                            max_measuring = cur_measure
                            best_pred = pred
                            succ_best_pred = module

                if best_pred:
                    process.add(best_pred)
                    checked.add(best_pred)
                    for pred in filter(lambda x: x in process, best_pred.predecessors):
                        self.not_checked_calls.setdefault(pred.id, set()).difference_update \
                            ([f for f, m in pred.export_functions.items() if best_pred.id in m])
                    for succ in filter(lambda x: x in process, best_pred.successors):
                        self.not_checked_calls.setdefault(best_pred, set()).difference_update \
                            ([f for f, m in best_pred.export_functions.items() if succ.id in m])
                else:
                    break
            else:
                if process in ret:
                    break
                ret.append(frozenset(process))
                for module in process:
                    self.checked_modules.add(module)
                    self.count_groups_for_m.setdefault(module, 0)
                    self.count_groups_for_m[module] += 1
                continue
            if len(process) > 1:
                ret.append(frozenset(process))
            for module in process:
                self.checked_modules.add(module)
                self.count_groups_for_m.setdefault(module, 0)
                self.count_groups_for_m[module] += 1
            break

        return ret
