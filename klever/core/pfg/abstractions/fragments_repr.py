#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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


class Fragment:
    """Represent a program fragment - a set of files."""

    def __init__(self, identifier):
        """
        Create a fragment.

        :param identifier: Unique among other fragments identifier.
        """
        # Identifier
        self.name = identifier

        # Description of the module content
        self.files = set()

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
    def unique_files(self):
        return set(f for f in self.files if f.unique)

    @property
    def export_functions(self):
        """Set with all function names that are exported by files of the fragments"""
        return {f for file in self.files for f in file.export_functions}

    @property
    def import_functions(self):
        """Set with all function names that are imported by files of the fragments"""
        return {f for file in self.files for f in file.import_functions}

    @property
    def ccs(self):
        """Set of all CC compilation files."""
        return {(file.cmd_id, file.cmd_type) for file in self.files}

    @property
    def size(self):
        """Total size of all files of the fragment in LoC."""
        return sum(f.size for f in self.files)

    @property
    def target(self):
        """It is true if any file of the fragment is marked as intended for verification."""
        return any(f.target for f in self.files)

    @property
    def target_files(self):
        """Return all file objects marked as targets."""
        return [f for f in self.files if f.target]

    @target.setter
    def target(self, flag):
        """Set all files of the fragment as target and intended for verification."""
        for f in self.files:
            f.target = flag
