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

from core.vtg.emg.common.signature import import_declaration, Declaration


class Variable:
    name_re = re.compile("\(?\*?%s\)?")

    def __init__(self, name, file, signature, export=False, scope=None):
        self.name = name
        self.file = file
        self.export = export
        self.value = None
        self.use = 0
        self.scope = scope

        if isinstance(signature, str):
            self.declaration = import_declaration(signature)
        elif issubclass(type(signature), Declaration):
            self.declaration = signature
        else:
            raise ValueError("Attempt to create variable {} without signature".format(name))

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
        if extern and self.scope == 'global':
            expr = "extern " + expr
        elif extern and self.scope == 'local':
            raise ValueError('Cannot print external declaration for local variable {!r}'.format(self.name))

        return expr


class FunctionDefinition:

    def __init__(self, name, file, signature=None, export=False, callback=False):
        self.name = name
        self.file = file
        self.export = export
        self.body = []
        self.callback = callback

        if not signature:
            signature = 'void f(void)'
        if isinstance(signature, str):
            self.declaration = import_declaration(signature)
        elif issubclass(type(signature), Declaration):
            self.declaration = signature
        else:
            raise ValueError("Attempt to create variable {} without signature".format(name))

    def declare(self, extern=False):
        declaration = self.declaration.to_string(self.name, typedef='complex_and_params')
        declaration += ';'

        if extern:
            declaration = "extern " + declaration
        return [declaration + "\n"]

    def define(self):
        declaration = self.declaration.define_with_args(self.name, typedef='complex_and_params')
        lines = list()
        lines.append(declaration + " {\n")
        lines.extend(['\t{}\n'.format(stm) for stm in self.body])
        lines.append("}\n")
        return lines


class Aspect(FunctionDefinition):

    def __init__(self, name, declaration, aspect_type="after"):
        self.name = name
        self.declaration = declaration
        self.aspect_type = aspect_type
        self.body = []

    def get_aspect(self):
        lines = list()
        lines.append("around: call({}) ".format("$ {}(..)".format(self.name)) +
                     " {\n")
        lines.extend(['\t{}\n'.format(stm) for stm in self.body])
        lines.append("}\n")
        return lines
