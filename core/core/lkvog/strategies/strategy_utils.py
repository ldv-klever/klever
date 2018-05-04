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

from hashlib import md5
from graphviz import Digraph
import os.path
import collections


class Module:

    def __init__(self, module_id):
        self.id = module_id
        self.predecessors = []
        self.successors = []
        self.size = 0
        self.export_functions = {}
        self.call_functions = {}

    def __lt__(self, other):
        return self.id < other.id

    def __hash__(self):
        return hash(self.id)

    def __str__(self):
        return str(self.id)

    def __repr__(self):
        return str(self)

    def __eq__(self, rhs):
        return self.id.__eq__(rhs.id)

    def __cmp__(self, rhs):
        return self.id.__cmp__(rhs.id)

    def add_predecessor(self, predecessor):
        if predecessor and predecessor not in self.predecessors:
            self.predecessors.append(predecessor)
            predecessor.successors.append(self)

    def add_successor(self, successor):
        if successor and successor not in self.successors:
            self.successors.append(successor)
            successor.predecessors.append(self)

    @property
    def md5_hash(self):
        return md5(self.id.encode('utf-8').hexdigest())[:12]


class Cluster:

    def __init__(self, root):
        self.root = root
        modules = {}
        self.hash = None
        check = [self.root]

        while check:
            module = check.pop(0)
            check.extend(module.predecessors)
            modules[module.id] = module

        self.modules = list(modules.values())

    def draw(self, dir):
        g = Digraph(name=str(self.root.id),
                    format="png")
        for module in self.modules:
            g.node(module.id, module.id)
        for module in self.modules:
            for pred in module.predecessors:
                g.edge(module.id, pred.id)
        g.save(os.path.join(dir, self.root.id + self.md5_hash))
        g.render()

    def __hash__(self):
        return hash(frozenset(self.modules))

    def __str__(self):
        return str(self.modules)

    def __repr__(self):
        return str(self)

    def __eq__(self, rhs):
        return set(self.modules).__eq__(set(rhs.modules))

    def __cmp__(self, rhs):
        return set(self.modules).__cmp__(set(rhs.modules))

    @property
    def md5_hash(self):
        return md5("".join([module.id for module in self.modules]).encode('utf-8')).hexdigest()[:12]

    @property
    def size(self):
        return len(self.modules)


class Graph:

    def __init__(self, modules):
        self.modules = modules
        self.root = self.modules[0]

    def __hash__(self):
        return hash(frozenset(self.modules))

    def __str__(self):
        return str(self.modules)

    def __repr__(self):
        return str(self)

    def __eq__(self, rhs):
        if isinstance(rhs, collections.Iterable):
            return False
            return set(self.modules).__eq__(set(rhs))
        else:
            return set(self.modules).__eq__(set(rhs.modules))

    def __cmp__(self, rhs):
        if isinstance(rhs, collections.Iterable):
            return False
            return set(self.modules).__cmp__(set(rhs))
        else:
            return set(self.modules).__cmp__(set(rhs.modules))
        #return set(self.modules).__cmp__(set(rhs.modules))

    def __lt__(self, rhs):
        return self.modules < rhs.modules

    def draw(self, dir):
        g = Digraph(name=str(self.root.id),
                    format="png")
        for module in self.modules:
            g.node(module.id, module.id)
        for module in self.modules:
            for pred in module.predecessors:
                g.edge(module.id, pred.id)
        g.save(os.path.join(dir, self.root.id + self.md5_hash))
        g.render()

    @property
    def md5_hash(self):
        return md5("".join([module.id for module in self.modules]).encode('utf-8')).hexdigest()[:12]

    @property
    def size(self):
        return len(self.modules)

