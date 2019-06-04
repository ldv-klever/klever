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

import copy
import re

from core.vtg.emg.common.c.types.typeParser import parse_declaration

_type_collection = {}
_noname_identifier = 0
_typedefs = {}


def _new_identifier():
    global _noname_identifier

    _noname_identifier += 1
    return _noname_identifier


def is_not_null_function(declaration, value):
    """
    Check that the value for given function or function pointer is not Null. For other types it returns false.

    :param declaration: Declaration
    :param value: Value string.
    :return: False if it is a function or function pointer and the value is null and False otherwise.
    """
    check = re.compile('[\s]*[(]?[\s]*0[\s]*[)]?[\s]*')
    if (isinstance(declaration, Function) or
       (isinstance(declaration, Pointer) and isinstance(declaration.points, Function))) and check.fullmatch(value):
        return False
    else:
        return True


def extract_name(declaration):
    """
    Extract name from the declarator of the declaration.

    :param declaration: Declaration string.
    :return: Declarator string or None if there is no declarator.
    """
    try:
        ast = parse_declaration(declaration)
    except Exception:
        raise ValueError("Cannot parse declaration: {}".format(declaration))

    if 'declarator' in ast and len(ast['declarator']) > 0 and 'identifier' in ast['declarator'][-1] and \
            ast['declarator'][-1]['identifier']:
        return ast['declarator'][-1]['identifier']
    else:
        return None


def import_typedefs(tds, dependencies):
    """
    Get collection from source analysis with typedefs and import them into collection.

    :param tds: Raw dictionary from SA: {'file': [typedef definitions]}
    :param dependencies: Dictionary with {dep->{C files}} structure.
    :return: None
    """
    global _typedefs
    global _type_collection

    def add_file(typeast, typename, filename):
        if name in _typedefs:
            _typedefs[typename][1].add(filename)
        else:
            _typedefs[typename] = [typeast, {filename}]

    candidates = []
    for tp in (t for t in _type_collection if isinstance(_type_collection[t], Primitive)):
        candidates.append(tp)

    for dep in tds:
        for decl in tds[dep]:
            ast = parse_declaration(decl)
            name = ast['declarator'][-1]['identifier']

            add_file(ast, name, dep)
            for file in dependencies.get(dep, list()):
                add_file(ast, name, file)

    for tp in candidates:
        if tp in _typedefs:
            _typedefs[tp][1].add('common')


def is_static(declaration):
    """
    Check that given declaration is static.

    :param declaration: Declaration string.
    :return: True if it static and False otherwise.
    """
    def check(a):
        return 'specifiers' in a and 'specifiers' in a['specifiers'] and 'static' in a['specifiers']['specifiers']

    ast = parse_declaration(declaration)
    if ('return value type' in ast and check(ast['return value type'])) or check(ast):
        return True
    else:
        return False


def reduce_level(ast):
    """
    The function removes from the abstract syntax tree a declaration current level (pointer or array). For instance it
    makes from AST of 'int *a' it makes AST for 'int a'.

    :param ast: Current abstract syntax tree.
    :return: Abstract syntax tree for the pointer or an array element type.
    """
    if len(ast['declarator']) > 1 and \
            ('pointer' not in ast['declarator'][-1] or ast['declarator'][-1]['pointer'] == 0) and \
            ('arrays' not in ast['declarator'][-1] or len(ast['declarator'][-1]['arrays']) == 0) and \
            'function arguments' not in ast['declarator'][-1]:
        ast['declarator'].pop()
    return ast


def import_declaration(declaration, ast=None, track_typedef=False):
    """
    Import into the declaration collection a new declaration. The function either get an existing object from a cache
    or creates a new object for the given declaration.

    :param declaration: Declaration string.
    :param ast: Corresponding abstract syntax tree if it is known.
    :param track_typedef: Specify flag that at parsing the declaration it is allowed to match typedefs.
    :return: Declaration object.
    """
    global _type_collection
    global _typedefs
    typedef = None

    if not ast:
        try:
            ast = parse_declaration(declaration)
        except Exception:
            raise ValueError("Cannot parse declaration: {}".format(declaration))

    if 'declarator' not in ast or ('declarator' in ast and len(ast['declarator']) == 0):
        if 'specifiers' in ast and 'type specifier' in ast['specifiers'] and \
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
        elif 'pointer' in ast['declarator'][-1] and ast['declarator'][-1]['pointer'] > 0:
            ret = Pointer(ast)
            if track_typedef and ret.points.typedef:
                typedef = ret.points.typedef
        else:
            raise NotImplementedError

    if ret.identifier not in _type_collection:
        _type_collection[ret.identifier] = ret
    else:
        if ret.typedef:
            _type_collection[ret.identifier].typedef = ret.typedef
        if isinstance(ret, Function):
            if ret.ret_typedef and not _type_collection[ret.identifier].ret_typedef:
                _type_collection[ret.identifier].ret_typedef = ret.ret_typedef
            for index, pt in enumerate(_type_collection[ret.identifier].params_typedef):
                if not pt and ret.params_typedef[index]:
                    _type_collection[ret.identifier].params_typedef[index] = ret.params_typedef[index]
        ret = _type_collection[ret.identifier]

    if not track_typedef:
        return ret
    else:
        return ret, typedef


def _take_pointer(exp, tp):
    if tp is Array or tp is Function:
        exp = '(*' + exp + ')'
    else:
        exp = '*' + exp
    return exp


def _add_parent(declaration, parent):
    global _type_collection

    if parent.identifier in _type_collection:
        parent = _type_collection[parent.identifier]
    else:
        _type_collection[parent.identifier] = parent

    if parent.identifier not in (p.identifier for p in declaration.parents):
        declaration.parents.append(parent)


class Declaration:
    """Base type to represent C declarations."""

    def __init__(self, ast):
        self._ast = ast
        self.parents = []
        self.typedef = None

    @property
    def take_pointer(self):
        """
        Return a Declaration object which corresponds to the pointer to this type.

        :return: Declaration object.
        """
        pointer_declaration = self.to_string('a', True)
        return import_declaration(pointer_declaration)

    @property
    def identifier(self):
        """
        Identifier of the declaration. Identifier is a declaration string without a declarator and with all known
        typdefs resolved into basic types.

        :return: String.
        """
        return self.to_string(declarator='')

    @property
    def pretty_name(self):
        """
        This is an identifier string which can be used in variable names. It is not implemented for the base type.

        :return: String.
        """
        raise NotImplementedError

    def add_parent(self, parent):
        """
        Specify that the given declaration object contains this one (in terms of structure fields or array alements).

        :param parent: Declaration object.
        :return: None.
        """
        _add_parent(self, parent)

    def compare(self, target):
        """
        Compare this and given declaration. If they correspond to the same C declaration then return True. For void
        pointers the function returns True for any pointer.

        :param target: Declaration object.
        :return: True if declarations are equal.
        """
        # Apply all transformations
        if type(self) is type(target):
            if self.identifier == target.identifier:
                return True
            elif self.identifier == 'void *' or target.identifier == 'void *':
                return True
        return False

    def pointer_alias(self, alias):
        """
        Compare this type with the given one and return None or declaration object which is a pointer to the another
        one in this pair.

        :param alias: Declaration object.
        :return: Declaration object.
        """
        if isinstance(self, Pointer) and self.points.compare(alias):
            return self
        elif isinstance(alias, Pointer) and self.compare(alias.points):
            return alias

        return None

    def nameless_type(self):
        """
        Return True if this declaration has no named type (for structures, unions).

        :return: Bool.
        """
        queue = [self]
        ret = True

        while len(queue) > 0:
            tp = queue.pop()

            if isinstance(tp, Array):
                queue.append(tp.element)
            elif isinstance(tp, Pointer):
                queue.append(tp.points)
            elif (isinstance(tp, Structure) or isinstance(tp, Union) or isinstance(tp, Enum)) and not tp.name:
                ret = False
                break

        return ret

    def to_string(self, declarator='', pointer=False, typedef='none', scope=None):
        """
        Print declaration as a string with the given declarator.

        :param declarator: Declarator string.
        :param pointer: Return pointer to this type.
        :param typedef: Insert typedefs: 'none' - no typedefs, 'all' - all possible, 'complex_and_params' -
                        for function parameters.
        :param scope: File with the declaration to check visible typedefs.
        :return: String.
        """
        global _typedefs
        if pointer:
            declarator = _take_pointer(declarator, type(self))

        if isinstance(typedef, set) or isinstance(typedef, str):
            if self.typedef and (
                    (isinstance(typedef, set) and self.typedef in typedef) or
                    (
                        (isinstance(typedef, str) and typedef == 'all') or
                        typedef != 'none' and not self.nameless_type()
                     )) and \
                    (not scope or (self.typedef in _typedefs and
                                   len(_typedefs[self.typedef][1] & scope) > 0)):
                return "{} {}".format(self.typedef, declarator)
            else:
                return self._to_string(declarator, typedef=typedef, scope=scope)
        else:
            raise TypeError('Expect typedef flag to be set or str instead of {!r}'.format(type(typedef).__name__))

    def _to_string(self, replacement, typedef=None, scope=None):
        raise NotImplementedError


class Primitive(Declaration):
    """Class represents base build-in (non-complex) types (string, int) and complex typedef types."""

    def __init__(self, ast):
        super(Primitive, self).__init__(ast)

    @property
    def pretty_name(self):
        """
        This is an identifier string which can be used in variable names. For primitives it is a type itself with added
        specifiers like 'unsigned_int'.

        :return: String.
        """
        pn = self._ast['specifiers']['type specifier']['name']
        return pn.replace(' ', '_')

    def _to_string(self, replacement, typedef='none', scope=None):
        if replacement == '':
            return self._ast['specifiers']['type specifier']['name']
        else:
            return "{} {}".format(self._ast['specifiers']['type specifier']['name'], replacement)


class Enum(Declaration):
    """The class represents Enum types."""

    def __init__(self, ast):
        super(Enum, self).__init__(ast)
        self.enumerators = []

        if 'enumerators' in self._ast['specifiers']['type specifier']:
            self.enumerators = self._ast['specifiers']['type specifier']['enumerators']

    @property
    def name(self):
        """
        Return name of the Enum.

        :return: String
        """
        return self._ast['specifiers']['type specifier']['name']

    @property
    def pretty_name(self):
        """
        This is an identifier string which can be used in variable names. An example for the Enum 'enum_myenum'.

        :return: String.
        """
        return 'enum_{}'.format(self.name)

    def _to_string(self, replacement, typedef='none', scope=None):
        if not self.name:
            name = '{ ' + ', '.join(self.enumerators) + ' }'
        else:
            name = self.name

        if replacement == '':
            return "enum {}".format(name)
        else:
            return "enum {} {}".format(name, replacement)


class Function(Declaration):
    """The class represents Function types."""

    def __init__(self, ast):
        super(Function, self).__init__(ast)
        self.return_value = None
        self.parameters = []
        self.ret_typedef = None
        self.params_typedef = list()

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
    def pretty_name(self):
        """
        This is an identifier string which can be used in variable names. For function it prints just an expression with
        a unique numerical identifier like 'func_543'.

        :return: String.
        """
        global _type_collection

        key = _new_identifier()
        return 'func_{}'.format(key)

    def _to_string(self, replacement, typedef='none', scope=None, with_args=False):
        def filtered_typedef_param(available):
            if isinstance(typedef, set):
                return {available}
            elif available and typedef == 'complex_and_params':
                return {available}
            else:
                return typedef

        if typedef == 'complex_and_params' and not scope:
            scope = {'common'}

        if len(self.parameters) == 0:
            replacement += '(void)'
        else:
            parameter_declarations = []
            for index, param in enumerate(self.parameters):
                if type(param) is str:
                    parameter_declarations.append(param)
                else:
                    if with_args:
                        declarator = 'arg{}'.format(index)
                    else:
                        declarator = ''
                    expr = param.to_string(declarator, typedef=filtered_typedef_param(self.params_typedef[index]),
                                           scope=scope)
                    parameter_declarations.append(expr)
            replacement += '(' + ', '.join(parameter_declarations) + ')'

        if self.return_value:
            replacement = self.return_value.to_string(replacement, typedef=filtered_typedef_param(self.ret_typedef),
                                                      scope=scope)
        else:
            replacement = 'void {}'.format(replacement)
        return replacement

    def define_with_args(self, replacement, typedef='none', scope=None):
        """
        Prints function dewclaration with arguments given with declarators. As argument declarators it prints
        expressions like 'arg1', 'arg2', ....

        :param replacement: Function name or any other declarator.
        :param typedef: Insert typedefs: 'none' - no typedefs, 'all' - all possible, 'complex_and_params' -
                        for function parameters.
        :param scope: File with the declaration to check visible typedefs.
        :return: String.
        """
        return self._to_string(replacement, typedef, scope, with_args=True)


class Structure(Declaration):
    """THe class represents Structure types."""

    def __init__(self, ast):
        super(Structure, self).__init__(ast)
        self.fields = {}

        if 'fields' in self._ast['specifiers']['type specifier']:
            for declaration in sorted([d for d in self._ast['specifiers']['type specifier']['fields']
                                       if d['declarator'][-1]['identifier'] is not None],
                                      key=lambda decl: str(decl['declarator'][-1]['identifier'])):
                name = declaration['declarator'][-1]['identifier']
                if name:
                    self.fields[name] = import_declaration(None, declaration)

    @property
    def name(self):
        """
        Return structure name.

        :return: String.
        """
        return self._ast['specifiers']['type specifier']['name']

    @property
    def pretty_name(self):
        """
        This is an identifier string which can be used in variable names. Prints a name based on the structure name like
        'struct_usb_driver' or for nameless structures also numerical identifier like 'struct_noname_343'.

        :return: String.
        """
        if self.name:
            return 'struct_{}'.format(self.name)
        else:
            global _type_collection

            key = _new_identifier()
            return 'struct_noname_{}'.format(key)

    def contains(self, target):
        """
        Check True if target declaration is used for one of structure fields and False otherwise.

        :param target: Declaration type.
        :return: Bool.
        """
        return [field for field in self.fields.keys() if self.fields[field].compare(target)]

    def weak_contains(self, target):
        """
        Check True if target declaration is used for one of structure fields and False otherwise. In this function
        comparison with argument types also accepts pointer to the type of the interest and arrays.

        :param target: Declaration type.
        :return: Bool.
        """
        return [field for field in self.fields.keys() if self.fields[field].compare(target) or
                self.fields[field].pointer_alias(target)]

    def _to_string(self, replacement, typedef='none', scope=None):
        if not self.name:
            name = '{' + \
                   ('; '.join([self.fields[field].to_string(field, typedef=typedef, scope=scope)
                               for field in self.fields.keys()]) +
                    '; ' if len(self.fields) > 0 else '') \
                   + '}'
        else:
            name = self.name

        if replacement == '':
            return "struct {}".format(name)
        else:
            return "struct {} {}".format(name, replacement)


class Union(Declaration):
    """The class represents union types."""

    def __init__(self, ast):
        super(Union, self).__init__(ast)
        self.fields = {}

        if 'fields' in self._ast['specifiers']['type specifier']:
            for declaration in sorted(self._ast['specifiers']['type specifier']['fields'],
                                      key=lambda decl: str(decl['declarator'][-1]['identifier'])):
                name = declaration['declarator'][-1]['identifier']
                if name:
                    self.fields[name] = import_declaration(None, declaration)

    @property
    def name(self):
        """
        Return union name.

        :return: String.
        """
        return self._ast['specifiers']['type specifier']['name']

    @property
    def pretty_name(self):
        """
        This is an identifier string which can be used in variable names. Prints a name based on the union name like
        'union_my_union' or for nameless unions also numerical identifier like 'union_3454'.

        :return: String.
        """
        if self._ast['specifiers']['type specifier']['name']:
            return 'union_{}'.format(self.name)
        else:
            global _type_collection

            key = _new_identifier()
            return 'union_noname_{}'.format(key)

    def contains(self, target):
        """
        Check True if target declaration is used for one of union fields and False otherwise.

        :param target: Declaration type.
        :return: Bool.
        """
        return [field for field in self.fields.keys() if self.fields[field].compare(target)]

    def weak_contains(self, target):
        """
        Check True if target declaration is used for one of union fields and False otherwise. In this function
        comparison with argument types also accepts pointer to the type of the interest and arrays.

        :param target: Declaration type.
        :return: Bool.
        """
        return [field for field in self.fields.keys() if self.fields[field].compare(target) or
                self.fields[field].pointer_alias(target)]

    def _to_string(self, replacement, typedef='none', scope=None):
        if not self.name:
            name = '{ ' + '; '.join([self.fields[field].to_string(field, typedef=typedef, scope=scope)
                                     for field in sorted(self.fields.keys())]) + \
                   '; ' + ' }'
        else:
            name = self.name

        if replacement == '':
            return "union {}".format(name)
        else:
            return "union {} {}".format(name, replacement)


class Array(Declaration):
    """The class represent array types."""

    def __init__(self, ast):
        super(Array, self).__init__(ast)
        self.element = None

        array = ast['declarator'][-1]['arrays'].pop()
        self.size = array['size']
        ast = reduce_level(ast)
        self.element = import_declaration(None, ast)
        self.element.add_parent(self)

    @property
    def pretty_name(self):
        """
        This is an identifier string which can be used in variable names. Prints a name based on the pretty name of
        the element type. For instance for 'int []' it is 'int_array'.

        :return: String.
        """
        return '{}_array'.format(self.element.pretty_name)

    def contains(self, target):
        """
        Check True if target declaration is used as the array element type.

        :param target: Declaration type.
        :return: Bool.
        """
        if self.element.compare(target):
            return True
        else:
            return False

    def weak_contains(self, target):
        """
        Check True if target declaration is used as the array element type. The comparison also accepts pointers and
        arrays (arrays of arrays).

        :param target: Declaration type.
        :return: Bool.
        """
        if self.element.compare(target) or self.element.pointer_alias(target):
            return True
        else:
            return False

    def _to_string(self, replacement, typedef='none', scope=None):
        if self.size:
            size = self.size
        else:
            size = ''
        replacement += '[{}]'.format(size)
        return self.element.to_string(replacement, typedef=typedef, scope=scope)


class Pointer(Declaration):
    """The class represents pointers."""

    def __init__(self, ast):
        super(Pointer, self).__init__(ast)

        ast['declarator'][-1]['pointer'] -= 1
        ast = reduce_level(ast)
        self.points = import_declaration(None, ast)
        self.points.add_parent(self)

    def _to_string(self, replacement, typedef='none', scope=None):
        replacement = _take_pointer(replacement, type(self.points))

        return self.points.to_string(replacement, typedef=typedef, scope=scope)

    @property
    def pretty_name(self):
        """
        This is an identifier string which can be used in variable names. Prints a name based on the type to which this
        type points. For instance for 'int *' it is 'int_ptr'.

        :return: String.
        """
        return '{}_ptr'.format(self.points.pretty_name)
