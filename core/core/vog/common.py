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

from hashlib import md5

import core.utils


def size_in_locs(logger, file):
    number = core.utils.execute(logger, ['wc', '-l', '<', file], collect_all_stdout=True)
    number = int(number.strip())
    return number


class Module:

    def __init__(self, module_id):
        # Identifier
        self.name = module_id
        # Connections
        self.predecessors = set()
        self.successors = set()
        # Description of the module content
        self.ccs = set()
        self.in_files = set()
        self.canon_files = set()
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
        return self.name.__eq__(rhs.id)

    def __cmp__(self, rhs):
        return self.name.__cmp__(rhs.id)

    @property
    def md5_hash(self):
        return md5(self.name.encode('utf-8').hexdigest())[:12]

    def add_predecessor(self, predecessor):
        self.predecessors.add(predecessor)
        predecessor.successors.add(self)

    def add_successor(self, successor):
        self.successors.add(successor)
        successor.predecessors.add(self)

