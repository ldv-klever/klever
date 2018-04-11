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
        self.clade = None
        self.graphs = None
        self.is_deps = False
        self.vog_modules = None

    def divide(self, module):
        if self.graphs is not None:
            return self.graphs.get(module, [Graph([Module(module)])])
        else:
            return self._divide(module)

    def divide_by_function(self, func):
        modules = self.get_modules_by_func(func)
        clusters = set()
        for module in modules:
            clusters.update(self.divide(module))
        return clusters

    def set_dependencies(self, deps, sizes):
        self.is_deps = True
        self._set_dependencies(deps, sizes)

    def set_callgraph(self, callgraph):
        pass

    def _set_dependencies(self, deps, sizes):
        pass

    def set_modules(self, modules):
        self.vog_modules = modules

    def set_clade(self, clade):
        self.clade = clade

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

    def need_callgraph(self):
        return False

    def get_modules_by_func(self, func_name):
        files = self.get_files_by_func(func_name)
        res = []
        for file in files:
            res.append(self.get_module_by_file(file))

        return res

    def get_files_by_func(self, func_name, call_graph_dict=None):
        if not call_graph_dict:
            call_graph = self.clade.get_callgraph()
            call_graph_dict = call_graph.load_callgraph()

        files = set()
        for func in call_graph_dict:
            if func == func_name:
                files.update(filter(lambda x: x != 'unknown', list(call_graph_dict[func].keys())))
        return list(files)

    def get_module_by_file(self, file):
        cc = self.clade.get_cc()
        desc = cc.load_json_by_in(file)
        for module, module_desc in self.vog_modules.items():
            if desc['id'] in (int(cc) for cc in module_desc['CCs']):
                return module

    def get_modules_for_subsystem(self, subsystem):
        ret = []
        for module in self.vog_modules:
            if module.startswith(subsystem):
                ret.append(module)

        return ret

    def _is_module(self, file):
        return file.endswith('.ko')

    def is_subsystem(self, file):
        return file.endswith('/')

