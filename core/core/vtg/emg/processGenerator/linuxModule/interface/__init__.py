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


def implementations(self, interface, weakly=True):
    """
    Finds all implementations which are relevant to the given interface. This function finds all implementations
    available for a given declaration in interface and tries to filter out that implementations which implements
    the other interfaces with the same declaration. This can be done on base of connections with containers and
    many other assumptions.

    :param interface: Interface object.
    :param weakly: Seach for implementations in implementations of pointers to given type or in implementations
                   available for a type to which given type points.
    :return: List of Implementation objects.
    """
    if weakly and interface.identifier in self._implementations_cache and \
            isinstance(self._implementations_cache[interface.identifier]['weak'], list):
        return self._implementations_cache[interface.identifier]['weak']
    elif not weakly and interface.identifier in self._implementations_cache and \
            isinstance(self._implementations_cache[interface.identifier]['strict'], list):
        return self._implementations_cache[interface.identifier]['strict']

    if weakly:
        candidates = interface.declaration.weak_implementations
    else:
        candidates = [interface.declaration.implementations[name] for name in
                      sorted(interface.declaration.implementations.keys())]

    # Filter implementations with fixed interafces
    if len(candidates) > 0:
        candidates = [impl for impl in candidates
                      if not impl.fixed_interface or impl.fixed_interface == interface.identifier]

    if len(candidates) > 0:
        # Filter filter interfaces
        implementations = []
        for impl in candidates:
            cnts = self.resolve_containers(interface, interface.category)
            if len(impl.sequence) > 0 and len(cnts) > 0:
                for cnt in sorted(list(cnts.keys())):
                    cnt_intf = self.get_intf(cnt)
                    if isinstance(cnt_intf.declaration, Array) and cnt_intf.element_interface and \
                            interface.identifier == cnt_intf.element_interface.identifier:
                        implementations.append(impl)
                        break
                    elif (isinstance(cnt_intf.declaration, Structure) or isinstance(cnt_intf.declaration, Union)) \
                            and interface in cnt_intf.field_interfaces.values():
                        field = list(cnt_intf.field_interfaces.keys())[list(cnt_intf.field_interfaces.values()).
                            index(interface)]

                        if field == impl.sequence[-1]:
                            base_value_match = not impl.base_value or \
                                               (impl.base_value and
                                                len([i for i in self.implementations(cnt_intf)
                                                     if (i.base_value and i.base_value == impl.base_value)
                                                     or (i.value and i.value == impl.base_value)]) > 0)
                            if base_value_match:
                                implementations.append(impl)
                                break
            elif len(impl.sequence) == 0 and len(cnts) == 0:
                implementations.append(impl)

        candidates = implementations

    # Save results
    if interface.identifier not in self._implementations_cache:
        self._implementations_cache[interface.identifier] = {'weak': None, 'strict': None}

    # Sort results before saving
    candidates = sorted(candidates, key=lambda i: i.identifier)

    if weakly and not self._implementations_cache[interface.identifier]['weak']:
        self._implementations_cache[interface.identifier]['weak'] = candidates
    elif not weakly and not self._implementations_cache[interface.identifier]['strict']:
        self._implementations_cache[interface.identifier]['strict'] = candidates
    return candidates


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


class Callback(FunctionInterface):

    def __init__(self, category, identifier, manually_specified=False):
        super(Callback, self).__init__(category, identifier, manually_specified)
        self.called = False
        self.interrupt_context = False


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
from core.vtg.emg.common.c.types import Function, Pointer, InterfaceReference, import_declaration


def compare(self, target):
    # Apply all transformations
    if self.clean_declaration and target.clean_declaration:
        a = import_declaration(self.to_string('a', typedef='all'))
        b = import_declaration(target.to_string('a', typedef='all'))
    else:
        a = self
        b = target

    if type(a) is type(b):
        if a.identifier == b.identifier:
            return True
        elif a.identifier == 'void *' or b.identifier == 'void *':
            return True
    return False

def add_implementation(self, value, path, root_type, root_value, root_sequence, static=False):
    new = Implementation(self, value, path, root_type, root_value, root_sequence, static)
    if new.identifier not in self.implementations:
        self.implementations[new.identifier] = new
    return new

 @property
    def weak_implementations(self):
        if isinstance(self, Pointer):
            return list(self.implementations.values()) + list(self.points.implementations.values())
        else:
            return list(self.implementations.values()) + list(self.take_pointer.implementations.values())

class Function(Declaration):

    def __init__(self, ast):
        super(Function, self).__init__(ast)
        self.return_value = None
        self.parameters = []
        self.ret_typedef = None
        self.params_typedef = list()

        if 'specifiers' in self._ast['return value type'] and \
                'type specifier' in self._ast['return value type']['specifiers'] and \
                self._ast['return value type']['specifiers']['type specifier']['class'] == 'Primitive' and \
                self._ast['return value type']['specifiers']['type specifier']['name'] == 'void':
            self.return_value = None
        else:
            self.return_value, self.ret_typedef = import_declaration(None, self._ast['return value type'],
                                                                     track_typedef=True)
        for parameter in self._ast['declarator'][0]['function arguments']:
            if isinstance(parameter, str):
                self.parameters.append(parameter)
                self.params_typedef.append(None)
            else:
                param, typedef = import_declaration(None, parameter, track_typedef=True)
                self.parameters.append(param)
                self.params_typedef.append(typedef)

        if len(self.parameters) == 1 and isinstance(self.parameters[0], Primitive) and \
                self.parameters[0].pretty_name == 'void':
            self.parameters = []

    @property
    def clean_declaration(self):
        if not self.return_value.clean_declaration:
            return False
        for param in self.parameters:
            if not isinstance(param, str) and not param.clean_declaration:
                return False
        return True


class InterfaceReference(Declaration):

    def __init__(self, ast):
        # Superclass init intentionally missed
        self._ast = ast
        self._identifier = None
        self.parents = []
        self.typedef = None

    @property
    def category(self):
        return self._ast['specifiers']['category']

    @property
    def short_identifier(self):
        return self._ast['specifiers']['identifier']

    @property
    def interface(self):
        return "{}.{}".format(self.category, self.short_identifier)

    @property
    def pointer(self):
        return self._ast['specifiers']['pointer']

    def _to_string(self, replacement, typedef='none', scope=None):
        if self.pointer:
            ptr = '*'
        else:
            ptr = ''

        if replacement == '':
            return '{}%{}%'.format(ptr, self.interface)
        else:
            return '{}%{}% {}'.format(ptr, self.interface, replacement)


def import_declaration(signature, ast=None, track_typedef=False):
    global __type_collection
    global _typedefs
    typedef = None

    if not ast:
        try:
            ast = parse_declaration(signature)
        except:
            raise ValueError("Cannot parse signature: {}".format(signature))

    if 'declarator' not in ast or ('declarator' in ast and len(ast['declarator']) == 0):
        if 'specifiers' in ast and 'category' in ast['specifiers'] and 'identifier' in ast['specifiers']:
            ret = InterfaceReference(ast)
        elif 'specifiers' in ast and ast['specifiers'] == '$':
            ret = UndefinedReference(ast)
        elif 'specifiers' in ast and 'type specifier' in ast['specifiers'] and \
                ast['specifiers']['type specifier']['class'] == 'typedef' and \
                ast['specifiers']['type specifier']['name'] in _typedefs:
            ret = import_declaration(None, copy.deepcopy(_typedefs[ast['specifiers']['type specifier']['name']][0]))
            ret.typedef = ast['specifiers']['type specifier']['name']
            typedef = ret.typedef
        elif 'specifiers' in ast and 'type specifier' in ast['specifiers'] and \
                ast['specifiers']['type specifier']['class'] == 'structure':
            ret = Structure(ast)
        elif 'specifiers' in ast and 'type specifier' in ast['specifiers'] and \
                ast['specifiers']['type specifier']['class'] == 'enum':
            ret = Enum(ast)
        elif 'specifiers' in ast and 'type specifier' in ast['specifiers'] and \
                ast['specifiers']['type specifier']['class'] == 'union':
            ret = Union(ast)
        else:
            ret = Primitive(ast)
    else:
        if len(ast['declarator']) == 1 and \
                ('pointer' not in ast['declarator'][-1] or ast['declarator'][-1]['pointer'] == 0) and \
                ('arrays' not in ast['declarator'][-1] or len(ast['declarator'][-1]['arrays']) == 0):
            if 'specifiers' not in ast:
                ret = Function(ast)
            else:
                if ast['specifiers']['type specifier']['class'] == 'structure':
                    ret = Structure(ast)
                elif ast['specifiers']['type specifier']['class'] == 'enum':
                    ret = Enum(ast)
                elif ast['specifiers']['type specifier']['class'] == 'union':
                    ret = Union(ast)
                elif ast['specifiers']['type specifier']['class'] == 'typedef' and \
                        ast['specifiers']['type specifier']['name'] in _typedefs:
                    ret = import_declaration(None,
                                             copy.deepcopy(_typedefs[ast['specifiers']['type specifier']['name']][0]))
                    ret.typedef = ast['specifiers']['type specifier']['name']
                    typedef = ret.typedef
                else:
                    ret = Primitive(ast)
        elif 'arrays' in ast['declarator'][-1] and len(ast['declarator'][-1]['arrays']) > 0:
            ret = Array(ast)
            if track_typedef and ret.element.typedef:
                typedef = ret.element.typedef
        elif 'pointer' not in ast['declarator'][-1] or ast['declarator'][-1]['pointer'] > 0:
            ret = Pointer(ast)
            if track_typedef and ret.points.typedef:
                typedef = ret.points.typedef
        else:
            raise NotImplementedError

    if ret.identifier not in __type_collection:
        __type_collection[ret.identifier] = ret
    else:
        if ret.typedef:
            __type_collection[ret.identifier].typedef = ret.typedef
        if isinstance(ret, Function):
            if ret.ret_typedef and not __type_collection[ret.identifier].ret_typedef:
                __type_collection[ret.identifier].ret_typedef = ret.ret_typedef
            for index, pt in enumerate(__type_collection[ret.identifier].params_typedef):
                if not pt and ret.params_typedef[index]:
                    __type_collection[ret.identifier].params_typedef[index] = ret.params_typedef[index]
        ret = __type_collection[ret.identifier]

    if not track_typedef:
        return ret
    else:
        return ret, typedef


class Implementation:

    def __init__(self, declaration, value, file, base_container=None, base_value=None, sequence=None, static=False):
        self.base_container = base_container
        self.base_value = base_value
        self.value = value
        self.file = file
        self.sequence = sequence
        self.is_static = static
        self.identifier = str([value, file, base_value, sequence])
        self.fixed_interface = None
        self.declaration = declaration

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


def refine_declaration(interfaces, declaration):
    global __type_collection

    if declaration.clean_declaration:
        raise ValueError('Cannot clean already cleaned declaration')

    if isinstance(declaration, UndefinedReference):
        return None
    elif isinstance(declaration, InterfaceReference):
        if declaration.interface in interfaces and \
                interfaces[declaration.interface].declaration.clean_declaration:
            if declaration.pointer:
                return interfaces[declaration.interface].declaration.take_pointer
            else:
                return interfaces[declaration.interface].declaration
        else:
            return None
    elif isinstance(declaration, Function):
        refinement = False
        new = copy.deepcopy(declaration)

        # Refine the same object
        if new.return_value and not new.return_value.clean_declaration:
            rv = refine_declaration(interfaces, new.return_value)
            if rv:
                new.return_value = rv
                refinement = True

        for index in range(len(new.parameters)):
            if type(new.parameters[index]) is not str and \
                    not new.parameters[index].clean_declaration:
                pr = refine_declaration(interfaces, new.parameters[index])
                if pr:
                    new.parameters[index] = pr
                    refinement = True

        # Update identifier
        if refinement and new.identifier in __type_collection:
            if new.ret_typedef and not __type_collection[new.identifier].ret_typedef:
                __type_collection[new.identifier].ret_typedef = new.ret_typedef
            for index, pt in enumerate(__type_collection[new.identifier].params_typedef):
                if not pt and new.params_typedef[index]:
                    __type_collection[new.identifier].params_typedef[index] = new.params_typedef[index]
            new = __type_collection[new.identifier]
        elif refinement:
            __type_collection[new.identifier] = new

        if refinement:
            return new
        else:
            return None
    elif isinstance(declaration, Pointer) and isinstance(declaration.points, Function):
        refined = refine_declaration(interfaces, declaration.points)
        if refined:
            ptr = refined.take_pointer
            if ptr.identifier in __type_collection:
                ptr = __type_collection[ptr.identifier]
            else:
                __type_collection[ptr.identifier] = ptr

            return ptr
        else:
            return None
    else:
        raise ValueError('Cannot clean a declaration which is not a function or an interface reference')


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
            if isinstance(self_declaration.return_value, InterfaceReference) and \
                    self_declaration.return_value.pointer:
                self.rv_interface.update_declaration(declaration.return_value.points)
            else:
                self.rv_interface.update_declaration(declaration.return_value)

        for index in range(len(self_declaration.parameters)):
            p_declaration = declaration.parameters[index]

            if len(self.param_interfaces) > index and self.param_interfaces[index]:
                if isinstance(self_declaration.parameters[index], InterfaceReference) and \
                        self_declaration.parameters[index].pointer:
                    self.param_interfaces[index].update_declaration(p_declaration.points)
                else:
                    self.param_interfaces[index].update_declaration(p_declaration)

        super(FunctionInterface, self).update_declaration(declaration)


class SourceFunction(FunctionInterface):

    def __init__(self, identifier, raw_declaration):
        super(SourceFunction, self).__init__(None, identifier, False)
        self.identifier = identifier
        self.calls = dict()
        self.called_at = dict()
        self.declaration_files = set()
        self.definition_file = None
        self.raw_declaration = raw_declaration
        self.static = False

        self.declaration = import_declaration(raw_declaration)

    @property
    def files_called_at(self):
        return self.called_at.keys()

    def call_function(self, func, path):
        if path not in self.calls:
            self.calls[path] = {func}
        else:
            self.calls[path].add(func)

    def add_call(self, func, path):
        if path not in self.called_at:
            self.called_at[path] = {func}
        else:
            self.called_at[path].add(func)


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


class Callback(FunctionInterface):

    def __init__(self, category, identifier, manually_specified=False):
        super(Callback, self).__init__(category, identifier, manually_specified)
        self.called = False
        self.interrupt_context = False