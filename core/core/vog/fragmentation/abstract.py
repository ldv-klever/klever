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
import ujson
from graphviz import Digraph

import core.vog.common as common


class AbstractDivider:

    DESC_FILE = 'fragments description.json'

    def __init__(self, logger, conf, source, clade_api):
        self.logger = logger
        self.conf = conf
        self.source = source
        self.clade = clade_api

        # Cache
        self._target_fragments = None
        self._fragments = None

    @property
    def attributes(self):
        data = dict()
        data['target fragments'] = [f.name for f in self.target_fragments]
        data['fragments'] = {f.name: list(f.in_files) for f in self.fragments}

        with open(self.DESC_FILE, 'w', encoding='utf8') as fp:
            ujson.dump(data, fp, sort_keys=True, indent=4, ensure_ascii=False, escape_forward_slashes=False)

        return [
                   {
                       'name': 'Fragmentation strategy',
                       'value': [
                           {'name': 'name', 'value': self.conf['Fragmentation strategy']['name'],
                            'data': self.DESC_FILE}
                        ]
                   },
               ], [self.DESC_FILE]

    @property
    def target_fragments(self):
        if not self._target_fragments:
            self._divide()
            # Check that for all build targets the strategy generated a fragment with target flag
            self.source.check_targets_consistency()
        return self._target_fragments

    @property
    def fragments(self):
        if self._fragments is None:
            self._divide()
        return self._fragments

    def find_fragment_by_name(self, name):
        for f in self.fragments:
            if f.name == name:
                return f
        return None

    def _divide(self):
        raise NotImplementedError

    def __check_cc(self, desc):
        if len(desc['in']) != 1:
            raise NotImplementedError('CC build commands with more than one input file are not supported')

        if len(desc['out']) != 1:
            raise NotImplementedError('CC build commands with more than one output file are not supported')

    def _create_fragment_from_ld(self, identifier, name, cmdg, srcg):
        ccs = cmdg.get_ccs_for_ld(identifier)

        fragment = common.Fragment(name)
        fragment.ccs = set()
        fragment.in_files = set()

        for i, d in ccs:
            self.__check_cc(d)
            fragment.ccs.add(str(i))
            fragment.in_files.add(d['in'][0])

        fragment.size = sum(srcg.get_sizes(fragment.in_files).values())

        return fragment

    def _create_fragment_from_cc(self, identifier, name):
        desc = self.clade.get_cc(identifier)
        fragment = common.Fragment(name)
        self.__check_cc(desc)
        fragment.ccs = {str(identifier)}
        fragment.in_files = {desc['in'][0]}
        return fragment

    def establish_dependencies(self):
        self.logger.info("Connect frgaments between each other on base of callgraph")
        cg = self.clade.CallGraph().graph
        c_to_deps = dict()
        c_to_frag = dict()
        f_to_deps = dict()

        # Fulfil callgraph dependencies
        for fragment in self.fragments:
            # First collect export functions
            for path in fragment.in_files:
                c_to_frag[path] = fragment
                deps = c_to_deps.setdefault(path, set())

                for func, desc in cg.get(path, dict()).items():
                    tp = desc.get('type', 'static')
                    if tp == 'global':
                        fragment.add_export_function(path, func)
                        f_to_deps.setdefault(func, set())
                        f_to_deps[func].add(fragment)

                    for calls_scope, called_functions in ((s, d) for s, d in desc.get('calls', dict()).items()
                                                          if s != path and s != 'unknown'):
                        deps.add(calls_scope)
                        for called_func in called_functions:
                            fragment.add_extern_call(calls_scope, called_func)

        # Now connect different fragments
        for path, deps in c_to_deps.items():
            fragment = c_to_frag[path]

            for required_file in (f for f in deps if f in c_to_frag):
                required_fragment = c_to_frag[required_file]

                # Connect
                fragment.add_successor(required_fragment)

        # Print if neccessary as a graph
        if self.conf['Fragmentation strategy'].get('draw dependencies'):
            self.print_fragments()

        return c_to_deps, f_to_deps, c_to_frag

    def print_fragments(self):
        g = Digraph(graph_attr={'rankdir': 'LR'}, node_attr={'shape': 'rectangle'})
        for fragment in self.fragments:
            g.node(fragment.name, "{}".format(fragment.name) + (' (target)' if fragment.target else ''))

        for fragment in self.fragments:
            for suc in fragment.successors:
                g.edge(fragment.name, suc.name)
        g.render('program fragments')
