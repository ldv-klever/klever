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

from klever.core.vtg.emg.common import model_comment
from klever.core.vtg.emg.common.process.actions import Subprocess, Parentheses, Choice, Concatenation, Behaviour
from klever.core.vtg.emg.translation.code import control_function_comment_begin, control_function_comment_end
from klever.core.vtg.emg.translation.fsa_translator.common import initialize_automaton_variables


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

    # Intialize repeat counters
    for behaviour in (b for b in automaton.process.actions.behaviour()
                      if isinstance(b, Behaviour) and isinstance(b.description, Subprocess) and
                         isinstance(b.repeat, int)):
        var = __repeate_subprocess_var_name(automaton, behaviour)
        v_code.append("int {} = {};".format(var, behaviour.repeat))

    main_v_code, main_f_code = __subprocess_code(automaton, automaton.process.actions.initial_action)
    v_code += main_v_code
    f_code += main_f_code + ["/* End of the process */"]
    if ret_expression:
        f_code.append(ret_expression)

    processed = set()
    for subp in automaton.process.actions.filter(include={Subprocess}):
        if subp.name not in processed:
            first_actual_state = subp.action
            sp_v_code, sp_f_code = __subprocess_code(automaton, first_actual_state)

            v_code.extend(sp_v_code)
            f_code.extend([
                '',
                '/* Subprocess {} */'.format(subp.name),
                'emg_{}_{}:'.format(str(subp.name), str(automaton))
            ])
            f_code.extend(sp_f_code)
            f_code.append("/* End of the subprocess '{}' */".format(subp.name))
            if ret_expression:
                f_code.append(ret_expression)
            processed.add(subp.name)

    comment_data = {'name': 'aux_variables_declaration'}
    v_code = [model_comment('ACTION_BEGIN', 'Declare auxiliary variables.', comment_data)] + \
             v_code + \
             [model_comment('ACTION_END', other=comment_data)]
    if model:
        name = automaton.process.name
        v_code.insert(0, control_function_comment_begin(cf.name, automaton.process.comment))
    else:
        name = '{}({})'.format(automaton.process.name, automaton.process.category)
        v_code.insert(0, control_function_comment_begin(cf.name, automaton.process.comment, automaton.identifier))
    f_code.append(control_function_comment_end(cf.name, name))
    cf.body.extend(v_code + f_code)

    return cf.name


def __repeate_subprocess_var_name(automaton, behaviour):
    behaviours = sorted([b for b in automaton.process.actions.behaviour(behaviour.name) if isinstance(b.repeat, int)])
    if len(behaviours) > 1:
        index = behaviours.index(behaviour)
        return f'emg_repeat_cnt_{behaviour.name}_{str(automaton)}_{index}'
    elif len(behaviours) == 1:
        return f'emg_repeat_cnt_{behaviour.name}_{str(automaton)}'
    else:
        raise NotImplementedError


def __subprocess_code(automaton, initial_action):

    def _serialize_action(behaviour, tab):
        v, f = [], []

        if isinstance(behaviour, Behaviour) and behaviour.kind is Subprocess:
            base_jump = [
                '\t' * tab + '/* Jump to a subprocess {!r} initial state */'.format(behaviour.name),
                '\t' * tab + 'goto emg_{}_{};'.format(behaviour.name, str(automaton))
            ]

            if isinstance(behaviour.repeat, int):
                var = __repeate_subprocess_var_name(automaton, behaviour)

                base_jump = ['\t' * tab + f'if ({var} > 0)' + ' {',
                             '\t' * (tab + 1) + f'{var}--;'] + \
                            ['\t' + s for s in base_jump] + \
                            ['\t' * tab + '} else {',
                             '\t' * (tab + 1) + 'ldv_assume(0);',
                             '\t' * tab + '}']
            elif isinstance(behaviour.repeat, str):
                access = automaton.process.resolve_access(f'%{behaviour.repeat}%')
                if not access or not access.label:
                    raise ValueError(f"Unknown label '{behaviour.repeat}' in process '{str(automaton.process)}'")
                var = automaton.determine_variable(access.label)
                base_jump = ['\t' * tab + f'if ({var.name})' + ' {'] + \
                            ['\t' + s for s in base_jump] + \
                            ['\t' * tab + '} else {',
                             '\t' * (tab + 1) + 'ldv_assume(0);',
                             '\t' * tab + '}']

            f += base_jump
        if isinstance(behaviour, Behaviour):
            my_v, my_f = automaton.code[hash(behaviour)]
            v += my_v
            f += ['\t' * tab + stm for stm in my_f]
        elif isinstance(behaviour, Choice):
            if len(behaviour) == 2:
                act1, act2 = behaviour
                act1_v, act1_f = _serialize_action(act1, tab + 1)
                act2_v, act2_f = _serialize_action(act2, tab + 1)

                v += act1_v + act2_v
                f += ['\t' * tab + 'if (ldv_undef_int()) {'] + act1_f + ['\t' * tab + '} else {'] + \
                     act2_f + ['\t' * tab + '}']
            elif len(behaviour) > 2:
                f += ['\t' * tab + 'switch (ldv_undef_int()) {']
                for case, branch in enumerate(behaviour):
                    branch_v, branch_f = _serialize_action(branch, tab + 2)
                    v += branch_v
                    f += ['\t' * (tab + 1) + 'case {}: '.format(case) + '{'] + branch_f + \
                         ['\t' * (tab + 2) + 'break;', '\t' * (tab + 1) + '}']
                f += ['\t' * (tab + 1) + 'default: ldv_assume(0);', '\t' * tab + '}']
            else:
                raise ValueError("Invalid number of conditions in '%s': %d" % (str(behaviour), len(behaviour)))
        elif isinstance(behaviour, Concatenation):
            for itm in behaviour:
                itm_v, itm_f = _serialize_action(itm, tab)
                v += itm_v
                f += [''] + itm_f

            # Remove the first empty string
            if f:
                f.pop(0)
        elif isinstance(behaviour, Parentheses):
            return _serialize_action(behaviour[0], tab)
        else:
            raise NotImplementedError

        return v, f

    return _serialize_action(initial_action, 0)
