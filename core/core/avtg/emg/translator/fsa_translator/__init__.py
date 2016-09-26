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
from core.avtg.emg.common import get_conf_property, get_necessary_conf_property
from core.avtg.emg.common.signature import Pointer, Primitive, import_declaration
from core.avtg.emg.common.process import Receive, Dispatch, Call, CallRetval, Condition, Subprocess,\
    get_common_parameter
from core.avtg.emg.translator.code import FunctionDefinition
from core.avtg.emg.translator.fsa_translator.common import action_model_comment, model_comment, \
    extract_relevant_automata, choose_file, registration_intf_check


class FSATranslator(metaclass=abc.ABCMeta):

    def __init__(self, logger, conf, analysis, cmodel, entry_fsa, model_fsa, callback_fsa):
        self._cmodel = cmodel
        self._entry_fsa = entry_fsa
        self._model_fsa = model_fsa
        self._callback_fsa = callback_fsa
        self._conf = conf
        self._analysis = analysis
        self._logger = logger
        self._structures = dict()
        self._control_functions = dict()
        self._logger.info("Include extra header files if necessary")

        # Get from unused interfaces
        header_list = list()
        for interface in (self._analysis.get_intf(i) for i in self._analysis.interfaces):
            if len(interface.declaration.implementations) == 0 and interface.header:
                for header in interface.header:
                    if header not in header_list:
                        header_list.append(header)

        # Get from specifications
        for process in (a.process for a in self._model_fsa + self._callback_fsa if len(a.process.headers) > 0):
            for header in process.headers:
                if header not in header_list:
                    header_list.append(header)

        # Generate aspect
        self._cmodel.add_before_aspect(('#include <{}>'.format(h) for h in header_list))
        self._logger.info("Have added {!s} additional headers".format(len(header_list)))

        # Generates base code blocks
        self._logger.info("Start the preparation of actions code")
        for automaton in self._callback_fsa + self._model_fsa + [self._entry_fsa]:
            self._logger.debug("Generate code for instance {} of process '{}' of categorty '{}'".
                               format(automaton.identifier, automaton.process.name, automaton.process.category))
            for state in sorted(automaton.fsa.states, key=attrgetter('identifier')):
                self.__compose_action(state, automaton)

        # Start generation of control functions
        for automaton in self._callback_fsa + self._model_fsa + [self._entry_fsa]:
            self._compose_control_function(automaton)

        # Generate aspects with kernel models
        for automaton in self._model_fsa:
            aspect_code = [
                model_comment('KERNEL_MODEL', 'Perform the model code of the function {!r}'.
                              format(automaton.process.name))
            ]
            function_obj = self._analysis.get_kernel_function(automaton.process.name)
            params = []
            for position, param in enumerate(function_obj.declaration.parameters):
                if type(param) is str:
                    params.append(param)
                else:
                    params.append('$arg{}'.format(str(position + 1)))

            ret_expression = ''
            if len(params) == 0 and function_obj.declaration.return_value.identifier == 'void':
                argiments = []
            elif len(params) == 0:
                argiments = ['$res']
                ret_expression = 'return '
            elif function_obj.declaration.return_value.identifier == 'void':
                argiments = ['0'] + params
            else:
                ret_expression = 'return '
                argiments = ['$res'] + params

            invoke = '{}{}({});'.format(ret_expression, self._control_function(automaton).name, ', '.join(argiments))
            aspect_code.append(invoke)

            self._cmodel.add_function_model(function_obj, aspect_code)

        # Generate entry point function
        self._entry_point()

        # Add types
        self._cmodel.types = list(self._structures.values())

        return

    def __compose_action(self, state, automaton):
        def compose_single_action(st, code, v_code, conditions, comments):
            final_code = list()
            final_code.append(comments[0])

            # Skip or assert action according to conditions
            if len(st.predecessors) > 0 and len(list(st.predecessors)[0].successors) > 1 and len(conditions) > 0:
                final_code.append('ldv_assume({});'.format(' && '.join(conditions)))
                final_code.extend(code)
            elif len(conditions) > 0 and len(code) > 0:
                final_code.append('if ({}) '.format(' && '.join(conditions)) + '{')
                final_code.extend(['\t{}'.format(s) for s in code])
                final_code.append('}')
            elif len(code) > 0:
                final_code.extend(code)

            if len(comments) == 2:
                final_code.append(comments[1])

            # Append trailing empty space
            final_code.append('')
            st.code = (v_code, final_code)

        if type(state.action) is Call:
            for st, code, v_code, conditions, comments in self._call(state, automaton):
                compose_single_action(st, code, v_code, conditions, comments)
        else:
            if type(state.action) is Dispatch:
                code_generator = self._dispatch
            elif type(state.action) is Receive:
                code_generator = self._receive
            elif type(state.action) is CallRetval:
                code_generator = self._call_retval
            elif type(state.action) is Condition:
                code_generator = self._condition
            elif type(state.action) is Subprocess:
                code_generator = self._subprocess
            elif state.action is None:
                code_generator = self._art_action
            else:
                raise TypeError('Unknown action type: {!r}'.format(type(state.action).__name__))

            code, v_code, conditions, comments = code_generator(state, automaton)
            compose_single_action(state, code, v_code, conditions, comments)

    def save_digraph(self, directory):
        # todo: port it
        raise NotImplementedError
        # Generate graph
        self.logger.info("Generate graph for automaton based on process {} with category {}".
                         format(self.process.name, self.process.category))
        dg_file = "{}/{}.dot".format(directory, "{}_{}_{}".
                                     format(self.process.category, self.process.name, self.identifier))

        graph = graphviz.Digraph(
            name=str(self.identifier),
            comment="Digraph for FSA {} based on self.process {} with category {}".
                    format(self.identifier, self.process.name, self.process.category),
            format="png"
        )

        # Add self.process description
        graph.node(
            self.process.name,
            "self.process: {}".format(self.process.process),
            {
                "shape": "rectangle"
            }
        )

        # Add subself.process description
        for subp in [self.process.actions[name] for name in sorted(self.process.actions.keys())
                       if type(self.process.actions[name]) is Subprocess]:
            graph.node(
                subp.name,
                "Subprocess {}: {}".format(subp.name, subp.process),
                {
                    "shape": "rectangle"
                }
            )

        subprocesses = {}
        for state in automaton.fsa.states:
            label = "Action {}: {}\n".format(state.identifier, state.desc['label'])

            if 'guard' in state.code and len(state.code['guard']) > 0:
                label += 'Guard: ' + ' && '.join(state.code['guard'])
                label += '\n'

            if type(state.action) is Call and 'invoke' in state.code:
                if 'file' in state.code:
                    label += "File: '{}'\n".format(state.code['file'])
                call = ''
                if 'pre_call' in state.code:
                    call += '\n'.join(state.code['pre_call'])
                    call += '\n'
                if 'retval' in state.code:
                    call += "{} = ".format(state.code['retval'])
                call += state.code['invoke']
                if 'check pointer' in state.code and state.code['check pointer']:
                    call += 'if ({})'.format(state.code['invoke']) + '\n\t'
                call += '(' + ', '.join(state.code['parameters']) + ')'
                if 'post_call' in state.code:
                    call += '\n'.join(state.code['post_call'])
                    call += '\n'
                label += call
            else:
                if 'body' in state.code and len(state.code['body']) > 0:
                    label += 'Body:\n' + '\n'.join(state.code['body'])

            if 'relevant automata' in state.code:
                label += '\nRelevant automata:\n'
                if len(state.code['relevant automata']) > 0:
                    for automaton in state.code['relevant automata'].values():
                        label += "Automaton '{}': '{}' ({})\n".format(automaton['automaton'].identifier,
                                                                      automaton['automaton'].process.name,
                                                                      automaton['automaton'].process.category)

            if type(state.action) is not Subprocess or state.action.name not in subprocesses:
                graph.node(str(state.identifier), label)
                if type(state.action) is Subprocess:
                    subprocesses[state.action.name] = state.identifier

        for state in automaton.fsa.states:
            if type(state.action) is not Subprocess or state.identifier in subprocesses.values():
                for succ in state.successors:
                    if type(succ.action) is Subprocess:
                        graph.edge(
                            str(state.identifier),
                            str(subprocesses[succ.action.name])
                        )
                    else:
                        graph.edge(
                            str(state.identifier),
                            str(succ.identifier)
                    )

        if len(automaton.fsa._initial_states) > 1:
            name = 'Artificial initial state'
            graph.node(name, name)
            for entry in automaton.fsa._initial_states:
                graph.edge(
                    str(name),
                    str(entry.identifier)
                )

        # Save to dg_file
        graph.save(dg_file)
        graph.render()
        self.logger.debug("Graph image has been successfully rendered and saved")

    def _prepare_control_functions(self):
        raise NotImplementedError

    def _art_action(self, state, automaton):
        # Make comments
        code, v_code, conditions, comments = list(), list(), list(), list()
        comments.append(action_model_comment(state.action, 'Artificial state of a process {!r}'.
                                             format(automaton.process.name)))

        return code, v_code, conditions, comments

    def _dispatch(self, state, automaton):
        # Make comments
        code, v_code, conditions, comments = list(), list(), list(), list()
        comments.append(action_model_comment(state.action,
                                             'Signal dispatch {!r} of a process {!r} of an interface category '
                                             '{!r}'.format(state.action.name, automaton.process.name,
                                                           automaton.process.category)))

        # Determine peers to receive the signal
        automata_peers = dict()
        if len(state.action.peers) > 0:
            # Do call only if model which can be called will not hang
            extract_relevant_automata(self._callback_fsa + self._model_fsa + [self._entry_fsa],
                                      automata_peers, state.action.peers, Receive)
        else:
            # Generate comment
            code.append("/* Dispatch {!r} is not expected by any process, skipping the action */".
                        format(state.action.name))

        # Add given conditions from a spec
        conditions = []
        if state.action.condition and len(state.action.condition) > 0:
            for statement in state.action.condition:
                cn = self._cmodel.text_processor(automaton, statement)
                conditions.extend(cn)

        if len(automata_peers) > 0:
            # Add conditions on base of dispatches
            checks = self._relevant_checks(state)
            if len(checks) > 0:
                conditions.append(' || '.join(checks))

            # Generate artificial function
            body = []
            file = choose_file(self._cmodel, self._analysis, automaton)

            if not get_conf_property(self._conf, 'direct control functions call'):
                body = ['int ret;']

            # Check dispatch type
            replicative = False
            for name in automata_peers:
                for st in automata_peers[name]['states']:
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

            # Generate blocks on each receive to another process
            pre, blocks, post = self._dispatch_blocks(state, file, automaton, function_parameters, param_interfaces, automata_peers,
                                                      replicative)
            body.extend(pre)

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

            if len(function_parameters) > 0:
                df = FunctionDefinition(
                    "ldv_dispatch_{}_{}_{}".format(state.action.name, automaton.identifier, state.identifier),
                    self._cmodel.entry_file,
                    "void f({})".format(', '.
                                        join([function_parameters[index].to_string('arg{}'.format(index)) for index in
                                              range(len(function_parameters))])),
                    False
                )
            else:
                df = FunctionDefinition(
                    "ldv_dispatch_{}_{}_{}".format(state.action.name, automaton.identifier, state.identifier),
                    self._cmodel.entry_file,
                    "void f(void)",
                    False
                )
            body.extend(post)
            body.append('return;')
            df.body.extend(body)

            # Add function definition
            self._cmodel.add_function_definition(file, df)

            # Add additional declarations
            self._cmodel.propogate_aux_function(self._analysis, automaton, df)

            code.extend([
                '{}({});'.format(df.name, ', '.join(df_parameters))
            ])
        else:
            code.append('/* Skip the dispatch because there is no process to receive the signal */')

        return code, v_code, conditions, comments

    def _condition(self, state, automaton):
        code, v_code, conditions, comments = list(), list(), list(), list()

        # Make comments
        comments.append(action_model_comment(state.action,
                                             'Code fragment {!r} of a process {!r} of an interface category {!r}'.\
                                             format(state.action.name, automaton.process.name,
                                                    automaton.process.category),
                                             begin=True))
        comments.append(action_model_comment(state.action, None, begin=False))

        # Add additional conditions
        conditions = list()
        if state.action.condition and len(state.action.condition) > 0:
            for statement in state.action.condition:
                cn = self._cmodel.text_processor(automaton, statement)
                conditions.extend(cn)

        if state.action.statements:
            for statement in state.action.statements:
                code.extend(self._cmodel.text_processor(automaton, statement))

        return code, v_code, conditions, comments

    def _call(self, state, automaton):
        def ret_expression(st):
            # Generate external function retval
            ret_declaration = 'void'
            callback_return_expression = ''
            external_return_expression = ''
            ret_access = None
            if st.action.retlabel:
                ret_access = automaton.process.resolve_access(st.action.retlabel)
            else:
                ret_subprocess = [automaton.process.actions[name] for name in sorted(automaton.process.actions.keys())
                                  if type(automaton.process.actions[name]) is CallRetval and
                                  automaton.process.actions[name].callback == st.action.callback and
                                  automaton.process.actions[name].retlabel]
                if ret_subprocess:
                    ret_access = automaton.process.resolve_access(ret_subprocess[0].retlabel)

            if ret_access:
                suits = [access for access in ret_access if
                         (access.interface and
                          access.interface.declaration.compare(signature.points.return_value)) or
                         (not access.interface and access.label and
                          signature.points.return_value.identifier in (d.identifier for d
                                                                       in access.label.declarations))]
                if len(suits) > 0:
                    if suits[0].interface:
                        label_var = automaton.determine_variable(suits[0].label, suits[0].interface.identifier)
                    else:
                        label_var = automaton.determine_variable(suits[0].label)
                    ret_declaration = signature.points.return_value.to_string('')
                    callback_return_expression = 'return '
                    external_return_expression = suits[0].access_with_variable(label_var) + ' = '
                else:
                    raise RuntimeError("Cannot find a suitable label for return value of action '{}'".
                                       format(st.action.name))

            return ret_declaration, callback_return_expression, external_return_expression

        def match_parameters(declaration):
            # Try to match action parameters
            found_positions = dict()
            for label_index in range(len(st.action.parameters)):
                accesses = automaton.process.resolve_access(st.action.parameters[label_index])
                for acc in (a for a in accesses if a.list_interface and len(a.list_interface) > 0):
                    for position in (p for p in list(range(len(declaration.points.parameters)))[label_index:]
                                     if p not in found_positions):
                        parameter = declaration.points.parameters[position]
                        if (acc.list_interface[-1].declaration.compare(parameter) or
                                acc.list_interface[-1].declaration.pointer_alias(parameter)):
                            expression = acc.access_with_variable(
                                automaton.determine_variable(acc.label, acc.list_interface[0].identifier))
                            found_positions[position] = expression
                            break

            # Fulfil rest parameters
            pointer_params = []
            label_params = []
            for index in range(len(declaration.points.parameters)):
                if type(declaration.points.parameters[index]) is not str and index not in found_positions:
                    if type(declaration.points.parameters[index]) is not Primitive and \
                            type(declaration.points.parameters[index]) is not Pointer:
                        param_signature = declaration.points.parameters[index].take_pointer
                        pointer_params.append(index)
                    else:
                        param_signature = declaration.points.parameters[index]

                    lb, var = automaton.new_param("ldv_param_{}_{}".format(st.identifier, index),
                                                  param_signature, None)
                    label_params.append(lb)
                    expression = var.name

                    # Add string
                    found_positions[index] = expression

            return pointer_params, label_params, found_positions

        def manage_default_resources(label_parameters):
            # Add precondition and postcondition
            if len(label_parameters) > 0:
                pre_stments = []
                post_stments = []
                for label in sorted(list(set(label_parameters)), key=lambda lb: lb.name):
                    pre_stments.append('%{}% = $UALLOC(%{}%);'.format(label.name, label.name))
                    post_stments.append('$FREE(%{}%);'.format(label.name))

                pre_name = 'pre_call_{}'.format(st.identifier)
                pre_action = automaton.process.add_condition(pre_name, [], pre_stments)
                pre_st = automaton.fsa.add_new_predecessor(st, pre_action)
                self.__compose_action(pre_st, automaton)

                post_name = 'post_call_{}'.format(st.identifier)
                post_action = automaton.process.add_condition(post_name, [], post_stments)
                post_st = automaton.fsa.add_new_successor(st, post_action)
                self.__compose_action(post_st, automaton)

        def generate_function(st, callback_declaration, invoke, file, check, func_variable):
            pointer_params, label_parameters, external_parameters = match_parameters(callback_declaration)
            manage_default_resources(label_parameters)
            ret_declaration, callback_return_expression, external_return_expression = ret_expression(st)

            # Determine external function params
            resources = [signature.to_string('arg0')]
            callback_params = []
            for index in range(len(signature.points.parameters)):
                if type(signature.points.parameters[index]) is not str:
                    if index in pointer_params:
                        resources.append(signature.points.parameters[index].take_pointer.
                                         to_string('arg{}'.format(index + 1)))
                        callback_params.append('*arg{}'.format(index + 1))
                    else:
                        resources.append(signature.points.parameters[index].
                                         to_string('arg{}'.format(index + 1)))
                        callback_params.append('arg{}'.format(index + 1))
            callback_params = ", ".join(callback_params)
            resources = ", ".join(resources)

            fname = "ldv_{}_{}_{}_{}".format(automaton.process.name, st.action.name, automaton.identifier,
                                             st.identifier)
            function = FunctionDefinition(fname, file, "{} {}({})".format(ret_declaration, fname, resources), True)

            function.body.append(model_comment('callback', None, st.action.name))
            inv = []

            # Determine label params
            external_parameters = [external_parameters[i] for i in sorted(external_parameters.keys())]

            if check:
                f_invoke = external_return_expression + fname + '(' + ', '.join([invoke] + external_parameters) + ');'
                inv.append('if ({})'.format(invoke))
                inv.append('\t' + f_invoke)
                call = callback_return_expression + '(*arg0)' + '(' + callback_params + ')'
            else:
                f_invoke = external_return_expression + fname + '(' + \
                           ', '.join([func_variable] + external_parameters) + ');'
                inv.append(f_invoke)
                call = callback_return_expression + '({})'.format(invoke) + '(' + callback_params + ')'
            function.body.append('{};'.format(call))

            self._cmodel.add_function_definition(file, function)
            self._cmodel.add_function_declaration(choose_file(self._cmodel, self._analysis, automaton),
                                                  function, extern=True)
            self._cmodel.propogate_aux_function(self._analysis, automaton, function)

            return inv

        def add_post_conditions(st, inv):
            post_call = []
            if access.interface and access.interface.interrupt_context:
                post_call.append(self._cmodel.text_processor(automaton, '$SWITCH_TO_PROCESS_CONTEXT();'))

            if st.action.post_call and len(st.action.post_call) > 0:
                for stment in st.action.post_call:
                    post_call.extend(self._cmodel.text_processor(automaton, stment))

            if len(post_call) > 0:
                post_call.insert(0, '/* Callback post-call */')
                inv += post_call

            return inv

        def add_pre_conditions(st, inv):
            callback_pre_call = []
            if st.action.pre_call and len(st.action.pre_call) > 0:
                for stment in st.action.pre_call:
                    callback_pre_call.extend(self._cmodel.text_processor(automaton, stment))

            if access.interface and access.interface.interrupt_context:
                callback_pre_call.append(self._cmodel.text_processor(automaton, '$SWITCH_TO_IRQ_CONTEXT();'))

            if len(callback_pre_call) > 0:
                callback_pre_call.insert(0, '/* Callback pre-call */')
                inv = callback_pre_call + inv

            return inv

        def compose_action(st, declaration, invoke, file, check, func_variable):
            # Add an additional condition
            if st.action.condition and len(st.action.condition) > 0:
                for stment in st.action.condition:
                    cn = self._cmodel.text_processor(automaton, stment)
                    conditions.extend(cn)

            inv = generate_function(st, declaration, invoke, file, check, func_variable)
            inv = add_pre_conditions(st, inv)
            inv = add_post_conditions(st, inv)

            return inv

        # Determine callback implementations
        accesses = automaton.process.resolve_access(state.action.callback)
        generated_callbacks = []
        for access in accesses:
            if access.interface:
                signature = access.interface.declaration
                implementation = automaton.process.get_implementation(access)

                if implementation and self._analysis.callback_name(implementation.value):
                    invoke = '(' + implementation.value + ')'
                    file = implementation.file
                    check = False
                    func_variable = access.access_with_variable(automaton.determine_variable(access.label,
                                                                                        access.list_interface[0].
                                                                                        identifier))
                elif signature.clean_declaration:
                    invoke = access.access_with_variable(automaton.determine_variable(access.label,
                                                                                 access.list_interface[0].
                                                                                 identifier))
                    check = True
                    file = self._cmodel.entry_file
                    func_variable = invoke
                else:
                    invoke = None
            else:
                signature = access.label.prior_signature

                func_variable = automaton.determine_variable(access.label)
                if access.label.value and self._analysis.callback_name(access.label.value):
                    invoke = self._analysis.callback_name(access.label.value)
                    func_variable = func_variable.name
                    file = self._analysis.determine_original_file(access.label.value)
                    check = False
                else:
                    if func_variable:
                        invoke = access.access_with_variable(func_variable)
                        func_variable = func_variable.name
                        file = self._cmodel.entry_file
                        check = True
                    else:
                        invoke = None

            if invoke:
                if len(generated_callbacks) == 0:
                    st = state
                else:
                    st = automaton.fsa.clone_state(state)
                code, comments = list(), list()

                # Make comments
                comments.append(action_model_comment(state.action,
                                                     'Call callback {!r} of a process {!r} of an interface category '
                                                     '{!r}'.format(st.action.name, automaton.process.name,
                                                                   automaton.process.category),
                                                     begin=True))
                comments.append(action_model_comment(state.action, None, begin=False))

                relevant_automata = registration_intf_check(self._analysis,
                                                            self._callback_fsa + self._model_fsa + [self._entry_fsa],
                                                            self._model_fsa,
                                                            invoke)

                conditions = list()
                if not get_necessary_conf_property(self._conf, 'nested automata'):
                    checks = self._relevant_checks(relevant_automata)
                    if len(checks) > 0:
                        conditions.append('ldv_assume({});'.format(' || '.join(checks)))

                inv = compose_action(st, signature, invoke, file, check, func_variable)
                code.extend(inv)
                
                generated_callbacks.append((st, code, list(), conditions, comments))

        if len(generated_callbacks) == 0:
            code, comments = list(), list()

            # Make comments
            comments.append(action_model_comment(state.action,
                                                 'Call callback {!r} of a process {!r} of an interface category {!r}'.\
                                                 format(state.action.name, automaton.process.name,
                                                        automaton.process.category),
                                                 begin=True))
            comments.append(action_model_comment(state.action, None, begin=False))
            code.append('/* Skip callback without implementations */')
            generated_callbacks.append((state, code, list(), list(), comments))

        return generated_callbacks

    def _call_retval(self, state, automaton):
        # Add begin model comment
        code, v_code, conditions, comments = list(), list(), list(), list()
        comments.append(action_model_comment(state.action,
                                             'Callback return value expectation {!r} of a process {!r} of an '
                                             'interface category {!r}'.format(state.action.name, automaton.process.name,
                                                                              automaton.process.category),
                                             begin=True))
        comments.append(action_model_comment(state.action, None, begin=False))
        code.append('/* Return value expectation is not supported in the current version of EMG */')

        return code, v_code, conditions, comments

    def _subprocess(self, state, automaton):
        code, v_code, conditions, comments = list(), list(), list(), list()

        # Make comments
        comments.append(action_model_comment(state.action,
                                             'Code fragment {!r} of a process {!r} of an interface category {!r}'.
                                             format(state.action.name, automaton.process.name,
                                                    automaton.process.category),
                                             begin=True))
        comments.append(action_model_comment(state.action, None, begin=False))

        # Add additional condition
        if state.action.condition and len(state.action.condition) > 0:
            for statement in state.action.condition:
                cn = self._cmodel.text_processor(automaton, statement)
                conditions.extend(cn)

        return code, v_code, conditions, comments

    @abc.abstractstaticmethod
    def _relevant_checks(self, relevent_automata):
        raise NotImplementedError

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
    
    def _call_cf(self, file, automaton, parameter='0'):
        self._cmodel.add_function_declaration(file, self._control_function(automaton), extern=True)

        if get_conf_property(self._conf, 'direct control functions calls'):
            return '{}({});'.format(self._control_function(automaton).name, parameter)
        else:
            return self._call_cf_code(file, automaton, parameter)

    def _join_cf(self, file, automaton):
        self._cmodel.add_function_declaration(file, self._control_function(automaton), extern=True)

        if get_conf_property(self._conf, 'direct control functions calls'):
            return '/* Skip thread join call */'
        else:
            return self._join_cf_code(file, automaton)

    @abc.abstractstaticmethod
    def _receive(self, state, automaton):
        code, v_code, conditions, comments = list(), list(), list(), list()

        # Make comments
        comments.append(action_model_comment(state.action,
                                             'Receive signal {!r} of a process {!r} of an interface category {!r}'.\
                                             format(state.action.name, automaton.process.name,
                                                    automaton.process.category),
                                             begin=True))
        comments.append(action_model_comment(state.action, None, begin=False))

        return code, v_code, conditions, comments

    def _control_function(self, automaton):
        if automaton.identifier not in self._control_functions:
            # Check that this is an aspect function or not
            name = 'ldv_control_function_' + str(automaton.identifier)
            if automaton in self._model_fsa:
                function_obj = self._analysis.get_kernel_function(automaton.process.name)
                params = []
                for position, param in enumerate(function_obj.declaration.parameters):
                    if type(param) is str:
                        params.append(param)
                    else:
                        params.append(param.to_string('arg{}'.format(str(position + 1))))

                if len(params) == 0 and function_obj.declaration.return_value.identifier == 'void':
                    param_types = ['void']
                elif len(params) == 0:
                    param_types = [function_obj.declaration.return_value.to_string('res')]
                elif function_obj.declaration.return_value.identifier == 'void':
                    param_types = ['void *'] + params
                else:
                    param_types = [function_obj.declaration.return_value.to_string('res')] + params

                declaration = '{0} f({1})'.format(function_obj.declaration.return_value.to_string(''),
                                                  ', '.join(param_types))
                cf = FunctionDefinition(name, self._cmodel.entry_file, declaration, False)
            else:
                cf = FunctionDefinition(name, self._cmodel.entry_file, 'void f(void *cf_arg)', False)

            self._control_functions[automaton.identifier] = cf

        return self._control_functions[automaton.identifier]
    
    @abc.abstractstaticmethod
    def _join_cf_code(self, file, automaton):
        raise NotImplementedError

    @abc.abstractstaticmethod
    def _call_cf_code(self, file, automaton, parameter='0'):
        raise NotImplementedError

    @abc.abstractstaticmethod
    def _dispatch_blocks(self, state, file, automaton, function_parameters, param_interfaces, automata_peers, replicative):
        raise NotImplementedError

    @abc.abstractstaticmethod
    def _compose_control_function(self, automaton):
        raise NotImplementedError

    @abc.abstractstaticmethod
    def _entry_point(self):
        raise NotImplementedError

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
