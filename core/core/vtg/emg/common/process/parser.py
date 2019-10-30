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

import collections
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


Concat = collections.namedtuple('Concatenation', ('actions',))
Choice = collections.namedtuple('Choice', ('actions',))
Disp = collections.namedtuple('Disp', ('name', 'label', 'number', 'broadcast'))
Recv = collections.namedtuple('Recv', ('name', 'label', 'number', 'replicative'))
Subp = collections.namedtuple('Subp', ('name', 'label'))
Block = collections.namedtuple('Block', ('name', 'label', 'number'))


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
    _, action_list = p
    p[0] = action_list


def p_action_list(p):
    """
    action_list : concatenation_list
                | choice_list
    """
    _, some_list = p
    p[0] = some_list


def p_action(p):
    """
    action : dispatch
           | receive
           | subprocess
           | condition
           | bracket
    """
    _, action = p
    p[0] = action


def p_concatenation_list(p):
    """
    concatenation_list : action DOT concatenation_list
                       | action
    """
    _, action, *concatenation_list = p
    if concatenation_list:
        concatenation_list = concatenation_list[-1]
        concatenation_list.actions.appendleft(action)
        p[0] = concatenation_list
    else:
        chain = collections.deque()
        chain.appendleft(action)
        p[0] = Concat(chain)


def p_choice_list(p):
    """
    choice_list : concatenation_list SEP choice_list
                | concatenation_list
    """
    _, concatenation_list, *choice_list = p
    if choice_list:
        choice_list = choice_list[-1]
        choice_list.actions.appendleft(concatenation_list)
        p[0] = choice_list
    else:
        chain = collections.deque()
        chain.appendleft(concatenation_list)
        p[0] = Choice(chain)


def p_bracket(p):
    """
    bracket : PAR_OPEN action_list PAR_CLOSE
    """
    _, _, action_list, _ = p
    p[0] = action_list


def p_repeate(p):
    """
    repeate : SBR_OPEN NUMBER SBR_CLOSE
            | SBR_OPEN PER IDENTIFIER PER SBR_CLOSE
    """
    context = p[2:-1]
    if len(context) > 1:
        number = context[1]
    else:
        number = context[0]
    p[0] = number


def p_dispatch(p):
    """
    dispatch : SBR_OPEN BS IDENTIFIER repeate SBR_CLOSE
             | SBR_OPEN IDENTIFIER repeate SBR_CLOSE
             | SBR_OPEN BS IDENTIFIER SBR_CLOSE
             | SBR_OPEN IDENTIFIER SBR_CLOSE
    """
    context = p[2:-1]
    if not isinstance(context[0], str) and context[0]:
        # We have broadcast symbol at the very beginning
        _, name, *number = context
        broadcast = True
        label = '@'
    else:
        # We have ordinary dispatch
        name, *number = context
        broadcast = False
        label = ''
    number = number[-1] if number else 1
    label = '[' + label + '%s[%s]' % (name, number) + ']'
    action = Disp(name, label, number, broadcast)
    p[0] = action


def p_receive(p):
    """
    receive : PAR_OPEN RS IDENTIFIER repeate PAR_CLOSE
            | PAR_OPEN IDENTIFIER repeate PAR_CLOSE
            | PAR_OPEN RS IDENTIFIER PAR_CLOSE
            | PAR_OPEN IDENTIFIER PAR_CLOSE
    """
    context = p[2:-1]
    if not isinstance(context[0], str) and context[0]:
        # We have replicative symbol at the very beginning
        _, name, *number = context
        replicative = True
        label = '!'
    else:
        # We have ordinary receive
        name, *number = context
        replicative = False
        label = ''
    number = number[-1] if number else 1
    label += '(' + label + '%s[%s]' % (name, number) + ')'
    action = Recv(name, label, number, replicative)
    p[0] = action


def p_condition(p):
    """
    condition : DIM_OPEN IDENTIFIER repeate DIM_CLOSE
              | DIM_OPEN IDENTIFIER DIM_CLOSE
    """
    name, *number = p[2:-1]
    number = number[-1] if number else 1
    action = Block(name, '<%s>' % name, number)
    p[0] = action


def p_subprocess(p):
    """
    subprocess : BR_OPEN IDENTIFIER BR_CLOSE
    """
    name = p[2]
    action = Subp(name, '{%s}' % name)
    p[0] = action


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
