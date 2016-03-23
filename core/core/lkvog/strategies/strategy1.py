import os

from core.lkvog.strategies.module import Module
from core.lkvog.strategies.module import Graph


class Strategy1:
    def __init__(self, logger, deps, user_deps={}, params={}, export_func={}, module_sizes={}):
        self.logger = logger
        self.koef = params.get('koef', 5)
        self.max_g_for_m = params.get('max_g_for_m', 5)
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
        self.checked_modules = set()
        self.count_groups_for_m = {}

    def is_fully_checked(self, module):
        if module not in self.checked_modules:
            return False

        if self.analyze_all_export_function and self.not_checked_export_f.get(module.id, {}):
            return False

        if not self.analyze_all_export_function and self.count_groups_for_m.get(module, 0) > self.max_g_for_m:
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
        ret = 0
        for ex_f in self.not_checked_export_f.get(module_pred.id, set()):
            if module_succ.id in module_pred.export_functions[ex_f]:
                ret += 1
        return 3 * ret

    def size_weight(self, unused_module, module):
        if not self.priority_on_module_size:
            return 0
        if module.size < 256 * 1024:
            return 2
        elif module.size < 1024 * 1024:
            return 1
        return 0

    def provided_weight(self, unused, module):
        return len(module.export_functions)

    def remoteness_weight(self, module1, module2):
        if not self.maximize_subsystems:
            return 0
        subsystem1 = module1.id[:module1.id.rfind('/')]
        subsystem2 = module2.id[:module2.id.rfind('/')]
        return 1 if subsystem1.startswith(subsystem2) or subsystem2.startswith(subsystem1) else 0

    def count_already_weight(self, unused_module, module):
        return int((self.max_g_for_m - self.count_groups_for_m.get(module, 0)) / self.max_g_for_m)

    def measure(self, module_pred, module_succ):
        weights = (self.export_weight, self.size_weight,
                   self.provided_weight, self.remoteness_weight, self.count_already_weight)
        ret = sum([x(module_pred, module_succ) for x in weights])
        return ret

    def get_user_deps(self, module):
        ret = set()
        process = [self.user_deps.get(module.id, [])]
        while process:
            curr = process.pop(0)
            for c in curr:
                if c not in self.modules:
                    continue
                ret.add(self.modules[c])
                if c in self.user_deps:
                    process.append(self.user_deps[c])
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
            if module_name == 'drivers/usb/core/usbcore.ko':
                pass
            checked = set()
            while not self.is_fully_checked(main_module):

                process = set()
                process.add(main_module)
                process.update(self.get_user_deps(main_module))
                checked.update(self.get_user_deps(main_module))
                while len(process) < self.koef:
                    max_measuring = 0
                    best_succ = None
                    for module in process:
                        for succ in filter(lambda x: x not in process and
                                not self.count_groups_for_m.get(x.id, 0) > self.max_g_for_m and x not in checked and
                                len(process) + len(self.get_user_deps(x)) < self.koef,
                                           module.successors):
                            cur_measure = self.measure(module, succ)
                            if cur_measure > 0 and cur_measure > max_measuring:
                                max_measuring = cur_measure
                                best_succ = succ

                    if best_succ:
                        process.add(best_succ)
                        process.update(self.get_user_deps(best_succ))
                        checked.update(self.get_user_deps(best_succ))
                        checked.add(best_succ)
                        for pred in filter(lambda x: x in process, best_succ.predecessors):
                            self.not_checked_export_f.setdefault(pred.id, set()).difference_update \
                                ([f for f, m in pred.export_functions.items() if best_succ.id in m])
                        for succ in filter(lambda x: x in process, best_succ.successors):
                            self.not_checked_export_f.setdefault(best_succ, set()).difference_update \
                                ([f for f, m in best_succ.export_functions.items() if succ.id in m])
                    else:
                        break
                else:
                    if process in ret:
                        break
                    ret.add(frozenset(process))
                    for module in process:
                        self.checked_modules.add(module)
                        self.count_groups_for_m.setdefault(module, 0)
                        self.count_groups_for_m[module] += 1
                    continue
                if len(process) > 1:
                    ret.add(frozenset(process))
                for module in process:
                    self.checked_modules.add(module)
                    self.count_groups_for_m.setdefault(module, 0)
                    self.count_groups_for_m[module] += 1
                break

        return ret
