#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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

import abc
from operator import attrgetter
from core.avtg.emg.common import get_necessary_conf_property
from core.avtg.emg.common.process import Receive, Dispatch, Call, CallRetval, Condition, Subprocess,\
    get_common_parameter
from core.avtg.emg.translator.code import FunctionDefinition, Variable
from core.avtg.emg.translator.fsa_translator.common import model_comment, extract_relevant_automata

class FSATranslator(metaclass=abc.ABCMeta):

    def __init__(self, logger, conf, analysis, cmodel, entry_fsa, model_fsa, main_fsa):
        self._cmodel = cmodel
        self._entry_fsa = entry_fsa
        self._model_fsa = model_fsa
        self._main_fsa = main_fsa
        self._conf = conf
        self._analysis = analysis
        self._logger = logger

        self._logger.info("Include extra header files if necessary")
        self.__include_extra_headers()

        self._logger.info("Start the preparation of actions code")
        self.__prepare_code_blocks()

    def __prepare_code_blocks(self):
        # Generates base code blocks
        for automaton in self.callback_fsa + self._model_fsa + [self._entry_fsa]:
            self._logger.debug("Generate code for instance {} of process '{}' of categorty '{}'".
                               format(automaton.identifier, automaton.process.name, automaton.process.category))
            for state in sorted(automaton.fsa.states, key=attrgetter('identifier')):
                if type(state.action) is Dispatch:
                    code_generator = self._dispatch
                elif type(state.action) is Receive:
                    code_generator = self._receive
                elif type(state.action) is Call:
                    code_generator = self._call
                elif type(state.action) is CallRetval:
                    code_generator = self._call_retval
                elif type(state.action) is Condition:
                    code_generator = self._condition
                elif type(state.action) is Subprocess:
                    code_generator = self._subprocess
                elif type(state.action) is None:
                    code_generator = self._art_action
                else:
                    raise TypeError('Unknown action type: {!r}'.format(type(state.action).__name__))

                code, v_code, conditions, comments = code_generator(state, automaton)
                final_code = list()
                final_code.append(comments[0])

                # Skip or assert action according to conditions
                if len(state.predecessors) > 1 and len(conditions) > 0:
                    final_code.append('ldv_assume({});'.format(' && '.join(conditions)))
                    final_code.extend(code)
                elif len(conditions) > 0:
                    final_code.append('if ({}) '.format(' && '.join(conditions)) + '{')
                    final_code.extend(['\t{}'.format(s) for s in code])
                    final_code.append('}')
                else:
                    final_code.extend(code)

                if len(comments) == 2:
                    final_code.append(comments[1])

                state.code = (v_code, final_code)

    def _prepare_control_functions(self):
        pass

    @abc.abstractstaticmethod
    def _entry_point(self):
        pass

    @abc.abstractstaticmethod
    def _control_function(self):
        pass

    @abc.abstractstaticmethod
    def _art_action(self, state, automaton):
        # Add begin model comment
        code, v_code, conditions, comments = list(), list(), list(), list()
        conditions.append(model_comment(state.action, 'Artificial state {!r} of a process {!r}'.
                                                      format(state.action.name, automaton.process.name)))

        return code, v_code, conditions, comments

    @abc.abstractstaticmethod
    def _dispatch(self, state, automaton):
        # Add begin model comment
        code = list()
        code.append(model_comment(state.action, 'Signal dispatch {!r} of a process {!r} of an interface category '
                                                      '{!r}'.format(state.action.name, automaton.process.name,
                                                                  automaton.process.category)))

        # Generate dispatch function
        automata_peers = dict()
        if len(state.action.peers) > 0:
            # Do call only if model which can be called will not hang
            extract_relevant_automata(automata_peers, state.action.peers, Receive)
        else:
            # Generate comment
            code.append("/* Dispatch {!r} is not expected by any process, skipping the action */".
                        format(state.action.name))

        # Add additional condition
        conditions = []
        if state.action.condition and len(state.action.condition) > 0:
            for statement in state.action.condition:
                cn = self._cmodel.text_processor(statement)
                conditions.extend(cn)

        if not get_necessary_conf_property('nested automata'):
            checks = state._relevant_checks()
            if len(checks) > 0:
                conditions.append(' || '.join(checks))

        body = []
        file = self._choose_file(analysis, automaton)
        if not self._direct_cf_calls:
            body = ['int ret;']

        if len(state.code['relevant automata']) == 0:
            return ['/* Skip dispatch {} without processes to receive */'.format(state.action.name)]

        # Check dispatch type
        replicative = False
        for name in state.code['relevant automata']:
            for st in state.code['relevant automata'][name]['states']:
                if st.action.replicative:
                    replicative = True
                    break

        # Determine parameters
        param_interfaces = []
        df_parameters = []
        function_parameters = []

        # Add parameters
        for index in range(len(state.action.parameters)):
            # Determine dispatcher parameter
            interface = get_common_parameter(state.action, automaton.process, index)

            # Determine dispatcher parameter
            dispatcher_access = automaton.process.resolve_access(state.action.parameters[index],
                                                                 interface.identifier)
            variable = automaton.determine_variable(dispatcher_access.label, interface.identifier)
            dispatcher_expr = dispatcher_access.access_with_variable(variable)

            param_interfaces.append(interface)
            function_parameters.append(variable.declaration)
            df_parameters.append(dispatcher_expr)

        blocks = []
        if self._nested_automata:
            decl = self._get_cf_struct(automaton, function_parameters)
            cf_param = 'cf_arg'

            vf_param_var = Variable('cf_arg', None, decl, False)
            body.append(vf_param_var.declare() + ';')

            for index in range(len(function_parameters)):
                body.append('{}.arg{} = arg{};'.format(vf_param_var.name, index, index))
            body.append('')

            if replicative:
                for name in state.code['relevant automata']:
                    for r_state in state.code['relevant automata'][name]['states']:
                        block = []
                        call = self._call_cf(file,
                                             state.code['relevant automata'][name]['automaton'], '& ' + cf_param)
                        if r_state.action.replicative:
                            if self._direct_cf_calls:
                                block.append(call)
                            else:
                                block.append('ret = {}'.format(call))
                                block.append('ldv_assume(ret == 0);')
                            blocks.append(block)
                            break
                        else:
                            self.logger.warning(
                                'Cannot generate dispatch based on labels for receive {} in process {} with category {}'
                                    .format(r_state.action.name,
                                            state.code['relevant automata'][name]['automaton'].process.name,
                                            state.code['relevant automata'][name]['automaton'].process.category))
            else:
                for name in (n for n in state.code['relevant automata']
                             if len(state.code['relevant automata'][n]['states']) > 0):
                    call = self._join_cf(file, state.code['relevant automata'][name]['automaton'])
                    if self._direct_cf_calls:
                        block = [call]
                    else:
                        block = ['ret = {}'.format(call),
                                 'ldv_assume(ret == 0);']
                    blocks.append(block)
        else:
            for name in state.code['relevant automata']:
                for r_state in state.code['relevant automata'][name]['states']:
                    block = []

                    # Assign parameters
                    if len(function_parameters) > 0:
                        block.append("/* Transfer parameters */")

                        for index in range(len(function_parameters)):
                            # Determine exression
                            receiver_access = state.code['relevant automata'][name]['automaton'].process.\
                                resolve_access(r_state.action.parameters[index], param_interfaces[index].identifier)

                            # Determine var
                            var = state.code['relevant automata'][name]['automaton'].\
                                determine_variable(receiver_access.label, param_interfaces[index].identifier)
                            self._add_global_variable(var, self._choose_file(analysis, automaton), extern=True)

                            receiver_expr = receiver_access.access_with_variable(var)
                            block.append("{} = arg{};".format(receiver_expr, index))

                    # Update state
                    block.extend(['', "/* Switch state of the reciever */"])
                    block.extend(self._switch_state_code(analysis, state.code['relevant automata'][name]['automaton'],
                                                         r_state))
                    self._add_global_variable(state.code['relevant automata'][name]['automaton'].state_variable,
                                              self._choose_file(analysis, automaton), extern=True)

                    blocks.append(block)

        # Print body of a dispatching function
        if state.action.broadcast:
            for block in blocks:
                body.extend(block)
        else:
            if len(blocks) == 1:
                body.extend(blocks[0])
            elif len(blocks) == 2:
                for index in range(2):
                    if index == 0:
                        body.append('if (ldv_undef_int()) {')
                    else:
                        body.append('else {')
                    body.extend(['\t' + stm for stm in blocks[index]])
                    body.append('}')
            else:
                body.append('switch (ldv_undef_int()) {')
                for index in range(len(blocks)):
                    body.append('\tcase {}: '.format(index) + '{')
                    body.extend(['\t\t' + stm for stm in blocks[index]])
                    body.append('\t\tbreak;')
                    body.append('\t};')
                body.append('\tdefault: ldv_stop();')
                body.append('};')
        body.append('return;')

        if len(function_parameters) > 0:
            df = FunctionDefinition(
                "ldv_dispatch_{}_{}_{}".format(state.action.name, automaton.identifier, state.identifier),
                self.entry_file,
                "void f({})".format(', '.join([function_parameters[index].to_string('arg{}'.format(index)) for index in
                                               range(len(function_parameters))])),
                False
            )
        else:
            df = FunctionDefinition(
                "ldv_dispatch_{}_{}_{}".format(state.action.name, automaton.identifier, state.identifier),
                self.entry_file,
                "void f(void)",
                False
            )
        df.body.extend(body)

        # Add function definition
        self._cmodel.add_function_definition(file, df)

        # Add additional declarations
        self._cmodel.propogate_aux_function(self.analysis, automaton, df)

        code.extend([
            '{}({});'.format(df.name, ', '.join(df_parameters))
        ])

        return v_code, code

    @abc.abstractstaticmethod
    def _receive(self, state, automaton):
        code, v_code, conditions, comments = list(), list(), list(), list()

        # Make comments
        conditions.append(model_comment(state.action, 'Receive signal {!r} of a process {!r} of an '
                                                      'interface category {!r}'.
                                                      format(state.action.name, automaton.process.name,
                                                             automaton.process.category),
                                        begin=True))
        conditions.append(model_comment(state.action, '', begin=False))

        automata_peers = {}
        if len(state.action.peers) > 0:
            # Do call only if model which can be called will not hang
            extract_relevant_automata(automata_peers, state.action.peers, Dispatch)

            # Add additional condition
            if state.action.condition and len(state.action.condition) > 0:
                for statement in state.action.condition:
                    cn = self._cmodel.text_processor(statement)
                    conditions.extend(cn)
        else:
            # Generate comment
            code.append("/* Signal receive {!r} does not expect any signal from existing processes, skip it */".
                        format(state.action.name))

        param_declarations = []
        param_expressions = []

        if len(state.action.parameters) > 0:
            for index in range(len(state.action.parameters)):
                # Determine dispatcher parameter
                interface = get_common_parameter(state.action, automaton.process, index)

                # Determine receiver parameter
                receiver_access = automaton.process.resolve_access(state.action.parameters[index],
                                                                   interface.identifier)
                var = automaton.determine_variable(receiver_access.label, interface.identifier)
                receiver_expr = receiver_access.access_with_variable(var)

                param_declarations.append(var.declaration)
                param_expressions.append(receiver_expr)

        if get_necessary_conf_property('nested automata'):
            if state.action.replicative:
                if len(param_declarations) > 0:
                    decl = self._get_cf_struct(automaton, [val for val in param_declarations])
                    var = Variable('cf_arg_struct', None, decl.take_pointer, False)
                    v_code.append('/* Received labels */')
                    v_code.append('{} = ({}*) arg0;'.format(var.declare(), decl.to_string('')))
                    v_code.append('')

                    code.append('')
                    code.append('/* Assign recieved labels */')
                    code.append('if (cf_arg_struct) {')
                    for index in range(len(param_expressions)):
                        code.append('\t{} = cf_arg_struct->arg{};'.format(param_expressions[index], index))
                    code.append('}')
            else:
                code.append('/* Skip {} */'.format(state.desc['label']))
        else:
            code.append("/* Automaton itself cannot perform receive '{}' */".format(state.action.name))

        return code, v_code, conditions, comments

    @abc.abstractstaticmethod
    def _condition(self, state, automaton):
        code, v_code, conditions, comments = list(), list(), list(), list()

        # Make comments
        conditions.append(model_comment(state.action, 'Code fragment {!r} of a process {!r} of an interface category '
                                                      '{!r}'.format(state.action.name, automaton.process.name,
                                                                    automaton.process.category),
                                        begin=True))
        conditions.append(model_comment(state.action, '', begin=False))

        # Add additional conditions
        conditions = list()
        if state.action.condition and len(state.action.condition) > 0:
            for statement in state.action.condition:
                cn = self._cmodel.text_processor(statement)
                conditions.extend(cn)

        if state.action.statements:
            for statement in state.action.statements:
                code.extend(self._cmodel.text_processor(statement))

        return code, v_code, conditions, comments

    @abc.abstractstaticmethod
    def _call(self):
        base_case = {
            "guard": [],
            "body": [],
        }

        if type(state.action) is Call:
            self.logger.debug("Prepare code for callback call '{}' in automaton '{}' for process '{}' of category "
                              "'{}'".format(state.action.name, self.identifier, self.process.name,
                                            self.process.category))
            accesses = self.process.resolve_access(state.action.callback)
            callbacks = []

            for access in accesses:
                if access.interface:
                    signature = access.interface.declaration
                    implementation = self.process.get_implementation(access)

                    if implementation and analysis.callback_name(implementation.value):
                        invoke = '(' + implementation.value + ')'
                        file = implementation.file
                        check = False
                        func_variable = access.access_with_variable(self.determine_variable(access.label,
                                                                                            access.list_interface[0].
                                                                                            identifier))
                    elif signature.clean_declaration:
                        invoke = access.access_with_variable(self.determine_variable(access.label,
                                                                                     access.list_interface[0].
                                                                                     identifier))
                        func_variable = invoke
                        file = translator.entry_file
                        check = True
                    else:
                        invoke = None
                else:
                    signature = access.label.prior_signature

                    func_variable = self.determine_variable(access.label)
                    if access.label.value and analysis.callback_name(access.label.value):
                        invoke = analysis.callback_name(access.label.value)
                        func_variable = func_variable.name
                        file = analysis.determine_original_file(access.label.value)
                        check = False
                    else:
                        if func_variable:
                            invoke = access.access_with_variable(func_variable)
                            func_variable = func_variable.name
                            file = translator.entry_file
                            check = True
                        else:
                            invoke = None

                if invoke:
                    new_case = copy.deepcopy(base_case)
                    additional_checks = translator.registration_intf_check(analysis, model, invoke)
                    if len(list(additional_checks.keys())) > 0:
                        new_case['relevant automata'] = additional_checks

                    if len(callbacks) == 0:
                        st = state
                    else:
                        st = self.fsa.clone_state(state)

                    if access.interface and access.interface.interrupt_context:
                        new_case['pre_call'] = [
                            "/* Callback pre-call */"
                        ]
                        new_case['pre_call'].extend(
                            self._cmodel.text_processor(self.process, '$SWITCH_TO_IRQ_CONTEXT();'))
                        new_case['post_call'] = [
                            "/* Callback post-call */"
                        ]
                        new_case['post_call'].extend(
                            self._cmodel.text_processor(self.process, '$SWITCH_TO_PROCESS_CONTEXT();'))
                    callbacks.append([st, new_case, signature, invoke, file, check, func_variable])

            if len(callbacks) > 0:
                for st, case, signature, invoke, file, check, func_variable in callbacks:
                    self.logger.debug("Prepare callback call '{}'".format(invoke))
                    # Generate function call and corresponding function
                    params = []
                    pointer_params = []
                    label_params = []
                    cb_statements = []

                    # Try to match action parameters
                    found_positions = dict()
                    for label_index in range(len(st.action.parameters)):
                        accesses = self.process.resolve_access(st.action.parameters[label_index])
                        for acc in (a for a in accesses if a.list_interface and len(a.list_interface) > 0):
                            for position in (p for p in list(range(len(signature.points.parameters)))[label_index:]
                                             if p not in found_positions):
                                parameter = signature.points.parameters[position]
                                if (acc.list_interface[-1].declaration.compare(parameter) or
                                        acc.list_interface[-1].declaration.pointer_alias(parameter)):
                                    expression = acc.access_with_variable(
                                        self.determine_variable(acc.label, acc.list_interface[0].identifier))
                                    found_positions[position] = expression
                                    break

                    # Fulfil rest parameters
                    for index in range(len(signature.points.parameters)):
                        if type(signature.points.parameters[index]) is not str and index not in found_positions:
                            if type(signature.points.parameters[index]) is not Primitive and \
                                    type(signature.points.parameters[index]) is not Pointer:
                                param_signature = signature.points.parameters[index].take_pointer
                                pointer_params.append(index)
                            else:
                                param_signature = signature.points.parameters[index]

                            lb, var = self.new_param("ldv_param_{}_{}".format(st.identifier, index),
                                                     param_signature, None)
                            label_params.append(lb)
                            expression = var.name

                            # Add string
                            found_positions[index] = expression

                    # Print params
                    params = [found_positions[i] for i in sorted(found_positions.keys())]

                    # Add precondition and postcondition
                    if len(label_params) > 0:
                        pre_statements = []
                        post_statements = []
                        for label in sorted(list(set(label_params)), key=lambda lb: lb.name):
                            pre_statements.append('%{}% = $UALLOC(%{}%);'.format(label.name, label.name))
                            post_statements.append('$FREE(%{}%);'.format(label.name))

                        pre_name = 'pre_call_{}'.format(st.identifier)
                        pre_action = self.process.add_condition(pre_name, [], pre_statements)
                        pre_st = self.fsa.add_new_predecessor(st, pre_action)
                        self.generate_meta_code(analysis, model, translator, pre_st)

                        post_name = 'post_call_{}'.format(st.identifier)
                        post_action = self.process.add_condition(post_name, [], post_statements)
                        post_st = self.fsa.add_new_successor(st, post_action)
                        self.generate_meta_code(analysis, model, translator, post_st)

                    # Generate return value assignment
                    ret_access = None
                    if st.action.retlabel:
                        ret_access = self.process.resolve_access(st.action.retlabel)
                    else:
                        ret_subprocess = [self.process.actions[name] for name in sorted(self.process.actions.keys())
                                          if type(self.process.actions[name]) is CallRetval and
                                          self.process.actions[name].callback == st.action.callback and
                                          self.process.actions[name].retlabel]
                        if ret_subprocess:
                            ret_access = self.process.resolve_access(ret_subprocess[0].retlabel)

                    # Match label
                    if ret_access:
                        suits = [access for access in ret_access if
                                 (access.interface and
                                  access.interface.declaration.compare(signature.points.return_value)) or
                                 (not access.interface and access.label and
                                  signature.points.return_value.identifier in (d.identifier for d
                                                                               in access.label.declarations))]
                        if len(suits) > 0:
                            if suits[0].interface:
                                label_var = self.determine_variable(suits[0].label, suits[0].interface.identifier)
                            else:
                                label_var = self.determine_variable(suits[0].label)
                            retval = suits[0].access_with_variable(label_var)
                            case['retval'] = retval
                        else:
                            raise RuntimeError("Cannot find a suitable label for return value of action '{}'".
                                               format(state.action.name))

                    # Add additional condition
                    if state.action.condition and len(state.action.condition) > 0:
                        for statement in state.action.condition:
                            cn = self._cmodel.text_processor(statement)
                            base_case["guard"].extend(cn)

                    if st.action.pre_call and len(st.action.pre_call) > 0:
                        pre_call = []
                        for statement in st.action.pre_call:
                            pre_call.extend(self._cmodel.text_processor(statement))

                        if 'pre_call' not in case:
                            case['pre_call'] = ['/* Callback pre-call */'] + pre_call
                        else:
                            # Comment + user pre-call + interrupt switch
                            case['pre_call'] = ['/* Callback pre-call */'] + pre_call + case['pre_call'][1:]

                    if st.action.post_call and len(st.action.post_call) > 0:
                        post_call = []
                        for statement in st.action.post_call:
                            post_call.extend(self._cmodel.text_processor(statement))

                        if 'post_call' not in case:
                            case['post_call'] = ['/* Callback post-call */'] + post_call
                        else:
                            # Comment + user post-call + interrupt switch
                            case['post_call'] = ['/* Callback pre-call */'] + pre_call + case['post_call'][1:]

                    # Generate comment
                    case["parameters"] = params
                    case["pointer parameters"] = pointer_params
                    case["callback"] = signature
                    case["check pointer"] = check
                    case["invoke"] = invoke
                    case["body"].append("/* Call callback {} */".format(st.action.name))
                    case["body"].extend(cb_statements)
                    case['file'] = file
                    case['variable'] = func_variable
                    st.code = case
            else:
                # Generate comment
                base_case["body"].append("/* Skip callback call {} without an implementation */".
                                         format(state.action.name))
                state.code = base_case



        block = []
        v_code = []

        if type(state.action) is Call:
            if not self._nested_automata:
                checks = state._relevant_checks()
                if len(checks) > 0:
                    block.append('ldv_assume({});'.format(' || '.join(checks)))

            call = self._call(analysis, automaton, state)
            block.extend(call)
        elif type(state.action) is CallRetval:
            block.append('/* Skip {} */'.format(state.desc['label']))
        elif type(state.action) is Condition:
            for stm in state.code['body']:
                block.append(stm)
        elif type(state.action) is Dispatch:
            if not self._nested_automata:
                checks = state._relevant_checks()
                if len(checks) > 0:
                    block.append('ldv_assume({});'.format(' || '.join(checks)))

            call = self._dispatch(analysis, automaton, state)

            block.extend(call)
        elif type(state.action) is Receive:
            param_declarations = []
            param_expressions = []

            if len(state.action.parameters) > 0:
                for index in range(len(state.action.parameters)):
                    # Determine dispatcher parameter
                    interface = get_common_parameter(state.action, automaton.process, index)

                    # Determine receiver parameter
                    receiver_access = automaton.process.resolve_access(state.action.parameters[index],
                                                                       interface.identifier)
                    var = automaton.determine_variable(receiver_access.label, interface.identifier)
                    receiver_expr = receiver_access.access_with_variable(var)

                    param_declarations.append(var.declaration)
                    param_expressions.append(receiver_expr)

            if self._nested_automata:
                if state.action.replicative:
                    if len(param_declarations) > 0:
                        decl = self._get_cf_struct(automaton, [val for val in param_declarations])
                        var = Variable('cf_arg_struct', None, decl.take_pointer, False)
                        v_code.append('/* Received labels */')
                        v_code.append('{} = ({}*) arg0;'.format(var.declare(), decl.to_string('')))
                        v_code.append('')

                        block.append('')
                        block.append('/* Assign recieved labels */')
                        block.append('if (cf_arg_struct) {')
                        for index in range(len(param_expressions)):
                            block.append('\t{} = cf_arg_struct->arg{};'.format(param_expressions[index], index))
                        block.append('}')
                else:
                    block.append('/* Skip {} */'.format(state.desc['label']))
            else:
                block.append("/* Automaton itself cannot perform receive '{}' */".format(state.action.name))
        elif type(state.action) is Subprocess:
            for stm in state.code['body']:
                block.append(stm)
        elif state.action is None:
            # Artificial state
            block.append("/* {} */".format(state.desc['label']))
        else:
            raise ValueError('Unexpected state action')

        return v_code, block

    @abc.abstractstaticmethod
    def _call_retval(self, state, automaton):
        # Add begin model comment
        code, v_code, conditions, comments = list(), list(), list(), list()
        conditions.append(model_comment(state.action, 'Callback return value expectation {!r} of a process {!r} of an '
                                                      'interface category {!r}'.
                                                      format(state.action.name, automaton.process.name,
                                                             automaton.process.category),
                                        begin=True))
        conditions.append(model_comment(state.action, '', begin=False))
        code.append('/* Return value expectation is not supported in the current version of EMG */')

        return code, v_code, conditions, comments

    @abc.abstractstaticmethod
    def _subprocess(self, state, automaton):
        code, v_code, conditions, comments = list(), list(), list(), list()

        # Make comments
        conditions.append(model_comment(state.action, 'Code fragment {!r} of a process {!r} of an interface category '
                                                      '{!r}'.format(state.action.name, automaton.process.name,
                                                                    automaton.process.category),
                                        begin=True))
        conditions.append(model_comment(state.action, '', begin=False))

        # Add additional condition
        if state.action.condition and len(state.action.condition) > 0:
            for statement in state.action.condition:
                cn = self._cmodel.text_processor(statement)
                conditions.extend(cn)

        return code, v_code, conditions, comments

    def __include_extra_headers(self):
        extra_aspects = list()

        # Get from unused interfaces
        header_list = list()
        for interface in (self.analysis.get_intf(i) for i in self.analysis.interfaces):
            if len(interface.declaration.implementations) == 0 and interface.header:
                for header in interface.header:
                    if header not in header_list:
                        header_list.append(header)

        # Get from specifications
        for process in (a.process for a in self.model_fsa + self.main_fsa if len(a.process.headers) > 0):
            for header in process.headers:
                if header not in header_list:
                    header_list.append(header)

        # Generate aspect
        self._cmodel.add_before_aspect(('#include <{}>'.format(h) for h in header_list))

        self.logger.info("Have added {!s} additional headers".format(len(header_list)))
        return extra_aspects

    def _get_cf_struct(self, automaton, params):
        cache_identifier = ''
        for param in params:
            cache_identifier += param.identifier

        if cache_identifier not in self._structures:
            struct_name = 'ldv_struct_{}_{}'.format(automaton.process.name, automaton.identifier)
            if struct_name in self._structures:
                raise KeyError('Structure name is not unique')

            decl = import_declaration('struct {} a'.format(struct_name))
            for index in range(len(params)):
                decl.fields['arg{}'.format(index)] = params[index]
            decl.fields['signal_pending'] = import_declaration('int a')

            self._structures[cache_identifier] = decl
        else:
            decl = self._structures[cache_identifier]

        return decl

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
