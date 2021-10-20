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

from klever.core.vtg.emg.common import get_or_die, model_comment
from klever.core.vtg.emg.common.c.types import import_declaration
from klever.core.vtg.emg.common.process.actions import Receive, Dispatch, Block, Subprocess, Choice, \
    Concatenation, Behaviour
from klever.core.vtg.emg.common.c import Function
from klever.core.vtg.emg.translation.code import action_model_comment
from klever.core.vtg.emg.translation.fsa_translator.common import extract_relevant_automata


class FSATranslator:

    def __init__(self, logger, conf, source, collection, cmodel, entry_fsa, model_fsa, event_fsa):
        """
        Initialize new FSA translation object. During the initialization an environment model in form of finite
        state machines with process-like actions is translated to C code. Translation includes the following steps:
        each pair label-interface is translated in a separate variable, each action is translated in code blocks
        (aux functions can be additionally generated), for each automaton a control function is generated, control
        functions for event modeling are called in a specific entry point function and control functions for function
        modeling are called instead of modelled functions. This class has an abstract methods to provide ability to
        implement different translation.

        :param logger: Logger object.
        :param conf: Configuration properties dictionary.
        :param source: Source collection object.
        :param collection: ProcessCollection.
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
        self._source = source
        self._collection = collection
        self._logger = logger
        self._structures = sortedcontainers.SortedDict()
        self._control_functions = sortedcontainers.SortedDict()
        self._logger.info("Include extra header files if necessary")
        conf.setdefault('do not skip signals', False)

        # Get from unused interfaces
        for process in (a.process for a in self._model_fsa + self._event_fsa + [entry_fsa] 
                        if len(a.process.headers) > 0):
            self._cmodel.add_headers(process.file, sorted(process.headers, key=len))

        # Generates base code blocks
        self._logger.info("Start the preparation of actions code")
        for automaton in self._event_fsa + self._model_fsa + [self._entry_fsa]:
            self._logger.debug("Generate code for instance {!r} of process {!r} of category {!r}".
                               format(str(automaton), automaton.process.name, automaton.process.category))
            for beh in automaton.process.actions.behaviour():
                if isinstance(beh, Behaviour):
                    self._compose_action(beh, automaton)

        # Start generators of control functions
        for automaton in self._event_fsa + self._model_fsa + [self._entry_fsa]:
            self._compose_control_function(automaton)

        # Generate aspects with kernel models
        for automaton in self._model_fsa:
            aspect_code = [
                model_comment('FUNCTION_MODEL', 'Perform the model code of the function {!r}'.
                              format(automaton.process.name))
            ]
            function_obj = self._source.get_source_function(automaton.process.name)
            params = []
            for position, param in enumerate(function_obj.declaration.parameters):
                if isinstance(param, str):
                    params.append(param)
                else:
                    params.append('$arg{}'.format(str(position + 1)))

            if not params and function_obj.declaration.return_value == 'void':
                arguments = []
                ret_expression = ''
            elif not params:
                arguments = []
                ret_expression = 'return '
            elif function_obj.declaration.return_value == 'void':
                arguments = params
                ret_expression = ''
            else:
                ret_expression = 'return '
                arguments = params

            if arguments and '...' == arguments[-1]:
                arguments = arguments[:-1]

            invoke = '{}{}({});'.format(ret_expression, self._control_function(automaton).name, ', '.join(arguments))
            aspect_code.append(invoke)

            self._cmodel.add_function_model(function_obj, aspect_code)

        # Generate entry point function
        self._entry_point()

        # Add types
        for pair in self._structures.values():
            file, decl = pair
            self._cmodel.types.setdefault(file, list())
            if decl not in self._cmodel.types[file]:
                self._cmodel.types[file].append(decl)

        return

    def _prepare_control_functions(self):
        """
        Generate code of all control functions for each automata. It expects that all actions are already transformed
        into code blocks and control functions can be combined from such blocks. The implementation of the method
        depends on configuration properties and chosen kind of an output environment model.

        :return: None
        """
        raise NotImplementedError

    def _art_action(self, action, automaton):
        """
        Generate a code block for an artificial node in FSA which does not correspond to any action.

        :param action: Action object.
        :param automaton: Automaton object which contains the artificial node.
        :return: [list of strings with lines of C code statements of the code block],
                 [list of strings with new local variable declarations required for the block],
                 [list of strings with boolean conditional expressions which guard code block entering],
                 [list of strings with model comments which embrace the code block]
        """
        # Make comments
        code, v_code, conditions, comments = list(), list(), list(), list()
        comments.append(action_model_comment(action, 'Artificial state in scenario'.format(automaton.process.name)))

        return code, v_code, conditions, comments

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

            if not self._conf.get('direct control functions calls'):
                body = ['int ret;']

            # Check dispatch type
            replicative = False
            for a_peer in automata_peers:
                for act in automata_peers[a_peer]['actions']:
                    if act.replicative:
                        replicative = True
                        break

            # Determine parameters
            df_parameters = []
            function_parameters = []

            # Add parameters
            for index in range(len(action.parameters)):
                # Determine dispatcher parameter
                # We expect strictly one
                dispatcher_access = automaton.process.resolve_access(action.parameters[index])
                variable = automaton.determine_variable(dispatcher_access.label)
                function_parameters.append(variable.declaration)
                df_parameters.append(variable.name)

            # Generate blocks on each receive to another process
            # You can implement your own translation with different implementations of the function
            pre, blocks, post = self._dispatch_blocks(action, automaton, function_parameters, automata_peers,
                                                      replicative)
            if len(blocks) > 0:
                body += pre

                # Print body of a dispatching function
                if action.broadcast:
                    for block in blocks:
                        body += block
                else:
                    imply_signals = self._conf.get('do not skip signals')
                    if len(blocks) > 2 or (len(blocks) == 2 and not imply_signals):
                        body.append('switch (ldv_undef_int()) {')
                        for index in range(len(blocks)):
                            body.extend(
                                ['\tcase {}: '.format(index) + '{'] + \
                                ['\t\t' + stm for stm in blocks[index]] + \
                                ['\t\tbreak;',
                                 '\t};']
                            )
                        if imply_signals:
                            body.append('\tdefault: ldv_assume(0);')
                        body.append('};')
                    elif len(blocks) == 2 and imply_signals:
                        body.append('if (ldv_undef_int()) {')
                        body.extend(['\t' + stm for stm in blocks[0]])
                        body.extend(['}', 'else {'])
                        body.extend(['\t' + stm for stm in blocks[1]])
                        body.extend(['}'])
                    elif len(blocks) == 1 and not imply_signals:
                        body.append('if (ldv_undef_int()) {')
                        body.extend(['\t' + stm for stm in blocks[0]])
                        body.extend(['}'])
                    else:
                        body.extend(blocks[0])

                if len(function_parameters) > 0:
                    df = Function(
                        "emg_dispatch_{}_{}".format(str(action), str(automaton)),
                        "void f({})".format(', '.
                                            join([function_parameters[index].to_string('arg{}'.format(index),
                                                                                       typedef='complex_and_params')
                                                  for index in range(len(function_parameters))])))
                else:
                    df = Function(
                        "emg_dispatch_{}_{}".format(str(action), str(automaton)),
                        "void f(void)")
                df.definition_file = automaton.process.file
                body.extend(post)
                body.append('return;')
                df.body.extend(body)

                # Add function definition
                self._cmodel.add_function_definition(df)

                code.extend([
                    '{}({});'.format(df.name, ', '.join(df_parameters))
                ])
            else:
                # This is because translation can have specific restrictions
                self._logger.debug(f"No block to implement signal receive of action"
                                   f" '{str(action)}' in '{str(automaton)}'")
                code.append('/* Skip the dispatch because there is no process to receive the signal */')
        else:
            self._logger.debug(f"No peers to implement signal receive of action '{str(action)}' in '{str(automaton)}'")
            code.append('/* Skip the dispatch because there is no process to receive the signal */')

        return code, v_code, conditions, comments

    def _condition(self, action, automaton):
        """
        Always translate a conditional action boolean expression or statement string into a corresponding boolean
        conditional expression or C statement string correspondingly. Each such conditional expression or statement is
        parsed and all entries of labels and the other model expressions are replaced by particular C implementation.
        Note, that if a label with different interface matches is used than each string can be translated into several
        ones depending on the number of interfaces but keeping the original order with a respect to the other statements
        or boolean expressions.

        :param action: Action object.
        :param automaton: Automaton object which contains the condition.
        :return: [list of strings with lines of C code statements of the code block],
                 [list of strings with new local variable declarations required for the block],
                 [list of strings with boolean conditional expressions which guard code block entering],
                 [list of strings with model comments which embrace the code block]
        """
        code, v_code, conditions, comments = list(), list(), list(), list()

        # Make comments
        comment = action.comment
        comments.append(action_model_comment(action, comment, begin=True))
        comments.append(action_model_comment(action, None, begin=False))

        # Add additional conditions
        for stm in action.condition:
            conditions.extend(self._cmodel.text_processor(automaton, stm))

        for stm in action.statements:
            code.extend(self._cmodel.text_processor(automaton, stm))

        return code, v_code, conditions, comments

    def _subprocess(self, action, automaton):
        """
        Generate reduction to a subprocess as a code block. Add your own logic in the corresponding implementation.

        :param action: Action object.
        :param automaton: Automaton object which contains the subprocess.
        :return: [list of strings with lines of C code statements of the code block],
                 [list of strings with new local variable declarations required for the block],
                 [list of strings with boolean conditional expressions which guard code block entering],
                 [list of strings with model comments which embrace the code block]
        """
        code, v_code, conditions, comments = list(), list(), list(), list()

        # Make comments
        comment = action.comment
        comments.append(action_model_comment(action, comment, begin=True))
        comments.append(action_model_comment(action, None, begin=False))

        # Add additional condition
        for stm in action.condition:
            conditions.extend(self._cmodel.text_processor(automaton, stm))

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
            cache_identifier += str(param)

        if cache_identifier not in self._structures:
            struct_name = 'emg_struct_{}_{}'.format(automaton.process.name, str(automaton))
            if struct_name in self._structures:
                raise KeyError('Structure name is not unique')

            decl = import_declaration('struct {} a'.format(struct_name))
            for index in range(len(params)):
                decl.fields['arg{}'.format(index)] = params[index]
            decl.fields['signal_pending'] = import_declaration('int a')

            self._structures[cache_identifier] = [automaton.process.file, decl]
        else:
            decl = self._structures[cache_identifier][1]

        return decl

    def _call_cf(self, automaton, parameter='0'):
        """
        Generate statement with control function call.

        :param automaton: Automaton object.
        :param parameter: String with argument of the control function.
        :return: String expression.
        """
        self._cmodel.add_function_declaration(automaton.process.file, self._control_function(automaton), extern=True)

        if self._conf.get('direct control functions calls'):
            return '{}({});'.format(self._control_function(automaton).name, parameter)
        else:
            return self._call_cf_code(automaton, parameter)

    def _join_cf(self, automaton):
        """
        Generate statement to join control function thread if it is called in a separate thread.

        :param automaton: Automaton object.
        :return: String expression.
        """
        self._cmodel.add_function_declaration(automaton.process.file, self._control_function(automaton), extern=True)

        if self._conf.get('direct control functions calls'):
            return '/* Skip thread join call */'
        else:
            return self._join_cf_code(automaton)

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
                name = 'emg_{}'.format(automaton.process.name)
                function_objs = self._source.get_source_functions(automaton.process.name)
                if len(function_objs) == 0:
                    raise ValueError("Unfortunately there is no function {!r} found by the source analysis".
                                     format(automaton.process.name))
                else:
                    # We ignore there that fact that functions can have different scopes
                    function_obj = function_objs[0]
                params = []
                for position, param in enumerate(function_obj.declaration.parameters):
                    if isinstance(param, str):
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
                cf = Function(name, declaration)
            else:
                name = f'emg_{automaton.process.category}_{automaton.process.name}'
                if not get_or_die(self._conf, "direct control functions calls"):
                    declaration = 'void *f(void *data)'
                else:
                    declaration = 'void f(void *data)'
                cf = Function(name, declaration)
            cf.definition_file = automaton.process.file

            self._control_functions[automaton] = cf

        return self._control_functions[automaton]

    def _relevant_checks(self, relevant_automata):
        """
        This function allows to add your own additional conditions before function calls and dispatches. The
        implementation in your translation is required.

        :param relevant_automata: {'Automaton identifier string': {'automaton': Automaton object,
               'states': set of Action objects peered with the considered action}}
        :return: List with additional C logic expressions.
        """
        raise NotImplementedError

    def _join_cf_code(self, automaton):
        """
        Generate statement to join control function thread if it is called in a separate thread. Depends on a
        translation implementation.

        :param automaton: Automaton object.
        :return: String expression.
        """
        raise NotImplementedError

    def _call_cf_code(self, automaton, parameter='0'):
        """
        Generate statement with control function call. Depends on a translation implementation.

        :param automaton: Automaton object.
        :param parameter: String with argument of the control function.
        :return: String expression.
        """
        raise NotImplementedError

    def _dispatch_blocks(self, action, automaton, function_parameters, automata_peers,
                         replicative):
        """
        Generate parts of dispatch code blocks for your translation implementation.

        :param action: Action object.
        :param automaton: Automaton object.
        :param function_parameters: list of Label objects.
        :param automata_peers: {'Automaton identifier string': {'automaton': Automaton object,
                                'states': set of Action objects peered with the considered action}}
        :param replicative: True/False.
        :return: [List of C statements before dispatching], [[List of C statements with dispatch]],
                 [List of C statements after performed dispatch]
        """
        raise NotImplementedError

    def _receive(self, action, automaton):
        """
        Generate code block for receive action. Require more detailed implementation in your translation.

        :param action: Action object.
        :param automaton: Automaton object.
        :return: [list of strings with lines of C code statements of the code block],
                 [list of strings with new local variable declarations required for the block],
                 [list of strings with boolean conditional expressions which guard code block entering],
                 [list of strings with model comments which embrace the code block]
        """
        code, v_code, conditions, comments = list(), list(), list(), list()

        # Make comments
        comment = action.comment.format(automaton.process.category.upper())
        comments.append(action_model_comment(action, comment, begin=True))
        comments.append(action_model_comment(action, None, begin=False))

        return code, v_code, conditions, comments

    def _compose_control_function(self, automaton):
        """
        Generate body of a control function according to your translation implementation.

        :param automaton: Automaton object.
        :return: None
        """
        raise NotImplementedError

    def _entry_point(self):
        """
        Generate statements for entry point function body.

        :return: [List of C statements]
        """
        raise NotImplementedError

    def _compose_action(self, behaviour, automaton):
        """
        Generate one single code block from given guard, body, model comments statements.

        :param behaviour: Behaviour object.
        :param automaton: Automaton object.
        :return: None
        """
        action = behaviour.description

        def compose_single_action(beh, code, v_code, conditions, comments):
            final_code = list()
            final_code.append(comments[0])

            # Skip or assert action according to conditions
            if conditions and (isinstance(beh.my_operator, Choice) or
                               (isinstance(beh.my_operator, Concatenation) and not beh.my_operator.index(beh))):
                # todo: if not isinstance(predecessor, Receive):
                final_code += ['ldv_assume({});'.format(' && '.join(conditions))] + code
            elif conditions and code:
                final_code += ['if ({}) '.format(' && '.join(conditions)) + '{'] + \
                              ['\t{}'.format(s) for s in code] + \
                              ['}']
            elif conditions:
                raise ValueError(f"Action '{str(beh.description)}' should have either both condition and statements "
                                 f"attributes, or a statements attribute or at least it can be used in a choice "
                                 f"operator.")
            else:
                final_code += code

            if len(comments) == 2:
                final_code.append(comments[1])

            automaton.code[hash(behaviour)] = (v_code, final_code)

        if isinstance(action, Dispatch):
            code_generator = self._dispatch
        elif isinstance(action, Receive):
            code_generator = self._receive
        elif isinstance(action, Block):
            code_generator = self._condition
        elif isinstance(action, Subprocess):
            code_generator = self._subprocess
        elif action is None:
            code_generator = self._art_action
        else:
            raise TypeError("Unknown action type: {!r}".format(type(action).__name__))

        c, vc, grds, cmmnts = code_generator(action, automaton)
        compose_single_action(behaviour, c, vc, grds, cmmnts)
