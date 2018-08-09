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


class Unit:

    def __init__(self, identifier):
        # Identifier
        self.name = identifier
        # Connections
        self.predecessors = set()
        self.successors = set()
        # Description of the module content
        self.ccs = set()
        self.in_files = set()
        self.size = 0
        self.export_functions = {}
        self.call_functions = {}

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


class Aggregation:

    def __init__(self, main_unit=None, name=None):
        self.units = set()
        self.name = name
        if main_unit:
            self.root = main_unit
            self.units.add(main_unit)

    @property
    def ccs(self):
        return {cc for unit in self.units for cc in unit.ccs}

    @property
    def size(self):
        return sum(unit.size for unit in self.units)

    def recursive_insert(self, unit):
        check = [unit]
        while check:
            unit = check.pop(0)
            check.extend(unit.predecessors)
            self.units.add(unit)

    def draw(self, path):
        g = Digraph(name=str(self.root.id),
                    format="png")
        for unit in self.units:
            g.node(unit.id, unit.id)
        for unit in self.units:
            for pred in unit.predecessors:
                g.edge(unit.id, pred.id)
        g.save(os.path.join(path, self.root.id + self.md5_hash))
        g.render()

    def __hash__(self):
        return hash(frozenset(self.units))

    def __str__(self):
        return str(self.units)

    def __repr__(self):
        return str(self)

    def __eq__(self, rhs):
        return set(self.units).__eq__(set(rhs.units))

    def __cmp__(self, rhs):
        return set(self.units).__cmp__(set(rhs.units))

    @property
    def md5_hash(self):
        return md5("".join([module.id for module in self.units]).encode('utf-8')).hexdigest()[:12]

    @property
    def size(self):
        return len(self.units)


