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

import sortedcontainers

from klever.core.vtg.emg.common.process import Dispatch, Receive
from klever.core.vtg.emg.translation.fsa_translator import FSATranslator
from klever.core.vtg.emg.common.c import Function
from klever.core.vtg.emg.translation.code import action_model_comment
from klever.core.vtg.emg.translation.fsa_translator.common import extract_relevant_automata
from klever.core.vtg.emg.translation.fsa_translator.label_control_function import label_based_function


class SimplestTranslator(FSATranslator):

    def _relevant_checks(self, relevant_automata):
        return list()

    def _dispatch(self, action, automaton):
        """
        Generate a code block for a dispatch action of the process for which the automaton is generated. A dispatch code
        block is always generated in a fixed form: as a function call of auxiliary function. Such a function contains
        switch or if operator to choose one of available optional receivers to send the signal. Implementation of
        particular dispatch to particular receiver is configurable and can be implemented differently in various
        translation.

        :param action: Action object.
        :param automaton: Automaton object which contains the dispatch.
        :return: [list of strings with lines of C code statements of the code block],
                 [list of strings with new local variable declarations required for the block],
                 [list of strings with boolean conditional expressions which guard code block entering],
                 [list of strings with model comments which embrace the code block]
        """
        code, v_code, conditions, comments = list(), list(), list(), list()

        # Determine peers to receive the signal
        automata_peers = sortedcontainers.SortedDict()
        action_peers = self._collection.peers(automaton.process, {str(action)})
        if len(action_peers) > 0:
            # Do call only if model which can be called will not hang
            extract_relevant_automata(self._logger, self._event_fsa + self._model_fsa + [self._entry_fsa],
                                      automata_peers, action_peers, Receive)
        else:
            # Generate comment
            code.append("/* Dispatch {!r} is not expected by any process, skipping the action */".
                        format(action.name))

        # Make comments
        if len(automata_peers) > 0:
            category = list(automata_peers.values())[0]['automaton'].process.category.upper()
            comment = action.comment.format(category)
        else:
            comment = 'Skip the action, since no peers has been found.'
        comments.append(action_model_comment(action, comment, begin=True))
        comments.append(action_model_comment(action, None, begin=False))

        # Add given conditions from a spec
        conditions = []
        if action.condition and len(action.condition) > 0:
            for statement in action.condition:
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

            # Check dispatch type
            replicative = False
            for a_peer in automata_peers:
                for act in automata_peers[a_peer]['actions']:
                    if act.replicative:
                        replicative = True
                        break

            # Determine parameters
            function_parameters = []

            # Add parameters
            for index in range(len(action.parameters)):
                # Determine dispatcher parameter
                # We expect strictly one
                dispatcher_access = automaton.process.resolve_access(action.parameters[index])
                variable = automaton.determine_variable(dispatcher_access.label)
                function_parameters.append(variable)

            # Generate blocks on each receive to another process
            # You can implement your own translation with different implementations of the function
            _, blocks, _ = self._dispatch_blocks(action, automaton, function_parameters, automata_peers,
                                                 replicative)
            if len(blocks) > 0:
                # Print body of a dispatching function
                if action.broadcast:
                    for block in blocks:
                        code += block
                else:
                    imply_signals = self._conf.get('do not skip signals')
                    if len(blocks) > 2 or (len(blocks) == 2 and not imply_signals):
                        code.append('switch (ldv_undef_int()) {')
                        for index in range(len(blocks)):
                            code.extend(
                                ['\tcase {}: '.format(index) + '{'] + \
                                ['\t\t' + stm for stm in blocks[index]] + \
                                ['\t\tbreak;',
                                 '\t};']
                            )
                        if imply_signals:
                            code.append('\tdefault: ldv_assume(0);')
                        code.append('};')
                    elif len(blocks) == 2 and imply_signals:
                        code.append('if (ldv_undef_int()) {')
                        code.extend(['\t' + stm for stm in blocks[0]])
                        code.extend(['}', 'else {'])
                        code.extend(['\t' + stm for stm in blocks[1]])
                        code.extend(['}'])
                    elif len(blocks) == 1 and not imply_signals:
                        code.append('if (ldv_undef_int()) {')
                        code.extend(['\t' + stm for stm in blocks[0]])
                        code.extend(['}'])
                    else:
                        code.extend(blocks[0])
            else:
                # This is because translation can have specific restrictions
                self._logger.debug(
                    f"No block to implement signal receive of action '{str(action)}' in '{str(automaton)}'")
                code.append('/* Skip the dispatch because there is no process to receive the signal */')
        else:
            self._logger.debug(f"No peers to implement signal receive of action '{str(action)}' in '{str(automaton)}'")
            code.append('/* Skip the dispatch because there is no process to receive the signal */')

        return code, v_code, conditions, comments

    def _dispatch_blocks(self, action, automaton, function_parameters, automata_peers, replicative):
        pre = []
        post = []
        blocks = []

        for a_peer in (a for a in automata_peers if automata_peers[a]['actions']):
            if replicative:
                for r_action in automata_peers[a_peer]['actions']:
                    block = list()
                    if r_action.replicative:
                        call = '{}({});'.format(self._control_function(a_peer).name,
                                                ', '.join(v.name for v in function_parameters))
                        block.append(call)
                        blocks.append(block)
                        break
                    else:
                        self._logger.warning(
                            'Cannot generate dispatch based on labels for receive {} in process {} with category {}'
                            .format(r_action.name, a_peer.process.name, a_peer.process.category))

        return pre, blocks, post

    def _receive(self, action, automaton):
        code, v_code, conditions, comments = super(SimplestTranslator, self)._receive(action, automaton)

        automata_peers = {}
        action_peers = self._collection.peers(automaton.process, {str(action)})
        if len(action_peers) > 0:
            # Do call only if model which can be called will not hang
            extract_relevant_automata(self._logger, self._event_fsa + self._model_fsa + [self._entry_fsa],
                                      automata_peers, action_peers, Dispatch)

            # Add additional condition
            if action.replicative:
                param_expressions = []

                if len(action.parameters) > 0:
                    for index, param in enumerate(action.parameters):
                        receiver_access = automaton.process.resolve_access(param)
                        var = automaton.determine_variable(receiver_access.label)
                        param_expressions.append(var.name)

                if action.condition and len(action.condition) > 0:
                    # Arguments comparison is not supported in label-based model
                    for statement in action.condition:
                        # Replace first $ARG expressions
                        s = statement
                        for index, _ in enumerate(param_expressions):
                            replacement = 'arg{}'.format(index)
                            s = s.replace("$ARG{}".format(index + 1), replacement)
                        cn = self._cmodel.text_processor(automaton, s)
                        conditions.extend(cn)

                # This should be before precondition because it may check values unpacked in this section
                if len(param_expressions) > 0:
                    code += ['/* Assign received labels */'] + \
                            ['{} = arg{};'.format(v, i) for i, v in enumerate(param_expressions)]
            else:
                code.append('/* Skip a non-replicative signal receiving %s */' % action.name)
                # Ignore conditions
                conditions = []
        else:
            # Generate comment
            code.append("/* Signal receive {!r} does not expect any signal from existing processes */".
                        format(action.name))

        return code, v_code, conditions, comments

    def _compose_control_function(self, automaton):
        self._logger.info("Generate label-based control function for automaton {!r} based on process {!r}".
                          format(str(automaton), str(automaton.process)))

        # Get function prototype
        cf = self._control_function(automaton)

        # Generate function body
        label_based_function(self._conf, self._source, automaton, cf,
                             True if automaton in self._model_fsa else False)

        # Add function to source code to print
        self._cmodel.add_function_definition(cf)
        self._cmodel.add_function_declaration(automaton.process.file, cf, extern=True)
        if automaton in self._model_fsa:
            for file in self._source.get_source_function(automaton.process.name).declaration_files:
                self._cmodel.add_function_declaration(file, cf, extern=True)
        return

    def _control_function(self, automaton):
        """
        Generate control function. This function generates a FunctionDefinition object without a body. It is required
        to call control function within code blocks until all code blocks are translated and control function body
        can be generated.

        :param automaton: Automaton object.
        :return: FunctionDefinition object.
        """
        if str(automaton) not in self._control_functions:
            # Check that this is an aspect function or not
            if automaton in self._model_fsa:
                return super(SimplestTranslator, self)._control_function(automaton)
            else:
                name = f'emg_{automaton.process.category}_{automaton.process.name}'

                receives = [r for r in automaton.process.actions.filter(include={Receive}) if r.replicative]
                if len(receives) == 0:
                    # This is the main process
                    declaration = f'void f(void)'
                elif len(receives) > 1:
                    raise RuntimeError(f'Process {str(automaton.process)} has more than the one receive signal which'
                                       f'is not supported by the translator. Choose an another one.')
                else:
                    action = receives.pop()
                    param_declarations = []

                    for index, param in enumerate(action.parameters):
                        receiver_access = automaton.process.resolve_access(param)
                        var = automaton.determine_variable(receiver_access.label)
                        param_declarations.append(var.declaration.to_string('', typedef='complex_and_params',
                                                  scope={automaton.process.file}))
                    args = ', '.join(param_declarations)
                    declaration = f'void f({args})'
                cf = Function(name, declaration)
                cf.definition_file = automaton.process.file
                self._control_functions[automaton] = cf
        return self._control_functions[automaton]

    def _entry_point(self):
        self._logger.info("Finally generate an entry point function {!r}".format(self._cmodel.entry_name))
        cf = self._control_function(self._entry_fsa)
        body = ['{}();'.format(cf.name)]
        if self._entry_fsa.process.file != self._cmodel.entry_file:
            self._cmodel.add_function_declaration(self._cmodel.entry_file, cf, extern=True)
        return self._cmodel.compose_entry_point(body)
