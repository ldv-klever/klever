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
from hashlib import md5
from graphviz import Digraph


class Fragment:

    def __init__(self, identifier):
        # Identifier
        self.name = identifier
        self.target = False
        # Connections
        self.predecessors = set()
        self.successors = set()
        # Description of the module content
        self.ccs = set()
        self.in_files = set()
        self.size = 0
        self.export_functions = dict()
        self.import_functions = dict()

    def __lt__(self, other):
        return self.name < other.id

    def __hash__(self):
        return hash(self.name)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return str(self)

    def __eq__(self, rhs):
        return self.name.__eq__(rhs.name)

    def __cmp__(self, rhs):
        return self.name.__cmp__(rhs.name)

    @property
    def md5_hash(self):
        return md5(self.name.encode('utf-8').hexdigest())[:12]

    def add_predecessor(self, predecessor):
        self.predecessors.add(predecessor)
        predecessor.successors.add(self)

    def add_successor(self, successor):
        self.successors.add(successor)
        successor.predecessors.add(self)

    def add_export_function(self, scope, func):
        funcs = self.export_functions.setdefault(scope, set())
        funcs.add(func)

    def add_extern_call(self, definition_file, func):
        funcs = self.import_functions.setdefault(definition_file, set())
        funcs.add(func)


class Aggregation:

    def __init__(self, main_fragment=None, name=None):
        self.fragments = set()
        self.name = name
        if main_fragment:
            self.root = main_fragment
            self.fragments.add(main_fragment)

    @property
    def ccs(self):
        return {cc for frag in self.fragments for cc in frag.ccs}

    @property
    def size(self):
        return sum(frag.size for frag in self.fragments)

    def recursive_insert(self, fragment):
        check = [fragment]
        while check:
            fragment = check.pop(0)
            check.extend(fragment.predecessors)
            self.fragments.add(fragment)

    def draw(self, path):
        g = Digraph(name=str(self.root.id),
                    format="png")
        for frag in self.fragments:
            g.node(frag.id, frag.id)
        for frag in self.fragments:
            for pred in frag.predecessors:
                g.edge(frag.id, pred.id)
        g.save(os.path.join(path, self.root.id + self.md5_hash))
        g.render()

    def __hash__(self):
        return hash(frozenset(self.fragments))

    def __str__(self):
        return str(self.fragments)

    def __repr__(self):
        return str(self)

    def __eq__(self, rhs):
        return set(self.fragments).__eq__(set(rhs.fragments))

    def __cmp__(self, rhs):
        return set(self.fragments).__cmp__(set(rhs.fragments))

    @property
    def md5_hash(self):
        return md5("".join([module.id for module in self.fragments]).encode('utf-8')).hexdigest()[:12]

    @property
    def size(self):
        return len(self.fragments)


