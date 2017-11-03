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
from core.vtg.emg.common import get_conf_property, get_necessary_conf_property
from core.vtg.emg.common.process import Dispatch, get_common_parameter
from core.vtg.emg.translator.code import Variable
from core.vtg.emg.translator.fsa_translator import FSATranslator
from core.vtg.emg.translator.fsa_translator.common import extract_relevant_automata, choose_file, add_model_function
from core.vtg.emg.translator.fsa_translator.label_control_function import label_based_function, normalize_fsa


class LabelTranslator(FSATranslator):

    def __init__(self, logger, conf, analysis, cmodel, entry_fsa, model_fsa, event_fsa):
        self.__thread_variables = dict()
        super(LabelTranslator, self).__init__(logger, conf, analysis, cmodel, entry_fsa, model_fsa, event_fsa)

    def _relevant_checks(self, relevant_automata):
        return list()

    def _join_cf_code(self, file, automaton):
        if automaton.process.self_parallelism and get_necessary_conf_property(self._conf, 'self parallelism') and \
                get_conf_property(self._conf, 'pure pthread interface'):
            for var in self.__thread_variable(automaton, 'pair'):
                self._cmodel.add_global_variable(var, file, extern=True)
            return 'pthread_join({}, 0);'
        else:
            if automaton.process.self_parallelism and get_necessary_conf_property(self._conf, 'self parallelism'):
                sv = self.__thread_variable(automaton, 'array')
                self._cmodel.add_global_variable(sv, file, extern=True)
                return 'pthread_join_N({}, 0);'.format(sv.name)
            else:
                sv = self.__thread_variable(automaton, 'single')
                self._cmodel.add_global_variable(sv, file, extern=True)
                return 'pthread_join({}, 0);'.format(sv.name)

    def _call_cf_code(self, file, automaton, parameter='0'):
        if automaton.process.self_parallelism and get_necessary_conf_property(self._conf, 'self parallelism') and \
                get_conf_property(self._conf, 'pure pthread interface'):
            for var in self.__thread_variable(automaton, 'pair'):
                self._cmodel.add_global_variable(var, file, extern=True)
            # Leave the first parameter to fill twise later
            return 'pthread_create({}, 0, {}, {});'.\
                format('{}', self._control_function(automaton).name, parameter)
        else:
            if automaton.process.self_parallelism and get_necessary_conf_property(self._conf, 'self parallelism'):
                sv = self.__thread_variable(automaton, 'array')
                self._cmodel.add_global_variable(sv, file, extern=True)
                return 'pthread_create_N({}, 0, {}, {});'.\
                    format(sv.name,self._control_function(automaton).name, parameter)
            else:
                sv = self.__thread_variable(automaton, 'single')
                self._cmodel.add_global_variable(sv, file, extern=True)
                return 'pthread_create({}, 0, {}, {});'.\
                    format('& ' + sv.name, self._control_function(automaton).name, parameter)

    def _dispatch_blocks(self, state, file, automaton, function_parameters, param_interfaces, automata_peers,
                         replicative):
        pre = []
        post = []
        blocks = []

        for name in (n for n in automata_peers if len(automata_peers[n]['states']) > 0):
            decl = self._get_cf_struct(automaton, function_parameters)
            cf_param = 'cf_arg_{}'.format(automata_peers[name]['automaton'].identifier)
            vf_param_var = Variable(cf_param, None, decl.take_pointer, False, 'local')
            pre.append(vf_param_var.declare() + ';')

            if replicative:
                for r_state in automata_peers[name]['states']:
                    block = list()
                    block.append('{} = {}(sizeof({}));'.format(vf_param_var.name, self._cmodel.mem_function_map["ALLOC"],
                                                        decl.identifier))
                    for index in range(len(function_parameters)):
                        block.append('{}->arg{} = arg{};'.format(vf_param_var.name, index, index))
                    if r_state.action.replicative:
                        call = self._call_cf(file, automata_peers[name]['automaton'], cf_param)
                        if get_conf_property(self._conf, 'direct control functions calls'):
                            block.append(call)
                        else:
                            if automata_peers[name]['automaton'].process.self_parallelism and \
                                    get_necessary_conf_property(self._conf, 'self parallelism') and \
                                    get_conf_property(self._conf, 'pure pthread interface'):
                                thread_vars = self.__thread_variable(automata_peers[name]['automaton'], type='pair')
                                for v in thread_vars:
                                    # Expect that for this particular case the first argument is unset
                                    block.extend(['ret = {}'.format(call.format("& " + v.name)),
                                                  'ldv_assume(ret == 0);'])
                            else:
                                block.extend(['ret = {}'.format(call),
                                              'ldv_assume(ret == 0);'])
                        blocks.append(block)
                        break
                    else:
                        self._logger.warning(
                            'Cannot generate dispatch based on labels for receive {} in process {} with category {}'
                            .format(r_state.action.name,
                                    automata_peers[name]['automaton'].process.name,
                                    automata_peers[name]['automaton'].process.category))
            # todo: Pretty ugly, but works
            elif state.action.name.find('dereg') != -1:
                block = list()
                call = self._join_cf(file, automata_peers[name]['automaton'])
                if get_conf_property(self._conf, 'direct control functions calls'):
                    block.append(call)
                else:
                    if automata_peers[name]['automaton'].process.self_parallelism and \
                            get_necessary_conf_property(self._conf, 'self parallelism') and \
                            get_conf_property(self._conf, 'pure pthread interface'):
                        thread_vars = self.__thread_variable(automata_peers[name]['automaton'], type='pair')
                        for v in thread_vars:
                            # Expect that for this particular case the first argument is unset
                            block.extend(['ret = {}'.format(call.format(v.name)),
                                          'ldv_assume(ret == 0);'])
                    else:
                        block.extend(['ret = {}'.format(call),
                                      'ldv_assume(ret == 0);'])
                blocks.append(block)

        return pre, blocks, post

    def _receive(self, state, automaton):
        code, v_code, conditions, comments = super(LabelTranslator, self)._receive(self, state, automaton)

        automata_peers = {}
        if len(state.action.peers) > 0:
            # Do call only if model which can be called will not hang
            extract_relevant_automata(self._event_fsa + self._model_fsa + [self._entry_fsa],
                                      automata_peers, state.action.peers, Dispatch)

            # Add additional condition
            if state.action.condition and len(state.action.condition) > 0:
                # Arguments comparison is not supported in label-based model
                for statement in (s for s in state.action.condition if s.find('$ARG') == -1):
                    cn = self._cmodel.text_processor(automaton, statement)
                    conditions.extend(cn)

            if state.action.replicative:
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

                if len(param_declarations) > 0:
                    decl = self._get_cf_struct(automaton, [val for val in param_declarations])
                    var = Variable('data', None, decl.take_pointer, False, 'local')
                    v_code.append('/* Received labels */')
                    v_code.append('{} = ({}*) arg0;'.format(var.declare(), decl.to_string('', typedef='complex')))
                    v_code.append('')

                    code.append('/* Assign recieved labels */')
                    code.append('if (data) {')
                    for index in range(len(param_expressions)):
                        code.append('\t{} = data->arg{};'.format(param_expressions[index], index))
                    code.append('\t{}({});'.format(self._cmodel.free_function_map["FREE"], 'data'))
                    code.append('}')
                else:
                    code.append('{}({});'.format(self._cmodel.free_function_map["FREE"], 'arg0'))
            else:
                code.append('/* Skip a non-replicative signal receiving */'.format(state.desc['label']))
        else:
            # Generate comment
            code.append("/* Signal receive {!r} does not expect any signal from existing processes */".
                        format(state.action.name))

        return code, v_code, conditions, comments
        
    def _compose_control_function(self, automaton):
        self._logger.info('Generate label-based control function for automaton {} based on process {} of category {}'.
                          format(automaton.identifier, automaton.process.name, automaton.process.category))

        # Get function prototype
        cf = self._control_function(automaton)

        # Do process initialization
        model_flag = True
        if automaton not in self._model_fsa:
            model_flag = False
            if not get_conf_property(self._conf, 'direct control functions calls') and automaton is not self._entry_fsa:
                if automaton.process.self_parallelism and \
                        get_necessary_conf_property(self._conf, 'self parallelism') and \
                        get_conf_property(self._conf, 'pure pthread interface'):
                    for var in self.__thread_variable(automaton, 'pair'):
                        self._cmodel.add_global_variable(var, choose_file(self._cmodel, self._analysis, automaton), False)
                elif automaton.process.self_parallelism and get_necessary_conf_property(self._conf, 'self parallelism'):
                    self._cmodel.add_global_variable(self.__thread_variable(automaton, 'array'),
                                                     choose_file(self._cmodel, self._analysis, automaton), extern=False)
                else:
                    self._cmodel.add_global_variable(self.__thread_variable(automaton, 'single'),
                                                     choose_file(self._cmodel, self._analysis, automaton), extern=False)

        # Generate function body
        label_based_function(self._conf, self._analysis, automaton, cf, model_flag)

        # Add function to source code to print
        self._cmodel.add_function_definition(choose_file(self._cmodel, self._analysis, automaton), cf)
        self._cmodel.add_function_declaration(self._cmodel.entry_file, cf, extern=True)
        if model_flag:
            add_model_function(self._analysis, self._cmodel, automaton, cf)
        return

    def _entry_point(self):
        self._logger.info("Finally generate an entry point function {!r}".format(self._cmodel.entry_name))
        body = [
            '{}(0);'.format(self._control_function(self._entry_fsa).name)
        ]
        return self._cmodel.compose_entry_point(body)

    def _normalize_model_fsa(self, automaton):
        """
        Since label-based control functions are generated use correponding function to normalize fsa.

        :param automaton: Automaton object.
        :return: None
        """
        normalize_fsa(automaton, self._compose_action)

    def _normalize_event_fsa(self, automaton):
        """
        Since label-based control functions are generated use correponding function to normalize fsa.

        :param automaton: Automaton object.
        :return: None
        """
        normalize_fsa(automaton, self._compose_action)

    def __thread_variable(self, automaton, type='single'):
        if automaton.identifier not in self.__thread_variables:
            signature = 'pthread_t a'
            if type == 'pair':
                thread_vars = []
                for i in range(2):
                    var = Variable('ldv_thread_{}_{}'.format(automaton.identifier, i), None, signature, True, 'global')
                    var.use += 1
                    thread_vars.append(var)
                ret = thread_vars
            else:
                if type == 'array':
                    signature = 'pthread_t **a'
                var = Variable('ldv_thread_{}'.format(automaton.identifier),  None, signature, True, 'global')
                var.use += 1
                ret = var
            self.__thread_variables[automaton.identifier] = ret

        return self.__thread_variables[automaton.identifier]

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
