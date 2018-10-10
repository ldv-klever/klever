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


class File:

    def __init__(self, name):
        # Identifier
        self.name = name

        # Here we will store links to callgraph and definition scopes data
        self.export_functions = dict()
        self.import_functions = dict()
        self.predecessors = set()
        self.successors = set()
        self.cc = None
        self.size = 0
        self.target = False

    def __lt__(self, other):
        return self.name < other.name

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

    def add_predecessor(self, predecessor):
        # Just ignore linking to self
        if predecessor.name != self.name:
            self.predecessors.add(predecessor)
            predecessor.successors.add(self)

    def add_successor(self, successor):
        # Just ignore linking to self
        if successor.name != self.name:
            self.successors.add(successor)
            successor.predecessors.add(self)