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

from core.vtg.emg.common import model_comment
from core.vtg.emg.common.process import Subprocess, Parentheses, Choice, Concatenation, Action
from core.vtg.emg.translation.code import control_function_comment_begin, control_function_comment_end
from core.vtg.emg.translation.fsa_translator.common import initialize_automaton_variables


def label_based_function(conf, analysis, automaton, cf, model=True):
    v_code, f_code = list(), list()

    # Determine returning expression for reuse
    if not conf.get('direct control functions calls') and not model:
        ret_expression = 'return 0;'
    else:
        ret_expression = 'return;'

    if model:
        kfunction_obj = analysis.get_source_function(automaton.process.name)
        if kfunction_obj.declaration.return_value != 'void':
            ret_expression = None

    # Then add memory external allocation marks
    f_code.extend(initialize_automaton_variables(conf, automaton))

    # Initialize variables
    # First add variables declarations
    for var in automaton.variables(only_used=True):
        scope = {automaton.process.file} if automaton.process.file else None
        v_code.append(var.declare(scope=scope) + ';')

    # After that assign explicit values
    for var in (v for v in automaton.variables(only_used=True) if v.value):
        f_code.append("{} = {};".format(var.name, var.value))

    main_v_code, main_f_code = __subprocess_code(automaton, automaton.process.actions.initial_action, ret_expression)
    v_code += main_v_code
    f_code += main_f_code + ["/* End of the process */"]
    if ret_expression:
        f_code.append(ret_expression)

    processed = set()
    for subp in automaton.process.actions.filter(include={Subprocess}):
        if subp.reference_name not in processed:
            first_actual_state = subp.action
            sp_v_code, sp_f_code = __subprocess_code(automaton, first_actual_state, ret_expression)

            v_code.extend(sp_v_code)
            f_code.extend([
                '',
                '/* Sbprocess {} */'.format(subp.action.name),
                'ldv_{}_{}:'.format(str(subp.reference_name), str(automaton))
            ])
            f_code.extend(sp_f_code)
            f_code.append("/* End of the subprocess '{}' */".format(subp.action.name))
            if ret_expression:
                f_code.append(ret_expression)
            processed.add(subp.reference_name)

    v_code = [model_comment('CONTROL_FUNCTION_INIT_BEGIN', 'Declare auxiliary variables.')] + \
             v_code + \
             [model_comment('CONTROL_FUNCTION_INIT_END', 'Declare auxiliary variables.')]
    if model:
        name = automaton.process.name
        v_code.insert(0, control_function_comment_begin(cf.name, automaton.process.comment))
    else:
        name = '{}({})'.format(automaton.process.name, automaton.process.category)
        v_code.insert(0, control_function_comment_begin(cf.name, automaton.process.comment, automaton.identifier))
    f_code.append(control_function_comment_end(cf.name, name))
    cf.body.extend(v_code + f_code)

    return cf.name


def __subprocess_code(automaton, initial_action, ret_expression):

    def _serialize_action(action, tab):
        v, f = [], []

        if isinstance(action, Subprocess):
            f += [
                '\t' * tab + '/* Jump to a subprocess {!r} initial state */'.format(action.name),
                '\t' * tab + 'goto ldv_{}_{};'.format(action.reference_name, str(automaton))
            ]
        elif isinstance(action, Action):
            my_v, my_f = automaton.code[action]
            v += my_v
            f += ['\t' * tab + stm for stm in my_f]
        elif isinstance(action, Choice):
            if len(action.actions) == 2:
                act1, act2 = action.actions
                act1_v, act1_f = _serialize_action(act1, tab + 1)
                act2_v, act2_f = _serialize_action(act2, tab + 1)

                v += act1_v + act2_v
                f += ['\t' * tab + 'if (ldv_undef_int()) {'] + act1_f + ['\t' * tab + '} else {'] + \
                     act2_f + ['\t' * tab + '}']
            elif len(action.actions) > 2:
                f += ['\t' * tab + 'switch (ldv_undef_int()) {']
                for case, branch in enumerate(action.actions):
                    branch_v, branch_f = _serialize_action(branch, tab + 2)
                    v += branch_v
                    f += ['\t' * (tab + 1) + 'case {}: '.format(case) + '{'] + branch_f + \
                         ['\t' * (tab + 2) + 'break;', '\t' * (tab + 1) + '}']
                f += ['\t' * (tab + 1) + 'default: ldv_assume(0);', '\t' * tab + '}']
            else:
                raise ValueError('Invalid number of conditions in %s: %d' % (str(action), len(action.actions)))
        elif isinstance(action, Concatenation):
            for itm in action.actions:
                itm_v, itm_f = _serialize_action(itm, tab)
                v += itm_v
                f += [''] + itm_f

            # Remove the first empty string
            if f:
                f.pop(0)
        elif isinstance(action, Parentheses):
            return _serialize_action(action.action, tab)
        else:
            raise NotImplementedError

        return v, f

    return _serialize_action(initial_action, 0)
