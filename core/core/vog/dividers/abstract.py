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
from hashlib import md5

import core.vog.common as common


class AbstractDivider:

    def __init__(self, logger, conf, source, clade_api):
        self.logger = logger
        self.conf = conf
        self.source = source
        self.clade = clade_api

        # Cache
        self._target_units = None
        self._units = None

    @property
    def attributes(self):
        return [{
            'name': 'VOG divider',
            'value': [{'name': 'name', 'value': self.conf['VOG divider']['name']}]
        }]

    @property
    def target_units(self):
        if not self._target_units:
            self._divide()
        return self._target_units

    @property
    def units(self):
        if not self._units:
            self._divide()
        return self._units

    def _divide(self):
        raise NotImplementedError

    def _create_unit_from_ld(self, identifier, name, cmdg, srcg):
        ccs = cmdg.get_ccs_for_ld(identifier)
        unit = common.Unit(name)
        unit.ccs = {i for i, d in ccs}
        unit.in_files = {d['in'][0] for i, d in ccs}
        unit.size = sum(srcg.get_sizes(unit.in_files).values())
        # todo: Establish dependencies and graph of dependencies
        # todo: Add information on functions
        return unit

    # todo: Remove this
    # def _build_dependencies(self):
    #     not_root_files = set()
    #     # Todo: Replace this
    #     dependencies = {}
    #     root_files = set()
    #
    #     # todo: Why sorting is needed? We always go over distionary in deterministic way
    #     # todo: Move this to Clade API
    #     for func in self.callgraph:
    #         for file in self.callgraph[func]:
    #             if file == 'unknown' or not file.endswith('.c'):
    #                 continue
    #             dependencies.setdefault(file, {})
    #             for t in ('calls', 'uses'):
    #                 for called_func in self.callgraph[func][file].get(t, set()):
    #                     for called_file in sorted(self.callgraph[func][file][t][called_func].keys()):
    #                         if called_file == 'unknown':
    #                             continue
    #                         if not called_file.endswith('.c'):
    #                             continue
    #                         if file != called_file:
    #                             dependencies.setdefault(file, {})
    #                             dependencies[file].setdefault(called_file, 0)
    #                             dependencies[file][called_file] += 1
    #                             not_root_files.add(called_file)
    #             root_files.add(file)
    #
    #     root_files.difference_update(not_root_files)
    #
    #     # Add circle dependencies files
    #     root_files.update(set(dependencies.keys()).difference(set(self._reachable_files(dependencies, root_files))))
    #
    #     return dependencies, sorted(root_files)
    #
    # def _reachable_files(self, deps, root_files):
    #     # Todo: Move to Clade
    #     reachable = set()
    #     process = list(root_files)
    #     while process:
    #         cur = process.pop(0)
    #         if cur in reachable:
    #             continue
    #         reachable.add(cur)
    #         process.extend(deps.get(cur, []))
    #     return reachable

    # def _create_module(self, cmd_id, module_id=None):
    #     cmd_type = self.cmd_graph[cmd_id]['type']
    #     if cmd_type == 'LD':
    #         return self.__create_unit_from_ld(cmd_id, module_id)
    #     else:
    #         return self.__create_module_by_cc(cmd_id, module_id)
    #
    # def _create_module_by_desc(self, desc_files, in_files):
    #     # Todo: this is a mess, ugly and useless
    #     module_id = md5("".join([in_file for in_file in sorted(in_files)]).encode('utf-8')).hexdigest()[:12] + ".o"
    #     ret = {
    #         module_id: {
    #             # todo: and another one sorting
    #             'CCs': [str(desc_file) for desc_file in sorted(desc_files)],
    #             'in files': sorted(in_files),
    #             'canon in files': sorted(in_files)
    #         }
    #     }
    #     desc_files.clear()
    #     in_files.clear()
    #     return ret

    # def __create_module_by_cc(self, cmd_id, module_id=None):
    #     desc = self._get_full_desc(cmd_id, self.cmd_graph[cmd_id]['type'])
    #     if module_id is None:
    #         if 'relative_out' in desc:
    #             module_id = desc['relative_out']
    #         else:
    #             module_id = desc['out']
    #     ccs = []
    #     process = [cmd_id]
    #     in_files = []
    #     canon_in_files = []
    #     while process:
    #         current = process.pop(0)
    #         current_type = self.cmd_graph[current]['type']
    #
    #         if current_type == 'CC':
    #             desc = self._get_full_desc(current, current_type)
    #             if not desc['in'][0].endswith('.S'):
    #                 ccs.append(current)
    #             in_files.extend([os.path.join(desc['cwd'], file) for file in desc['in']])
    #             canon_in_files.extend(desc['in'])
    #
    #         # todo: Do we need sorting?
    #         process.extend(sorted(self.cmd_graph[current]['using']))
    #
    #     return {
    #         module_id: {
    #             'CCs': ccs,
    #             'in files': in_files,
    #             'canon in files': canon_in_files
    #         }
    #     }
    #
    # def _get_full_desc(self, cmd_id, type_desc):
    #     desc = None
    #     # # Todo: this should be updated accoring to new Clade API
    #     # if type_desc == 'CC':
    #     #     desc = clade.get_cc()
    #     # elif type_desc == 'LD':
    #     #     desc = clade.get_ld()
    #     # elif type_desc == 'MV':
    #     #     desc = clade.get_mv()
    #     # else:
    #     #     raise TypeError("Type {!r} is not supported".format(type_desc))
    #     return desc.load_json_by_id(cmd_id)
    #
    # @property
    # def _cmd_graph_ccs(self):
    #     # todo: MAybe this this is also useful to implement in clade
    #     cmd_graph = None # clade.get_command_graph()
    #     build_graph = cmd_graph.load()
    #
    #     cc_modules = {}
    #
    #     for node_id, desc in build_graph.items():
    #         if desc['type'] == 'CC':
    #             # todo: Update with new Clade
    #             # full_desc = clade.get_cc().load_json_by_id(node_id)
    #             full_desc = None
    #             if full_desc['out'] and not full_desc['out'].endswith('.mod.o'):
    #                 for in_file in full_desc['in']:
    #                     cc_modules[in_file] = full_desc
    #
    #     return cc_modules
    #
    # def _get_locs(self, file):
    #     # todo: update
    #     desc = self._clade.get_cc().load_json_by_in(file)
    #     try:
    #         # Todo: fix this mess
    #         for in_file in desc['in']:
    #             return common.size_in_locs(self.logger, self._clade.get_file(os.path.join(desc['cwd'], in_file)))
    #             # self._clade.get_file(os.path.join(desc['cwd'], in_file))) as fp:
    #             #     return sum(1 for _ in fp)
    #     except:
    #         return 0
