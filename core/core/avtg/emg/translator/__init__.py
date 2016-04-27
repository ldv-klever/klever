import os
import copy
import abc

from core.avtg.emg.common.signature import import_signature
from core.avtg.emg.common.code import FunctionDefinition, Aspect, Variable
from core.avtg.emg.common.interface import Container, Callback
from core.avtg.emg.translator.fsa import Automaton
from core.avtg.emg.common.process import Receive, Dispatch, Call, CallRetval, Condition, Subprocess, \
    get_common_parameter


class AbstractTranslator(metaclass=abc.ABCMeta):

    CF_PREFIX = 'ldv_control_function_'

    def __init__(self, logger, conf, avt, header_lines=None, aspect_lines=None):
        self.logger = logger
        self.conf = conf
        self.task = avt
        self.files = {}
        self.aspects = {}
        self.entry_file = None
        self.model_aspects = []
        self._callback_fsa = []
        self._structures = {}
        self._model_fsa = []
        self._entry_fsa = None
        self._nested_automata = False
        self._omit_all_states = False
        self._omit_states = {
            'callback': True,
            'dispatch': True,
            'receive': True,
            'return value': False,
            'subprocess': False,
            'condition': False,
        }
        self.__identifier_cnt = -1
        self.__instance_modifier = 1
        self.__max_instances = None

        # Read translation options
        if "translation options" not in self.conf:
            self.conf["translation options"] = {}
        if "max instances number" in self.conf["translation options"]:
            self.__max_instances = int(self.conf["translation options"]["max instances number"])
        if "instance modifier" in self.conf["translation options"]:
            self.__instance_modifier = self.conf["translation options"]["instance modifier"]
        if "pointer initialization" not in self.conf["translation options"]:
            self.conf["translation options"]["pointer initialization"] = {}
        if "pointer free" not in self.conf["translation options"]:
            self.conf["translation options"]["pointer free"] = {}
        for tag in ['structures', 'arrays', 'unions', 'primitives', 'enums', 'functions']:
            if tag not in self.conf["translation options"]["pointer initialization"]:
                self.conf["translation options"]["pointer initialization"][tag] = False
            if tag not in self.conf["translation options"]["pointer free"]:
                self.conf["translation options"]["pointer free"][tag] = \
                    self.conf["translation options"]["pointer initialization"][tag]
        if 'omit all states' in self.conf['translation options']:
            self._omit_all_states = self.conf['translation options']['omit all states']
        if "omit states" in self.conf["translation options"]:
            self._omit_states = self.conf["translation options"]["omit states"]
        if not self._omit_states:
            if 'omit composition' in self.conf["translation options"]:
                for tag in self._omit_states:
                    if tag in self.conf["translation options"]['omit composition']:
                        self._omit_states[tag] = self.conf["translation options"]['omit composition'][tag]
        if "nested automata" in self.conf["translation options"]:
            self._nested_automata = self.conf["translation options"]["nested automata"]
        if "direct control function calls" in self.conf["translation options"]:
            self.direct_cf_calls = self.conf["translation options"]["direct control function calls"]

        self.jump_types = set()
        if self._omit_states['callback']:
            self.jump_types.add(Call)
        if self._omit_states['dispatch']:
            self.jump_types.add(Dispatch)
        if self._omit_states['receive']:
            self.jump_types.add(Receive)
        if self._omit_states['return value']:
            self.jump_types.add(CallRetval)
        if self._omit_states['subprocess']:
            self.jump_types.add(Subprocess)
        if self._omit_states['condition']:
            self.jump_types.add(Condition)

        if not header_lines:
            self.additional_headers = []
        else:
            self.additional_headers = header_lines
        if not aspect_lines:
            self.additional_aspects = []
        else:
            self.additional_aspects = aspect_lines

    def translate(self, analysis, model):
        # Determine entry point name and file
        self.logger.info("Determine entry point name and file")
        self.__determine_entry(analysis)
        self.logger.info("Going to generate entry point function {} in file {}".
                         format(self.entry_point_name, self.entry_file))

        # Prepare entry point function
        self.logger.info("Generate C code from an intermediate model")
        self._generate_code(analysis, model)

        # Print aspect text
        self.logger.info("Add individual aspect files to the abstract verification task")
        self.__generate_aspects()

        # Add aspects to abstract task
        self.logger.info("Add individual aspect files to the abstract verification task")
        self.__add_aspects()

        # Set entry point function in abstract task
        self.logger.info("Add entry point function to abstract verification task")
        self.__add_entry_points()

        self.logger.info("Model translation is finished")

    def _generate_code(self, analysis, model):
        # Determine how many instances is required for a model
        self.logger.info("Determine how many instances is required to add to an environment model for each process")
        for process in model.event_processes:
            base_list = self._initial_instances(analysis, process)
            base_list = self._instanciate_processes(analysis, base_list, process)
            self.logger.info("Generate {} FSA instances for process {} with category {}".
                             format(len(base_list), process.name, process.category))

            for instance in base_list:
                fsa = Automaton(self.logger, analysis, instance, self.__yeild_identifier())
                self._callback_fsa.append(fsa)

        # Generate automata for models
        for process in model.model_processes:
            self.logger.info("Generate FSA for kernel model process {}".format(process.name))
            processes = self._instanciate_processes(analysis, [process], process)
            for instance in processes:
                fsa = Automaton(self.logger, analysis, instance, self.__yeild_identifier())
                self._model_fsa.append(fsa)

        # Generate state machine for init an exit
        # todo: multimodule automaton (issues #6563, #6571, #6558)
        self.logger.info("Generate FSA for module initialization and exit functions")
        self._entry_fsa = Automaton(self.logger, analysis, model.entry_process, self.__yeild_identifier())

        # Generates base code blocks
        for automaton in self._callback_fsa + self._model_fsa + [self._entry_fsa]:
            for state in list(automaton.fsa.states):
                automaton.generate_code(analysis, model, self, state)

        # Save digraphs
        automaton_dir = "automaton"
        self.logger.info("Save automata to directory {}".format(automaton_dir))
        os.mkdir(automaton_dir)
        for automaton in self._callback_fsa + self._model_fsa + [self._entry_fsa]:
            automaton.save_digraph(automaton_dir)

        # Generate control functions
        self.logger.info("Generate control functions for each automaton")
        self._generate_control_functions(analysis, model)

        # Add structures to declare types
        self.files[self.entry_file]['types'] = sorted(self._structures.values(), key=lambda v: v.identifier)

    def _instanciate_processes(self, analysis, instances, process):
        base_list = instances

        # Copy base instances for each known implementation
        relevant_multi_containers = set()
        accesses = process.accesses()
        self.logger.debug("Calculate relevant containers with several implementations for process {} for category {}".
                          format(process.name, process.category))
        for access in [accesses[name] for name in sorted(accesses.keys())]:
            for inst_access in [inst for inst in sorted(access, key=lambda i: i.expression) if inst.interface]:
                if type(inst_access.interface) is Container and \
                                len(analysis.implementations(inst_access.interface)) > 1 and \
                                inst_access.interface not in relevant_multi_containers:
                    relevant_multi_containers.add(inst_access.interface)
                elif len(inst_access.complete_list_interface) > 1:
                    impl_cnt = [intf for intf in inst_access.complete_list_interface if type(intf) is Container and
                                len(analysis.implementations(intf)) > 1]
                    if len(impl_cnt) > 0:
                        relevant_multi_containers.add(impl_cnt[0])

        # Copy instances for each implementation of a container
        if len(relevant_multi_containers) > 0:
            self.logger.debug(
                "Found {} relevant containers with several implementations for process {} for category {}".
                format(str(len(relevant_multi_containers)), process.name, process.category))
            for interface in sorted(list(relevant_multi_containers), key=lambda intf: intf.identifier):
                new_base_list = []
                implementations = analysis.implementations(interface)

                for implementation in implementations:
                    for instance in base_list:
                        newp = self._copy_process(instance)
                        newp.forbide_except(analysis, implementation)
                        new_base_list.append(newp)

                base_list = list(new_base_list)

        new_base_list = []
        for instance in base_list:
            # Copy callbacks or resources which are not tied to a container
            accesses = instance.accesses()
            relevant_multi_leafs = set()
            for access in [accesses[name] for name in sorted(accesses.keys())]:
                relevant_multi_leafs.update([inst for inst in access if inst.interface and
                                             type(inst.interface) is Callback and
                                             len(instance.get_implementations(analysis, inst)) > 1])

            if len(relevant_multi_leafs) > 0:
                self.logger.debug("Found {} accesses with several implementations for process {} for category {}".
                                  format(len(relevant_multi_leafs), process.name, process.category))
                for access in sorted(list(relevant_multi_leafs), key=lambda intf: intf.expression):
                    for implementation in analysis.implementations(access.interface):
                        newp = self._copy_process(instance)
                        newp.forbide_except(analysis, implementation)
                        new_base_list.append(newp)
            else:
                new_base_list.append(instance)

        base_list = new_base_list
        return base_list

    def _initial_instances(self, analysis, process):
        base_list = []
        undefined_labels = []
        # Determine nonimplemented containers
        self.logger.debug("Calculate number of not implemented labels and collateral values for process {} with "
                          "category {}".format(process.name, process.category))
        for label in [process.labels[name] for name in sorted(process.labels.keys())
                      if len(process.labels[name].interfaces) > 0]:
            nonimplemented_intrerfaces = [interface for interface in label.interfaces
                                          if len(analysis.implementations(analysis.interfaces[interface])) == 0]
            if len(nonimplemented_intrerfaces) > 0:
                undefined_labels.append(label)

        # Determine is it necessary to make several instances
        if len(undefined_labels) > 0:
            for i in range(self.__instance_modifier):
                base_list.append(self._copy_process(process))
        else:
            base_list.append(self._copy_process(process))

        self.logger.info("Prepare {} instances for {} undefined labels of process {} with category {}".
                         format(len(base_list), len(undefined_labels), process.name, process.category))

        return base_list

    def extract_relevant_automata(self, automata_peers, peers, sb_type=None):
        for peer in peers:
            relevant_automata = [automaton for automaton in self._callback_fsa
                                 if automaton.process.name == peer["process"].name]
            for automaton in relevant_automata:
                if automaton.identifier not in automata_peers:
                    automata_peers[automaton.identifier] = {
                        "automaton": automaton,
                        "states": set()
                    }
                for state in [node for node in automaton.fsa.states
                              if node.action and node.action.name == peer["subprocess"].name]:
                    if not sb_type or isinstance(state.action, sb_type):
                        automata_peers[automaton.identifier]["states"].add(state)

    def registration_intf_check(self, analysis, model, function_call):
        automata_peers = {}

        name = analysis.callback_name(function_call)
        if name:
            # Caclulate relevant models
            if name in analysis.modules_functions:
                relevant_models = analysis.collect_relevant_models(name)

                # Get list of models
                process_models = [model for model in model.model_processes if model.name in relevant_models]

                # Check relevant state machines for each model
                for model in process_models:
                    signals = [model.actions[name] for name in sorted(model.actions.keys())
                               if (type(model.actions[name]) is Receive or
                                   type(model.actions[name]) is Dispatch) and
                               len(model.actions[name].peers) > 0]

                    # Get all peers in total
                    peers = []
                    for signal in signals:
                        peers.extend(signal.peers)

                    # Add relevant state machines
                    self.extract_relevant_automata(automata_peers, peers)
        else:
            self.logger.warning("Cannot find module function for callback '{}'".format(function_call))

        return automata_peers

    def _copy_process(self, process):
        inst = copy.copy(process)
        if self.__max_instances == 0:
            raise RuntimeError('EMG tries to generate more instances than it is allowed by configuration ({})'.
                               format(int(self.conf["translation options"]["max instances number"])))
        elif self.__max_instances:
            self.__max_instances -= 1
        return inst

    def __yeild_identifier(self):
        self.__identifier_cnt += 1
        return self.__identifier_cnt

    def __determine_entry(self, analysis):
        if len(analysis.inits) == 1:
            file = list(analysis.inits.keys())[0]
            self.logger.info("Choose file {} to add an entry point function".format(file))
            self.entry_file = file
        elif len(analysis.inits) < 1:
            raise RuntimeError("Cannot generate entry point without module initialization function")

        if "entry point" in self.conf:
            self.entry_point_name = self.conf["entry point"]
        else:
            self.entry_point_name = "main"

    def _add_function_definition(self, file, function):
        if file not in self.files:
            self.files[file] = {
                'variables': {},
                'functions': {}
            }

        self.files[file]['functions'][function.name] = function

    def _add_global_variable(self, file, variable):
        if file not in self.files:
            self.files[file] = {
                'variables': {},
                'functions': {}
            }

        self.files[file]['variables'][variable.name] = variable

    def _generate_control_functions(self, analysis, model):
        global_switch_automata = []

        # Generate automata control function
        self.logger.info("Generate control functions for the environment model")
        for automaton in sorted(list(self._callback_fsa), key=lambda fsa: fsa.identifier):
            if self._omit_all_states:
                func = self._generate_label_cfunction(analysis, automaton)
            else:
                func = self._generate_state_cfunction(analysis, automaton)

            if func and not self._nested_automata:
                global_switch_automata.append(func)

        if self._omit_all_states:
            func = self._generate_label_cfunction(analysis, self._entry_fsa)
        else:
            func = self._generate_state_cfunction(analysis, self._entry_fsa)
        if func:
            global_switch_automata.append(func)
        else:
            raise ValueError('Entry point function must contain init/exit automaton control function')

        # Generate model control function
        for name in (pr.name for pr in model.model_processes):
            for automaton in [a for a in sorted(list(self._model_fsa), key=lambda fsa: fsa.identifier)
                              if a.process.name == name]:
                self._generate_label_cfunction(analysis, automaton, name)

        # Generate entry point function
        func = self._generate_entry_functions(global_switch_automata)
        self._add_function_definition(self.entry_file, func)

    def _generate_entry_functions(self, global_switch_automata):
        self.logger.info("Finally generate entry point function {}".format(self.entry_point_name))
        # FunctionDefinition prototype
        ep = FunctionDefinition(
            self.entry_point_name,
            self.entry_file,
            "void {}(void)".format(self.entry_point_name),
            False
        )

        body = [
            "while(1) {",
            "\tswitch(ldv_undef_int()) {"
        ]

        for index in range(len(global_switch_automata)):
            cfunction = global_switch_automata[index]
            body.extend(
                [
                    "\t\tcase {}: ".format(index),
                    "\t\t\t{}(0);".format(cfunction.name),
                    "\t\tbreak;"
                ]
            )
        body.extend(
            [
                "\t\tdefault: break;",
                "\t}",
                "}"
            ]
        )
        ep.body.concatenate(body)

        return ep

    def _generate_call(self, automaton, state):
        # Generate function call and corresponding function
        fname = "ldv_{}_{}_{}_{}".format(automaton.process.name, state.action.name, automaton.identifier,
                                         state.identifier)
        if not state.code:
            return ['/* Skip callback, since no callbacks has been found */']

        # Generate special function with call
        if 'retval' in state.code:
            ret = state.code['callback'].points.return_value.to_string('')
            ret_expr = 'return '
            cf_ret_expr = state.code['retval'] + ' = '
        else:
            ret = 'void'
            ret_expr = ''
            cf_ret_expr = ''

        resources = [state.code['callback']] + state.code['callback'].points.parameters
        resources = [resources[p].to_string('arg{}'.format(p)) for p in range(len(resources))]
        function = FunctionDefinition(fname,
                                      state.code['file'],
                                      "{} {}({})".format(ret, fname, ', '.join(resources)),
                                      True)

        function.body.concatenate("/* Callback {} */".format(state.action.name))
        inv = [
            '/* Callback {} */'.format(state.action.name)
        ]

        # Generate callback call
        if state.code['check pointer']:
            f_invoke = cf_ret_expr + fname + '(' + ', '.join([state.code['invoke']] + state.code['parameters']) + ');'
            inv.append('if ({})'.format(state.code['invoke']))
            inv.append('\t' + f_invoke)
            call = ret_expr + '(*arg0)' + '(' + ", ".join(["arg{}".format(i) for i in range(1, len(resources))]) + ')'
        else:
            f_invoke = cf_ret_expr + fname + '(' + \
                       ', '.join([state.code['variable']] + state.code['parameters']) + ');'
            inv.append(f_invoke)
            call = ret_expr + '({})'.format(state.code['invoke']) + \
                   '(' + ", ".join(["arg{}".format(i) for i in range(1, len(resources))]) + ')'
        function.body.concatenate('{};'.format(call))

        self._add_function_definition(state.code['file'], function)

        return inv

    def _generate_relevant_checks(self, state):
        checks = []

        # Add state checks
        if 'relevant automata' in state.code:
            for name in sorted(state.code['relevant automata'].keys()):
                for st in state.code['relevant automata'][name]['states']:
                    checks.append("{} == {}".
                                  format(state.code['relevant automata'][name]["automaton"].state_variable.name,
                                         st.identifier))

        return checks

    def _generate_dispatch(self, analysis, automaton, state):
        # Generate dispatch function
        body = []
        blocks = []
        for name in state.code['relevant automata']:
            for st in state.code['relevant automata'][name]['states']:
                tmp_body = []
                receiver_condition = []

                if st.action.condition:
                    receiver_condition = st.action.condition

                # Add parameters
                for index in range(len(state.action.parameters)):
                    # Determine dispatcher parameter
                    interface = get_common_parameter(state.action, automaton.process, index)

                    # Determine receiver parameter
                    receiver_access = state.code['relevant automata'][name]['automaton'].process. \
                        resolve_access(st.action.parameters[index], interface.identifier)
                    receiver_expr = receiver_access. \
                        access_with_variable(state.code['relevant automata'][name]["automaton"].
                                             determine_variable(analysis, receiver_access.label,
                                                                interface.identifier))

                    # Determine dispatcher parameter
                    dispatcher_access = automaton.process. \
                        resolve_access(state.action.parameters[index], interface.identifier)
                    dispatcher_expr = dispatcher_access. \
                        access_with_variable(automaton.determine_variable(analysis, dispatcher_access.label,
                                                                          interface.identifier))

                    # Replace guard
                    receiver_condition = [stm.replace("$ARG{}".format(index + 1), dispatcher_expr) for stm
                                          in receiver_condition]

                    # Generate assignment
                    tmp_body.append("{} = {};".format(receiver_expr, dispatcher_expr))

                if len(receiver_condition) > 0:
                    new_receiver_condition = []
                    for stm in receiver_condition:
                        new_receiver_condition.extend(state.code['relevant automata'][name]["automaton"].
                                                      text_processor(analysis, stm))
                    receiver_condition = new_receiver_condition
                    dispatcher_condition = receiver_condition
                else:
                    dispatcher_condition = []

                tmp_body.append("{} = {};".
                                format(state.code['relevant automata'][name]["automaton"].state_variable.name,
                                       st.identifier))

                blocks.append({
                    'guards': dispatcher_condition,
                    'body': tmp_body
                })

        if state.action.broadcast:
            for index in range(len(blocks)):
                tab = 0
                if len(blocks[0]['guards']) > 0:
                    body.append('if ({}) '.format(' && '.join(blocks[index]['guards'])) + '{')
                    tab += 1
                for stm in blocks[index]['body']:
                    body.append('\t' * tab + stm)
                if len(blocks[0]['guards']) > 0:
                    body.append('}')
                    tab -= 1

        else:
            if len(blocks) == 1:
                if len(blocks[0]['guards']) > 0:
                    body.append('ldv_assert({});'.format(' && '.join(blocks[0]['guards'])))
                for stm in blocks[0]['body']:
                    body.append(stm)
            elif len(blocks) == 2:
                first = True
                for block in blocks:
                    if first:
                        body.append('if (ldv_nondet_int()) {')
                        first = False
                    else:
                        body.append('else {')

                    if len(blocks[0]['guards']) > 0:
                        body.append('\tldv_assert({});'.format(' && '.join(block[index]['guards'])))
                    for stm in block['body']:
                        body.append('\t' + stm)
                body.append('}')
            else:
                for index in range(len(blocks)):
                    body.append('\tcase {}: '.format(blocks[index]) + '{')
                    if len(blocks[index]['guards']) > 0:
                        body.append('\t\tldv_assert({});'.format(' && '.join(blocks[index]['guards'])))
                    for stm in blocks[index]['body']:
                        body.append('\t\t' + stm)
                    body.append('}')
                body.append('\tdefault: ldv_stop();')
                body.append('}')

        df = FunctionDefinition(
            "ldv_{}_{}_dispatch_{}".format(automaton.identifier, state.identifier, state.action.name),
            self.entry_file,
            "void f(void)",
            False
        )

        df.body.concatenate(body)
        self._add_function_definition(self.entry_file, df)
        automaton.functions.append(df)

        return [
            '/* Dispatch {} */'.format(state.action.name),
            '{}({});'.format(df.name, ', '.join(df_parameters))
        ]

    def _call_cf(self, automaton, parameter='0'):
        sv = automaton.thread_variable

        if self.direct_cf_calls:
            return '{}({});'.format(self.CF_PREFIX + str(automaton.identifier), parameter)
        else:
            return 'ldv_thread_create({}, {}, {});'.format('& ' + sv.name,
                                                           self.CF_PREFIX + str(automaton.identifier),
                                                           parameter)

    def join_cf(self, automaton):
        sv = automaton.thread_variable

        return 'ldv_thread_join({});'.format('& ' + sv.name)

    def _get_cf_struct(self, automaton, params):
        cache_identifier = ''
        for param in params:
            cache_identifier += param.identifier

        if cache_identifier not in self._structures:
            struct_name = 'ldv_struct_{}_{}'.format(automaton.process.name, automaton.identifier)
            if struct_name in self._structures:
                raise KeyError('Structure name is not unique')

            decl = import_signature('struct {} a'.format(struct_name))
            for index in range(len(params)):
                decl.fields['arg{}'.format(index)] = params[index]

            self._structures[cache_identifier] = decl
        else:
            decl = self._structures[cache_identifier]

        return decl

    def _generate_nested_dispatch(self, analysis, automaton, state):
        if self.direct_cf_calls:
            body = []
        else:
            body = ['int ret;']

        if len(state.code['relevant automata']) == 0:
            return ['/* Skip dispatch {} without processes to receive */']

        # Check dispatch type
        replicative = False
        for name in state.code['relevant automata']:
            for st in state.code['relevant automata'][name]['states']:
                if st.action.replicative:
                    replicative = True
                    break

        # Determine parameters
        df_parameters = []
        function_parameters = []
        cf_param = '0'
        if len(state.action.parameters) != 0:
            # Add parameters
            function_parameters = []
            for index in range(len(state.action.parameters)):
                # Determine dispatcher parameter
                interface = get_common_parameter(state.action, automaton.process, index)

                # Determine dispatcher parameter
                dispatcher_access = automaton.process.resolve_access(state.action.parameters[index],
                                                                     interface.identifier)
                variable = automaton.determine_variable(analysis, dispatcher_access.label, interface.identifier)
                dispatcher_expr = dispatcher_access.access_with_variable(variable)

                function_parameters.append(variable.declaration)
                df_parameters.append(dispatcher_expr)

            if replicative and len(function_parameters) > 0:
                decl = self._get_cf_struct(automaton, function_parameters)
                body.append(Variable('cf_arg', None, decl, False).declare() + ';')
                cf_param = '& cf_arg'
                for index in range(len(function_parameters)):
                    body.append('cf_arg.arg{} = arg{};'.format(index, index))
                body.append('')

        tmp_body = []
        if replicative:
            for name in state.code['relevant automata']:
                for r_state in state.code['relevant automata'][name]['states']:
                    if r_state.action.replicative:
                        tmp_body.append(self._call_cf(state.code['relevant automata'][name]['automaton'], cf_param))
                        break
                    else:
                        self.logger.warning('Cannot generate dispatch based on labels for receive {} in process {}'
                                            ' with category {}'.
                                            format(r_state.action.name,
                                                   state.code['relevant automata'][name]['automaton'].process.name,
                                                   state.code['relevant automata'][name]['automaton'].process.category))
        else:
            for name in state.code['relevant automata']:
                tmp_body.append(self.join_cf(state.code['relevant automata'][name]['automaton']))

        if state.action.broadcast:
            for index in range(len(tmp_body)):
                if self.direct_cf_calls:
                    body.append(tmp_body[index])
                else:
                    body.append('ret = {}'.format(tmp_body[index]))
                    body.append('ldv_assume(ret == 0);')
        else:
            if len(tmp_body) == 1:
                if self.direct_cf_calls:
                    body.append(tmp_body[0])
                else:
                    body.append('ret = {}'.format(tmp_body[0]))
                    body.append('ldv_assume(ret == 0);')
            elif len(tmp_body) == 2:
                for index in range(2):
                    if index == 0:
                        body.append('if (ldv_nondet_int()) {')
                    else:
                        body.append('else {')
                    if self.direct_cf_calls:
                        body.append('\t' + tmp_body[index])
                    else:
                        body.append('\tret = {}'.format(tmp_body[index]))
                        body.append('\tldv_assume(ret == 0);')
                    body.append('}')
            else:
                body.append('switch (ldv_undef_int()) {')
                for index in range(len(tmp_body)):
                    body.append('\tcase {}: '.format(index) + '{')
                    if self.direct_cf_calls:
                        body.append('\t\t' + tmp_body[index])
                    else:
                        body.append('\t\tret = {}'.format(tmp_body[index]))
                        body.append('\t\tldv_assume(ret == 0);')
                    body.append('\t};')
                body.append('\tdefault: ldv_stop();')
                body.append('};')
        body.append('return;')

        if len(function_parameters) > 0:
            df = FunctionDefinition(
                "ldv_{}_{}_dispatch_{}".format(automaton.identifier, state.identifier, state.action.name),
                self.entry_file,
                "void f({})".format(', '.join([function_parameters[index].to_string('arg{}'.format(index)) for index in
                                               range(len(function_parameters))])),
                False
            )
        else:
            df = FunctionDefinition(
                "ldv_{}_{}_dispatch_{}".format(automaton.identifier, state.identifier, state.action.name),
                self.entry_file,
                "void f(void)",
                False
            )

        df.body.concatenate(body)
        automaton.functions.append(df)
        self._add_function_definition(self.entry_file, df)
        return [
            '/* Dispatch {} */'.format(state.action.name),
            '{}({});'.format(df.name, ', '.join(df_parameters))
        ]

    def _generate_action_base_block(self, analysis, automaton, state):
        block = []
        if type(state.action) is Call:
            if not self._omit_all_states:
                checks = self._generate_relevant_checks(state)
                state.code['guard'].extend(checks)

            call = self._generate_call(automaton, state)
            block.extend(call)
        elif type(state.action) is CallRetval:
            block.append('/* Skip {} */'.format(state.desc['label']))
        elif type(state.action) is Condition:
            for stm in state.code['body']:
                block.append(stm)
        elif type(state.action) is Dispatch:
            if not self._omit_all_states and not self._nested_automata:
                checks = self._generate_relevant_checks(state)
                state.code['guard'].extend(checks)

            if self._nested_automata:
                call = self._generate_nested_dispatch(analysis, automaton, state)
            else:
                call = self._generate_dispatch(analysis, automaton, state)

            block.extend(call)
        elif type(state.action) is Receive:
            block.append('/* Skip {} */'.format(state.desc['label']))
        elif type(state.action) is Subprocess:
            for stm in state.code['body']:
                block.append(stm)
        else:
            raise ValueError('Unexpected state action')

        return block

    def _label_sequence(self, analysis, automaton, initial_states, name):
        f_code = []
        v_code = []

        state_stack = []
        if len(initial_states) > 1:
            action = Condition(name)
            new = automaton.fsa.new_state(action)
            new.successors = initial_states
            cd = {
                'body': ['/* Artificial state */'],
                'guard': []
            }
            new.code = cd
            state_stack.append(new)
        else:
            state_stack.append(list(automaton.fsa.initial_states)[0])

        processed_states = set()
        conditional_stack = []
        tab = 0
        while len(state_stack) > 0:
            state = state_stack.pop()
            processed_states.add(state)

            if type(state.action) is Subprocess:
                code = [
                    '/* Jump to subprocess {} initial state */'.format(state.action.name),
                    'goto ldv_{}_{};'.format(state.action.name, automaton.identifier)
                ]
            else:
                code = self._generate_action_base_block(analysis, automaton, state)

            if len(conditional_stack) > 0 and conditional_stack[-1]['condition'] == 'switch' and \
                    state in conditional_stack[-1]['state'].successors:
                if conditional_stack[-1]['counter'] != 0:
                    tab -= 1
                    f_code.append('\t' * tab + '}')
                f_code.append('\t' * tab + 'case {}: '.format(conditional_stack[-1]['counter']) + '{')
                conditional_stack[-1]['counter'] += 1
                conditional_stack[-1]['cases left'] -= 1
                tab += 1

                if state.code and len(state.code['guard']) > 0:
                    f_code.append('\t' * tab + 'if ({}) '.format(' && '.join(sorted(state.code['guard']))) + '{')
                    tab += 1
                    for stm in code:
                        f_code.append('\t' * tab + stm)
                    tab -= 1
                    f_code.append('\t' * tab + '}')
                    f_code.append('\t' * tab + 'else')
                    tab += 1
                    f_code.append('\t' * tab + 'ldv_stop();')
                    tab -= 1
                else:
                    for stm in code:
                        f_code.append('\t' * tab + stm)
            elif len(conditional_stack) > 0 and conditional_stack[-1]['condition'] == 'if' and \
                    (state in automaton.fsa.initial_states or state in conditional_stack[-1]['state'].successors):
                if conditional_stack[-1]['counter'] != 0:
                    tab -= 1
                    f_code.append('\t' * tab + '}')
                    f_code.append('\t' * tab + 'else {')
                    tab += 1

                conditional_stack[-1]['counter'] += 1
                conditional_stack[-1]['cases left'] -= 1

                if state.code and len(state.code['guard']) > 0:
                    f_code.append('\t' * tab + 'ldv_assume({});'.format(' && '.join(sorted(state.code['guard']))))
                for stm in code:
                    f_code.append('\t' * tab + stm)
            else:
                f_code.append('')

                if state.code and len(state.code['guard']) > 0:
                    f_code.append('\t' * tab + 'if ({}) '.format(' && '.join(state.code['guard'])) + '{')
                    tab += 1
                    for stm in code:
                        f_code.append('\t' * tab + stm)
                    tab -= 1
                    f_code.append('\t' * tab + '}')
                else:
                    for stm in code:
                        f_code.append('\t' * tab + stm)

            last_action = False
            closed_condition = True
            while closed_condition:
                last_action = False
                closed_condition = False
                if len(conditional_stack) > 0:
                    if len(state.successors) == 0:
                        last_action = True
                    elif type(state.action) is Subprocess:
                        last_action = True
                    else:
                        for succ in state.successors:
                            trivial_predecessors = len([p for p in succ.predecessors if type(p.action) is not Subprocess])
                            if trivial_predecessors > 1:
                                last_action = True
                                break

                    if last_action and conditional_stack[-1]['cases left'] == 0 and \
                            conditional_stack[-1]['condition'] == 'switch':
                        tab -= 1
                        f_code.append('\t' * tab + '}')
                        f_code.append('\t' * tab + 'default: ldv_stop();')
                        tab -= 1
                        f_code.append('\t' * tab + '}')
                        conditional_stack.pop()
                        closed_condition = True
                    elif last_action and conditional_stack[-1]['cases left'] == 0 and \
                            conditional_stack[-1]['condition'] == 'if':
                        tab -= 1
                        f_code.append('\t' * tab + '}')
                        conditional_stack.pop()
                        closed_condition = True

            if (type(state.action) is not Subprocess or len(state.code['guard']) > 0) and \
                    (not last_action or (last_action and closed_condition)):
                if len(state.successors) == 1:
                    if list(state.successors)[0] not in state_stack and \
                                    list(state.successors)[0] not in processed_states:
                        state_stack.append(list(state.successors)[0])
                elif len(state.successors) > 1:
                    if_condition = None
                    if len(state.successors) == 2:
                        successors = sorted(list(state.successors), key=lambda f: f.identifier)
                        if_condition = 'ldv_undef_int()'

                    if if_condition:
                        for succ in successors:
                            state_stack.append(succ)

                        condition = {
                            'condition': 'if',
                            'state': state,
                            'cases left': 2,
                            'counter': 0
                        }

                        f_code.append('\t' * tab + 'if ({}) '.format(if_condition) + '{')
                        tab += 1

                        conditional_stack.append(condition)
                    else:
                        for succ in sorted(list(state.successors), key=lambda f: f.identifier):
                            state_stack.append(succ)

                        condition = {
                            'condition': 'switch',
                            'state': state,
                            'cases left': len(list(state.successors)),
                            'counter': 0
                        }

                        f_code.append('\t' * tab + 'switch (ldv_undef_int()) {')
                        tab += 1

                        conditional_stack.append(condition)

        return [v_code, f_code]

    def _generate_label_cfunction(self, analysis, automaton, aspect=None):
        self.logger.info('Generate label-based control function for automaton {} based on process {} of category {}'.
                         format(automaton.identifier, automaton.process.name, automaton.process.category))
        v_code = []
        f_code = []

        # Check necessity to return a value
        if aspect and analysis.kernel_functions[aspect].declaration.return_value and \
                analysis.kernel_functions[aspect].declaration.return_value.identifier != 'void':
            ret_expression = 'return $res;'
        else:
            ret_expression = 'return;'

        # Generate function definition
        cf = self.__new_control_function(analysis, automaton, v_code, f_code, aspect)

        main_v_code, main_f_code = self._label_sequence(analysis, automaton, automaton.fsa.initial_states,
                                                        'initial_state')
        v_code.extend(main_v_code)
        f_code.extend(main_f_code)
        f_code.append(ret_expression)

        processed = []
        for subp in [s for s in sorted(automaton.fsa.states, key=lambda s: s.identifier)
                     if type(s.action) is Subprocess]:
            if subp.action.name not in processed:
                sp_v_code, sp_f_code = self._label_sequence(analysis, automaton, subp.successors,
                                                            '{}_initial_state'.format(subp.action.name))

                v_code.extend(sp_v_code)
                f_code.extend([
                    '',
                    '/* Sbprocess {} */'.format(subp.action.name),
                    'ldv_{}_{}:'.format(subp.action.name, automaton.identifier)
                ])
                f_code.extend(sp_f_code)
                f_code.append(ret_expression)
                processed.append(subp.action.name)

        if not self._nested_automata and not aspect:
            self._add_global_variable(self.entry_file, automaton.state_variable)
        elif not aspect:
            self._add_global_variable(self.entry_file, automaton.thread_variable)

        cf.body.concatenate(v_code + f_code)
        automaton.control_function = cf
        return cf

    def __new_control_function(self, analysis, automaton, v_code, f_code, aspect=None):
        # Function type
        if aspect:
            cf = Aspect(aspect, analysis.kernel_functions[aspect].declaration, 'around')
            self.model_aspects.append(cf)
        else:
            cf = FunctionDefinition(self.CF_PREFIX + str(automaton.identifier), self.entry_file, 'void f(void *cf_arg)',
                                    False)
            self._add_function_definition(self.entry_file, cf)

            if self._nested_automata:
                param_declarations = []
                param_expressions = []
                for receive in [r for r in automaton.process.actions.values() if type(r) is Receive and r.replicative]:
                    if len(receive.parameters) > 0:
                        for index in range(len(receive.parameters)):
                            # Determine dispatcher parameter
                            interface = get_common_parameter(receive, automaton.process, index)

                            # Determine receiver parameter
                            receiver_access = automaton.process.resolve_access(receive.parameters[index],
                                                                               interface.identifier)
                            var = automaton.determine_variable(analysis, receiver_access.label, interface.identifier)
                            receiver_expr = receiver_access.access_with_variable(var)

                            param_declarations.append(var.declaration)
                            param_expressions.append(receiver_expr)
                        break

                if len(param_declarations) > 0:
                    decl = self._get_cf_struct(automaton, [val for val in param_declarations])
                    var = Variable('cf_arg_struct', None, decl.take_pointer, False)
                    v_code.append('/* Received labels */')
                    v_code.append('{} = ({}*) arg0;'.format(var.declare(), decl.to_string('')))
                    v_code.append('')

                    f_code.append('')
                    f_code.append('/* Assign recieved labels */')
                    f_code.append('if (cf_arg_struct) {')
                    for index in range(len(param_expressions)):
                        f_code.append('\t{} = cf_arg_struct->arg{};'.format(param_expressions[0], index))
                    f_code.append('}')

        if self._nested_automata:
            for var in automaton.variables(analysis):
                definition = var.declare() + ";"
                v_code.append(definition)
        else:
            for var in automaton.variables(analysis):
                self._add_global_variable(self.entry_file, var)

        return cf

    def _state_sequence(self, analysis, automaton, origin):
        first = True
        state_stack = [origin]
        code = []
        no_jump = True

        while len(state_stack) > 0:
            state = state_stack.pop()
            no_jump = (type(state.action) not in self.jump_types) and no_jump
            act = self._generate_action_base_block(analysis, automaton, state)
            if state.code and len(state.code['guard']) > 0 and first:
                code.append('ldv_assert({});'.format(
                    ' && '.join(sorted(['{} == {}'.format(automaton.state_variable.name, state.identifier)] +
                                       state.code['guard']))))
                code.extend(act)
                first = False
            elif state.code and len(state.code['guard']) > 0:
                code.append('if({}) {'.format(
                    ' && '.join(sorted(['{} == {}'.format(automaton.state_variable.name, state.identifier)] +
                                       state.code['guard']))))
                for st in act:
                    code.append('\t' + st)
                code.append('}')
            else:
                code.extend(act)

            if len(state.successors) == 1 and (no_jump or list(state.successors)[0] not in self.jump_types):
                state_stack.append(list(state.successors)[0])
                code.append('')

        successors = sorted(list(state.successors), key=lambda f: f.identifier)
        if len(state.successors) == 1:
            code.append('{} = {};'.format(automaton.state_variable.name, successors[0].identifier))
        elif len(state.successors) == 2:
            code.extend([
                'if (ldv_nondet_int())',
                '\t{} = {};'.format(automaton.state_variable.name, successors[0].identifier),
                'else',
                '\t{} = {};'.format(automaton.state_variable.name, successors[1].identifier),
            ])
        elif len(state.successors) > 2:
            code.append('switch (ldv_nondet_int()) {')
            for index in range(len(successors)):
                code.append('\tcase {}: {} = {};'.format(index, automaton.state_variable.name,
                                                         successors[index].identifier))
            code.append('\tdefault: ldv_stop();')
            code.append('}')

        return code, successors

    def _generate_state_cfunction(self, analysis, automaton):
        self.logger.info('Generate state-based control function for automaton {} based on process {} of category {}'.
                         format(automaton.identifier, automaton.process.name, automaton.process.category))
        v_code = []
        f_code = []

        # Generate function definition
        cf = self.__new_control_function(analysis, automaton, v_code, f_code, None)

        state_stack = sorted(list(automaton.fsa.initial_states), key=lambda f: f.identifier)
        blocks = {}
        while len(state_stack) > 0:
            origin = state_stack.pop()
            code, successors = self._state_sequence(analysis, automaton, origin)
            blocks[origin.identifier] = code

            for state in [st for st in successors if st.identifier not in blocks and st not in state_stack]:
                state_stack.append(state)

        if self._nested_automata:
            raise NotImplementedError
        else:
            f_code.append('switch ({}) '.format(automaton.state_variable.name) + '{')
            for identifier in sorted(list(blocks.keys())):
                f_code.append('\tcase {}: '.format(identifier) + '{')
                f_code.extend(['\t\t' + st for st in blocks[identifier]])
                f_code.append('\t}')
            f_code.append('}')

        self._add_global_variable(self.entry_file, automaton.state_variable)
        cf.body.concatenate(v_code + f_code)
        automaton.control_function = cf

        return cf

    def __generate_aspects(self):
        aspect_dir = "aspects"
        self.logger.info("Create directory for aspect files {}".format("aspects"))
        os.makedirs(aspect_dir, exist_ok=True)

        for grp in self.task['grps']:
            # Generate function declarations
            self.logger.info('Add aspects to C files of group "{0}"'.format(grp['id']))
            for cc_extra_full_desc_file in sorted([df for df in grp['cc extra full desc files'] if 'in file' in df],
                                                  key=lambda f: f['in file']):
                # Aspect text
                lines = list()

                # Before file
                lines.append('before: file ("$this")\n')
                lines.append('{\n')

                if len(self.additional_headers) > 0:
                    lines.append("/* EMG additional headers */\n")
                    lines.extend(self.additional_headers)
                    lines.append("\n")
                lines.append('}\n')

                if len(self.additional_aspects) > 0:
                    lines.append("\n")
                    lines.append("/* EMG additional non-generated aspects */\n")
                    lines.extend(self.additional_aspects)
                    lines.append("\n")

                # After file
                lines.append('after: file ("$this")\n')
                lines.append('{\n')

                lines.append("/* EMG type declarations */\n")
                for file in sorted(self.files.keys()):
                    if "types" in self.files[file]:
                        for tp in self.files[file]["types"]:
                            lines.append(tp.to_string('') + " {\n")
                            for field in sorted(list(tp.fields.keys())):
                                lines.append("\t{};\n".format(tp.fields[field].to_string(field)))
                            lines.append("};\n")
                            lines.append("\n")

                lines.append("/* EMG Function declarations */\n")
                for file in sorted(self.files.keys()):
                    if "functions" in self.files[file]:
                        for function in [self.files[file]["functions"][name] for name
                                         in sorted(self.files[file]["functions"].keys())]:
                            if function.export and cc_extra_full_desc_file["in file"] != file:
                                lines.extend(function.get_declaration(extern=True))
                            else:
                                lines.extend(function.get_declaration(extern=False))

                lines.append("\n")
                lines.append("/* EMG variable declarations */\n")
                for file in sorted(self.files):
                    if "variables" in self.files[file]:
                        for variable in [self.files[file]["variables"][name] for name in
                                         sorted(self.files[file]["variables"].keys())]:
                            if variable.export and cc_extra_full_desc_file["in file"] != file:
                                lines.extend([variable.declare(extern=True) + ";\n"])
                            else:
                                lines.extend([variable.declare(extern=False) + ";\n"])

                lines.append("\n")
                lines.append("/* EMG variable initialization */\n")
                for file in sorted(self.files):
                    if "variables" in self.files[file]:
                        for variable in [self.files[file]["variables"][name] for name in
                                         sorted(self.files[file]["variables"].keys())]:
                            if cc_extra_full_desc_file["in file"] == file and variable.value:
                                lines.extend([variable.declare_with_init({}) + ";\n"])

                lines.append("\n")
                lines.append("/* EMG function definitions */\n")
                for file in sorted(self.files):
                    if "functions" in self.files[file]:
                        for function in [self.files[file]["functions"][name] for name
                                         in sorted(self.files[file]["functions"].keys())]:
                            if cc_extra_full_desc_file["in file"] == file:
                                lines.extend(function.get_definition())
                                lines.append("\n")

                lines.append("}\n")
                lines.append("/* EMG kernel function models */\n")
                for aspect in self.model_aspects:
                    lines.extend(aspect.get_aspect())
                    lines.append("\n")

                name = "aspects/ldv_{}.aspect".format(os.path.splitext(
                    os.path.basename(cc_extra_full_desc_file["in file"]))[0])
                with open(name, "w", encoding="ascii") as fh:
                    fh.writelines(lines)

                path = os.path.relpath(os.path.abspath(name), os.path.realpath(self.conf['source tree root']))
                self.logger.info("Add aspect file {}".format(path))
                self.aspects[cc_extra_full_desc_file["in file"]] = path

    def __add_aspects(self):
        for grp in self.task['grps']:
            self.logger.info('Add aspects to C files of group "{0}"'.format(grp['id']))
            for cc_extra_full_desc_file in sorted([f for f in grp['cc extra full desc files'] if 'in file' in f],
                                                  key=lambda f: f['in file']):
                if cc_extra_full_desc_file["in file"] in self.aspects:
                    if 'plugin aspects' not in cc_extra_full_desc_file:
                        cc_extra_full_desc_file['plugin aspects'] = []
                    cc_extra_full_desc_file['plugin aspects'].append(
                        {
                            "plugin": "EMG",
                            "aspects": [self.aspects[cc_extra_full_desc_file["in file"]]]
                        }
                    )

    def __add_entry_points(self):
        self.task["entry points"] = [self.entry_point_name]

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'


