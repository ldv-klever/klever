#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
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

import os
import json
import shutil

from core.lkvog.module_extractors import util


class LinuxKernel:
    def __init__(self, logger, clade, conf, specified_modules):
        self.logger = logger
        self.clade = clade
        self.modules = conf.get('modules', True)
        self.kernel = conf.get('kernel', False)
        self.specific_files = conf.get('specific files', [])
        self.specific_modules = conf.get('specific modules', [])
        self.kernel_subdirs = conf.get('kernel subdirs', False)

        self.subsystems = set([module for module in specified_modules if module.endswith('/')])

    def divide(self):
        modules = {}

        cmd_graph = self.clade.get_command_graph()
        build_graph = cmd_graph.load()
        kernel_modules = {}

        for id, desc in build_graph.items():
            if desc['type'] == 'LD':
                full_desc = util.get_full_desc(self.clade, id, desc['type'])
                if full_desc['out'].endswith('.ko'):
                    module = util.create_module(self.clade, id, build_graph,
                                                full_desc['relative_out']) #.replace('.ko', '.o'))
                    if self.modules \
                            or set(list(module.values())[0]['canon in files']).intersection(set(self.specific_files)) \
                            or list(module)[0] in self.specific_modules:
                        if not self.modules:
                            module[list(module.keys())[0]]['separate verify'] = False
                        modules.update(module)
                if self.kernel and full_desc['out'].endswith('built-in.o'):
                    for in_id in desc['using']:
                        full_desc_in = util.get_full_desc(self.clade, in_id, build_graph[in_id]['type'])
                        if full_desc_in['out'].endswith('built-in.o'):
                            continue
                        module = util.create_module(self.clade, in_id, build_graph)
                        module_subsystem = self._get_subsystem(list(module.keys())[0])
                        for subsystem in self.subsystems:
                            if module_subsystem == subsystem \
                                    or (self.kernel_subdirs and module_subsystem.startswith(subsystem)):
                                kernel_modules.setdefault(subsystem, {})
                                kernel_modules[subsystem].update(module)
                                break
            if desc['type'] == 'CC':
                full_desc = util.get_full_desc(self.clade, id, desc['type'])
                if set(full_desc['in']).intersection(set(self.specific_files)):
                    module = util.create_module(self.clade, id, build_graph, full_desc['out'].replace('.ko', '.o'))
                    module[list(module)[0]]['separate verify'] = False
                    modules.update(module)

        for kernel_subsystem in kernel_modules:
            kernel_module = self.merge_modules(kernel_modules[kernel_subsystem].values(), kernel_subsystem)
            modules.update(kernel_module)

        return modules

    @staticmethod
    def merge_modules(modules, module_name):
        module = {
            module_name: {
                'CCs': [cc for module in modules for cc in module['CCs']],
                'in files': [cc for module in modules for cc in module['in files']],
                'canon in files': [cc for module in modules for cc in module['canon in files']],
                'separate verify': any(module.get('separate verify', True) for module in modules)
            }
        }
        return module

    @staticmethod
    def _get_subsystem(module_name):
        return os.path.sep.join(module_name.split(os.path.sep)[:-1]) + os.path.sep

