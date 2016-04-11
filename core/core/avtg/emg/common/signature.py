import copy
import re

from core.avtg.emg.grammars.signature import setup_parser, parse_signature


__typedef_collection = {}

__typedefs = {}

__noname_identifier = 0


def check_null(declaration, value):
    check = re.compile('[\s]*[(]?[\s]*0[\s]*[)]?[\s]*')
    if (type(declaration) is Function or (type(declaration) is Pointer and type(declaration.points) is Function)) and \
            check.fullmatch(value):
        return False
    else:
        return True


def extract_name(signature):
    try:
        ast = parse_signature(signature)
    except:
        raise ValueError("Cannot parse signature: {}".format(signature))

    if 'declarator' in ast and len(ast['declarator']) > 0 and 'identifier' in ast['declarator'][-1] and \
            ast['declarator'][-1]['identifier']:
        return ast['declarator'][-1]['identifier']
    else:
        return None


def import_typedefs(tds):
    global __typedefs

    for td in sorted(tds):
        ast = parse_signature(td)
        name = ast['declarator'][-1]['identifier']
        __typedefs[name] = ast


def import_signature(signature, ast=None, parent=None):
    global __typedef_collection
    global __typedefs

    if not ast:
        try:
            ast = parse_signature(signature)
        except:
            raise ValueError("Cannot parse signature: {}".format(signature))

    if 'declarator' not in ast or ('declarator' in ast and len(ast['declarator']) == 0):
        if 'specifiers' in ast and 'category' in ast['specifiers'] and 'identifier' in ast['specifiers']:
            ret = InterfaceReference(ast, parent)
        elif 'specifiers' in ast and ast['specifiers'] == '$':
            ret = UndefinedReference(ast, parent)
        elif 'specifiers' in ast and 'type specifier' in ast['specifiers'] and \
                ast['specifiers']['type specifier']['class'] == 'typedef' and \
                ast['specifiers']['type specifier']['name'] in __typedefs:
            ret = import_signature(None, copy.deepcopy(__typedefs[ast['specifiers']['type specifier']['name']]))
        elif 'specifiers' in ast and 'type specifier' in ast['specifiers'] and \
                ast['specifiers']['type specifier']['class'] == 'structure':
            ret = Structure(ast, parent)
        elif 'specifiers' in ast and 'type specifier' in ast['specifiers'] and \
                ast['specifiers']['type specifier']['class'] == 'enum':
            ret = Enum(ast, parent)
        elif 'specifiers' in ast and 'type specifier' in ast['specifiers'] and \
                ast['specifiers']['type specifier']['class'] == 'union':
            ret = Union(ast, parent)
        else:
            ret = Primitive(ast, parent)
    else:
        if len(ast['declarator']) == 1 and \
                ('pointer' not in ast['declarator'][-1] or ast['declarator'][-1]['pointer'] == 0) and \
                ('arrays' not in ast['declarator'][-1] or len(ast['declarator'][-1]['arrays']) == 0):
            if 'specifiers' not in ast:
                ret = Function(ast, parent)
            else:
                if ast['specifiers']['type specifier']['class'] == 'structure':
                    ret = Structure(ast, parent)
                elif ast['specifiers']['type specifier']['class'] == 'enum':
                    ret = Enum(ast, parent)
                elif ast['specifiers']['type specifier']['class'] == 'union':
                    ret = Union(ast, parent)
                elif ast['specifiers']['type specifier']['class'] == 'typedef' and \
                        ast['specifiers']['type specifier']['name'] in __typedefs:
                    ret = import_signature(None, copy.deepcopy(__typedefs[ast['specifiers']['type specifier']['name']]))
                else:
                    ret = Primitive(ast, parent)
        elif 'arrays' in ast['declarator'][-1] and len(ast['declarator'][-1]['arrays']) > 0:
            ret = Array(ast, parent)
        elif 'pointer' not in ast['declarator'][-1] or ast['declarator'][-1]['pointer'] > 0:
            ret = Pointer(ast, parent)
        else:
            raise NotImplementedError

    if ret.identifier not in __typedef_collection:
        __typedef_collection[ret.identifier] = ret
    else:
        if parent and parent not in __typedef_collection[ret.identifier].parents:
            __typedef_collection[ret.identifier].parents.append(parent)
        ret = __typedef_collection[ret.identifier]
    return ret


def _reduce_level(ast):
    if len(ast['declarator']) > 1 and \
            ('pointer' not in ast['declarator'][-1] or ast['declarator'][-1]['pointer'] == 0) and \
            ('arrays' not in ast['declarator'][-1] or len(ast['declarator'][-1]['arrays']) == 0) and \
            'function arguments' not in ast['declarator'][-1]:
        ast['declarator'].pop()
    return ast


def _take_pointer(exp, tp):
    if tp is Array or tp is Function:
        exp = '(*' + exp + ')'
    else:
        exp = '*' + exp
    return exp


def setup_collection(collection, typedefs):
    global __typedef_collection
    global __typedefs

    setup_parser()

    __typedef_collection = collection
    __typedefs = typedefs


def new_identifier():
    global __noname_identifier

    __noname_identifier += 1
    return __noname_identifier


class BaseType:

    @property
    def take_pointer(self):
        pointer_signature = self.to_string('a', True)
        return import_signature(pointer_signature)

    @property
    def identifier(self):
        return self.to_string(replacement='')

    @property
    def weak_implementations(self):
        if type(self) is Pointer:
            return list(self.implementations.values()) + list(self.points.implementations.values())
        else:
            return list(self.implementations.values()) + list(self.take_pointer.implementations.values())

    @property
    def pretty_name(self):
        raise NotImplementedError

    def common_initialization(self, ast, parent):
        self._ast = ast
        self.implementations = {}
        self.path = None
        self.parents = []
        self.add_parent(parent)

    def add_parent(self, parent):
        if parent and parent not in self.parents:
            self.parents.append(parent)

    def compare(self, target):
        if type(self) is type(target):
            if self.identifier == target.identifier:
                return True
        return False

    def pointer_alias(self, alias):
        if type(self) is Pointer and self.points.compare(alias):
            return self
        elif type(alias) is Pointer and self.compare(alias.points):
            return alias

        return None

    def add_implementation(self, value, path, root_type, root_value, root_sequence):
        new = Implementation(self, value, path, root_type, root_value, root_sequence)
        if new.identifier not in self.implementations:
            self.implementations[new.identifier] = new

    def to_string(self, replacement='', pointer=False):
        if pointer:
            replacement = _take_pointer(replacement, type(self))

        return self._to_string(replacement)


class Primitive(BaseType):

    def __init__(self, ast, parent):
        self.common_initialization(ast, parent)

    @property
    def clean_declaration(self):
        return True

    @property
    def pretty_name(self):
        pn = self._ast['specifiers']['type specifier']['name']
        return pn.replace(' ', '_')

    def _to_string(self, replacement):
        if replacement == '':
            return self._ast['specifiers']['type specifier']['name']
        else:
            return "{} {}".format(self._ast['specifiers']['type specifier']['name'], replacement)


class Enum(BaseType):

    def __init__(self, ast, parent):
        self.common_initialization(ast, parent)

    @property
    def name(self):
        return self._ast['specifiers']['type specifier']['name']

    @property
    def clean_declaration(self):
        return True

    @property
    def pretty_name(self):
        return 'enum_{}'.format(self.name)

    def _to_string(self, replacement):
        if replacement == '':
            return "enum {}".format(self.name)
        else:
            return "enum {} {}".format(self.name, replacement)


class Function(BaseType):

    def __init__(self, ast, parent):
        self.common_initialization(ast, parent)
        self.return_value = None
        self.parameters = []

        if 'specifiers' in self._ast['return value type'] and \
                'type specifier' in self._ast['return value type']['specifiers'] and \
                self._ast['return value type']['specifiers']['type specifier']['class'] == 'Primitive' and \
                self._ast['return value type']['specifiers']['type specifier']['name'] == 'void':
            self.return_value = None
        else:
            self.return_value = import_signature(None, self._ast['return value type'])

        for parameter in self._ast['declarator'][0]['function arguments']:
            if type(parameter) is str:
                self.parameters.append(parameter)
            else:
                self.parameters.append(import_signature(None, parameter))

        if len(self.parameters) == 1 and type(self.parameters[0]) is Primitive and \
                self.parameters[0].pretty_name == 'void':
            self.parameters = []

    @property
    def clean_declaration(self):
        if not self.return_value.clean_declaration:
            return False
        for param in self.parameters:
            if type(param) is not str and not param.clean_declaration:
                return False
        return True

    @property
    def pretty_name(self):
        global __typedef_collection

        key = new_identifier()
        return 'func_{}'.format(key)

    def _to_string(self, replacement):
        if len(self.parameters) == 0:
            replacement += '(void)'
        else:
            parameter_declarations = []
            for param in self.parameters:
                if type(param) is str:
                    parameter_declarations.append(param)
                else:
                    parameter_declarations.append(param.to_string(''))
            replacement = replacement + '(' + ', '.join(parameter_declarations) + ')'

        if self.return_value:
            replacement = self.return_value.to_string(replacement)
        else:
            replacement = 'void {}'.format(replacement)
        return replacement


class Structure(BaseType):

    def __init__(self, ast, parent):
        self.common_initialization(ast, parent)
        self.fields = {}

        if 'fields' in self._ast['specifiers']['type specifier']:
            for declaration in sorted(self._ast['specifiers']['type specifier']['fields'],
                                      key=lambda decl: str(decl['declarator'][-1]['identifier'])):
                name = declaration['declarator'][-1]['identifier']
                if name:
                    self.fields[name] = import_signature(None, declaration)

    @property
    def clean_declaration(self):
        return True

    @property
    def name(self):
        return self._ast['specifiers']['type specifier']['name']

    @property
    def pretty_name(self):
        if self._ast['specifiers']['type specifier']['name']:
            return 'struct_{}'.format(self.name)
        else:
            global __typedef_collection

            key = new_identifier()
            return 'struct_noname_{}'.format(key)

    def contains(self, target):
        return [field for field in sorted(self.fields.keys()) if self.fields[field].compare(target)]

    def weak_contains(self, target):
        return [field for field in sorted(self.fields.keys()) if self.fields[field].compare(target) or
                self.fields[field].pointer_alias(target)]

    def _to_string(self, replacement):
        if not self.name:
            name = '{ ' + '; '.join([self.fields[field].to_string(field) for field in sorted(self.fields.keys())]) + \
                   '; ' + ' }'
        else:
            name = self.name

        if replacement == '':
            return "struct {}".format(name)
        else:
            return "struct {} {}".format(name, replacement)


class Union(BaseType):

    def __init__(self, ast, parent):
        self.common_initialization(ast, parent)
        self.fields = {}

        if 'fields' in self._ast['specifiers']['type specifier']:
            for declaration in sorted(self._ast['specifiers']['type specifier']['fields'],
                                      key=lambda decl: str(decl['declarator'][-1]['identifier'])):
                name = declaration['declarator'][-1]['identifier']
                if name:
                    self.fields[name] = import_signature(None, declaration)

    @property
    def clean_declaration(self):
        #for field in self.fields.values():
        #    if not field.clean_declaration:
        #        return False
        return True

    @property
    def name(self):
        return self._ast['specifiers']['type specifier']['name']

    @property
    def pretty_name(self):
        if self._ast['specifiers']['type specifier']['name']:
            return 'union_{}'.format(self.name)
        else:
            global __typedef_collection

            key = new_identifier()
            return 'union_noname_{}'.format(key)

    def contains(self, target):
        return [field for field in sorted(self.fields.keys()) if self.fields[field].compare(target)]

    def weak_contains(self, target):
        return [field for field in sorted(self.fields.keys()) if self.fields[field].compare(target) or
                self.fields[field].pointer_alias(target)]

    def _to_string(self, replacement):
        if not self.name:
            name = '{ ' + '; '.join([self.fields[field].to_string(field) for field in sorted(self.fields.keys())]) + \
                   '; ' + ' }'
        else:
            name = self.name

        if replacement == '':
            return "union {}".format(name)
        else:
            return "union {} {}".format(name, replacement)


class Array(BaseType):

    def __init__(self, ast, parent):
        self.common_initialization(ast, parent)
        self.element = None

        array = ast['declarator'][-1]['arrays'].pop()
        self.size = array['size']
        ast = _reduce_level(ast)
        self.element = import_signature(None, ast, self)

    @property
    def clean_declaration(self):
        return self.element.clean_declaration

    @property
    def pretty_name(self):
        return '{}_array'.format(self.element.pretty_name)

    def contains(self, target):
        if self.element.compare(target):
            return True
        else:
            return False

    def weak_contains(self, target):
        if self.element.compare(target) or self.element.pointer_alias(target):
            return True
        else:
            return False

    def _to_string(self, replacement):
        if self.size:
            size = self.size
        else:
            size = ''
        replacement += '[{}]'.format(size)
        return self.element.to_string(replacement)


class Pointer(BaseType):

    def __init__(self, ast, parent):
        self.common_initialization(ast, parent)

        ast['declarator'][-1]['pointer'] -= 1
        ast = _reduce_level(ast)
        self.points = import_signature(None, ast, self)

    @property
    def clean_declaration(self):
        return self.points.clean_declaration

    def _to_string(self, replacement):
        replacement = _take_pointer(replacement, type(self.points))

        return self.points.to_string(replacement)

    @property
    def pretty_name(self):
        return '{}_ptr'.format(self.points.pretty_name)


class InterfaceReference(BaseType):

    def __init__(self, ast, parent):
        self._ast = ast
        self._identifier = None
        self.parents = []
        self.add_parent(parent)

    @property
    def clean_declaration(self):
        return False

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

    def _to_string(self, replacement):
        if self.pointer:
            ptr = '*'
        else:
            ptr = ''

        if replacement == '':
            return '{}%{}%'.format(ptr, self.interface)
        else:
            return '{}%{}% {}'.format(ptr, self.interface, replacement)


class UndefinedReference(BaseType):

    def __init__(self, ast, parent):
        self._ast = ast
        self.parents = []
        self.add_parent(parent)

    @property
    def clean_declaration(self):
        return False

    @property
    def _identifier(self):
        return '$'

    def _to_string(self, replacement):
        if replacement == '':
            return '$'
        else:
            return '$ {}'.format(replacement)


class Implementation:

    def __init__(self, declaration, value, file, base_container=None, base_value=None, sequence=None):
        self.base_container = base_container
        self.base_value = base_value
        self.value = value
        self.file = file
        self.sequence = sequence
        self.identifier = str([value, file, base_value])
        self.__declaration = declaration

    def adjusted_value(self, declaration):
        if self.__declaration.compare(declaration):
            return self.value
        elif self.__declaration.compare(declaration.take_pointer):
            return '*' + self.value
        elif self.__declaration.take_pointer.compare(declaration):
            return '&' + self.value
        else:
            raise ValueError("Cannot adjust declaration '{}' to declaration '{}'".
                             format(self.__declaration.to_string('%s'), declaration.to_string('%s')))

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
