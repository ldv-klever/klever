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

import ply.lex as lex
import ply.yacc as yacc
import re

__parser = None
__lexer = None

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
    'BLOCK_OPEN',
    'BLOCK_CLOSE',
    'COMMA',
    'DOTS',
    'BIT_SIZE_DELEMITER',
    'NUMBER',
    'END',
    'IDENTIFIER',
    'EQUAL_SIGN'
)

keyword_map = None

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

t_BIT_SIZE_DELEMITER = r'[:]'

t_END = r'[;]'

t_EQUAL_SIGN = r'='

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
    raise TypeError("Unknown text '%s'" % (t.value,))


def p_error(t):
    raise TypeError("Unknown text '%s'" % (t.value,))


def p_full_declaration(p):
    """
    full_declaration : parameter_declaration BIT_SIZE_DELEMITER NUMBER END
                     | parameter_declaration BIT_SIZE_DELEMITER NUMBER
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
                     | STRUCT BLOCK_OPEN BLOCK_CLOSE
                     | STRUCT BLOCK_OPEN struct_declaration_list BLOCK_CLOSE
    """
    if len(p) == 3:
        p[0] = {
            'class': 'structure',
            'name': p[2]
        }
    elif len(p) == 4:
        p[0] = {
            'class': 'structure',
            'name': None
        }
    else:
        p[0] = {
            'class': 'structure',
            'name': None,
            'fields': p[3]
        }


def p_struct_declaration_list(p):
    """
    struct_declaration_list : struct_declaration struct_declaration_list
                            | struct_declaration
    """
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        p[0] = [p[1]] + p[2]


def p_struct_declaration(p):
    """
    struct_declaration : parameter_declaration BIT_SIZE_DELEMITER NUMBER END
                       | parameter_declaration BIT_SIZE_DELEMITER NUMBER
                       | parameter_declaration END
    """
    p[0] = p[1]


def p_union_specifier(p):
    """
    union_specifier : UNION IDENTIFIER
                    | UNION BLOCK_OPEN struct_declaration_list BLOCK_CLOSE
    """
    if len(p) == 3:
        p[0] = {
            'class': 'union',
            'name': p[2]
        }
    else:
        p[0] = {
            'class': 'union',
            'name': None,
            'fields': p[3]
        }


def p_enum_specifier(p):
    """
    enum_specifier : ENUM IDENTIFIER
                   | ENUM BLOCK_OPEN enumerator_list BLOCK_CLOSE
    """
    if len(p) == 3:
        p[0] = {
            'class': 'enum',
            'name': p[2]
        }
    else:
        p[0] = {
            'class': 'enum',
            'name': None,
            'enumerators': p[3]
        }


def p_enumerator_list(p):
    """
    enumerator_list : enumerator COMMA enumerator_list
                    | enumerator
    """
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        p[0] = [p[1]] + p[3]


def p_enumerator(p):
    """
    enumerator : IDENTIFIER
               | IDENTIFIER EQUAL_SIGN NUMBER
    """
    p[0] = p[1]


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
        if 'arrays' in p[0][0] or 'function arguments' in p[0][0]:
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


def setup_parser():
    global __parser
    global __lexer

    __lexer = lex.lex()
    __parser = yacc.yacc(debug=0, write_tables=0)


def parse_signature(string):
    global __parser
    global __lexer

    if not __parser:
        setup_parser()

    return __parser.parse(string, lexer=__lexer)

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'