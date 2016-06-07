from core.lkvog.strategies.module import Module
from core.lkvog.strategies.module import Graph


class Separate_modules:
    def __init__(self, logger, module_deps, params):
        self.logger = logger
        self.checked_clusters = set()

    def divide(self, module_name):
        return [Graph([Module(module_name)])]
