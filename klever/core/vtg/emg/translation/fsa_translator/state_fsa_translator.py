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

from klever.core.vtg.emg.common import get_or_die, model_comment
from klever.core.vtg.emg.common.c import Variable, Function
from klever.core.vtg.emg.common.process import Dispatch, Receive, Block, Subprocess
from klever.core.vtg.emg.translation.code import control_function_comment_begin, control_function_comment_end
from klever.core.vtg.emg.translation.fsa_translator import FSATranslator
from klever.core.vtg.emg.translation.fsa_translator.common import initialize_automaton_variables
from klever.core.vtg.emg.translation.fsa_translator.label_control_function import label_based_function


class StateTranslator(FSATranslator):

    def __init__(self, logger, conf, source, collection, cmodel, entry_fsa, model_fsa, event_fsa):
        raise NotImplementedError('State translator requires update to the newest API which has not been done')

        self.__state_variables = dict()
        self.__state_chains_memoization = dict()
        self.__switchers_cache = dict()

        conf.setdefault('actions composition', default_value=[])
        self.__jump_types = set([t for t in [Dispatch, Receive, Block, Subprocess]
                                 if t.__name__ not in get_or_die(conf, 'actions composition')])
        super(StateTranslator, self).__init__(logger, conf, source, cmodel, entry_fsa, model_fsa, event_fsa)

    def _relevant_checks(self, relevant_automata):
        checks = []

        for name in sorted(relevant_automata.keys()):
            for st in relevant_automata[name]['states']:
                index = self.__state_chain(relevant_automata[name]["automaton"], st)
                if index:
                    checks.append("{} == {}".
                                  format(self.__state_variable(relevant_automata[name]["automaton"]).name, index))
        return checks

    def _join_cf_code(self, automaton):
        raise NotImplementedError('State control functions are not designed to be run in separate threads')

    def _call_cf_code(self, automaton, parameter='0'):
        return "{}({});".format(self._control_function(automaton).name, parameter),

    def _dispatch_blocks(self, action, automaton, function_parameters, automata_peers, replicative):
        pre = []
        post = []
        blocks = []

        for name in automata_peers:
            for r_state in automata_peers[name]['states']:
                block = []

                # Assign parameters
                if len(function_parameters) > 0:
                    block.append("/* Transfer parameters */")

                    for index in range(len(function_parameters)):
                        # Determine expression
                        receiver_access = automata_peers[name]['automaton'].process.\
                            resolve_access(r_state.action.parameters[index])

                        # Determine var
                        var = automata_peers[name]['automaton'].determine_variable(receiver_access.label)
                        self._cmodel.add_global_variable(var, automaton.process.file, extern=True)
                        block.append("{} = arg{};".format(var.name, index))

                # Update state
                block.extend(['', "/* Switch state of the receiver */"])
                block.extend(self.__switch_state_code(automata_peers[name]['automaton'], r_state))
                self._cmodel.add_global_variable(self.__state_variable(automata_peers[name]['automaton']),
                                                 automaton.process.file, extern=True)

                blocks.append(block)

        return pre, blocks, post

    def _receive(self, action, automaton):
        code, v_code, conditions, comments = super(StateTranslator, self)._receive(action, automaton)
        code.append("/* Automaton itself cannot perform a receive, look at a dispatcher's code */".
                    format(action.action.name))

        return code, v_code, conditions, comments

    def _compose_control_function(self, automaton):
        self._logger.info(
            "Generate state-based control function for automaton {!r} based on process {!r} of category {!r}".
            format(automaton.identifier, automaton.process.name, automaton.process.category))

        # Get function prototype
        cf = self._control_function(automaton)
        cf.definition_file = automaton.process.file

        # Do process initialization
        model_flag = True
        if automaton not in self._model_fsa:
            model_flag = False
            v_code = ["/* Control function based on process '{}' generated for interface category '{}' */".
                      format(automaton.process.name, automaton.process.category)]
            f_code = []
            tab = 0
            state_chains = self.__state_chains(automaton)

            if len(state_chains) == 0:
                f_code.append('/* Empty control function */')
            else:
                if len(state_chains) == 1:
                    new_v_code, new_f_code = self.__state_chain_code(automaton,
                                                                     list(state_chains.values())[0])
                    v_code.extend(new_v_code)
                    f_code.extend(['\t' * tab + stm for stm in new_f_code])
                else:
                    f_code.append('\t' * tab + 'switch ({}) '.format(self.__state_variable(automaton).name) + '{')
                    tab += 1
                    for case in sorted(list(state_chains.keys())):
                        f_code.append('\t' * tab + 'case {}: '.format(case) + '{')
                        tab += 1
                        new_v_code, new_f_code = self.__state_chain_code(automaton, state_chains[case])
                        v_code.extend(new_v_code)
                        f_code.extend(['\t' * tab + stm for stm in new_f_code])
                        f_code.append('\t' * tab + 'break;')
                        tab -= 1
                        f_code.append('\t' * tab + '}')
                    f_code.append('\t' * tab + 'default: ldv_assume(0);')
                    tab -= 1
                    f_code.append('\t' * tab + '}')

            # Add comments
            comment_data = {'name': 'var_init'}
            # TODO: Reimplement this
            v_code = [model_comment('CONTROL_FUNCTION_INIT_BEGIN', 'Declare auxiliary variables.', comment_data)] + \
                     v_code + \
                     [model_comment('CONTROL_FUNCTION_INIT_END', 'Declare auxiliary variables.', comment_data)]
            v_code.insert(0, control_function_comment_begin(cf.name, automaton.process.comment, automaton.identifier))
            f_code.append(control_function_comment_end(cf.name, automaton.process.category))

            # Add loop for nested case
            cf.body.extend(v_code + f_code)
            self._cmodel.add_global_variable(self.__state_variable(automaton), automaton.process.file, extern=False,
                                             initialize=True)
        else:
            # Generate function body
            label_based_function(self._conf, self._source, automaton, cf, model_flag)

        # Add function to source code to print
        self._cmodel.add_function_definition(cf)
        if model_flag:
            for file in self._source.get_source_function(automaton.process.name).declaration_files:
                self._cmodel.add_function_declaration(file, cf, extern=True)
        else:
            for var in automaton.variables():
                self._cmodel.add_global_variable(var, automaton.process.file, initialize=False)
        return

    def _entry_point(self):
        self._logger.info("Generate body for entry point function {!r}".format(self._cmodel.entry_name))
        body = []
        # Init original states
        for automaton in [self._entry_fsa] + self._event_fsa:
            body.extend(self.__set_initial_state(automaton))

        # Generate loop
        body.extend([
            ''
            "while(1) {",
            "\tswitch(ldv_undef_int()) {"
        ])

        for index, automaton in enumerate([self._entry_fsa] + self._event_fsa):
            body.extend(
                [
                    "\t\tcase {}: ".format(index),
                    '\t\t\t{}'.format(self._call_cf(automaton, '0')),
                    "\t\tbreak;"
                ]
            )
        body.extend(
            [
                "\t\tdefault: ldv_assume(0);",
                "\t}",
                "}"
            ]
        )

        return self._cmodel.compose_entry_point(body)

    def _normalize_event_fsa(self, automaton):
        """
        There are no specific requirements implied on fsa structure.

        :param automaton: Automaton object.
        :return: None
        """
        pass

    def __state_variable(self, automaton):
        if automaton.identifier not in self.__state_variables:
            var = Variable('emg_statevar_{}'.format(automaton.identifier),  'int a')
            var.use += 1
            self.__state_variables[automaton.identifier] = var

        return self.__state_variables[automaton.identifier]

    def __state_chain_code(self, automaton, state_block):
        code = []
        v_code = []

        for action in state_block:
            new_v_code, block = automaton.code[action]
            v_code.extend(new_v_code)
            code.extend(block)

        if not isinstance(state_block[0].action, Receive):
            code.append('/* Set the next state */')
            code.extend(self.__switch_state_code(automaton, action))
        else:
            code.append('/* Omit state transition for a receive */')

        return v_code, code

    def __state_chains(self, automaton):
        if automaton.identifier not in self.__state_chains_memoization:
            blocks_stack = sorted(list(automaton.fsa.initial_states), key=lambda f: f.identifier)
            self.__state_chains_memoization[automaton.identifier] = dict()
            while len(blocks_stack) > 0:
                origin = blocks_stack.pop()
                block = []
                state_stack = [origin]
                no_jump = True

                state = None
                while len(state_stack) > 0:
                    state = state_stack.pop()
                    block.append(state)
                    no_jump = (type(state.action) not in self.__jump_types) and no_jump

                    if len(state.successors) == 1 and (no_jump or type(list(state.successors)[0].action)
                                                       not in self.__jump_types) \
                            and not isinstance(state.action, Receive):
                        state_stack.append(list(state.successors)[0])

                self.__state_chains_memoization[automaton.identifier][origin.identifier] = block

                for state in [st for st in sorted(list(state.successors), key=lambda f: f.identifier)
                              if st.identifier not in self.__state_chains_memoization[automaton.identifier]
                              and st not in blocks_stack]:
                    blocks_stack.append(state)

        return self.__state_chains_memoization[automaton.identifier]

    def __state_chain(self, automaton, state_identifier):
        chains = self.__state_chains(automaton)

        # Expect exactly single chain with the state identifier
        try:
            found = (o for o in chains if state_identifier in next(chains[o]))
        except StopIteration:
            raise RuntimeError("Seems that state {!r} is not reachable in automaton {!r}".
                               format(state_identifier, automaton.process.name))

        return found

    def __switch_state_code(self, automaton, state):
        code = []

        successors = state.successors
        if len(state.successors) == 1:
            code.append('{} = {};'.format(self.__state_variable(automaton).name, successors[0].identifier))
        elif len(state.successors) == 2:
            code.extend([
                'if (ldv_undef_int())',
                '\t{} = {};'.format(self.__state_variable(automaton).name, successors[0].identifier),
                'else',
                '\t{} = {};'.format(self.__state_variable(automaton).name, successors[1].identifier),
            ])
        elif len(state.successors) > 2:
            switch_call = self.__state_switch([st.identifier for st in successors])
            code.append('{} = {};'.format(self.__state_variable(automaton).name, switch_call))
        else:
            code.append('/* Reset automaton state */')
            code.extend(self.__set_initial_state(automaton))

        return code

    def __state_switch(self, states):
        key = ''.join(sorted([str(i) for i in states]))
        if key in self.__switchers_cache:
            return self.__switchers_cache[key]['call']

        # Generate switch function
        name = 'emg_switch_{}'.format(len(list(self.__switchers_cache.keys())))
        func = Function(name, 'int f(void)')
        # todo: Incorrect file
        func.definition_file = self._cmodel.entry_file

        # Generate switch body
        code = list()
        code.append('switch (ldv_undef_int()) {')
        for index in range(len(states)):
            code.append('\tcase {}: '.format(index) + '{')
            code.append('\t\treturn {};'.format(states[index]))
            code.append('\t\tbreak;')
            code.append('\t}')
        code.append('\tdefault: ldv_assume(0);')
        code.append('}')
        func.body.extend(code)

        # Add function
        self._cmodel.add_function_definition(func)

        invoke = '{}()'.format(name)
        self.__switchers_cache[key] = {
            'call': invoke,
            'function':  func
        }
        return invoke

    def __set_initial_state(self, automaton):
        body = list()
        body.append('/* Initialize initial state of automaton {!r} with process {!r} of category {!r} */'.
                    format(automaton.identifier, automaton.process.name, automaton.process.category))

        body.extend(initialize_automaton_variables(self._conf, automaton))
        initial_states = sorted(list(automaton.fsa.initial_states), key=lambda s: s.identifier)
        if len(initial_states) == 1:
            body.append('{} = {};'.format(self.__state_variable(automaton).name, initial_states[0].identifier))
        elif len(initial_states) == 2:
            body.extend([
                'if (ldv_undef_int())',
                '\t{} = {};'.format(self.__state_variable(automaton).name, initial_states[0].identifier),
                'else',
                '\t{} = {};'.format(self.__state_variable(automaton).name, initial_states[1].identifier),
            ])
        elif len(initial_states) > 2:
            body.append('switch (ldv_undef_int()) {')
            for index in range(len(initial_states)):
                body.append('\tcase {}: '.format(index) + '{')
                body.append('\t\t{} = {};'.format(self.__state_variable(automaton).name,
                                                  initial_states[index].identifier))
                body.append('\t\tbreak;'.format(self.__state_variable(automaton).name,
                                                initial_states[index].identifier))
                body.append('\t}')
                body.append('\tdefault: ldv_assume(0);')
                body.append('}')

        return body
