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

from klever.core.vtg.emg.common.process import Dispatch
from klever.core.vtg.emg.translation.fsa_translator import FSATranslator
from klever.core.vtg.emg.common.c import Variable
from klever.core.vtg.emg.common.c.types import import_declaration
from klever.core.vtg.emg.translation.fsa_translator.common import extract_relevant_automata
from klever.core.vtg.emg.translation.fsa_translator.label_control_function import label_based_function


class LabelTranslator(FSATranslator):

    def __init__(self, logger, conf, source, collection, cmodel, entry_fsa, model_fsa, event_fsa):
        self.__thread_variables = sortedcontainers.SortedDict()
        super().__init__(logger, conf, source, collection, cmodel, entry_fsa, model_fsa, event_fsa)

    def _relevant_checks(self, relevant_automata):
        return []

    def _join_cf_code(self, automaton):
        if automaton.self_parallelism and self._conf.get('self parallel processes') and \
                self._conf.get('pure pthread interface'):
            for var in self.__thread_variable(automaton, 'pair'):
                self._cmodel.add_global_variable(var, automaton.process.file, extern=True)
            return 'pthread_join({}, 0);'

        if automaton.self_parallelism and self._conf.get('self parallel processes'):
            sv = self.__thread_variable(automaton, 'array')
            self._cmodel.add_global_variable(sv, automaton.process.file, extern=True)
            return 'pthread_join_N({}, 0);'.format(sv.name)

        sv = self.__thread_variable(automaton, 'single')
        self._cmodel.add_global_variable(sv, automaton.process.file, extern=True)
        return 'pthread_join({}, 0);'.format(sv.name)

    def _call_cf_code(self, automaton, parameter='0'):
        if automaton.self_parallelism and self._conf.get('self parallel processes') and \
                self._conf.get('pure pthread interface'):
            for var in self.__thread_variable(automaton, 'pair'):
                self._cmodel.add_global_variable(var, automaton.process.file, extern=True)
            # Leave the first parameter to fill twice later
            return 'pthread_create({}, 0, {}, {});'.\
                format('{}', self._control_function(automaton).name, parameter)

        if automaton.self_parallelism and self._conf.get('self parallel processes'):
            sv = self.__thread_variable(automaton, 'array')
            self._cmodel.add_global_variable(sv, automaton.process.file, extern=True)
            return 'pthread_create_N({}, 0, {}, {});'.\
                format(sv.name, self._control_function(automaton).name, parameter)

        sv = self.__thread_variable(automaton, 'single')
        self._cmodel.add_global_variable(sv, automaton.process.file, extern=True)
        return 'pthread_create({}, 0, {}, {});'.\
            format('& ' + sv.name, self._control_function(automaton).name, parameter)

    def _dispatch_blocks(self, action, automaton, function_parameters, automata_peers, replicative):
        pre = []
        post = []
        blocks = []

        for a_peer in (a for a in automata_peers if automata_peers[a]['actions']):
            decl = self._get_cf_struct(automaton, function_parameters)
            cf_param = 'cf_arg_{}'.format(str(a_peer))
            vf_param_var = Variable(cf_param, decl.take_pointer)
            pre.append(vf_param_var.declare() + ';')

            if replicative:
                for r_action in automata_peers[a_peer]['actions']:
                    block = ['{} = {}(sizeof({}));'.
                             format(vf_param_var.name, self._cmodel.mem_function_map["ALLOC"], str(decl))]
                    for index, _ in enumerate(function_parameters):
                        block.append('{}->arg{} = arg{};'.format(vf_param_var.name, index, index))  # pylint: disable=duplicate-string-formatting-argument
                    if r_action.replicative:
                        call = self._call_cf(a_peer, cf_param)
                        if self._conf.get('direct control functions calls'):
                            block.append(call)
                        else:
                            if a_peer.self_parallelism and self._conf.get("self parallel processes") and \
                                    self._conf.get('pure pthread interface'):
                                thread_vars = self.__thread_variable(a_peer, var_type='pair')
                                for v in thread_vars:
                                    # Expect that for this particular case the first argument is unset
                                    block.extend(['ret = {}'.format(call.format("& " + v.name)),
                                                  'ldv_assume(ret == 0);'])
                            else:
                                block.extend(['ret = {}'.format(call),
                                              'ldv_assume(ret == 0);'])
                        blocks.append(block)
                        break

                    self._logger.warning(
                        'Cannot generate dispatch based on labels for receive {} in process {} with category {}'
                        .format(r_action.name, a_peer.process.name, a_peer.process.category))
            # todo: Pretty ugly, but works
            elif action.name.find('dereg') != -1:
                block = []
                call = self._join_cf(automata_peers[a_peer]['automaton'])
                if not self._conf.get('direct control functions calls'):
                    if automata_peers[a_peer]['automaton'].self_parallelism and self._conf.get("self parallel processes")\
                            and self._conf.get('pure pthread interface'):
                        thread_vars = self.__thread_variable(automata_peers[a_peer]['automaton'], var_type='pair')
                        for v in thread_vars:
                            # Expect that for this particular case the first argument is unset
                            block.extend(['ret = {}'.format(call.format(v.name)),
                                          'ldv_assume(ret == 0);'])
                    else:
                        block.extend(['ret = {}'.format(call),
                                      'ldv_assume(ret == 0);'])
                    blocks.append(block)

        return pre, blocks, post

    def _receive(self, action, automaton):
        code, v_code, conditions, comments = super()._receive(action, automaton)

        automata_peers = {}
        action_peers = self._collection.peers(automaton.process, {str(action)})
        if len(action_peers) > 0:
            # Do call only if model which can be called will not hang
            extract_relevant_automata(self._logger, self._event_fsa + self._model_fsa + [self._entry_fsa],
                                      automata_peers, action_peers, Dispatch)

            # Add additional condition
            if action.replicative:
                param_declarations = []
                param_expressions = []

                if len(action.parameters) > 0:
                    for index, param in enumerate(action.parameters):
                        receiver_access = automaton.process.resolve_access(param)
                        var = automaton.determine_variable(receiver_access.label)
                        param_declarations.append(var.declaration)
                        param_expressions.append(var.name)

                if action.condition and len(action.condition) > 0:
                    # Arguments comparison is not supported in label-based model
                    for statement in action.condition:
                        # Replace first $ARG expressions
                        s = statement
                        for index, _ in enumerate(param_expressions):
                            replacement = 'data->arg{}'.format(index)
                            s = s.replace("$ARG{}".format(index + 1), replacement)
                        cn = self._cmodel.text_processor(automaton, s)
                        conditions.extend(cn)

                # This should be before precondition because it may check values unpacked in this section
                if len(param_declarations) > 0:
                    decl = self._get_cf_struct(automaton, param_declarations)
                    var = Variable('data', decl.take_pointer)
                    v_code += ['/* Received labels */',
                               '{} = ({}*) arg0;'.format(var.declare(), decl.to_string('', typedef='complex')), '']

                    code += ['/* Assign received labels */',
                             'if (data) {'] + \
                            ['\t{} = data->arg{};'.format(v, i) for i, v in enumerate(param_expressions)] + \
                            ['\t{}({});'.format(self._cmodel.free_function_map["FREE"], 'data'), '}']
                else:
                    code.append('{}({});'.format(self._cmodel.free_function_map["FREE"], 'arg0'))
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

        # Do process initialization
        model_flag = True
        if automaton not in self._model_fsa:
            model_flag = False
            if not self._conf.get('direct control functions calls') and automaton is not self._entry_fsa:
                if automaton.self_parallelism and self._conf.get("self parallel processes") and \
                        self._conf.get('pure pthread interface'):
                    for var in self.__thread_variable(automaton, 'pair'):
                        self._cmodel.add_global_variable(var, automaton.process.file, False)
                elif automaton.self_parallelism and self._conf.get("self parallel processes"):
                    self._cmodel.add_global_variable(self.__thread_variable(automaton, 'array'),
                                                     automaton.process.file, extern=False)
                else:
                    self._cmodel.add_global_variable(self.__thread_variable(automaton, 'single'),
                                                     automaton.process.file, extern=False)

        # Generate function body
        label_based_function(self._conf, self._source, automaton, cf, model_flag)

        # Add function to source code to print
        self._cmodel.add_function_definition(cf)
        self._cmodel.add_function_declaration(automaton.process.file, cf, extern=True)
        if model_flag:
            for file in self._source.get_source_function(automaton.process.name).declaration_files:
                self._cmodel.add_function_declaration(file, cf, extern=True)

    def _entry_point(self):
        self._logger.info("Finally generate an entry point function {!r}".format(self._cmodel.entry_name))
        cf = self._control_function(self._entry_fsa)
        if self._conf.get("self parallel model"):
            cf.declaration = import_declaration("void *(*start_routine)(void *)")
            body = [
                "pthread_t **thread;",
                "pthread_create_N(thread, 0, {}, 0);".format(cf.name),
                "pthread_join_N(thread, {});".format(cf.name)
            ]
        else:
            body = [
                '{}(0);'.format(cf.name)
            ]
        if self._entry_fsa.process.file != self._cmodel.entry_file:
            self._cmodel.add_function_declaration(self._cmodel.entry_file, cf, extern=True)
        return self._cmodel.compose_entry_point(body)

    def __thread_variable(self, automaton, var_type='single'):
        if automaton.identifier not in self.__thread_variables:
            signature = 'pthread_t a'
            if var_type == 'pair':
                thread_vars = []
                for i in range(2):
                    var = Variable('emg_thread_{}_{}'.format(automaton.identifier, i), signature)
                    var.use += 1
                    thread_vars.append(var)
                ret = thread_vars
            else:
                if var_type == 'array':
                    signature = 'pthread_t **a'
                var = Variable('emg_thread_{}'.format(automaton.identifier),  signature)
                var.use += 1
                ret = var
            self.__thread_variables[automaton.identifier] = ret

        return self.__thread_variables[automaton.identifier]
