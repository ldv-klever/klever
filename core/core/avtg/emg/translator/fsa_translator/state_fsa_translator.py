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
from core.avtg.emg.common import get_necessary_conf_property
from core.avtg.emg.translator.code import Variable
from core.avtg.emg.translator.fsa_translator import FSATranslator


class StateTranslator(FSATranslator):

    def __init__(self, logger, conf, analysis, cmodel, entry_fsa, model_fsa, callback_fsa):
        self.__state_variables = dict()
        super(StateTranslator, self).__init__(logger, conf, analysis, cmodel, entry_fsa, model_fsa, callback_fsa)

    def _relevant_checks(self, relevant_automata):
        checks = []

        if not get_necessary_conf_property(self._conf, 'nested automata'):
            for name in sorted(relevant_automata.keys()):
                for st in relevant_automata[name]['states']:
                    index = self.__state_block(relevant_automata[name]["automaton"], st)
                    if index:
                        checks.append("{} == {}".
                                      format(self.__state_variable(relevant_automata[name]["automaton"]).name, index))
        return checks

    def __state_variable(self, automaton):
        if automaton.identifier not in self.__state_variables:
            var = Variable('ldv_statevar_{}'.format(automaton.identifier),  None, 'int a', True)
            var.use += 1
            self.__state_variables[automaton.identifier] = var

        return self.__state_variables[automaton.identifier]

    def __state_block(self, automaton, state_identifier):
        raise NotImplementedError

    def _join_cf_code(self, file, automaton):
        raise NotImplementedError('State control functions are not designed to be run in separate threads')

    def _call_cf_code(self, file, automaton, parameter='0'):
        raise NotImplementedError('State control functions are not designed to be run in separate threads')

    def _dispatch_blocks(self, body, file, automaton, function_parameters, param_interfaces, automata_peers,
                         replicative):
        blocks = []
        
        for name in automata_peers:
            for r_state in automata_peers[name]['states']:
                block = []

                # Assign parameters
                if len(function_parameters) > 0:
                    block.append("/* Transfer parameters */")

                    for index in range(len(function_parameters)):
                        # Determine exression
                        receiver_access = automata_peers[name]['automaton'].process.\
                            resolve_access(r_state.action.parameters[index], param_interfaces[index].identifier)

                        # Determine var
                        var = automata_peers[name]['automaton'].\
                            determine_variable(receiver_access.label, param_interfaces[index].identifier)
                        self._cmodel.add_global_variable(var, file, extern=True)

                        receiver_expr = receiver_access.access_with_variable(var)
                        block.append("{} = arg{};".format(receiver_expr, index))

                # Update state
                block.extend(['', "/* Switch state of the reciever */"])
                block.extend(self.__switch_state_code(self._analysis, automata_peers[name]['automaton'],
                                                      r_state))
                self._cmodel.add_global_variable(self.__state_variable(automata_peers[name]['automaton']),
                                                 file, extern=True)

                blocks.append(block)
                        
        return blocks

    def _receive(self, state, automaton):
        code, v_code, conditions, comments = super(StateTranslator, self)._receive(self, state, automaton)

        code.append("/* Automaton itself cannot perform a receive */".format(state.action.name))

        return code, v_code, conditions, comments
    
    def __switch_state_code(self, analysis, automaton, state):
        code = []

        successors = state.successors
        if len(state.successors) == 1:
            code.append('{} = {};'.format(automaton.state_variable.name, successors[0].identifier))
        elif len(state.successors) == 2:
            code.extend([
                'if (ldv_undef_int())',
                '\t{} = {};'.format(automaton.state_variable.name, successors[0].identifier),
                'else',
                '\t{} = {};'.format(automaton.state_variable.name, successors[1].identifier),
            ])
        elif len(state.successors) > 2:
            switch_call = self._state_switch([st.identifier for st in successors],
                                              self._choose_file(analysis, automaton))
            code.append('{} = {};'.format(automaton.state_variable.name, switch_call))
        else:
            code.append('/* Reset automaton state */')            
            code.extend(self._set_initial_state(automaton))
            if get_necessary_conf_property(self._conf, 'nested automata'):
                code.append('goto out_{};'.format(automaton.identifier))

        return code

    def _entry_point(self):
        raise NotImplementedError

    def _control_function(self):
        raise NotImplementedError

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'