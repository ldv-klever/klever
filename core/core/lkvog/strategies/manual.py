from core.lkvog.strategies.strategy_utils import Module, Graph
from core.lkvog.strategies.abstract_strategy import AbstractStrategy


class Manual(AbstractStrategy):
    def __init__(self, logger, strategy_params, params):
        super().__init__(logger)
        self.groups = []
        for group in params['groups']:
            self.groups.append([Module(group[0])])
            for module in group[1:]:
                self.groups[-1].append(Module(module))
                for pred in self.groups[-1][:-1]:
                    self.groups[-1][-1].add_predecessor(pred)

    def divide(self, module_name):
        ret = []
        for group in self.groups:
            if module_name in [module.id for module in group]:
                ret.append(Graph(group))
        return ret
