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
import sortedcontainers
import ply.lex as lex
import ply.yacc as yacc

__parser = None
__lexer = None

tokens = (
    'STRING',
    'ATTRIBUTE',
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
    'BLOCK_OPEN',
    'BLOCK_CLOSE',
    'COMMA',
    'DOTS',
    'BIT_SIZE_DELIMITER',
    'NUMBER',
    'END',
    'IDENTIFIER',
    'EQUAL_SIGN'
)

keyword_map = None

t_STRING = r'"'

t_STAR_SIGN = r"\*"

t_SQUARE_BOPEN_SIGN = r"\["

t_SQUARE_BCLOSE_SIGN = r"\]"

t_PARENTH_OPEN = r"\("

t_PARENTH_CLOSE = r"\)"

t_BLOCK_OPEN = r'[{]'

t_BLOCK_CLOSE = r'[}]'

t_COMMA = r","

t_DOTS = r"\.\.\."

t_UNKNOWN = r"\$"

t_BIT_SIZE_DELIMITER = r'[:]'

t_END = r'[;]'

t_EQUAL_SIGN = r'='

t_ignore = ' \t\n'


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
            'ENUM': re.compile('enum'),
            'ATTRIBUTE': re.compile('__attribute__')
        }

    for keyword_type in sorted(keyword_map.keys()):
        if keyword_map[keyword_type].fullmatch(string):
            return keyword_type
    return None


def t_NUMBER(t):
    r'[-]?\d+[\w+]?'
    # todo: here should be constant-expression but it is quite complicated
    try:
        t.value = int(t.value)
    except ValueError:
        pass
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
    raise TypeError("Unknown token '%s'" % (t.value,))


def p_error(t):
    raise TypeError("Unknown token '%s'" % (t.value,))


def p_full_declaration(p):
    """
    full_declaration : parameter_declaration BIT_SIZE_DELIMITER NUMBER END
                     | parameter_declaration BIT_SIZE_DELIMITER NUMBER
                     | parameter_declaration END
                     | parameter_declaration
    """
    p[0] = p[1]

# todo: this is declaration with declarator but an input sometimes does not contain it
#def p_declaration(p):
#    """
#    declaration : declaration_specifiers_list declarator
#                | UNKNOWN declarator
#                | INTERFACE declarator
#                | UNKNOWN
#                | INTERFACE
#    """
#    declaration_processing(p)


def p_declaration_specifiers_list(p):
    """
    declaration_specifiers_list : prefix_specifiers_list type_specifier suffix_specifiers_list
                                | prefix_specifiers_list type_specifier
                                | type_specifier suffix_specifiers_list
                                | type_specifier
    """
    values = p[1:]
    unknown_specifier = values[0]

    declaration_specifiers_list = sortedcontainers.SortedDict()
    if len(values) == 1:
        type_specifier, = values
        specifiers = None
    elif len(values) == 2 and isinstance(unknown_specifier, list):
        specifiers, type_specifier = values
    elif len(values) == 2 and isinstance(unknown_specifier, dict):
        type_specifier, specifiers = values
    else:
        prefix_specifiers_list, type_specifier, suffix_specifiers_list = values
        specifiers = prefix_specifiers_list + suffix_specifiers_list

    declaration_specifiers_list['type specifier'] = type_specifier
    if specifiers:
        new_specifiers = []
        new_qualifiers = []
        for specifier in specifiers:
            if keyword_lookup(specifier) == 'TYPE_QUALIFIER':
                new_qualifiers.append(specifier)
            else:
                new_specifiers.append(specifier)
        declaration_specifiers_list['specifiers'] = new_specifiers
        declaration_specifiers_list['qualifiers'] = new_qualifiers

    p[0] = declaration_specifiers_list


def p_prefix_specifiers_list(p):
    """
    prefix_specifiers_list : prefix_specifiers_option prefix_specifiers_list
                           | prefix_specifiers_option
    """
    _list_element_processing(p)


def p_prefix_specifiers_option(p):
    """
    prefix_specifiers_option : STORAGE_CLASS_SPECIFIER
                             | TYPE_QUALIFIER
                             | FUNCTION_SPECIFIER
    """
    qualifier = p[1]
    p[0] = qualifier


def p_suffix_specifiers_list(p):
    """
    suffix_specifiers_list : suffix_specifiers_option suffix_specifiers_list
                           | suffix_specifiers_option
    """
    _list_element_processing(p)


def p_suffix_specifiers_option(p):
    """
    suffix_specifiers_option : TYPE_QUALIFIER
    """
    qualifier = p[1]
    p[0] = qualifier


def p_type_specifier(p):
    """
    type_specifier : type_specifier_list
                   | struct_specifier
                   | union_specifier
                   | enum_specifier
                   | typedef
    """
    type_specifier = p[1]

    if isinstance(type_specifier, str):
        type_specifier = {
            'class': 'primitive',
            'name': type_specifier
        }
    p[0] = type_specifier


def p_type_specifier_list(p):
    """
    type_specifier_list : TYPE_SPECIFIER type_specifier_list
                        | TYPE_SPECIFIER attribute_dict
                        | TYPE_SPECIFIER
    """
    type_specifier, *type_specifier_list = p[1:]

    if type_specifier_list:
        type_specifier_list, = type_specifier_list
        if not isinstance(type_specifier_list, dict):
            type_specifier_list = type_specifier + ' %s' % type_specifier_list
        else:
            type_specifier_list = type_specifier
    else:
        type_specifier_list = type_specifier

    p[0] = type_specifier_list


def p_struct_specifier(p):
    """
    struct_specifier : complete_struct_specifier attribute_dict
                     | short_struct_specifier attribute_dict
                     | complete_struct_specifier
                     | short_struct_specifier
    """
    struct_specifier, *rest = p[1:]
    if rest:
        attributes, = rest
        struct_specifier['attributes'] = attributes
    p[0] = struct_specifier


def p_short_struct_specifier(p):
    """
    short_struct_specifier : STRUCT BLOCK_OPEN struct_declaration_list BLOCK_CLOSE
                           | STRUCT BLOCK_OPEN BLOCK_CLOSE
    """
    *struct_declaration_list, _ = p[3:]
    struct = {'class': 'structure', 'name': None}
    if struct_declaration_list:
        struct_declaration_list, = struct_declaration_list
        struct['fields'] = struct_declaration_list
    p[0] = struct


def p_complete_struct_specifier(p):
    """
    complete_struct_specifier : STRUCT IDENTIFIER BLOCK_OPEN struct_declaration_list BLOCK_CLOSE
                              | STRUCT IDENTIFIER BLOCK_OPEN BLOCK_CLOSE
                              | STRUCT IDENTIFIER
    """
    name, *rest = p[2:]
    struct = {'class': 'structure', 'name': name}
    if rest:
        *rest, _ = rest[1:]
        if rest:
            struct_declaration_list, = rest
            struct['fields'] = struct_declaration_list

    p[0] = struct


def p_attribute_dict(p):
    """
    attribute_dict : attribute attribute_dict
                   | attribute 
    """
    attribute, *attr_dict = p[1:]
    if attr_dict:
        attr_dict, = attr_dict
    else:
        attr_dict = dict()
    attr_dict.update(attribute)
    p[0] = attr_dict


def p_attribute(p):
    """
    attribute : ATTRIBUTE PARENTH_OPEN PARENTH_OPEN inside_attr_list PARENTH_CLOSE PARENTH_CLOSE
              | ATTRIBUTE PARENTH_OPEN PARENTH_OPEN PARENTH_CLOSE PARENTH_CLOSE
    """
    name, _, _, *inside_list, _, _ = p[1:]
    if inside_list:
        inside_list, = inside_list
    else:
        inside_list = None
    p[0] = {
        name: inside_list
    }


def p_inside_attr_list(p):
    """
    inside_attr_list : inside_attr COMMA inside_attr_list
                     | inside_attr 
    """
    inside_attr, *rest = p[1:]
    if rest:
        _, inside_attr_list = rest
    else:
        inside_attr_list = []
    inside_attr_list = [inside_attr] + inside_attr_list
    p[0] = inside_attr_list


def p_inside_attr(p):
    """
    inside_attr : IDENTIFIER PARENTH_OPEN attr_param_list PARENTH_CLOSE 
                | IDENTIFIER PARENTH_OPEN PARENTH_CLOSE
                | IDENTIFIER 
    """
    name, *rest = p[1:]
    params = None
    if rest:
        _, *nparams, _ = rest
        if nparams:
            params, = nparams
    p[0] = {
        name: params
    }


def p_attr_param_list(p):
    """
    attr_param_list : attr_param COMMA attr_param_list
                    | attr_param
    """
    param, *rest = p[1:]
    if rest:
        _, attrs = rest
        attrs = [param] + attrs
    else:
        attrs = [param]
    p[0] = attrs


def p_attr_param(p):
    """
    attr_param : STRING IDENTIFIER STRING
               | IDENTIFIER
               | NUMBER
    """
    tokens = p[1:]
    if len(tokens) == 1:
        p[0] = tokens[0]
    else:
        _, token, _ = tokens
        p[0] = f'"{token}"'


def p_struct_declaration_list(p):
    """
    struct_declaration_list : struct_declaration struct_declaration_list
                            | struct_declaration
    """
    _list_element_processing(p)


def p_struct_declaration(p):
    """
    struct_declaration : parameter_declaration BIT_SIZE_DELIMITER NUMBER END
                       | parameter_declaration BIT_SIZE_DELIMITER NUMBER
                       | parameter_declaration END
    """
    parameter_declaration = p[1]
    p[0] = parameter_declaration


def p_union_specifier(p):
    """
    union_specifier : union_partial_complex_specifier attribute_dict
                    | union_partial_complex_specifier 
                    | union_partial_simple_specifier
    """
    union_specifier, *rest = p[1:]

    if rest:
        attributes, = rest
        union_specifier['attributes'] = attributes
    p[0] = union_specifier


def p_union_partial_simple_specifier(p):
    """
    union_partial_simple_specifier : UNION IDENTIFIER
    """
    p[0] = {'class': 'union', 'name': p[2]}


def p_union_partial_complex_specifier(p):
    """
    union_partial_complex_specifier : UNION BLOCK_OPEN struct_declaration_list BLOCK_CLOSE
                                    | UNION BLOCK_OPEN BLOCK_CLOSE
    """
    *struct_declaration_list, _ = p[3:]
    union_specifier = {'class': 'union', 'name': None}
    if struct_declaration_list:
        struct_declaration_list, = struct_declaration_list
        union_specifier['fields'] = struct_declaration_list
    p[0] = union_specifier


def p_enum_specifier(p):
    """
    enum_specifier : ENUM IDENTIFIER
                   | ENUM BLOCK_OPEN enumerator_list BLOCK_CLOSE
    """
    first, *rest = p[2:]

    enum_specifier = {'class': 'enum', 'name': None}
    if rest:
        enumerator_list = rest.pop(0)
        enum_specifier['enumerators'] = enumerator_list
    else:
        enum_specifier['name'] = first

    p[0] = enum_specifier


def p_enumerator_list(p):
    """
    enumerator_list : enumerator COMMA enumerator_list
                    | enumerator
    """
    _comma_list_element_processing(p)


def p_enumerator(p):
    """
    enumerator : IDENTIFIER
               | IDENTIFIER EQUAL_SIGN NUMBER
    """
    enumerator = p[1]
    p[0] = enumerator


def p_typedef(p):
    """
    typedef : IDENTIFIER attribute_dict
            | IDENTIFIER
    """
    identifier, *attrs = p[1:]
    p[0] = {
        'class': 'typedef',
        'name': identifier
    }


def p_declarator(p):
    """
    declarator : pointer direct_declarator
               | direct_declarator
    """
    _declarator_processing(p)


def p_pointer(p):
    """
    pointer : STAR_SIGN suffix_specifiers_list pointer
            | STAR_SIGN suffix_specifiers_list
            | STAR_SIGN pointer
            | STAR_SIGN
    """
    values = p[2:]
    pointer = 1

    if values:
        first, *last = values
        if last:
            pointer, = last
            pointer += 1
        elif isinstance(first, int):
            pointer = first + 1

    p[0] = pointer


def p_direct_declarator(p):
    """
    direct_declarator : direct_declarator array_list
                      | direct_declarator PARENTH_OPEN PARENTH_CLOSE
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
    _list_element_processing(p)


def p_array_expression(p):
    """
    array_expression : SQUARE_BOPEN_SIGN array_size SQUARE_BCLOSE_SIGN
                     | SQUARE_BOPEN_SIGN SQUARE_BCLOSE_SIGN
    """
    array_size = p[2:-1]
    if array_size:
        array_size, = array_size
    else:
        array_size = {"size": None}

    p[0] = array_size


def p_array_size(p):
    """
    array_size : suffix_specifiers_list STAR_SIGN
               | suffix_specifiers_list NUMBER
               | STAR_SIGN
               | NUMBER
    """
    if len(p) == 2:
        number = p[1]
    else:
        number = p[2]

    if isinstance(number, int):
        array_size = {'size': number}
    else:
        array_size = {'size': None}

    p[0] = array_size


def p_function_parameters_list(p):
    """
    function_parameters_list : parameter_declaration COMMA function_parameters_list
                             | parameter_declaration
    """
    _comma_list_element_processing(p)


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
    _declaration_processing(p)


def p_abstract_declarator(p):
    """
    abstract_declarator : pointer direct_abstract_declarator
                        | direct_abstract_declarator
                        | pointer
    """
    _declarator_processing(p)


def p_direct_abstract_declarator(p):
    """
    direct_abstract_declarator : direct_abstract_declarator array_list
                               | direct_abstract_declarator PARENTH_OPEN PARENTH_CLOSE
                               | direct_abstract_declarator PARENTH_OPEN function_parameters_list PARENTH_CLOSE
                               | PARENTH_OPEN abstract_declarator PARENTH_CLOSE
    """
    direct_declarator_processing(p)


def _list_element_processing(p):
    """
    [some_list : value some_list
               | value]
    """
    value, *some_list = p[1:]

    if some_list:
        some_list, = some_list
        some_list.insert(0, value)
    else:
        some_list = [value]

    p[0] = some_list


def _comma_list_element_processing(p):
    """
    [some_list : value COMMA some_list
               | value]
    """
    value, *some_list = p[1::2]

    if some_list:
        some_list, = some_list
        some_list.insert(0, value)
    else:
        some_list = [value]

    p[0] = some_list


def _declaration_processing(p):
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
    specifiers, *declarator = p[1:]

    if declarator:
        declarator, = declarator
        declaration = {'specifiers': specifiers, 'declarator': declarator}
    else:
        if isinstance(specifiers, dict) and 'type specifier' in specifiers:
            declaration = {'specifiers': specifiers, 'declarator': [{'identifier': None}]}
        elif isinstance(specifiers, dict) and 'category' in specifiers or specifiers == '$':
            declaration = {'specifiers': specifiers}
        else:
            declaration = specifiers

    # Move return value types and declarators to separate attributes
    if isinstance(declaration, dict) and declaration.get('declarator'):
        separators = [i for i in range(len(declaration['declarator']))
                      if 'function arguments' in declaration['declarator'][i]]

        if len(separators) > 0:
            current_ast = declaration
            while len(separators) > 0:
                separator = separators.pop()
                declarator = current_ast['declarator'][separator:]
                ret_declarator = current_ast['declarator'][0:separator]
                current_ast.update({'declarator': declarator, 'return value type': {'declarator': ret_declarator}})
                current_ast = current_ast['return value type']

            current_ast['specifiers'] = declaration['specifiers']
            del declaration['specifiers']
            
    p[0] = declaration


def _declarator_processing(p):
    """
    [abstract_]declarator : pointer direct_[abstract_]declarator
                        | direct_[abstract_]declarator
                        [| pointer]
    """
    declarator_or_pointer, *declarator = p[1:]

    if not declarator:
        # Either declarator or pointer
        if isinstance(declarator_or_pointer, int):
            declarator = [{'pointer': declarator_or_pointer, 'identifier': None}]
        elif isinstance(declarator_or_pointer, list):
            declarator = declarator_or_pointer
    else:
        # Both pointer and declarator
        pointer = declarator_or_pointer
        declarator, = declarator

        if 'arrays' in declarator[0] or 'function arguments' in declarator[0]:
            # If it is an array or function make a stack from it
            declarator.insert(0, {'pointer': pointer})
        else:
            # Increase pointer counter if necessary
            declarator[0].setdefault('pointer', 0)
            declarator[0]['pointer'] += pointer
                
    p[0] = declarator


def direct_declarator_processing(p):
    """
    [abstract_]declarator : direct_[abstract_]declarator array_list
                          | direct_[abstract_]declarator PARENTH_OPEN PARENTH_CLOSE
                          | direct_[abstract_]declarator PARENTH_OPEN function_parameters_list PARENTH_CLOSE
                          | PARENTH_OPEN [abstract_]declarator PARENTH_CLOSE
                          [| IDENTIFIER]
    """
    if len(p) == 2:
        identifier = p[1]
        declarator = [{'identifier': identifier}]
    else:
        if isinstance(p[1], str):
            declarator = p[2]
        else:
            declarator, *data = p[1:]
            if isinstance(data[0], str):
                # inside parentheses
                # PARENTH_OPEN PARENTH_CLOSE
                # PARENTH_OPEN function_parameters_list PARENTH_CLOSE
                function_parameters_list = data[1:-1]
                if function_parameters_list:
                    function_parameters_list, = function_parameters_list
                    top = function_parameters_list[0]

                    if len(function_parameters_list) == 1 and isinstance(top, dict) and \
                            top.get('type specifier', dict()).get('name') == 'void' and 'declarator' not in top:
                        # Detect void
                        declarator[0]['function arguments'] = []
                    else:
                        declarator[0]['function arguments'] = function_parameters_list
                else:
                    declarator[0]['function arguments'] = []
            else:
                # array list
                array_list, = data

                if 'pointer' in declarator[0]:
                    declarator.insert(0, {'arrays': array_list})
                else:
                    declarator[0]['arrays'] = array_list
    
    p[0] = declarator


def setup_parser():
    """
    Setup the parser.

    :return: None
    """
    global __parser
    global __lexer

    __lexer = lex.lex()
    __parser = yacc.yacc(debug=0, write_tables=0)


def parse_declaration(string):
    """
    Parse the given C declaration string with the possible interface extensions.

    :param string: C declaration string.
    :return: Obtained abstract syntax tree.
    """
    global __parser
    global __lexer

    if not __parser:
        setup_parser()

    return __parser.parse(string, lexer=__lexer)
