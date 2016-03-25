import ply.lex as lex
import ply.yacc as yacc
import re

__collection = {}

__typedefs = {}

tokens = (
    'INTERFACE',
    'UNKNOWN',
    'TYPE_SPECIFIER',
    'STORAGE_CLASS_SPECIFIER',
    'TYPE_QUALIFIER',
    'FUNCTION_SPECIFIER',
    'ENUM',
    'STRUCT',
    'UNION',
    'STAR_SIGN',
    'SQUARE_BOPEN_SIGN',
    'SQUARE_BCLOSE_SIGN',
    'PARENTH_OPEN',
    'PARENTH_CLOSE',
    'COMMA',
    'DOTS',
    'BIT_SIZE_DELEMITER',
    'NUMBER',
    'END',
    'IDENTIFIER'
)

keyword_map = None

t_STAR_SIGN = r"\*"

t_SQUARE_BOPEN_SIGN = r"\["

t_SQUARE_BCLOSE_SIGN = r"\]"

t_PARENTH_OPEN = r"\("

t_PARENTH_CLOSE = r"\)"

t_COMMA = r","

t_DOTS = r"\.\.\."

t_UNKNOWN = r"\$"

t_BIT_SIZE_DELEMITER = r'[:]'

t_END = r'[;]'

t_ignore = ' \t'


def keyword_lookup(string):
    global keyword_map

    if not keyword_map:
        keyword_map = {
            'TYPE_SPECIFIER': re.compile('void|char|short|int|long|float|double|signed|unsigned|_Bool|_Complex'),
            'STORAGE_CLASS_SPECIFIER': re.compile('extern|static|_Thread_local|auto|register'),
            'TYPE_QUALIFIER': re.compile('const|restrict|volatile|_Atomic'),
            'FUNCTION_SPECIFIER': re.compile('inline|_Noreturn'),
            'STRUCT': re.compile('struct'),
            'UNION': re.compile('union'),
            'ENUM': re.compile('enum')
        }

    for keyword_type in keyword_map:
        if keyword_map[keyword_type].fullmatch(string):
            return keyword_type
    return None


def t_NUMBER(t):
    r'\d+[\w+]?'
    t.value = int(re.compile('(\d+)').match(t.value).group(1))
    return t


def t_INTERFACE(t):
    r'(\*?)%(\w+)\.(\w+)%'
    if t.value[0] == '*':
        value = t.value[2:-1]
        pointer = True
    else:
        value = t.value[1:-1]
        pointer = False
    category, identifier = str(value).split('.')
    t.value = {
        "category": category,
        "identifier": identifier,
        "pointer": pointer
    }
    return t


def t_IDENTIFIER(t):
    r'\w+'
    tp = keyword_lookup(t.value)
    if tp:
        t.type = tp
    return t


def t_error(t):
    raise TypeError("Unknown text '%s'" % (t.value,))


def p_error(t):
    raise TypeError("Unknown text '%s'" % (t.value,))


def p_full_declaration(p):
    """
    full_declaration : declaration BIT_SIZE_DELEMITER NUMBER END
                     | declaration BIT_SIZE_DELEMITER NUMBER
                     | declaration END
                     | declaration
    """
    p[0] = p[1]


def p_declaration(p):
    """
    declaration : declaration_specifiers_list declarator
                | UNKNOWN declarator
                | INTERFACE declarator
                | UNKNOWN
                | INTERFACE
    """
    declaration_processing(p)


def p_declaration_specifiers_list(p):
    """
    declaration_specifiers_list : prefix_specifiers_list type_specifier suffix_specifiers_list
                                | prefix_specifiers_list type_specifier
                                | type_specifier suffix_specifiers_list
                                | type_specifier
    """
    p[0] = {}
    if len(p) == 2:
        p[0]['type specifier'] = p[1]
    elif len(p) == 3 and type(p[1]) is list:
        p[0]['type specifier'] = p[2]
        p[0]['specifiers'] = p[1]
    elif len(p) == 3 and type(p[1]) is dict:
        p[0]['type specifier'] = p[1]
        p[0]['specifiers'] = p[2]
    else:
        p[0]['type specifier'] = p[2]
        p[0]['specifiers'] = p[1] + p[3]


def p_prefix_specifiers_list(p):
    """
    prefix_specifiers_list : prefix_specifiers_option prefix_specifiers_list
                           | prefix_specifiers_option
    """
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        p[0] = [p[1]] + list(p[2])


def p_prefix_specifiers_option(p):
    """
    prefix_specifiers_option : STORAGE_CLASS_SPECIFIER
                             | TYPE_QUALIFIER
                             | FUNCTION_SPECIFIER
    """
    p[0] = p[1]


def p_suffix_specifiers_list(p):
    """
    suffix_specifiers_list : suffix_specifiers_option suffix_specifiers_list
                           | suffix_specifiers_option
    """
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        p[0] = [p[1]] + list(p[2])


def p_suffix_specifiers_option(p):
    """
    suffix_specifiers_option : TYPE_QUALIFIER
    """
    p[0] = p[1]


def p_type_specifier(p):
    """
    type_specifier : type_specifier_list
                   | struct_specifier
                   | union_specifier
                   | enum_specifier
                   | typedef
    """
    if type(p[1]) is str:
        p[0] = {
            'class': 'primitive',
            'name': p[1]
        }
    else:
        p[0] = p[1]


def p_type_specifier_list(p):
    """
    type_specifier_list : TYPE_SPECIFIER type_specifier_list
                        | TYPE_SPECIFIER
    """
    if len(p) == 2:
        p[0] = p[1]
    else:
        p[0] = p[1] + str(" {}".format(p[2]))


def p_struct_specifier(p):
    """
    struct_specifier : STRUCT IDENTIFIER
    """
    p[0] = {
        'class': 'structure',
        'name': p[2]
    }


def p_union_specifier(p):
    """
    union_specifier : UNION IDENTIFIER
    """
    p[0] = {
        'class': 'union',
        'name': p[2]
    }


def p_enum_specifier(p):
    """
    enum_specifier : ENUM IDENTIFIER
    """
    p[0] = {
        'class': 'enum',
        'name': p[2]
    }


def p_typedef(p):
    """
    typedef : IDENTIFIER
    """
    p[0] = {
        'class': 'typedef',
        'name': p[1]
    }


def p_declarator(p):
    """
    declarator : pointer direct_declarator
               | direct_declarator
    """
    declarator_processing(p)


def p_pointer(p):
    """
    pointer : STAR_SIGN suffix_specifiers_list pointer
            | STAR_SIGN suffix_specifiers_list
            | STAR_SIGN pointer
            | STAR_SIGN
    """
    if len(p) == 2:
        p[0] = 1
    elif len(p) == 3 and type(p[2]) is int:
        p[0] = int(p[2]) + 1
    elif len(p) == 3 and type(p[2]) is list:
        p[0] = 1
    else:
        p[0] = int(p[3]) + 1


def p_direct_declarator(p):
    """
    direct_declarator : direct_declarator array_list
                      | direct_declarator PARENTH_OPEN function_parameters_list PARENTH_CLOSE
                      | PARENTH_OPEN declarator PARENTH_CLOSE
                      | IDENTIFIER
    """
    direct_declarator_processing(p)


def p_array_list(p):
    """
    array_list : array_expression array_list
               | array_expression
    """
    p[0] = []
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        p[0] = [p[1]] + p[2]


def p_array_expression(p):
    """
    array_expression : SQUARE_BOPEN_SIGN array_size SQUARE_BCLOSE_SIGN
                     | SQUARE_BOPEN_SIGN SQUARE_BCLOSE_SIGN
    """
    if len(p) == 4:
        p[0] = p[2]
    else:
        p[0] = {"size": None}


def p_array_size(p):
    """
    array_size : suffix_specifiers_list STAR_SIGN
               | suffix_specifiers_list NUMBER
               | STAR_SIGN
               | NUMBER
    """
    if len(p) == 3 and type(p[2]) is str:
        p[0] = {"size": None}
    elif len(p) == 3 and type(p[2]) is int:
        p[0] = {"size": p[2]}
    elif len(p) == 2 and type(p[1]) is str:
        p[0] = {"size": None}
    else:
        p[0] = {"size": p[1]}


def p_function_parameters_list(p):
    """
    function_parameters_list : parameter_declaration COMMA function_parameters_list
                             | parameter_declaration
    """
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        p[0] = [p[1]] + p[3]


def p_parameter_declaration(p):
    """
    parameter_declaration : declaration_specifiers_list declarator
                          | declaration_specifiers_list abstract_declarator
                          | UNKNOWN declarator
                          | INTERFACE declarator
                          | UNKNOWN abstract_declarator
                          | INTERFACE abstract_declarator
                          | declaration_specifiers_list
                          | UNKNOWN
                          | INTERFACE
                          | DOTS
    """
    declaration_processing(p)


def p_abstract_declarator(p):
    """
    abstract_declarator : pointer direct_abstract_declarator
                        | direct_abstract_declarator
                        | pointer
    """
    declarator_processing(p)


def p_direct_abstract_declarator(p):
    """
    direct_abstract_declarator : direct_abstract_declarator array_list
                               | direct_abstract_declarator PARENTH_OPEN function_parameters_list PARENTH_CLOSE
                               | PARENTH_OPEN abstract_declarator PARENTH_CLOSE
    """
    direct_declarator_processing(p)


def declaration_processing(p):
    """
    [parameter_]declaration : declaration_specifiers_list declarator
                            | declaration_specifiers_list abstract_declarator
                            | UNKNOWN declarator
                            | INTERFACE declarator
                            [| UNKNOWN abstract_declarator]
                            [| INTERFACE abstract_declarator]
                            [| declaration_specifiers_list]
                            | UNKNOWN
                            | INTERFACE
                            [| DOTS]
    """
    if len(p) == 3:
        p[0] = {
            'specifiers': p[1],
            'declarator': p[2]
        }
    elif len(p) == 2 and type(p[1]) is dict and 'type specifier' in p[1]:
        p[0] = {
            'specifiers': p[1],
            'declarator': [{'identifier': None}]
        }
    elif len(p) == 2 and (type(p[1]) is dict and 'category' in p[1] or p[1] == '$'):
        p[0] = {
            'specifiers': p[1]
        }
    else:
        p[0] = p[1]

    # Move return value types and declarators to separate attributes
    if 'declarator' in p[0]:
        separators = [index for index in range(len(p[0]['declarator']))
                      if 'function arguments' in p[0]['declarator'][index]]

        if len(separators) > 0:
            current_ast = p[0]
            while len(separators) > 0:
                separator = separators.pop()
                declarator = current_ast['declarator'][separator:]
                ret_declarator = current_ast['declarator'][0:separator]
                current_ast['declarator'] = declarator
                current_ast['return value type'] = {'declarator': ret_declarator}
                current_ast = current_ast['return value type']

            current_ast['specifiers'] = p[0]['specifiers']
            del p[0]['specifiers']


def declarator_processing(p):
    """
    [abstract_]declarator : pointer direct_[abstract_]declarator
                        | direct_[abstract_]declarator
                        [| pointer]
    """
    if len(p) == 2 and type(p[1]) is int:
        new = {
            'pointer': p[1],
            'identifier': None
        }
        p[0] = [new]
    elif len(p) == 2 and type(p[1]) is list:
        p[0] = p[1]
    else:
        p[0] = p[2]
        if 'pointer' in p[0][0] and ('arrays' in p[0][0] or 'function arguments' in p[0][0]):
            new = {'pointer': p[1]}
            p[0] = [new] + p[0]
        else:
            if 'pointer' in p[0][0]:
                p[0][0]['pointer'] = p[1] + p[0][0]['pointer']
            else:
                p[0][0]['pointer'] = p[1]


def direct_declarator_processing(p):
    """
    [abstract_]declarator : direct_[abstract_]declarator array_list
                          | direct_[abstract_]declarator PARENTH_OPEN function_parameters_list PARENTH_CLOSE
                          | PARENTH_OPEN [abstract_]declarator PARENTH_CLOSE
                          [| IDENTIFIER]
    """
    if len(p) == 2:
        p[0] = [
            {
                'identifier': p[1]
            }
        ]
    else:
        if 'size' in p[2][0] and 'pointer' not in p[1][0]:
            p[0] = p[1]
            p[0][0]['arrays'] = p[2]
        elif 'size' in p[2][0] and 'pointer' in p[1][0]:
            new = {'arrays': p[2]}
            p[0] = [new] + p[1]
        else:
            if len(p) == 5:
                p[0] = p[1]

                if len(p[3]) == 1 and type(p[3][0]) is dict and 'type specifier' in p[3][0] and \
                        p[3][0]['type specifier']['name'] == 'void' and 'declarator' not in p[3][0]:
                    p[0][0]['function arguments'] = []
                else:
                    p[0][0]['function arguments'] = p[3]
            else:
                p[0] = p[2]


def extract_name(signature):
    __check_grammar()

    try:
        ast = yacc.parse(signature)
    except:
        raise ValueError("Cannot parse signature: {}".format(signature))

    if 'declarator' in ast and len(ast['declarator']) > 0 and 'identifier' in ast['declarator'][-1] and \
            ast['declarator'][-1]['identifier']:
        return ast['declarator'][-1]['identifier']
    else:
        raise ValueError('Cannot extract name from declaration without declarator')


def import_typedefs(tds):
    pass


def import_signature(signature, ast=None, parent=None):
    if not ast:
        __check_grammar()

        try:
            ast = yacc.parse(signature)
        except:
            raise ValueError("Cannot parse signature: {}".format(signature))

    if 'declarator' not in ast or ('declarator' in ast and len(ast['declarator']) == 0):
        if 'specifiers' in ast and 'category' in ast['specifiers'] and 'identifier' in ast['specifiers']:
            ret = InterfaceReference(ast, parent)
        elif 'specifiers' in ast and ast['specifiers'] == '$':
            ret = UndefinedReference(ast, parent)
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
                    raise NotImplementedError
                elif ast['specifiers']['type specifier']['class'] == 'union':
                    ret = Union(ast, parent)
                else:
                    ret = Primitive(ast, parent)
        elif 'arrays' in ast['declarator'][-1] and len(ast['declarator'][-1]['arrays']) > 0:
            ret = Array(ast, parent)
        elif 'pointer' not in ast['declarator'][-1] or ast['declarator'][-1]['pointer'] > 0:
            ret = Pointer(ast, parent)
        else:
            raise NotImplementedError

    if ret.identifier not in __collection:
        __collection[ret.identifier] = ret
    else:
        if parent and parent not in __collection[ret.identifier].parents:
            __collection[ret.identifier].parents.append(parent)
        ret = __collection[ret.identifier]
    return ret


def __check_grammar():
    lex.lex()
    yacc.yacc(debug=0, write_tables=0)


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
    global __collection
    global __typedefs

    __collection = collection
    __typedefs = typedefs


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
        return self._ast['specifiers']['type specifier']['name']

    def _to_string(self, replacement):
        if replacement == '':
            return self._ast['specifiers']['type specifier']['name']
        else:
            return "{} {}".format(self._ast['specifiers']['type specifier']['name'], replacement)


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
            if not param.clean_declaration:
                return False
        return True

    @property
    def pretty_name(self):
        global __collection

        key = list(__collection.keys()).index(self.identifier)
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
        return 'struct_{}'.format(self.name)

    def contains(self, target):
        return [field for field in self.fields if self.fields[field].compare(target)]

    def weak_contains(self, target):
        return [field for field in self.fields if self.fields[field].compare(target) or
                self.fields[field].pointer_alias(target)]

    def _to_string(self, replacement):
        if replacement == '':
            return "struct {}".format(self.name)
        else:
            return "struct {} {}".format(self.name, replacement)


class Union(BaseType):

    def __init__(self, ast, parent):
        self.common_initialization(ast, parent)
        self.fields = {}

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
        return 'union_{}'.format(self.name)

    def _to_string(self, replacement):
        if replacement == '':
            return "union {}".format(self.name)
        else:
            return "union {} {}".format(self.name, replacement)


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
        replacement = replacement + '[{}]'.format(size)
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
