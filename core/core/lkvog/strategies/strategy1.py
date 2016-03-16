import os

from core.lkvog.strategies.module import Module
from core.lkvog.strategies.module import Graph


class Strategy1:
    def __init__(self, logger, deps, user_deps={}, params={}, export_func={}, module_sizes={}):
        self.logger = logger
        self.koef = params.get('koef', 5)
        self.user_deps = user_deps
        self.group_size_non_const = params.get('group_size_non_const', True)
        self.minimize_groups_for_module = params.get('minimize_groups_for_module', True)
        self.analyze_all_export_function = params.get('analyze_all_export_function', True) and bool(export_func)
        self.priority_on_module_size = params.get('priority_on_module_size', True) and bool(module_sizes)
        self.priority_on_export_function = params.get('priority_on_export_function', True) and bool(export_func)
        self.maximize_subsystems = params.get('maximize_subsystems', True)
        self.division_type = params.get('division_type', 'Library')
        if self.division_type not in ('Library', 'Module'):
            raise ValueError("Division type {} doesn't exist".format(self.division_type))

        self.modules = {}
        self.not_checked_export_f = {}
        for module, m_deps in deps.items():
            self.modules.setdefault(module, Module(module))
            for m_dep in m_deps:
                self.modules.setdefault(m_dep, Module(m_dep))
                self.modules[module].add_predecessor(self.modules[m_dep])

            self.modules[module].size = module_sizes.get(module, 0)

        for module in export_func:
            if module not in self.modules:
                continue
            self.modules[module].export_functions = export_func[module]
            self.not_checked_export_f[module] = set(self.modules[module].export_functions.keys())

        self.checked_clusters = set()
        self.count_groups_for_m = {}
        self.max_g_for_m = self.koef + 2
        self.min_g_for_m = self.koef

    def is_fully_checked(self, module):
        if self.analyze_all_export_function and self.not_checked_export_f.get(module.id, {}):
            return False
        # TODO: replace 5
        if not self.analyze_all_export_function and self.count_groups_for_m.get(module, 0) > 5:
            return True
        if self.analyze_all_export_function and not self.not_checked_export_f.get(module.id, {}) \
                and self.minimize_groups_for_module:
            return True

        return False


    def user_weight(self, module1, module2):
        if (module1 in self.user_deps and module2 in self.user_deps[module1]) \
                or (module2 in self.user_deps and module1 in self.user_deps[module2]):
            return 1
        else:
            return 0

    def export_weight(self, module_pred, module_succ):
        if not self.priority_on_export_function:
            return 0
        return sum(map(lambda x: 1 if module_succ.id in x else 0, module_pred.export_functions))

    def size_weight(self, module, unused_module):
        if not self.priority_on_module_size:
            return 0
        if module.size < 256 * 1024:
            return 2
        elif module.size < 1024 * 1024:
            return 1
        return 0

    def provided_weight(self, module, unused_module):
        return len(module.export_functions)

    def remoteness_weight(self, module1, module2):
        if not self.maximize_subsystems:
            return 0
        subsystem1 = module1.id[:module1.id.rfind('/')]
        subsystem2 = module2.id[:module2.id.rfind('/')]
        return 1 if subsystem1.startswith(subsystem2) or subsystem2.startswith(subsystem1) else 0

    def count_already_weight(self, unused_module, module):
        return -self.count_groups_for_m.get(module, 0)

    def measure(self, module_pred, module_succ):
        weights = (self.export_weight, self.size_weight,
                   self.provided_weight, self.remoteness_weight, self.count_already_weight)
        ret = sum([x(module_pred, module_succ) for x in weights])
        return ret

    def divide(self, module_name):
        if module_name not in self.modules:
            # This module has no dependencies
            self.logger.debug('Module {} has no dependencies'.format(module_name))
            return [[Module(module_name)]]

        main_module = self.modules[module_name]
        if self.division_type == 'Library':
            if self.is_fully_checked(main_module):
                self.logger.debug('Module {} reachs max group'.format(main_module.id))
                return []

            ret = set()
            while not self.is_fully_checked(main_module):

                process = set()
                process.add(main_module)
                self.count_groups_for_m.setdefault(main_module, 1)
                while len(process) < self.koef:
                    max_measuring = 0
                    best_succ = None
                    for module in process:
                        for succ in filter(lambda x: x not in process and not self.is_fully_checked(x), module.successors):
                            cur_measure = self.measure(module, succ)
                            if cur_measure > 0 and cur_measure > max_measuring:
                                max_measuring = self.measure(module, succ)
                                best_succ = succ

                    if best_succ:
                        process.add(best_succ)
                        for pred in filter(lambda x: x in process, best_succ.predecessors):
                            self.not_checked_export_f.setdefault(pred.id, set()).difference_update\
                                ([f for f, m in pred.export_functions.items() if best_succ in m])
                        for succ in filter(lambda x: x in process, best_succ.successors):
                            self.not_checked_export_f.setdefault(best_succ, set()).difference_update\
                                ([f for f, m in best_succ.export_functions.items() if succ in m])
                    else:
                        break
                else:
                    if process in ret:
                        break
                    ret.add(frozenset(process))
                    for module in process:
                        self.count_groups_for_m.setdefault(module, 0)
                        self.count_groups_for_m[module] += 1
                    continue
                break

        return ret