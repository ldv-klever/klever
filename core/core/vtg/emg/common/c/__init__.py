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
import re

from core.vtg.emg.common.c.types import import_declaration, Declaration


class Variable:
    name_re = re.compile("\(?\*?%s\)?")

    def __init__(self, name, declaration):
        self.name = name
        self.static = False
        self.raw_declaration = None
        self.declaration = None
        self.value = None
        self.declaration_files = set()
        self.use = 0
        self.initialization_file = None

        if not declaration:
            declaration = 'void f(void)'
        if isinstance(declaration, str):
            self.declaration = import_declaration(declaration)
            self.raw_declaration = declaration
        elif issubclass(type(declaration), Declaration):
            self.declaration = declaration
        else:
            raise ValueError("Attempt to add variable {!r} without signature".format(name))

    def declare_with_init(self):
        # Get declaration
        declaration = self.declare(extern=False)

        # Add memory allocation
        if self.value:
            declaration += " = {}".format(self.value)

        return declaration

    def declare(self, extern=False):
        # Generate declaration
        expr = self.declaration.to_string(self.name, typedef='complex_and_params')

        # Add extern prefix
        if extern:
            expr = "extern " + expr

        return expr


class Function:

    def __init__(self, name, declaration=None):
        self.name = name
        self.static = False
        self.raw_declaration = None
        self.declaration = None
        self.body = []
        self.calls = dict()
        self.called_at = dict()
        self.declaration_files = set()
        self.definition_file = None

        if not declaration:
            declaration = 'void f(void)'
        if isinstance(declaration, str):
            self.declaration = import_declaration(declaration)
            self.raw_declaration = declaration
        elif issubclass(type(declaration), Declaration):
            self.declaration = declaration
        else:
            raise ValueError("Attempt to add function {!r} without signature".format(name))

    @property
    def files_called_at(self):
        return self.called_at.keys()

    def call_in_function(self, func, parameters):
        """
        Save information that this function calls in its body another function which is provided within parameters
        alongside with arguments.

        :param func: Name of the called function.
        :param parameters: List of parameters. Currently all non-function pointers are None and for function pointers
                           the value is a function name
        :return:
        """
        if func not in self.calls:
            self.calls = {func: [parameters]}
        else:
            self.calls[func].append(parameters)

    def add_call(self, func, path):
        if path not in self.called_at:
            self.called_at[path] = {func}
        else:
            self.called_at[path].add(func)

    def declare(self, extern=False):
        declaration = self.declaration.to_string(self.name, typedef='complex_and_params')
        declaration += ';'

        if extern:
            declaration = "extern " + declaration
        return [declaration + "\n"]

    def define(self):
        declaration = self.declaration.define_with_args(self.name, typedef='complex_and_params')
        prefix = '/* AUX_FUNC {} */\n'.format(self.name)
        lines = [prefix]
        lines.append(declaration + " {\n")
        lines.extend(['\t{}\n'.format(stm) for stm in self.body])
        lines.append("}\n")
        return lines


class Macro:

    def __init__(self, name):
        self.name = name
        self.parameters = dict()

    def add_parameters(self, path, parameters):
        if path not in parameters:
            self.parameters[path] = [parameters]
        else:
            self.parameters[path].append(parameters)




