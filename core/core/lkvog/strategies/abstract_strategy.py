#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
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

import os
from core.lkvog.strategies.strategy_utils import Graph, Module


class AbstractStrategy:
    def __init__(self, logger):
        self.logger = logger
        self.clade = None
        self.graphs = None
        self.graphs_subsystems = set()
        self.is_deps = False
        self.vog_modules = None

    def divide(self, module):
        self.logger.debug("Module is {0}".format(module))
        self.logger.debug("Graphs is {0}".format(self.graphs))
        self.logger.debug("Graphs subsystem is {0}".format(self.graphs_subsystems))
        if self.graphs is not None:
            if module in self.graphs:
                return self.graphs[module]
            for subsystem in self.graphs_subsystems:
                if module.startswith(subsystem):
                    self.logger.debug("Module in graphs subsystem")
                    self.logger.debug("{0}".format(self.graphs[subsystem]))
                    return self.graphs[subsystem]
            return self.graphs.get(module, [Graph([Module(module)])])
        else:
            return self._divide(module)

    def divide_by_function(self, func):
        try:
            modules = self.get_modules_by_func(func)
        except FileNotFoundError:
            self.logger.debug("Not found files for {0} function".format(func))
            return []
        if not modules:
            self.logger.debug("Skipping {0} function".format(func))
            return []
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
            if self.is_subsystem(module):
                self.graphs_subsystems.add(module)
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
        descs = cc.load_all_json_by_in(file)
        for desc in descs:
            for module, module_desc in self.vog_modules.items():
                if desc['id'] in (int(cc) for cc in module_desc['CCs']):
                    return module

    def get_modules_for_subsystem(self, subsystem):
        ret = []
        for module in self.vog_modules:
            for cc_file in module['CCs']:
                if cc_file.startswith(subsystem):
                    ret.append(module)
                    break

        return ret

    def get_specific_files(self, files):
        return {}

    def get_specific_modules(self):
        return []

    def is_module_in_subsystem(self, module, subsystem, strict=False):
        if module not in self.vog_modules:
            return False

        for in_file in self.vog_modules[module]['in files']:
            if in_file.startswith(subsystem):
                return True
        if module.startswith("ext-modules/"):
            module = module[len('ext-modules/'):]
        if module.startswith(subsystem):
            if strict:
                if os.path.dirname(module) == os.path.dirname(subsystem):
                    return True
            else:
                return True
        return False

    def _is_module(self, file):
        return file.endswith('.o') or file.endswith('.ko')

    def is_subsystem(self, file):
        # todo: this is an ugly workaround
        # todo: an option is to check a file extension
        return file.endswith('/')

