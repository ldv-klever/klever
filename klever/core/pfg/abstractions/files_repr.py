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


class File:

    def __init__(self, name):
        """
        Represents a file of the program

        :param name: Path to the file relatively to source directory.
        """
        # Identifier
        self.name = name

        # Here we will store links to callgraph and definition scopes data
        self._export_functions = {}
        self._import_functions = {}
        self._predecessors = set()
        self._successors = set()
        self.abs_path = None
        self.cmd_id = None
        self.cmd_type = None
        self.size = 0
        self.target = False
        self.unique = True

    @property
    def successors(self):
        return set(self._successors)

    @property
    def predecessors(self):
        return set(self._predecessors)

    @property
    def export_functions(self):
        return dict(self._export_functions)

    @property
    def import_functions(self):
        return {f: desc[0] for f, desc in self._import_functions.items()}

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
        """
        Add a predecessor - the file that calls functions from this one.

        :param predecessor: File object.
        """
        # Just ignore linking to self
        if predecessor.name != self.name:
            self._predecessors.add(predecessor)
            predecessor._successors.add(self)

    def add_successor(self, successor):
        """
        Add a successor - the file that exports functions to this one.

        :param successor: File object.
        """
        # Just ignore linking to self
        if successor.name != self.name:
            self._successors.add(successor)
            successor._predecessors.add(self)

    def add_export_function(self, function_name, user_files=None):
        """
        Add an exported function.

        :param function_name: Function name
        :param user_files: None or a set of File objects that import this function.
        """
        # Just ignore linking to self
        if function_name not in self._export_functions:
            self._export_functions[function_name] = set()
        if user_files:
            self._export_functions[function_name].update(user_files)

    def add_import_function(self, function_name, definition_scope, match_score):
        if definition_scope.name == self.name:
            raise ValueError("Cannot import function {!r} from itself: {!r}".format(function_name, self.name))

        if function_name not in self._import_functions:
            self._import_functions[function_name] = [definition_scope, match_score]
            definition_scope.add_export_function(function_name, {self})
            self.add_successor(definition_scope)
        else:
            # todo: maybe add logger there? But this is not a good place to debug the callgraph
            # self.logger.warning('Cannot import function {!r} from two places: {!r} and {!r}'.
            #                     format(function_name, self._import_functions[function_name][0],
            #                            definition_scope.name))
            if self._import_functions[function_name][1] < match_score:
                self._import_functions[function_name] = [definition_scope, match_score]
                definition_scope.add_export_function(function_name, {self})
                self.add_successor(definition_scope)
