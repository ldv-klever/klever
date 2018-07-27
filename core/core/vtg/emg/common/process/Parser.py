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

__parser = None
__lexer = None

tokens = (
    'DOT',
    'SEP',
    'PAR_OPEN',
    'PAR_CLOSE',
    'BR_OPEN',
    'BR_CLOSE',
    'SBR_OPEN',
    'SBR_CLOSE',
    'DIM_OPEN',
    'DIM_CLOSE',
    'PER',
    'RS',
    'BS',
    'NUMBER',
    'IDENTIFIER',
)

t_DOT = r'[.]'

t_SEP = r'[|]'

t_PAR_OPEN = r'[(]'

t_PAR_CLOSE = r'[)]'

t_BR_OPEN = r'[{]'

t_BR_CLOSE = r'[}]'

t_SBR_OPEN = r'[[]'

t_SBR_CLOSE = r'[]]'

t_DIM_OPEN = r'[<]'

t_DIM_CLOSE = r'[>]'

t_PER =r'[%]'

t_IDENTIFIER = r'\w+'


def t_RS(t):
    r'[!]'
    t.value = True
    return t


def t_BS(t):
    r'[@]'
    t.value = True
    return t


def t_NUMBER(t):
    r'\d+'
    t.value = int(t.value)
    return t


def t_error(t):
    if t:
        raise TypeError("Unknown text '%s'" % (t.value,))
    else:
        raise TypeError('Unknown token parsing error')


def p_error(t):
    if t:
        raise TypeError("Unknown text '%s'" % (t.value,))
    else:
        raise TypeError('Unknown parsing error')


t_ignore = ' \t\n'


def p_process(p):
    """
    process : action_list
    """
    p[0] = p[1]


def p_action_list(p):
    """
    action_list : concatenation_list
                | choice_list
    """
    p[0] = p[1]


def p_action(p):
    """
    action : dispatch
           | receive
           | subprocess
           | condition
           | bracket
    """
    p[0] = p[1]


def p_concatenation_list(p):
    """
    concatenation_list : action DOT concatenation_list
                       | action
    """
    if len(p) > 2:
        p[3]['actions'] = [p[1]] + p[3]['actions']
        p[0] = p[3]
    else:
        p[0] = {
            'type': 'concatenation',
            'actions': [p[1]]
        }


def p_choice_list(p):
    """
    choice_list : concatenation_list SEP choice_list
                | concatenation_list
    """
    if len(p) > 2:
        p[3]['actions'] = [p[1]] + p[3]['actions']
        p[0] = p[3]
    else:
        p[0] = {
            'type': 'choice',
            'actions': [p[1]]
        }


def p_bracket(p):
    """
    bracket : PAR_OPEN action_list PAR_CLOSE
    """
    p[0] = p[2]


def p_repeate(p):
    """
    repeate : SBR_OPEN NUMBER SBR_CLOSE
            | SBR_OPEN PER IDENTIFIER PER SBR_CLOSE
    """
    if len(p) > 4:
        p[0] = p[3]
    else:
        p[0] = p[2]


def p_dispatch(p):
    """
    dispatch : SBR_OPEN BS IDENTIFIER repeate SBR_CLOSE
             | SBR_OPEN IDENTIFIER repeate SBR_CLOSE
             | SBR_OPEN BS IDENTIFIER SBR_CLOSE
             | SBR_OPEN IDENTIFIER SBR_CLOSE
    """
    p[0] = {
        'type': 'dispatch',
        'number': 1,
        'label': '['
    }
    if not isinstance(p[2], str) and p[2]:
        p[0]['broadcast'] = True
        p[0]['name'] = p[3]
        p[0]['label'] += '@'

        if len(p) == 6:
            p[0]['number'] = p[4]
    else:
        p[0]['broadcast'] = False
        p[0]['name'] = p[2]

        if len(p) == 5:
            p[0]['number'] = p[3]
    p[0]['label'] += "{}[{}]".format(p[0]['name'], p[0]['number']) + ']'


def p_receive(p):
    """
    receive : PAR_OPEN RS IDENTIFIER repeate PAR_CLOSE
            | PAR_OPEN IDENTIFIER repeate PAR_CLOSE
            | PAR_OPEN RS IDENTIFIER PAR_CLOSE
            | PAR_OPEN IDENTIFIER PAR_CLOSE
    """
    p[0] = {
        'type': 'receive',
        'number': 1,
        'label': '('
    }
    if not isinstance(p[2], str) and p[2]:
        p[0]['replicative'] = True
        p[0]['name'] = p[3]
        p[0]['label'] += '!'

        if len(p) == 6:
            p[0]['number'] = p[4]
    else:
        p[0]['replicative'] = False
        p[0]['name'] = p[2]

        if len(p) == 5:
            p[0]['number'] = p[3]
    p[0]['label'] += "{}[{}]".format(p[0]['name'], p[0]['number']) + ')'


def p_condition(p):
    """
    condition : DIM_OPEN IDENTIFIER repeate DIM_CLOSE
              | DIM_OPEN IDENTIFIER DIM_CLOSE
    """
    p[0] = {
        'type': 'condition',
        'name': p[2],
        'number': 1,
        'label': '<' + p[2] + '>'
    }

    if len(p) == 5:
        p[0]['number'] = p[3]


def p_subprocess(p):
    """
    subprocess : BR_OPEN IDENTIFIER BR_CLOSE
    """
    p[0] = {
        'type': 'subprocess',
        'name': p[2],
        'number': 1,
        'label': '{' + p[2] + '}'
    }


def setup_parser():
    """
    Setup the parser.

    :return: None
    """
    global __parser
    global __lexer

    __lexer = lex.lex()
    __parser = yacc.yacc(debug=0, write_tables=0)


def parse_process(string):
    """
    Main parsing method. It gets a raw string in DSL and returns an abstract syntax tree.

    :param string: Process description in DSL.
    :return: Abstract syntax tree.
    """
    global __parser
    global __lexer

    if not __parser:
        setup_parser()

    try:
        return __parser.parse(string, lexer=__lexer)
    except TypeError as err:
        raise ValueError("Cannot parse process '{}' due to parse error: {}".format(string, err.args))
