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
from core.vtg.emg.common.signature import Function, Pointer, InterfaceReference


class Interface:

    def __init__(self, category, identifier, manually_specified=False):
        self.category = category
        self.short_identifier = identifier
        self.identifier = "{}.{}".format(category, identifier)
        self.declaration = None
        self.header = None

    def update_declaration(self, declaration):
        if not self.declaration.clean_declaration:
            self.declaration = declaration


class Container(Interface):
    def __init__(self, category, identifier, manually_specified=False):
        super(Container, self).__init__(category, identifier, manually_specified)
        self.element_interface = None
        self.field_interfaces = {}

    def contains(self, target):
        if issubclass(type(target), Interface):
            target = target.declaration

        return self.declaration.contains(target)

    def weak_contains(self, target):
        if issubclass(type(target), Interface):
            target = target.declaration

        return self.declaration.weak_contains(target)


class Resource(Interface):

    def __init__(self, category, identifier, manually_specified=False):
        super(Resource, self).__init__(category, identifier, manually_specified)


class FunctionInterface(Interface):

    def __init__(self, category, identifier, manually_specified=False):
        super(FunctionInterface, self).__init__(category, identifier, manually_specified)
        self.param_interfaces = []
        self.rv_interface = None

    def update_declaration(self, declaration):
        if isinstance(self.declaration, Function):
            self_declaration = self.declaration
        elif isinstance(self.declaration, Pointer) and isinstance(self.declaration.points, Function):
            self_declaration = self.declaration.points
        else:
            raise TypeError("As a type of {!r} interface expect a function or a function pointer but have: {!r}".
                            format(self.identifier, self.declaration.identifier))

        if isinstance(declaration, Pointer) and isinstance(declaration.points, Function):
            declaration = declaration.points
        elif not isinstance(declaration, Function):
            raise TypeError("To update function interface a function type expected but have: {!r}".
                            format(declaration.identifier))

        if self.rv_interface:
            if type(self_declaration.return_value) is InterfaceReference and \
                    self_declaration.return_value.pointer:
                self.rv_interface.update_declaration(declaration.return_value.points)
            else:
                self.rv_interface.update_declaration(declaration.return_value)

        for index in range(len(self_declaration.parameters)):
            p_declaration = declaration.parameters[index]

            if self.param_interfaces[index]:
                if type(self_declaration.parameters[index]) is InterfaceReference and \
                        self_declaration.parameters[index].pointer:
                    self.param_interfaces[index].update_declaration(p_declaration.points)
                else:
                    self.param_interfaces[index].update_declaration(p_declaration)

        super(FunctionInterface, self).update_declaration(declaration)


class Callback(FunctionInterface):

    def __init__(self, category, identifier, manually_specified=False):
        super(Callback, self).__init__(category, identifier, manually_specified)
        self.called = False
        self.interrupt_context = False


class SourceFunction(FunctionInterface):

    def __init__(self, identifier, raw_declaration):
        super(SourceFunction, self).__init__(None, identifier, False)
        self.identifier = identifier
        self.calls = dict()
        self.called_at = dict()
        self.declaration_files = set()
        self.definition_file = None
        self.raw_declaration = raw_declaration

    @property
    def files_called_at(self):
        raise NotImplementedError

    def calls(self, func, path):
        if path not in self.calls:
            self.calls[path] = {func}
        else:
            self.calls[path].add(func)

    def add_call(self, func, path):
        if path not in self.called_at:
            self.called_at[path] = {func}
        else:
            self.called_at[path].add(func)
