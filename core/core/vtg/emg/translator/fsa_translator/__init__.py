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

import graphviz

from core.vtg.emg.common import get_conf_property, get_necessary_conf_property, model_comment
from core.vtg.emg.common.signature import Pointer, Primitive, Structure, import_declaration
from core.vtg.emg.common.process import Receive, Dispatch, Call, CallRetval, Condition, Subprocess, \
    get_common_parameter
from core.vtg.emg.translator.code import FunctionDefinition
from core.vtg.emg.translator.fsa_translator.common import action_model_comment, extract_relevant_automata, choose_file, initialize_automaton_variables


class FSATranslator(metaclass=abc.ABCMeta):

    def __init__(self, logger, conf, analysis, cmodel, entry_fsa, model_fsa, event_fsa):
        """
        Initialize new FSA translator object. During the initialization an enviornment model in form of finite state
        machines with process-like actions is translated to C code. Translation includes the following steps: each pair
        label-interface is translated in a separate variable, each action is translated in code blocks (aux functions
        can be additionally generated), for each automaton a control function is generated, control functions for event
        modeling are called in a specific entry point function and control functions for function modeling are called
        insted of modelled functions. This class has an abstract methods to provide ability to implement different
        translators.

        :param logger: logging object.
        :param conf: Configuration properties dictionary.
        :param analysis: ModuleCategoriesSpecification object.
        :param cmodel: CModel object.
        :param entry_fsa: An entry point Automaton object.
        :param model_fsa: List with Automaton objects which correspond to function models.
        :param event_fsa:  List with Automaton objects for event modeling.
        """
        self._cmodel = cmodel
        self._entry_fsa = entry_fsa
        self._model_fsa = model_fsa
        self._event_fsa = event_fsa
        self._conf = conf
        self._analysis = analysis
        self._logger = logger
        self._structures = dict()
        self._control_functions = dict()
        self._logger.info("Include extra header files if necessary")

        # Get from unused interfaces
        # todo: it is possible to replace this using explicit list of headers
        header_list = list()
        for interface in (self._analysis.get_intf(i) for i in self._analysis.interfaces):
            if len(interface.declaration.implementations) == 0 and interface.header:
                for header in interface.header:
                    if header not in header_list:
                        header_list.append(header)

        # Get from specifications
        for process in (a.process for a in self._model_fsa + self._event_fsa if len(a.process.headers) > 0):
            for header in process.headers:
                if header not in header_list:
                    header_list.append(header)

        # Generate aspect
        self._cmodel.add_before_aspect(('#include <{}>\n'.format(h) for h in header_list))
        self._logger.info("Have added {!s} additional headers".format(len(header_list)))

        # Generates base code blocks
        self._logger.info("Start the preparation of actions code")
        for automaton in self._event_fsa + self._model_fsa + [self._entry_fsa]:
            self._logger.debug("Generate code for instance {} of process '{}' of categorty '{}'".
                               format(automaton.identifier, automaton.process.name, automaton.process.category))
            for state in sorted(automaton.fsa.states, key=attrgetter('identifier')):
                self._compose_action(state, automaton)

        # Make graph postprocessing
        for automaton in self._event_fsa + [self._entry_fsa]:
            self._normalize_event_fsa(automaton)
        for automaton in self._model_fsa:
            self._normalize_model_fsa(automaton)

        # Dump graphs
        if get_conf_property(self._conf, 'dump automata graphs'):
            self._save_digraphs()

        # Start generation of control functions
        for automaton in self._event_fsa + self._model_fsa + [self._entry_fsa]:
            self._compose_control_function(automaton)

        # Generate aspects with kernel models
        for automaton in self._model_fsa:
            aspect_code = [
                model_comment('KERNEL_MODEL', 'Perform the model code of the function {!r}'.
                              format(automaton.process.name))
            ]
            # todo: Get this signature either explicitly or using short code analysis
            function_obj = self._analysis.get_kernel_function(automaton.process.name)
            params = []
            for position, param in enumerate(function_obj.declaration.parameters):
                if type(param) is str:
                    params.append(param)
                else:
                    params.append('$arg{}'.format(str(position + 1)))

            if len(params) == 0 and function_obj.declaration.return_value.identifier == 'void':
                argгments = []
                ret_expression = ''
            elif len(params) == 0:
                argгments = []
                ret_expression = 'return '
            elif function_obj.declaration.return_value.identifier == 'void':
                argгments = params
                ret_expression = ''
            else:
                ret_expression = 'return '
                argгments = params

            invoke = '{}{}({});'.format(ret_expression, self._control_function(automaton).name, ', '.join(argгments))
            aspect_code.append(invoke)

            self._cmodel.add_function_model(function_obj, aspect_code)

        # Generate entry point function
        self._entry_point()

        # Add types
        self._cmodel.types = sorted(set(self._structures.values()), key=lambda t: t.identifier)

        return

    def _save_digraphs(self):
        """
        Method saves Automaton with code in doe format in debug purposes. This functionality can be turned on by setting
        corresponding configuration property. Each action is saved as a node and for each possible state transition
        an edge is added. This function can be called only if code blocks for each action of all automata are already
        generated.

        :return: None
        """

        # Print DOT files to this directory inside plugin working directory
        directory = 'automata'

        # Dump separetly all automata
        for automaton in self._event_fsa + self._model_fsa + [self._entry_fsa]:
            self._logger.debug("Generate graph for automaton based on process {} with category {}".
                               format(automaton.process.name, automaton.process.category))
            dg_file = "{}/{}.dot".format(directory, "{}_{}_{}".
                                         format(automaton.process.category, automaton.process.name,
                                                automaton.identifier))

            graph = graphviz.Digraph(
                name=str(automaton.identifier),
                comment="Digraph for FSA {} based on self.process {} with category {}".
                        format(automaton.identifier, automaton.process.name, automaton.process.category),
                format="png"
            )

            # Add self.process description
            graph.node(
                automaton.process.name,
                "self.process: {}".format(automaton.process.process),
                {
                    "shape": "rectangle"
                }
            )

            # Add subself.process description
            for subp in [automaton.process.actions[name] for name in sorted(automaton.process.actions.keys())
                           if type(automaton.process.actions[name]) is Subprocess]:
                graph.node(
                    subp.name,
                    "Subprocess {}: {}".format(subp.name, subp.process),
                    {
                        "shape": "rectangle"
                    }
                )

            subprocesses = {}
            for state in automaton.fsa.states:
                label = "Action {}: {}\l".format(state.identifier, state.desc['label'])
                label += '\l'.join(state.code[1])

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

            # Save to dg_file
            graph.save(dg_file)
            graph.render()
            self._logger.debug("Graph image has been successfully rendered and saved")

    def _prepare_control_functions(self):
        """
        Generate code of all control functions for each automata. It expects that all actions are already transformed into
        code blocks and control functions can be combined from such blocks. The implementation of the method depends
        on configuration properties and chosen kind of an output environment model.

        :return: None
        """
        raise NotImplementedError

    def _art_action(self, state, automaton):
        """
        Generate a code block for an artificial node in FSA which does not correspond to any action.

        :param state: State object.
        :param automaton: Automaton object which contains the artificial node.
        :return: [list of strings with lines of C code statements of the code block],
                 [list of strings with new local variable declarations required for the block],
                 [list of strings with boolean conditional expressions which guard code block entering],
                 [list of strings with model comments which embrace the code block]
        """
        # Make comments
        code, v_code, conditions, comments = list(), list(), list(), list()
        comments.append(action_model_comment(state.action, 'Artificial state in scenario'.
                                             format(automaton.process.name)))

        return code, v_code, conditions, comments

    def _dispatch(self, state, automaton):
        """
        Generate a code block for a dispatch action of the process for which the automaton is generated. A dispatch code
        block is always generated in a fixed form: as a function call of auxiliary function. Such a function contains
        switch or if operator to choose one of available optional receivers to send the signal. Implementation of
        particular dispatch to particular receiver is configurable and can be implemented differently in various
        translators.

        :param state: State object.
        :param automaton: Automaton object which contains the dispatch.
        :return: [list of strings with lines of C code statements of the code block],
                 [list of strings with new local variable declarations required for the block],
                 [list of strings with boolean conditional expressions which guard code block entering],
                 [list of strings with model comments which embrace the code block]
        """
        code, v_code, conditions, comments = list(), list(), list(), list()

        # Determine peers to receive the signal
        automata_peers = dict()
        if len(state.action.peers) > 0:
            # Do call only if model which can be called will not hang
            extract_relevant_automata(self._event_fsa + self._model_fsa + [self._entry_fsa],
                                      automata_peers, state.action.peers, Receive)
        else:
            # Generate comment
            code.append("/* Dispatch {!r} is not expected by any process, skipping the action */".
                        format(state.action.name))

        # Make comments
        if len(automata_peers) > 0:
            category = list(automata_peers.values())[0]['automaton'].process.category.upper()
            comment = state.action.comment.format(category)
        else:
            comment = 'Skip the action, since no callbacks has been found.'
        comments.append(action_model_comment(state.action, comment, begin=True))
        comments.append(action_model_comment(state.action, None, begin=False))

        # Add given conditions from a spec
        conditions = []
        if state.action.condition and len(state.action.condition) > 0:
            for statement in state.action.condition:
                cn = self._cmodel.text_processor(automaton, statement)
                conditions.extend(cn)

        if len(automata_peers) > 0:
            # Add conditions on base of dispatches
            checks = self._relevant_checks(automata_peers)
            if len(checks) > 0:
                if automaton in self._model_fsa:
                    conditions.append("({})".format(' || '.join(checks)))
                else:
                    # Convert conditions into assume, because according to signals semantics process could not proceed
                    # until it sends a signal and condition describes precondition to prevent signal sending to a
                    # wrong process.
                    if len(checks) > 0:
                        code.append('ldv_assume({});'.format(' || '.join(checks)))

            # Generate artificial function
            body = []
            # todo: All entrances of choosing file should become unnecessary
            file = choose_file(self._cmodel, self._analysis, automaton)

            if not get_conf_property(self._conf, 'direct control functions calls'):
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
                # todo: this need to be simplified.
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
            # You can implement your own translator with different implementations of the function
            pre, blocks, post = self._dispatch_blocks(state, file, automaton, function_parameters, param_interfaces,
                                                      automata_peers,
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
                    body.append('\tdefault: ldv_assume(0);')
                    body.append('};')

            if len(function_parameters) > 0:
                df = FunctionDefinition(
                    "ldv_dispatch_{}_{}_{}".format(state.action.name, automaton.identifier, state.identifier),
                    self._cmodel.entry_file,
                    "void f({})".format(', '.
                                        join([function_parameters[index].to_string('arg{}'.format(index),
                                                                                   typedef='complex_and_params')
                                              for index in range(len(function_parameters))])),
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
        """
        Always translate a conditional action boolean expression or statement string into a corresponding boolean
        cnditional expression or C statement string correspondingly. Each such conditional expression or statement is
        parsed and all entries of labels and the other model expressions are replaced by particular C implementation.
        Note, that if a label with different interface matches is used than each string can be translated into several
        ones depending on the number of interfaces but keeping the original order with a respect to the other statements
        or boolean expressions.

        :param state: State object.
        :param automaton: Automaton object which contains the condition.
        :return: [list of strings with lines of C code statements of the code block],
                 [list of strings with new local variable declarations required for the block],
                 [list of strings with boolean conditional expressions which guard code block entering],
                 [list of strings with model comments which embrace the code block]
        """
        code, v_code, conditions, comments = list(), list(), list(), list()

        # Make comments
        comment = state.action.comment
        comments.append(action_model_comment(state.action, comment, begin=True))
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
        # todo: This is need to move to Linux specific part and replace it with a code block
        """
        Generate code block for callback call. This can not be configured in translator implementations and for each
        callback call consists of: guard, pre-conditions (similarly to conditional code blocks), function call of the
        aux function which will be added to the file where function name is definately visible and which contains only
        the callback call and post-conditions. If a callback is matched with several interfaces then instead several
        optional nodes will be generated with all additional pre and post- conditions.

        :param state: State object.
        :param automaton: Automaton object which contains the callback call.
        :return: [list of strings with lines of C code statements of the code block],
                 [list of strings with new local variable declarations required for the block],
                 [list of strings with boolean conditional expressions which guard code block entering],
                 [list of strings with model comments which embrace the code block]
        """
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
                          any((signature.points.return_value.compare(d) for d in access.label.declarations)))]
                if len(suits) > 0:
                    if suits[0].interface:
                        label_var = automaton.determine_variable(suits[0].label, suits[0].interface.identifier)
                    else:
                        label_var = automaton.determine_variable(suits[0].label)
                    ret_declaration = signature.points.return_value.to_string('', typedef='complex_and_params')
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
                pre_action = automaton.process.add_condition(pre_name, [], pre_stments,
                                                             "Allocate memory for adhoc callback parameters.")
                pre_st = automaton.fsa.add_new_predecessor(st, pre_action)
                self._compose_action(pre_st, automaton)

                post_name = 'post_call_{}'.format(st.identifier)
                post_action = automaton.process.add_condition(post_name, [], post_stments,
                                                              "Free memory of adhoc callback parameters.")
                post_st = automaton.fsa.add_new_successor(st, post_action)
                self._compose_action(post_st, automaton)

        def generate_function(st, callback_declaration, invoke, file, check, func_variable):
            pointer_params, label_parameters, external_parameters = match_parameters(callback_declaration)
            manage_default_resources(label_parameters)
            ret_declaration, callback_return_expression, external_return_expression = ret_expression(st)

            # Determine external function params
            resources = [signature.to_string('arg0', typedef='complex_and_params')]
            callback_params = []
            for index in range(len(signature.points.parameters)):
                if type(signature.points.parameters[index]) is not str:
                    if index in pointer_params:
                        resources.append(signature.points.parameters[index].take_pointer.
                                         to_string('arg{}'.format(index + 1), typedef='complex_and_params'))
                        callback_params.append('*arg{}'.format(index + 1))
                    else:
                        resources.append(signature.points.parameters[index].
                                         to_string('arg{}'.format(index + 1), typedef='complex_and_params'))
                        callback_params.append('arg{}'.format(index + 1))
            callback_params = ", ".join(callback_params)
            resources = ", ".join(resources)

            fname = "ldv_{}_{}_{}_{}".format(automaton.process.name, st.action.name, automaton.identifier,
                                             st.identifier)
            function = FunctionDefinition(fname, file, "{} {}({})".format(ret_declaration, fname, resources),
                                          export=True, callback=True)

            # Determine label params
            external_parameters = [external_parameters[i] for i in sorted(external_parameters.keys())]

            true_invoke = external_return_expression + '({})'.format(invoke) + \
                          '(' + ', '.join(external_parameters) + ');'
            inv = []
            if check:
                f_invoke = external_return_expression + fname + '(' + ', '.join([invoke] + external_parameters) + ');'
                inv.append('if ({}) '.format(invoke) + '{')
                inv.append(model_comment('callback', st.action.name, {'call': true_invoke}))
                inv.append('\t' + f_invoke)
                inv.append('}')
                call = callback_return_expression + '(*arg0)' + '(' + callback_params + ')'
            else:
                f_invoke = external_return_expression + fname + '(' + \
                           ', '.join([func_variable] + external_parameters) + ');'
                inv.append(model_comment('callback', st.action.name, {'call': true_invoke}))
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
                post_call.extend(self._cmodel.text_processor(automaton, '$SWITCH_TO_PROCESS_CONTEXT();'))

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
                callback_pre_call.extend(self._cmodel.text_processor(automaton, '$SWITCH_TO_IRQ_CONTEXT();'))

            if len(callback_pre_call) > 0:
                callback_pre_call.insert(0, '/* Callback pre-call */')
                inv = callback_pre_call + inv

            return inv

        def make_action(st, declaration, invoke, file, check, func_variable):
            # Add an additional condition
            if st.action.condition and len(st.action.condition) > 0:
                for stment in st.action.condition:
                    cn = self._cmodel.text_processor(automaton, stment)
                    conditions.extend(cn)

            inv = generate_function(st, declaration, invoke, file, check, func_variable)
            inv = add_pre_conditions(st, inv)
            inv = add_post_conditions(st, inv)

            return inv

        def reinitialize_variables(code):
            reinitialization_action_set = get_conf_property(self._conf, 'callback actions with reinitialization', list)
            if reinitialization_action_set and state.action.name in reinitialization_action_set:
                statements = initialize_automaton_variables(self._conf, automaton)
                code.extend(statements)

        # Determine callback implementations
        accesses = automaton.process.resolve_access(state.action.callback)
        generated_callbacks = []
        for access in accesses:
            reinitialize_vars_flag = False
            if access.interface:
                signature = access.interface.declaration
                implementation = automaton.process.get_implementation(access)

                # todo: This can be extraced also from code analysis results
                if implementation and self._analysis.callback_name(implementation.value):
                    # Eplicit callback call by found function name
                    invoke = '(' + implementation.value + ')'
                    file = implementation.file
                    check = False
                    func_variable = access.access_with_variable(automaton.determine_variable(access.label,
                                                                                        access.list_interface[0].
                                                                                        identifier))
                elif signature.clean_declaration and not isinstance(implementation, bool) and\
                        get_necessary_conf_property(self._conf, 'implicit callback calls'):
                    # Call by pointer
                    invoke = access.access_with_variable(
                        automaton.determine_variable(access.label, access.list_interface[0].identifier))
                    check = True
                    file = self._cmodel.entry_file
                    func_variable = invoke
                    reinitialize_vars_flag = True
                else:
                    # Avoid call if neither implementation and pointer call are known
                    invoke = None
            else:
                signature = access.label.prior_signature

                func_variable = automaton.determine_variable(access.label)
                # todo: This can be extraced also from code analysis results
                if access.label.value and self._analysis.callback_name(access.label.value):
                    # Call function provided by an explicit name but with no interface
                    invoke = self._analysis.callback_name(access.label.value)
                    func_variable = func_variable.name
                    # todo: This can be extraced also from code analysis results
                    file = self._analysis.determine_original_file(access.label.value)
                    check = False
                else:
                    if func_variable and get_necessary_conf_property(self._conf, 'implicit callback calls'):
                        # Call if label(variable) is provided but with no explicit value
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

                # Determine structure type name of the container with the callback if such exists
                # todo: This is used for comments. It is better to generate comments directly in model
                structure_name = None
                if access.interface and implementation and len(implementation.sequence) > 0:
                    field = implementation.sequence[-1]
                    containers = self._analysis.resolve_containers(access.interface.declaration,
                                                                   access.interface.category)
                    if len(containers.keys()) > 0:
                        for name in (name for name in containers if field in containers[name]):
                            structure = self._analysis.get_intf(name).declaration
                            # todo: this code does not take into account that implementation of callback and
                            #       implementation of the container should be connected.
                            if isinstance(structure, Structure):
                                structure_name = structure.name
                                break
                if not structure_name:
                    # Use instead role and category
                    field = state.action.name
                    structure_name = automaton.process.category.upper()
                comment = state.action.comment.format(field, structure_name)

                comments.append(action_model_comment(state.action, comment, begin=True, callback=True))

                conditions = list()

                inv = make_action(st, signature, invoke, file, check, func_variable)
                code.extend(inv)

                # If necessary reinitialize variables, for instance, if probe skipped
                if reinitialize_vars_flag:
                    reinitialize_variables(code)
                
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

            # If necessary reinitialize variables, for instance, if probe skipped
            reinitialize_variables(code)

            generated_callbacks.append((state, code, list(), list(), comments))

        return generated_callbacks

    def _call_retval(self, state, automaton):
        """
        Generate code block for returning value to ensure that callback is terminated. This is actual for true parallel
        environment model.

        :param state: State object.
        :param automaton: Automaton object which contains the callback return value action.
        :return: [list of strings with lines of C code statements of the code block],
                 [list of strings with new local variable declarations required for the block],
                 [list of strings with boolean conditional expressions which guard code block entering],
                 [list of strings with model comments which embrace the code block]
        """
        # Add begin model comment
        code, v_code, conditions, comments = list(), list(), list(), list()
        comment = state.action.comment
        comments.append(action_model_comment(state.action, comment, begin=True))
        comments.append(action_model_comment(state.action, None, begin=False))
        code.append('/* Return value expectation is not supported in the current version of EMG */')
        # todo: such kind of actions is no needed and not supported now, since no true parallel model can be generated
        raise NotImplementedError("Avoid using of deprecated return value actions and describe returned values"
                                  " directly at calling actions")

        return code, v_code, conditions, comments

    def _subprocess(self, state, automaton):
        """
        Generate reduction to a subprocess as a code block. Add your own logic in the corresponding implementation.

        :param state: State object.
        :param automaton: Automaton object which contains the subprocess.
        :return: [list of strings with lines of C code statements of the code block],
                 [list of strings with new local variable declarations required for the block],
                 [list of strings with boolean conditional expressions which guard code block entering],
                 [list of strings with model comments which embrace the code block]
        """
        code, v_code, conditions, comments = list(), list(), list(), list()

        # Make comments
        comment = state.action.comment
        comments.append(action_model_comment(state.action, comment, begin=True))
        comments.append(action_model_comment(state.action, None, begin=False))

        # Add additional condition
        if state.action.condition and len(state.action.condition) > 0:
            for statement in state.action.condition:
                cn = self._cmodel.text_processor(automaton, statement)
                conditions.extend(cn)

        return code, v_code, conditions, comments

    def _get_cf_struct(self, automaton, params):
        """
        Provides declaration of structure to pack all control function (or maybe other) parameters as a single argument
        with help of it.

        :param automaton: Automaton object.
        :param params: Declaration objects list.
        :return: Declaration object.
        """
        # todo: ensure proper ordering of structure parameters especially arrays, bit fields and so on.
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
        """
        Generate statement with control function call.

        :param file: File name string.
        :param automaton: Automaton object.
        :param parameter: String with argument of the control function.
        :return: String expression.
        """
        self._cmodel.add_function_declaration(file, self._control_function(automaton), extern=True)

        if get_conf_property(self._conf, 'direct control functions calls'):
            return '{}({});'.format(self._control_function(automaton).name, parameter)
        else:
            return self._call_cf_code(file, automaton, parameter)

    def _join_cf(self, file, automaton):
        """
        Generate statement to join control function thread if it is called in a separate thread.

        :param file: File name string.
        :param automaton: Automaton object.
        :return: String expression.
        """
        self._cmodel.add_function_declaration(file, self._control_function(automaton), extern=True)

        if get_conf_property(self._conf, 'direct control functions calls'):
            return '/* Skip thread join call */'
        else:
            return self._join_cf_code(file, automaton)

    def _control_function(self, automaton):
        """
        Generate control function. This function generates a FunctionDefinition object without a body. It is required
        to call control function within code blocks until all code blocks are translated and control function body
        can be generated.

        :param automaton: Automaton object.
        :return: FunctionDefinition object.
        """
        if automaton.identifier not in self._control_functions:
            # Check that this is an aspect function or not
            if automaton in self._model_fsa:
                name = 'ldv_emg_{}'.format(automaton.process.name)
                # todo: This can be extraced also from code analysis results
                function_obj = self._analysis.get_kernel_function(automaton.process.name)
                params = []
                for position, param in enumerate(function_obj.declaration.parameters):
                    if type(param) is str:
                        params.append(param)
                    else:
                        params.append(param.to_string('arg{}'.format(str(position)), typedef='complex_and_params'))

                if len(params) == 0:
                    param_types = ['void']
                else:
                    param_types = params

                declaration = '{0} f({1})'.format(
                    function_obj.declaration.return_value.to_string('', typedef='complex_and_params'),
                    ', '.join(param_types))
                cf = FunctionDefinition(name, self._cmodel.entry_file, declaration, False)
            else:
                name = 'ldv_{}_{}'.format(automaton.process.name, automaton.identifier)
                if not get_necessary_conf_property(self._conf, "direct control functions calls"):
                    declaration = 'void *f(void *data)'
                else:
                    declaration = 'void f(void *data)'
                cf = FunctionDefinition(name, self._cmodel.entry_file, declaration, False)

            self._control_functions[automaton.identifier] = cf

        return self._control_functions[automaton.identifier]

    @abc.abstractstaticmethod
    def _relevant_checks(self, relevent_automata):
        """
        This function allows to add your own additional conditions before function calls and dispatches. The
        implementation in your translator is required.

        :param relevent_automata: {'Automaton identifier string': {'automaton': Automaton object,
               'states': set of State objects peered with the considered action}}
        :return: List with additional C logic expressions.
        """
        raise NotImplementedError
    
    @abc.abstractstaticmethod
    def _join_cf_code(self, file, automaton):
        """
        Generate statement to join control function thread if it is called in a separate thread. Depends on a translator
        implementation.

        :param file: File name string.
        :param automaton: Automaton object.
        :return: String expression.
        """
        raise NotImplementedError

    @abc.abstractstaticmethod
    def _call_cf_code(self, file, automaton, parameter='0'):
        """
        Generate statement with control function call. Depends on a translator implementation.

        :param file: File name string.
        :param automaton: Automaton object.
        :param parameter: String with argument of the control function.
        :return: String expression.
        """
        raise NotImplementedError

    @abc.abstractstaticmethod
    def _dispatch_blocks(self, state, file, automaton, function_parameters, param_interfaces, automata_peers,
                         replicative):
        """
        Generate parts of dispatch code blocks for your translator implementation.

        :param state: State object.
        :param file: File name string.
        :param automaton: Automaton object.
        :param function_parameters: list of Label objects.
        :param param_interfaces: List of Interface objects.
        :param automata_peers: {'Automaton identifier string': {'automaton': Automaton object,
                                'states': set of State objects peered with the considered action}}
        :param replicative: True/False.
        :return: [List of C statements before dispatching], [[List of C statements with dispatch]],
                 [List of C statements after performed dispatch]
        """
        raise NotImplementedError

    @abc.abstractstaticmethod
    def _receive(self, state, automaton):
        """
        Generate code block for receive action. Require more detailed implementation in your translator.

        :param state: State object.
        :param automaton: Automaton object.
        :return: [list of strings with lines of C code statements of the code block],
                 [list of strings with new local variable declarations required for the block],
                 [list of strings with boolean conditional expressions which guard code block entering],
                 [list of strings with model comments which embrace the code block]
        """
        code, v_code, conditions, comments = list(), list(), list(), list()

        # Make comments
        comment = state.action.comment.format(automaton.process.category.upper())
        comments.append(action_model_comment(state.action, comment, begin=True))
        comments.append(action_model_comment(state.action, None, begin=False))

        return code, v_code, conditions, comments

    @abc.abstractstaticmethod
    def _compose_control_function(self, automaton):
        """
        Generate body of a control function according to your translator implementation.

        :param automaton: Automaton object.
        :return: None
        """
        raise NotImplementedError

    @abc.abstractstaticmethod
    def _entry_point(self):
        """
        Generate statements for entry point function body.

        :return: [List of C statements]
        """
        raise NotImplementedError

    @abc.abstractstaticmethod
    def _normalize_model_fsa(self, automaton):
        """
        Normalize function model fsa graph and apply necessary transformations.

        :param automaton: Automaton object.
        :return: None
        """
        raise NotImplementedError

    @abc.abstractstaticmethod
    def _normalize_event_fsa(self, automaton):
        """
        Normalize event automaton fsa graph and apply necessary transformations.

        :param automaton: Automaton object.
        :return: None
        """
        raise NotImplementedError

    def _compose_action(self, state, automaton):
        """
        Generate one single code block from given guard, body, model comments statements.

        :param state: State object.
        :param automaton: Automaton object.
        :return: None
        """
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

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
