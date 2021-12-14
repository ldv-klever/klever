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

import sortedcontainers

from klever.core.vtg.emg.common.c import Variable, Declaration
from klever.core.vtg.emg.common.c.types import Structure, Array, Pointer, Function


class Interface:

    def __init__(self, category, name):
        self.category = category
        self._name = name
        self.header = None
        self.implementations = []
        self._declaration = None

    def __str__(self):
        return "{}.{}".format(self.category, self._name)

    def __hash__(self):
        return hash(str(self))

    def __lt__(self, other):
        return str(self) < str(other)

    @property
    def name(self):
        return self._name

    @property
    def declaration(self):
        return self._declaration

    @declaration.setter
    def declaration(self, new_declaration: Declaration):
        self._declaration = new_declaration

    def add_implementation(self, value, declaration, path, base_container=None, base_value=None, sequence=None):
        new = Implementation(value, declaration, value, path, base_container, base_value, sequence)
        mv = new.adjusted_value(self.declaration)
        if new.declaration != self.declaration:
            new._declaration = self.declaration
        new.value = mv
        if new.value not in self.implementations:
            self.implementations.append(new)
        else:
            c = [v for v in self.implementations if v.value == new.value]
            if len(c) == 0 or len(c) > 1:
                raise ValueError("Interface {!r} has two the same implementations {!r}".
                                 format(self._name, mv))
            return c[0]
        return new


class Container(Interface):

    def __init__(self, category, identifier):
        super(Container, self).__init__(category, identifier)

    def contains(self, target):
        if isinstance(target, Interface):
            target = target.declaration

        return self.declaration.contains(target)

    def weak_contains(self, target):
        if issubclass(type(target), Interface):
            target = target.declaration

        return self.declaration.weak_contains(target)


class StructureContainer(Container):

    def __init__(self, category, identifier):
        super(Container, self).__init__(category, identifier)
        self.field_interfaces = sortedcontainers.SortedDict()

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
    def declaration(self, new_declaration: Array):
        assert isinstance(new_declaration, Array)
        Interface.declaration.fset(self, new_declaration)


class Resource(Interface):
    pass


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
    def declaration(self, new_declaration: Function):
        assert isinstance(new_declaration, Function)
        Interface.declaration.fset(self, new_declaration)


class Callback(FunctionInterface):

    def __init__(self, category, identifier):
        super(Callback, self).__init__(category, identifier)
        self.called = False
        self.interrupt_context = False

    @Interface.declaration.setter
    def declaration(self, new_declaration):
        assert isinstance(new_declaration, Pointer) and isinstance(new_declaration.points, Function)
        Interface.declaration.fset(self, new_declaration)


class Implementation(Variable):

    def __init__(self, name, declaration, value, file, base_container=None, base_value=None, sequence=None):
        super(Implementation, self).__init__(name, declaration)
        self.value = value
        self.initialization_file = file
        self.base_container = base_container
        self.base_value = base_value
        self.sequence = sequence if sequence else []

    @property
    def declaration(self):
        return self._declaration

    @declaration.setter
    def declaration(self, declaration):
        if isinstance(declaration, Declaration) and \
                (self.declaration == declaration or self.declaration.pointer_alias(declaration)):
            self._declaration = declaration
        else:
            raise RuntimeError("Cannot change declaration {!r} by {!r} for {!r} implementation".
                               format(str(self.declaration), str(declaration), str(self.name)))

    def adjusted_value(self, declaration):
        if self._declaration == declaration:
            return self.value
        elif self._declaration == declaration.take_pointer:
            return '*' + self.value
        elif self._declaration.take_pointer == declaration:
            return '&' + self.value
        elif isinstance(declaration, Pointer) and isinstance(self._declaration, Pointer) and \
                self._declaration == 'void *':
            return self.value
        else:
            raise ValueError("Cannot adjust declaration '{}' to declaration '{}' for value {!r}".
                             format(self._declaration.to_string('%s'), declaration.to_string('%s'), self.value))
