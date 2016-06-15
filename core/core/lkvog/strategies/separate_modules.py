from core.lkvog.strategies.strategy_utils import Module, Graph
from core.lkvog.strategies.abstract_strategy import AbstractStrategy


class SeparateModules(AbstractStrategy):
    def __init__(self, logger, strategy_params, params):
        super().__init__(logger)

    def divide(self, module_name):
        return [Graph([Module(module_name)])]
