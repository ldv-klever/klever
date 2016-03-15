import os

from core.lkvog.strategies.module import Module
from core.lkvog.strategies.module import Graph


class Strategy1:
    def __init__(self, logger, deps, find_cc_full_desc_func, user_deps={}, params={}, export_func={}, module_sizes={}):
        self.logger = logger
        self.koef = params.get('koef', 2)
        self.user_deps = user_deps
        self.group_size_non_const = params.get('group_size_non_const', True)
        self.minimize_groups_for_module = params.get('minimize_groups_for_module', True)
        self.analyze_all_export_function = params.get('analyze_all_export_function', True)
        self.priority_on_module_size = params.get('priority_on_module_size', True)
        self.priority_on_export_function = params.get('priority_on_export_function', True)
        self.maximize_subsystems = params.get('maximize_subsystems', True)
        self.division_type = params.get('division_type', 'Library')
        if self.division_type not in ('Library', 'Module'):
            raise ValueError("Division type {} doesn't exist".format(self.division_type))
        self.find_cc_full_desc_func = find_cc_full_desc_func

        self.modules = {}
        self.not_checked_export_f = {}
        for module, m_deps in deps.items():
            self.modules.setdefault(module, Module(module))
            for m_dep in m_deps:
                self.modules.setdefault(m_dep, Module(m_dep))
                self.modules[module].add_predecessor(self.modules[m_dep])

            for export_f, modules in export_func.get(module.id, {}):
                self.modules[module].export_functions[export_f] = set(self.modules[module] for module in modules)
            self.modules[module].size = module_sizes.get(module, 0)
            self.not_checked_export_f[module] = self.modules[module].export_functions.keys()

        self.checked_clusters = set()
        self.count_groups_for_m = {}

        self.max_g_for_m = self.koef +2
        self.min_g_for_m = self.koef

    def is_fully_checked(self, module):
        # TODO: replace '5' to parameter
        return self.count_groups_for_m.get(module) > 5 and self.minimize_groups_for_module \
                        and (not self.analyze_all_export_function
                             or self.minimize_groups_for_module and self.not_checked_export_f[module])

    def user_weight(self, module1, module2):
        if (module1 in self.user_deps and module2 in self.user_deps[module1]) \
                or (module2 in self.user_deps and module1 in self.user_deps[module2]):
            return 1
        else:
            return 0

    def export_weight(self, module_pred, module_succ):
        if not self.priority_on_export_function:
            return 0
        return sum(map(lambda x: 1 if module_succ in x else 0, module_pred))
        # TODO if method is works, then remove commented code
        """
        ret = 0
        for modules in module_pred.export_functions.values():
            ret += 1 if module_succ in modules else 0
        return ret"""

    def size_weight(self, module, unused_module):
        if not self.priority_on_module_size:
            return 0
        if module.size < 10 * 1024:
            return 3
        elif module.size < 100 * 1024:
            return 2
        elif module.size < 1024 * 1024:
            return 1
        return 0

    def provided_weight(self, module, unused_module):
        return len(module.export_functions)

    def remoteness_weight(self, module1, module2):
        if not self.maximize_subsystems:
            return 0
        subsystem1 = module1[:module1.rfind('/')]
        subsystem2 = module2[:module2.rfind('/')]
        return 1 if subsystem1.startswith(subsystem2) or subsystem2.startswith(subsystem1) else 0

    def count_already_weight(self, module, unused_module):
        if not self.minimize_groups_for_module:
            return 0
        return -self.count_groups_for_m[module]

    def measure(self, module_pred, module_succ):
        weights = (self.export_weight, self.size_weight,
                   self.provided_weight, self.remoteness_weight, self.count_already_weight)
        return sum([x(module_pred, module_succ) for x in weights])

    def divide(self, module_name):
        if module_name not in self.modules:
            # This module has no dependencies
            self.logger.debug('Module {} has no dependencies'.format(module_name))
            return [Graph([Module(module_name)])]

        main_module = self.modules[module_name]
        if self.division_type == 'Library':
            if self.is_fully_checked(main_module):
                self.logger.debug('Module {} reachs max group'.format(main_module.id))
                return []

            ret = []
            while not self.is_fully_checked(main_module):
                graph = {main_module: {}}

                process = [main_module]
                while len(process) < self.koef:
                    max_measuring = 0
                    best_succ = None
                    for module in process:
                        for succ in filter(lambda x: x not in process and not self.is_fully_checked(x), module.successors):
                            if self.measure(module, graph[module][succ]) > max_measuring:
                                max_measuring = self.measure(graph[module][succ])
                                best_succ = succ

                    if best_succ:
                        process.append(best_succ)
                        for pred in filter(lambda x: x in process, best_succ.predecessor):
                            self.not_checked_export_f[pred].difference_update\
                                ([f for f in pred.export_functions if best_succ in pred.export_functions[f]])
                        for succ in filter(lambda x: x in process, best_succ.successor):
                            self.not_checked_export_f[best_succ].differenc_update\
                                ([f for f in best_succ.export_functions if succ in best_succ.export_functions[f]])
                        self.count_groups_for_m.setdefault(best_succ, 0)
                        self.count_groups_for_m[best_succ] += 1

                ret.append(graph)