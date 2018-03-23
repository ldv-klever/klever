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

from core.lkvog.strategies.strategy_utils import Graph, Module


class AbstractStrategy:
    def __init__(self, logger):
        self.logger = logger
        self.graphs = None
        self.is_deps = False

    def divide(self, module):
        if self.graphs is not None:
            return self.graphs.get(module, [Graph([Module(module)])])
        else:
            return self._divide(module)

    def set_dependencies(self, deps, sizes):
        self.is_deps = True
        self._set_dependencies(deps, sizes)

    def _set_dependencies(self, deps, sizes):
        pass

    def _divide(self, module):
        raise NotImplementedError

    def get_modules_to_build(self, modules):
        """
        Returns list of modules to build and whether to build all
        """
        return modules, False

    def _collect_modules_to_build(self, modules):
        to_build = set()
        self.graphs = {}
        for module in modules:
            self.graphs[module] = self._divide(module)
            for graph in self.graphs[module]:
                for module in graph.modules:
                    to_build.add(module.id)

        return list(to_build)

    def need_dependencies(self):
        return False
