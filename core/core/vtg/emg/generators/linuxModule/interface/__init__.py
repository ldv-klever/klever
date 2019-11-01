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

from core.vtg.emg.common.c import Variable
from core.vtg.emg.common.c.types import Structure, Array, Pointer, Function


class Interface:

    def __init__(self, category, identifier):
        self.category = category
        self.short_identifier = identifier
        self.identifier = "{}.{}".format(category, identifier)
        self.header = None
        self._declaration = None
        self.implementations = []

    @property
    def declaration(self):
        return self._declaration

    @declaration.setter
    def declaration(self, new_declaration):
        self._declaration = new_declaration

    def add_implementation(self, value, declaration, path, base_container=None, base_value=None, sequence=None):
        new = Implementation(value, declaration, value, path, base_container, base_value, sequence)
        mv = new.adjusted_value(self.declaration)
        new.declaration = self.declaration
        new.value = mv
        if new.value not in self.implementations:
            self.implementations.append(new)
        else:
            c = [v for v in self.implementations if v.value == new.value]
            if len(c) == 0 or len(c) > 1:
                raise ValueError("Interface {!r} has two the same implementations {!r}".
                                 format(self.identifier, mv))
            return c[0]
        return new


class Container(Interface):
    def __init__(self, category, identifier):
        super(Container, self).__init__(category, identifier)

    def contains(self, target):
        if issubclass(type(target), Interface):
            target = target.declaration

        return self.declaration.contains(target)

    def weak_contains(self, target):
        if issubclass(type(target), Interface):
            target = target.declaration

        return self.declaration.weak_contains(target)


class StructureContainer(Container):

    def __init__(self, category, identifier):
        super(Container, self).__init__(category, identifier)
        self.field_interfaces = {}

    @Interface.declaration.setter
    def declaration(self, new_declaration):
        if not isinstance(new_declaration, Structure):
            raise ValueError("Structure container must have Container declaration but {!r} is provided".
                             format(str(type(new_declaration).__name__)))
        Interface.declaration.fset(self, new_declaration)


class ArrayContainer(Container):

    def __init__(self, category, identifier):
        super(Container, self).__init__(category, identifier)
        self.element_interface = None

    @Interface.declaration.setter
    def declaration(self, new_declaration):
        if not isinstance(new_declaration, Array):
            raise ValueError("Array container must have Container declaration but {!r} is provided".
                             format(str(type(new_declaration).__name__)))
        Interface.declaration.fset(self, new_declaration)


class Resource(Interface):

    def __init__(self, category, identifier):
        super(Resource, self).__init__(category, identifier)


class FunctionInterface(Interface):

    def __init__(self, category, identifier):
        super(FunctionInterface, self).__init__(category, identifier)
        self.param_interfaces = list()
        self.rv_interface = None

    def set_param_interface(self, index, interface):
        if len(self.param_interfaces) <= index:
            self.param_interfaces.extend([None for _ in range(index - len(self.param_interfaces) + 1)])
        self.param_interfaces[index] = interface

    @Interface.declaration.setter
    def declaration(self, new_declaration):
        if not isinstance(new_declaration, Function):
            raise ValueError("FunctionINterface must have Function declaration but {!r} is provided".
                             format(str(type(new_declaration).__name__)))
        Interface.declaration.fset(self, new_declaration)


class Callback(FunctionInterface):

    def __init__(self, category, identifier):
        super(Callback, self).__init__(category, identifier)
        self.called = False
        self.interrupt_context = False

    @Interface.declaration.setter
    def declaration(self, new_declaration):
        if not (isinstance(new_declaration, Pointer) and isinstance(new_declaration.points, Function)):
            raise ValueError("FunctionINterface must have Function Pointer declaration but {!r} is provided".
                             format(str(type(new_declaration).__name__)))
        Interface.declaration.fset(self, new_declaration)


class Implementation(Variable):

    def __init__(self, name, declaration, value, file, base_container=None, base_value=None, sequence=None):
        super(Implementation, self).__init__(name, declaration)
        self.value = value
        self.initialization_file = file
        self.base_container = base_container
        self.base_value = base_value
        if not sequence:
            self.sequence = []
        else:
            self.sequence = sequence

    def adjusted_value(self, declaration):
        if self.declaration.compare(declaration):
            return self.value
        elif self.declaration.compare(declaration.take_pointer):
            return '*' + self.value
        elif self.declaration.take_pointer.compare(declaration):
            return '&' + self.value
        elif isinstance(declaration, Pointer) and isinstance(self.declaration, Pointer) and \
                self.declaration.identifier == 'void *':
            return self.value
        else:
            raise ValueError("Cannot adjust declaration '{}' to declaration '{}' for value {!r}".
                             format(self.declaration.to_string('%s'), declaration.to_string('%s'), self.value))

