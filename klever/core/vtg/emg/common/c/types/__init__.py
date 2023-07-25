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

import re
import copy
import json
import sortedcontainers

from klever.core.vtg.emg.common.c.types.typeParser import parse_declaration

_type_collection = sortedcontainers.SortedDict()
_typedefs = sortedcontainers.SortedDict()
_noname_identifier = 0


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
    check = re.compile(r'[\s]*[(]?[\s]*0[\s]*[)]?[\s]*')
    if (isinstance(declaration, Function) or
        (isinstance(declaration, Pointer) and isinstance(declaration.points, Function))) and check.fullmatch(value):
        return False

    return True


def extract_name(declaration):
    """
    Extract name from the declarator of the declaration.

    :param declaration: Declaration string or ast.
    :return: Declarator string or None if there is no declarator.
    """
    if isinstance(declaration, str):
        try:
            ast = parse_declaration(declaration)
        except Exception as e:
            raise ValueError("Cannot parse declaration: {!r}".format(declaration)) from e
    else:
        ast = declaration

    if 'declarator' in ast and len(ast['declarator']) > 0 and 'identifier' in ast['declarator'][-1] and \
            ast['declarator'][-1]['identifier']:
        return ast['declarator'][-1]['identifier']

    return None


def import_typedefs(tds, dependencies):
    """
    Get collection from source analysis with typedefs and import them into collection.

    :param tds: Raw dictionary from SA: {'file': [typedef definitions]}
    :param dependencies: Dictionary with {dep->{C files}} structure.
    :return: None
    """

    def add_file(typeast, typename, filename):
        if name in _typedefs:
            _typedefs[typename][1].add(filename)
        else:
            _typedefs[typename] = [typeast, {filename}]

    candidates = [t for t in _type_collection if isinstance(_type_collection[t], Primitive)]
    for dep, decl in ((dep, decl) for dep in sorted(tds.keys()) for decl in tds[dep]):
        try:
            ast = parse_declaration(decl)
        except Exception as e:
            raise ValueError(f"Cannot parse typedef declaration: '{decl}'") from e
        name = extract_name(decl)

        add_file(ast, name, dep)
        for file in dependencies.get(dep, []):
            add_file(ast, name, file)

    for tp in candidates:
        if tp in _typedefs:
            _typedefs[tp][1].add('common')


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
    typedef = None

    if not ast:
        try:
            ast = parse_declaration(declaration)
        except Exception as e:
            raise ValueError("Cannot parse declaration: {!r}".format(declaration)) from e

    if not ast.get('declarator', []):
        ast_class = ast.get('specifiers', {}).get('type specifier', {}).get('class')

        if ast_class == 'typedef' and ast['specifiers']['type specifier']['name'] in _typedefs:
            ret = import_declaration(None, copy.deepcopy(_typedefs[ast['specifiers']['type specifier']['name']][0]))
            ret.typedef = ast['specifiers']['type specifier']['name']
            typedef = ret.typedef
        elif ast_class == 'structure':
            ret = Structure(ast)
        elif ast_class == 'enum':
            ret = Enum(ast)
        elif ast_class == 'union':
            ret = Union(ast)
        else:
            ret = Primitive(ast)
    else:
        if len(ast['declarator']) == 1 and not ast['declarator'][-1].get('pointer') and \
                not ast['declarator'][-1].get('arrays'):
            if 'specifiers' not in ast:
                ret = Function(ast)
            else:
                ast_type = ast['specifiers']['type specifier']['class']
                if ast_type == 'structure':
                    ret = Structure(ast)
                elif ast_type == 'enum':
                    ret = Enum(ast)
                elif ast_type == 'union':
                    ret = Union(ast)
                elif ast_type == 'typedef' and ast['specifiers']['type specifier']['name'] in _typedefs:
                    type_name = ast['specifiers']['type specifier']['name']
                    ret = import_declaration(None, copy.deepcopy(_typedefs[type_name][0]))
                    ret.typedef = type_name
                    typedef = ret.typedef
                else:
                    ret = Primitive(ast)
        elif ast['declarator'][-1].get('arrays'):
            ret = Array(ast)
            if track_typedef and ret.element.typedef:
                typedef = ret.element.typedef
        elif ast['declarator'][-1].get('pointer'):
            ret = Pointer(ast)
            if track_typedef and ret.points.typedef:
                typedef = ret.points.typedef
        else:
            raise NotImplementedError

    if ret not in _type_collection:
        _type_collection[ret] = ret
    else:
        if ret.typedef:
            _type_collection[ret].typedef = ret.typedef
        if isinstance(ret, Function):
            if ret.ret_typedef and not _type_collection[ret].ret_typedef:
                _type_collection[ret].ret_typedef = ret.ret_typedef
            for index, pt in enumerate(_type_collection[ret].params_typedef):
                if not pt and len(ret.params_typedef) > index and ret.params_typedef[index]:
                    _type_collection[ret].params_typedef[index] = ret.params_typedef[index]
        ret = _type_collection[ret]

    if not track_typedef:
        return ret

    return ret, typedef


def dump_types(file_name):
    with open(file_name, 'w') as fp:
        json.dump({str(k): v.dump() for k, v in _type_collection.items()}, fp, indent=2, sort_keys=True)


def _take_pointer(exp, tp):
    if isinstance(tp, (Array, Function)):
        return '(*' + exp + ')'

    return '*' + exp


def _add_parent(declaration, parent):
    parent = _type_collection.setdefault(parent, parent)
    if str(parent) not in (str(e) for e in declaration.parents):
        declaration.parents.append(parent)


class Declaration:
    """Base type to represent C declarations."""

    def __init__(self, ast):
        self._ast = ast
        self.parents = []
        self.typedef = None
        self._str = None
        self._str_no_specifiers = None

    def __str__(self):
        if not self._str:
            self._str = self.to_string(declarator='')
        return self._str

    def __hash__(self):
        return hash(self.to_string(declarator='', qualifiers=True))

    def __eq__(self, other):
        if isinstance(other, Declaration):
            # Apply all transformations
            if type(self) is type(other):
                if str(self) == str(other) or self.str_without_specifiers == other.str_without_specifiers:
                    return True
                if self.str_without_specifiers == 'void *' or other.str_without_specifiers == 'void *':
                    return True
                if isinstance(self, Pointer):
                    return self.points == other.points  # pylint: disable=no-member
                if isinstance(self, Array):
                    # Compare children to avoid comparing sizes
                    return self.element == other.element  # pylint: disable=no-member
                if isinstance(self, Function):
                    # pylint: disable=no-member
                    return self.return_value == other.return_value and len(self.parameters) == len(other.parameters) and \
                        all(x == y for x, y in zip(self.parameters, other.parameters))  # pylint: disable=no-member
            return False
        if isinstance(other, str):
            me = self.str_without_specifiers
            return me == other or str(me) == other
        return other.__eq__(self)

    def __lt__(self, other):
        return str(self) < str(other)

    @property
    def str_without_specifiers(self):
        if not self._str_no_specifiers:
            self._str_no_specifiers = self.to_string('', specifiers=False)
        return self._str_no_specifiers

    @property
    def take_pointer(self):
        """
        Return a Declaration object which corresponds to the pointer to this type.

        :return: Declaration object.
        """
        pointer_declaration = self.to_string('a', pointer=True, specifiers=True, qualifiers=True)
        return import_declaration(pointer_declaration)

    @property
    def pretty_name(self):
        """
        This is an identifier string which can be used in variable names. It is not implemented for the base type.

        :return: String.
        """
        raise NotImplementedError

    @property
    def static(self):
        """
        Check that this is static variable or function declaration.

        :return: Bool
        """
        specifiers = self._ast.get('specifiers')
        if specifiers and isinstance(specifiers, list):
            return 'static' in specifiers
        if specifiers and isinstance(specifiers, dict):
            return 'static' in specifiers.get('specifiers', [])

        return False

    def add_parent(self, parent):
        """
        Specify that the given declaration object contains this one (in terms of structure fields or array elements).

        :param parent: Declaration object.
        :return: None.
        """
        _add_parent(self, parent)

    def pointer_alias(self, alias):
        """
        Compare this type with the given one and return None or declaration object which is a pointer to the another
        one in this pair.

        :param alias: Declaration object.
        :return: Declaration object.
        """
        if isinstance(self, Pointer) and self.points == alias:   # pylint: disable=no-member
            return self
        if isinstance(alias, Pointer) and self == alias.points:
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
            elif isinstance(tp, (Structure, Union, Enum)) and not tp.name:
                ret = False
                break

        return ret

    def dump(self):
        """
        Dump various versions of the object string representation.

        :return: Dictionary with string keys and values.
        """
        return {
            'main': str(self),
            'basic': self.to_string('x', qualifiers=True),
            'with_qualifiers': self.to_string('x'),
            'typedef_all': self.to_string('x', typedef='all'),
            'typedef_none': self.to_string('x', typedef='none'),
            'typedef_mixed': self.to_string('x', typedef='complex_and_params')
        }

    def to_string(self, declarator='', pointer=False, typedef='none', scope=None, specifiers=True, qualifiers=False):
        """
        Print declaration as a string with the given declarator.

        :param declarator: Declarator string.
        :param pointer: Return pointer to this type.
        :param typedef: Insert typedefs: 'none' - no typedefs, 'all' - all possible, 'complex_and_params' -
                        for function parameters.
        :param scope: File with the declaration to check visible typedefs.
        :return: String.
        """
        if pointer:
            declarator = _take_pointer(declarator, self)

        if isinstance(typedef, (sortedcontainers.SortedSet, set, str)):
            if self.typedef and (
                    ((isinstance(typedef, (set, sortedcontainers.SortedSet))) and
                     self.typedef in typedef) or
                    (
                            (isinstance(typedef, str) and typedef == 'all') or
                            typedef != 'none' and not self.nameless_type()
                    )) and \
                    (not scope or (self.typedef in _typedefs and
                                   len(_typedefs[self.typedef][1] & scope) > 0)):
                result = "{} {}".format(self.typedef, declarator)
            else:
                result = self._to_string(declarator, typedef=typedef, scope=scope, qualifiers=qualifiers)
        else:
            raise TypeError('Expect typedef flag to be set or str instead of {!r}'.format(type(typedef).__name__))

        if not isinstance(self, Pointer) and qualifiers and self._ast.get('specifiers', {}).get('qualifiers'):
            result = ' '.join(self._ast['specifiers']['qualifiers']) + ' ' + result
        if specifiers and self._ast.get('specifiers', {}).get('specifiers'):
            result = ' '.join(self._ast['specifiers']['specifiers']) + ' ' + result
        return result

    def _to_string(self, replacement, typedef='none', scope=None, with_args=False, qualifiers=False):
        raise NotImplementedError


class Primitive(Declaration):
    """Class represents base build-in (non-complex) types (string, int) and complex typedef types."""

    @property
    def pretty_name(self):
        """
        This is an identifier string which can be used in variable names. For primitives it is a type itself with added
        specifiers like 'unsigned_int'.

        :return: String.
        """
        pn = self._ast['specifiers']['type specifier']['name']
        return pn.replace(' ', '_')

    def _to_string(self, replacement, typedef='none', scope=None, with_args=False, qualifiers=False):
        if replacement == '':
            return self._ast['specifiers']['type specifier']['name']

        return "{} {}".format(self._ast['specifiers']['type specifier']['name'], replacement)


class Enum(Declaration):
    """The class represents Enum types."""

    def __init__(self, ast):
        super().__init__(ast)
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

    def _to_string(self, replacement, typedef='none', scope=None, with_args=False, qualifiers=False):
        if not self.name:
            name = '{ ' + ', '.join(self.enumerators) + ' }'
        else:
            name = self.name

        if replacement == '':
            return "enum {}".format(name)

        return "enum {} {}".format(name, replacement)


class Function(Declaration):
    """The class represents Function types."""

    def __init__(self, ast):
        super().__init__(ast)
        self.return_value = None
        self.parameters = []
        self.ret_typedef = None
        self.params_typedef = []

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
        key = _new_identifier()
        return 'func_{}'.format(key)

    @property
    def static(self):
        """
        Check that this is static function declaration.

        :return: Bool
        """
        return self.return_value.static

    def _to_string(self, replacement, typedef='none', scope=None, with_args=False, qualifiers=False):
        def filtered_typedef_param(available):
            if isinstance(typedef, (set, sortedcontainers.SortedSet)):
                return {available}
            if available and typedef == 'complex_and_params':
                return {available}
            return typedef

        if typedef == 'complex_and_params' and not scope:
            scope = {'common'}

        if len(self.parameters) == 0:
            replacement += '(void)'
        else:
            parameter_declarations = []
            for index, param in enumerate(self.parameters):
                if isinstance(param, str):
                    parameter_declarations.append(param)
                else:
                    if with_args:
                        declarator = 'arg{}'.format(index)
                    else:
                        declarator = ''
                    expr = param.to_string(declarator, typedef=filtered_typedef_param(self.params_typedef[index]),
                                           scope=scope, specifiers=False, qualifiers=qualifiers)
                    parameter_declarations.append(expr)
            replacement += '(' + ', '.join(parameter_declarations) + ')'

        if self.return_value:
            replacement = self.return_value.to_string(replacement, typedef=filtered_typedef_param(self.ret_typedef),
                                                      scope=scope, specifiers=False, qualifiers=qualifiers)
        else:
            replacement = 'void {}'.format(replacement)
        return replacement

    def define_with_args(self, replacement, typedef='none', scope=None):
        """
        Prints function declaration with arguments given with declarators. As argument declarators it prints
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
        super().__init__(ast)
        self.fields = sortedcontainers.SortedDict()

        if 'fields' in self._ast['specifiers']['type specifier']:
            # Need to preserve order despite parser implementation
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

        key = _new_identifier()
        return 'struct_noname_{}'.format(key)

    def contains(self, target):
        """
        Check True if target declaration is used for one of structure fields and False otherwise.

        :param target: Declaration type.
        :return: Bool.
        """
        return [field for field, decl in self.fields.items() if decl == target]

    def weak_contains(self, target):
        """
        Check True if target declaration is used for one of structure fields and False otherwise. In this function
        comparison with argument types also accepts pointer to the type of the interest and arrays.

        :param target: Declaration type.
        :return: Bool.
        """
        return [field for field, decl in self.fields.items() if decl == target or
                decl.pointer_alias(target)]

    def _to_string(self, replacement, typedef='none', scope=None, with_args=False, qualifiers=False):
        if not self.name:
            name = '{' + \
                   ('; '.join([item.to_string(field, typedef=typedef, scope=scope, specifiers=False,
                                              qualifiers=qualifiers)
                               for field, item in self.fields.items()]) +
                    '; ' if len(self.fields) > 0 else '') \
                   + '}'
        else:
            name = self.name

        if replacement == '':
            return "struct {}".format(name)

        return "struct {} {}".format(name, replacement)


class Union(Declaration):
    """The class represents union types."""

    def __init__(self, ast):
        super().__init__(ast)
        self.fields = sortedcontainers.SortedDict()

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

        key = _new_identifier()
        return 'union_noname_{}'.format(key)

    def contains(self, target):
        """
        Check True if target declaration is used for one of union fields and False otherwise.

        :param target: Declaration type.
        :return: Bool.
        """
        return [field for field, decl in self.fields.items() if decl == target]

    def weak_contains(self, target):
        """
        Check True if target declaration is used for one of union fields and False otherwise. In this function
        comparison with argument types also accepts pointer to the type of the interest and arrays.

        :param target: Declaration type.
        :return: Bool.
        """
        return [field for field, decl in self.fields.items() if decl == target or
                decl.pointer_alias(target)]

    def _to_string(self, replacement, typedef='none', scope=None, with_args=False, qualifiers=False):
        if not self.name:
            name = '{ ' + '; '.join([self.fields[field].to_string(field, typedef=typedef, scope=scope, specifiers=False,
                                                                  qualifiers=qualifiers)
                                     for field in sorted(self.fields.keys())]) + \
                   '; ' + ' }'
        else:
            name = self.name

        if replacement == '':
            return "union {}".format(name)

        return "union {} {}".format(name, replacement)


class Array(Declaration):
    """The class represent array types."""

    def __init__(self, ast):
        super().__init__(ast)
        self.element = None

        array = ast['declarator'][-1]['arrays'].pop(0)
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

    @property
    def static(self):
        return self.element.static

    def contains(self, target):
        """
        Check True if target declaration is used as the array element type.

        :param target: Declaration type.
        :return: Bool.
        """
        return self.element == target

    def weak_contains(self, target):
        """
        Check True if target declaration is used as the array element type. The comparison also accepts pointers and
        arrays (arrays of arrays).

        :param target: Declaration type.
        :return: Bool.
        """
        return self.element == target or self.element.pointer_alias(target)

    def _to_string(self, replacement, typedef='none', scope=None, with_args=False, qualifiers=False):
        if self.size:
            size = self.size
        else:
            size = ''
        replacement += '[{}]'.format(size)
        return self.element.to_string(replacement, typedef=typedef, scope=scope, specifiers=False,
                                      qualifiers=qualifiers)


class Pointer(Declaration):
    """The class represents pointers."""

    def __init__(self, ast):
        super().__init__(ast)

        ast['declarator'][-1]['pointer'] -= 1
        ast = reduce_level(ast)
        self.points = import_declaration(None, ast)
        self.points.add_parent(self)

    def _to_string(self, replacement, typedef='none', scope=None, with_args=False, qualifiers=False):
        replacement = _take_pointer(replacement, self.points)

        return self.points.to_string(replacement, typedef=typedef, scope=scope, specifiers=False, qualifiers=qualifiers)

    @property
    def static(self):
        return self.points.static

    @property
    def pretty_name(self):
        """
        This is an identifier string which can be used in variable names. Prints a name based on the type to which this
        type points. For instance for 'int *' it is 'int_ptr'.

        :return: String.
        """
        return '{}_ptr'.format(self.points.pretty_name)
