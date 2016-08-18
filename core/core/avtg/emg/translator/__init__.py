#
# Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
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

import os
import copy
import abc
from operator import attrgetter
from pympler import asizeof

from core.avtg.emg.translator.instances import split_into_instances
from core.avtg.emg.translator.fsa import Automaton
from core.avtg.emg.common.signature import Function, Pointer, Primitive, import_declaration
from core.avtg.emg.common.code import FunctionDefinition, Aspect, Variable
from core.avtg.emg.common.process import Receive, Dispatch, Call, CallRetval, Condition, Subprocess, \
    get_common_parameter


class AbstractTranslator(metaclass=abc.ABCMeta):
    """
    This class implements translator from process format to C code. Its workflow in general looks as follows:
    1) Assign single implementation to each access of the process copying it into instances with corresponding
       different interface implementations.
    2) Translate each instance into a finitie-state automaton (FSM) with states and transitions.
    3) Generte a control function in C for each automaton.
    4) Generate an entry point function with invocations of all control functions.
    5) Generate aspect files with entry point, control functions and the other collateral functions and variables.
    """

    CF_PREFIX = 'ldv_control_function_'

    def __init__(self, logger, conf, avt, aspect_lines=None):
        """
        Just read translation configuration options and save corresponding values to object attributes. Do not do any
        translation actually.

        :param logger: Logger object.
        :param conf: Configuration dictionary for EMG plugin.
        :param avt: Abstract verification task dictionary.
        :param aspect_lines: List of lins with text of addiotional aspect files provided to EMG to add to the
                             generated model.
        """
        self.logger = logger
        self.conf = conf
        self.task = avt
        self.files = dict()
        self.aspects = dict()
        self.entry_file = None
        self.model_aspects = list()
        self.instance_maps = dict()
        self._callback_fsa = list()
        self._structures = dict()
        self._model_fsa = list()
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
        self.__dump_automata = False
        self.__identifier_cnt = -1
        self.__instance_modifier = 1
        self.__max_instances = None
        self.__resource_new_insts = 1
        self.__switchers_cache = {}
        self.__mem_aproaching = 0
        self.__analysis_memusage_cache = None
        self.__external_allocated = dict()
        self.__allocate_external = False

        # Read translation options
        if "translation options" not in self.conf:
            self.conf["translation options"] = {}
        if "dump automata graphs" in self.conf["translation options"]:
            self.__dump_automata = self.conf["translation options"]["dump automata graphs"]
        if "max instances number" in self.conf["translation options"]:
            self.__max_instances = int(self.conf["translation options"]["max instances number"])
        if "instance modifier" in self.conf["translation options"]:
            self.__instance_modifier = self.conf["translation options"]["instance modifier"]
        if "number of new instances per resource implementation" in self.conf["translation options"]:
            self.__resource_new_insts = \
                self.conf["translation options"]["number of new instances per resource implementation"]
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
            self._direct_cf_calls = self.conf["translation options"]["direct control function calls"]
        if "terminate approaching to memory usage" in self.conf["translation options"]:
            self.__mem_aproaching = self.conf["translation options"]["terminate approaching to memory usage"]
        if "allocate external" in self.conf["translation options"]:
            self.__allocate_external = self.conf["translation options"]["allocate external"]

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

        if not aspect_lines:
            self.additional_aspects = []
        else:
            self.additional_aspects = aspect_lines

    ####################################################################################################################
    # PUBLIC METHODS
    ####################################################################################################################

    def translate(self, analysis, model):
        """
        Main function for translation of processes to automata and then to C code.
        :param analysis: ModuleCategoriesSpecification object.
        :param model: ProcessModel object.
        :return: None.
        """
        # Determine entry point name and file
        self.logger.info("Determine entry point name and file")
        self._determine_entry(analysis)
        self.logger.info("Going to generate entry point function {} in file {}".
                         format(self.entry_point_name, self.entry_file))

        # Determine additional headers to include
        self.extract_headers_to_attach(analysis, model)

        # Prepare entry point function
        self.logger.info("Generate C code from an intermediate model")
        self._prepare_code(analysis, model)

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

    def extract_headers_to_attach(self, analysis, model):
        """
        Try to extract headers which are need to include in addition to existing in the source code. Get them from the
        list of interfaces without an implementations and from the model processes descriptions.

        :param analysis: ModuleCategoriesSpecification object.
        :param model: ProcessModel object.
        :return: None
        """
        # Get from unused interfaces
        header_list = list()
        for interface in (analysis.get_intf(i) for i in analysis.interfaces):
            if len(interface.declaration.implementations) == 0 and interface.header:
                for header in interface.header:
                    if header not in header_list:
                        header_list.append(header)

        # Get from specifications
        for process in (p for p in model.model_processes + model.event_processes if len(p.headers) > 0):
            for header in process.headers:
                if header not in header_list:
                    header_list.append(header)

        # Generate aspect
        if len(header_list) > 0:
            aspect = ['before: file ("$this")\n',
                      '{\n']
            aspect.extend(['#include <{}>\n'.format(h) for h in header_list])
            aspect.append('}\n')

            self.additional_aspects.extend(aspect)

        return

    def extract_relevant_automata(self, automata_peers, peers, sb_type=None):
        """
        Determine which automata can receive signals from the given instance or send signals to it.

        :param automata_peers: Dictionary {'Automaton.identfier string' -> {'states': ['relevant State objects'],
                                                                            'automaton': 'Automaton object'}
        :param peers: List of relevant Process objects: [{'process': 'Process obj',
                                                         'subprocess': 'Receive or Dispatch obj'}]
        :param sb_type: Receive or Dispatch class to choose only those automata that reseive or send signals to the
                        given one
        :return: None, since it modifies the first argument.
        """
        self.logger.debug("Searching for relevant automata")

        for peer in peers:
            relevant_automata = [automaton for automaton in self._callback_fsa + self._model_fsa + [self._entry_fsa]
                                 if automaton.process.identifier == peer["process"].identifier]
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
        """
        Tries to find relevant automata that can receive signals from model processes of those kernel functions which
        can be called whithin the execution of a provided callback.

        :param analysis: ModuleCategoriesSpecification object
        :param model: ProcessModel object.
        :param function_call: Function name string (Expect explicit function name like 'myfunc' or '(& myfunc)').
        :return: Dictionary {'Automaton.identfier string' -> {'states': ['relevant State objects'],
                                                                         'automaton': 'Automaton object'}
        """
        self.logger.debug("Searching for relevant automata to generate check before callback call '{}'".
                          format(function_call))
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

    ####################################################################################################################
    # PRIVATE METHODS
    ####################################################################################################################

    def _prepare_code(self, analysis, model):
        # Determine how many instances is required for a model
        self.logger.info("Generate automata for processes with callback calls")
        for process in model.event_processes:
            base_list = self._initial_instances(analysis, process)
            base_list = self._instanciate_processes(analysis, base_list, process)
            self.logger.info("Generate {} FSA instances for environment model processes {} with category {}".
                             format(len(base_list), process.name, process.category))

            for instance in base_list:
                fsa = Automaton(self.logger, self.conf["translation options"], instance, self.__yeild_identifier())
                self._callback_fsa.append(fsa)

            if self.__mem_aproaching:
                if not self.__analysis_memusage_cache:
                    self.__analysis_memusage_cache = asizeof.asizeof(analysis)
                mcnt = asizeof.asizeof(self) + self.__analysis_memusage_cache
                if mcnt >= self.__mem_aproaching:
                    raise RuntimeError("EMG has eaten more than '{}' bytes of memory, aborting")

        # Generate automata for models
        self.logger.info("Generate automata for kernel model processes")
        for process in model.model_processes:
            self.logger.info("Generate FSA for kernel model process {}".format(process.name))
            processes = self._instanciate_processes(analysis, [process], process)
            for instance in processes:
                fsa = Automaton(self.logger, self.conf["translation options"], instance, self.__yeild_identifier())
                self._model_fsa.append(fsa)

        # Generate state machine for init an exit
        # todo: multimodule automaton (issues #6563, #6571, #6558)
        self.logger.info("Generate FSA for module initialization and exit functions")
        self._entry_fsa = Automaton(self.logger, self.conf["translation options"], model.entry_process,
                                    self.__yeild_identifier())

        # Generates base code blocks
        self.logger.info("Prepare code on each action of each automanon instance")
        for automaton in self._callback_fsa + self._model_fsa + [self._entry_fsa]:
            self.logger.debug("Generate code for instance {} of process '{}' of categorty '{}'".
                              format(automaton.identifier, automaton.process.name, automaton.process.category))
            for state in sorted(list(automaton.fsa.states), key=attrgetter('identifier')):
                automaton.generate_meta_code(analysis, model, self, state)

        # Save digraphs
        if self.__dump_automata:
            automaton_dir = "automaton"
            self.logger.info("Save automata to directory {}".format(automaton_dir))
            os.mkdir(automaton_dir)
            for automaton in self._callback_fsa + self._model_fsa + [self._entry_fsa]:
                automaton.save_digraph(automaton_dir)

        # Generate control functions
        self.logger.info("Generate control functions for each automaton")
        self._generate_control_functions(analysis, model)

        # Add structures to declare types
        self.files[self.entry_file]['types'] = sorted(list(set(self._structures.values())), key=lambda v: v.identifier)

    def _instanciate_processes(self, analysis, instances, process):
        base_list = instances

        # Get map from accesses to implementations
        self.logger.info("Determine number of instances for process '{}' with category '{}'".
                         format(process.name, process.category))

        if process.category not in self.instance_maps:
            self.instance_maps[process.category] = dict()

        if process.name in self.instance_maps[process.category]:
            cached_map = self.instance_maps[process.category][process.name]
        else:
            cached_map = None
        maps, cached_map = split_into_instances(analysis, process, self.__resource_new_insts, cached_map)
        self.instance_maps[process.category][process.name] = cached_map

        self.logger.info("Going to generate {} instances for process '{}' with category '{}'".
                         format(len(maps), process.name, process.category))
        new_base_list = []
        for access_map in maps:
            for instance in base_list:
                newp = self._copy_process(instance)
                newp.allowed_implementations = access_map
                new_base_list.append(newp)

        return new_base_list

    def _initial_instances(self, analysis, process):
        base_list = []

        if self._nested_automata and self._omit_all_states and not self._direct_cf_calls:
            # So called parallel environment model
            base_list.append(self._copy_process(process))
        else:
            # Sequential environment model
            undefined_labels = []
            # Determine nonimplemented containers
            self.logger.debug("Calculate number of not implemented labels and collateral values for process {} with "
                              "category {}".format(process.name, process.category))
            for label in [process.labels[name] for name in sorted(process.labels.keys())
                          if len(process.labels[name].interfaces) > 0]:
                nonimplemented_intrerfaces = [interface for interface in label.interfaces
                                              if len(analysis.implementations(analysis.get_intf(interface))) == 0]
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

    def _copy_process(self, process):
        inst = copy.copy(process)
        if self.__max_instances == 0:
            raise RuntimeError('EMG tries to generate more instances than it is allowed by configuration ({})'.
                               format(int(self.conf["translation options"]["max instances number"])))
        elif self.__max_instances:
            self.__max_instances -= 1

        inst.allowed_implementations = dict(process.allowed_implementations)
        return inst

    def _determine_entry(self, analysis):
        if len(analysis.inits) >= 1:
            file = analysis.inits[0][0]
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
                'functions': {},
                'declarations': {},
                'initializations': {}
            }

        if self.entry_file not in self.files:
            self.files[self.entry_file] = {
                'variables': {},
                'functions': {},
                'declarations': {},
                'initializations': {}
            }

        self.files[file]['functions'][function.name] = function.get_definition()
        self._add_function_declaration(file, function, extern=False)

    def _add_function_declaration(self, file, function, extern=False):
        if file not in self.files:
            self.files[file] = {
                'variables': {},
                'functions': {},
                'declarations': {},
                'initializations': {}
            }

        if extern and function.name in self.files[file]['declarations']:
            return
        self.files[file]['declarations'][function.name] = function.get_declaration(extern=extern)

    def _add_global_variable(self, variable, file, extern=False):
        if not file and variable.file:
            file = variable.file
        elif not file:
            file = self.entry_file

        if file not in self.files:
            self.files[file] = {
                'variables': {},
                'functions': {},
                'declarations': {},
                'initializations': {}
            }

        if extern and variable.name not in self.files[file]['variables']:
            self.files[file]['variables'][variable.name] = variable.declare(extern=extern) + ";\n"
        elif not extern:
            self.files[file]['variables'][variable.name] = variable.declare(extern=extern) + ";\n"
            if variable.value and \
                    ((type(variable.declaration) is Pointer and type(variable.declaration.points) is Function) or
                     type(variable.declaration) is Primitive):
                self.files[file]['initializations'][variable.name] = variable.declare_with_init() + ";\n"
            elif not variable.value and type(variable.declaration) is Pointer:
                if file not in self.__external_allocated:
                    self.__external_allocated[file] = []
                self.__external_allocated[file].append(variable)

    def _set_initial_state(self, automaton):
        body = list()
        body.append('/* Initialize initial state of automaton {} with process {} of category {} */'.
                    format(automaton.identifier, automaton.process.name, automaton.process.category))
        
        initial_states = sorted(list(automaton.fsa.initial_states), key=lambda s: s.identifier)
        if len(initial_states) == 1:
            body.append('{} = {};'.format(automaton.state_variable.name, initial_states[0].identifier))
        elif len(initial_states) == 2:
            body.extend([
                'if (ldv_undef_int())',
                '\t{} = {};'.format(automaton.state_variable.name, initial_states[0].identifier),
                'else',
                '\t{} = {};'.format(automaton.state_variable.name, initial_states[1].identifier),
            ])
        elif len(initial_states) > 2:
            body.append('switch (ldv_undef_int()) {')
            for index in range(len(initial_states)):
                body.append('\tcase {}: '.format(index) + '{')
                body.append('\t\t{} = {};'.format(automaton.state_variable.name, initial_states[index].identifier))
                body.append('\t\tbreak;'.format(automaton.state_variable.name, initial_states[index].identifier))
                body.append('\t}')
                body.append('\tdefault: ldv_stop();')
                body.append('}')
        
        return body

    def _generate_control_functions(self, analysis, model):
        global_switch_automata = []

        if self._omit_all_states and not self._nested_automata:
            raise NotImplementedError('EMG options are inconsistent: cannot create label-based automata without nested'
                                      'dispatches')

        # Generate control function objects before filling their bodies
        for automaton in [self._entry_fsa] + self._callback_fsa:
            cf = FunctionDefinition(self.CF_PREFIX + str(automaton.identifier), self.entry_file, 'void f(void *cf_arg)',
                                    False)
            automaton.control_function = cf
        for automaton in self._model_fsa:
            function_obj = analysis.get_kernel_function(automaton.process.name)
            cf = Aspect(automaton.process.name, function_obj.declaration, 'around')
            self.model_aspects.append(cf)
            automaton.control_function = cf

        # Initialize states in an entry point
        body = []
        if not self._omit_all_states and not self._nested_automata:
            for automaton in [self._entry_fsa] + self._callback_fsa:
                body.extend(self._set_initial_state(automaton))

        # Prepare action blocks
        self.logger.info('Prepare code base block on each action of each instance')
        for automaton in [self._entry_fsa] + self._callback_fsa + self._model_fsa:
            for state in automaton.fsa.states:
                state.code['final block'] = self._action_base_block(analysis, automaton, state)

        # Generate model control function
        self.logger.info('Generate control functions for kernel model functions')
        while len(self._model_fsa) > 0:
            automaton = self._model_fsa.pop()
            self._label_cfunction(analysis, automaton, automaton.process.name)

        # Generate automata control function
        self.logger.info("Generate control functions for the rest automata of an environment model")
        while len(self._callback_fsa) > 0:
            automaton = self._callback_fsa.pop()

            if self._omit_all_states:
                func = self._label_cfunction(analysis, automaton)
            else:
                automaton.state_blocks = self._state_sequences(automaton)
                func = self._state_cfunction(analysis, automaton)

            if func and not self._nested_automata:
                global_switch_automata.append(func)

        # Generate entry automaton
        if self._omit_all_states:
            func = self._label_cfunction(analysis, self._entry_fsa)
        else:
            self._entry_fsa.state_blocks = self._state_sequences(self._entry_fsa)
            func = self._state_cfunction(analysis, self._entry_fsa)
        if func:
            global_switch_automata.append(func)
        else:
            raise ValueError('Entry point function must contain init/exit automaton control function')

        # Generate entry point function
        func = self._generate_entry_functions(body, global_switch_automata)
        self._add_function_definition(self.entry_file, func)

    def _choose_file(self, analysis, automaton):
        file = automaton.file
        if file:
            return file

        files = set()
        if automaton.process.category == "kernel models":
            # Calls
            function_obj = analysis.get_kernel_function(automaton.process.name)
            files.update(set(function_obj.files_called_at))
            for caller in (c for c in function_obj.functions_called_at):
                # Caller definitions
                files.update(set(analysis.get_modules_function_files(caller)))

        if len(files) == 0:
            return self.entry_file
        else:
            return sorted(list(files))[0]

    def _generate_entry_functions(self, body, global_switch_automata):
        self.logger.info("Finally generate entry point function {}".format(self.entry_point_name))
        # FunctionDefinition prototype
        ep = FunctionDefinition(
            self.entry_point_name,
            self.entry_file,
            "void {}(void)".format(self.entry_point_name),
            False
        )

        body = [
            "ldv_initialize();",
            ""
            "/* Initialize initial states of automata */"
        ] + body

        # Init external allocated pointers
        cnt = 0
        functions = []
        if self.__allocate_external and not self._omit_all_states and not self._nested_automata:
            for file in sorted(list(self.__external_allocated.keys())):
                func = FunctionDefinition('allocate_external_{}'.format(cnt),
                                          file,
                                          "void external_allocated_{}(void)".format(cnt),
                                          True)

                init = ["{} = {}();".format(var.name, 'external_allocated_data') for
                        var in self.__external_allocated[file]]
                func.body = init

                self._add_function_definition(file, func)
                self._add_function_declaration(self.entry_file, func, extern=True)
                functions.append(func)
                cnt += 1

            gl_init = FunctionDefinition('initialize_external_data',
                                         self.entry_file,
                                         'void initialize_external_data(void)')
            init_body = ['{}();'.format(func.name) for func in functions]
            gl_init.body = init_body
            self._add_function_definition(self.entry_file, gl_init)
            body.extend([
                '/* Initialize external data */',
                'initialize_external_data();'
            ])

        body.extend([
            "while(1) {",
            "\tswitch(ldv_undef_int()) {"
        ])

        for index in range(len(global_switch_automata)):
            cfunction = global_switch_automata[index]
            body.extend(
                [
                    "\t\tcase {}: ".format(index),
                    "\t\t\t{}(0);".format(cfunction),
                    "\t\tbreak;"
                ]
            )
        body.extend(
            [
                "\t\tdefault: ldv_stop();",
                "\t}",
                "}"
            ]
        )
        ep.body.extend(body)

        return ep

    def _propogate_aux_function(self, analysis, automaton, function):
        # Determine files to export
        files = set()
        if automaton.process.category == "kernel models":
            # Calls
            function_obj = analysis.get_kernel_function(automaton.process.name)
            files.update(set(function_obj.files_called_at))
            for caller in (c for c in function_obj.functions_called_at):
                # Caller definitions
                files.update(set(analysis.get_modules_function_files(caller)))

        # Export
        for file in files:
            self._add_function_declaration(file, function, extern=True)

    def _call(self, analysis, automaton, state):
        # Generate function call and corresponding function
        fname = "ldv_{}_{}_{}_{}".format(automaton.process.name, state.action.name, automaton.identifier,
                                         state.identifier)
        if 'invoke' not in state.code:
            return state.code['body']

        # Generate special function with call
        if 'retval' in state.code:
            ret = state.code['callback'].points.return_value.to_string('')
            ret_expr = 'return '
            cf_ret_expr = state.code['retval'] + ' = '
        else:
            ret = 'void'
            ret_expr = ''
            cf_ret_expr = ''

        resources = [state.code['callback'].to_string('arg0')]
        params = []
        for index in range(len(state.code['callback'].points.parameters)):
            if type(state.code['callback'].points.parameters[index]) is not str:
                if index in state.code["pointer parameters"]:
                    resources.append(state.code['callback'].points.parameters[index].take_pointer.
                                     to_string('arg{}'.format(index + 1)))
                    params.append('*arg{}'.format(index + 1))
                else:
                    resources.append(state.code['callback'].points.parameters[index].
                                     to_string('arg{}'.format(index + 1)))
                    params.append('arg{}'.format(index + 1))
        params = ", ".join(params)
        resources = ", ".join(resources)

        function = FunctionDefinition(fname, state.code['file'], "{} {}({})".format(ret, fname, resources), True)

        function.body.append("/* Callback {} */".format(state.action.name))
        inv = [
            '/* Callback {} */'.format(state.action.name)
        ]

        if state.code['check pointer']:
            f_invoke = cf_ret_expr + fname + '(' + ', '.join([state.code['invoke']] + state.code['parameters']) + ');'
            inv.append('if ({})'.format(state.code['invoke']))
            inv.append('\t' + f_invoke)
            call = ret_expr + '(*arg0)' + '(' + params + ')'
        else:
            f_invoke = cf_ret_expr + fname + '(' + \
                       ', '.join([state.code['variable']] + state.code['parameters']) + ');'
            inv.append(f_invoke)
            call = ret_expr + '({})'.format(state.code['invoke']) + '(' + params + ')'
        function.body.append('{};'.format(call))

        self._add_function_definition(state.code['file'], function)
        self._add_function_declaration(self._choose_file(analysis, automaton), function, extern=True)

        # Add declarations
        self._propogate_aux_function(analysis, automaton, function)

        if 'pre_call' in state.code and len(state.code['pre_call']) > 0:
            inv = state.code['pre_call'] + inv
        if 'post_call' in state.code and len(state.code['post_call']) > 0:
            inv.extend(state.code['post_call'])

        return inv

    def _call_cf(self, file, automaton, parameter='0'):
        self._add_function_declaration(file, automaton.control_function, extern=True)

        if self._direct_cf_calls:
            return '{}({});'.format(automaton.control_function.name, parameter)
        elif self._omit_all_states and self._nested_automata and self.__instance_modifier > 1:
            sv = automaton.thread_variable(self.__instance_modifier)
            self._add_global_variable(sv, file, extern=True)
            return 'ldv_thread_create_N({}, {}, {});'.format('& ' + sv.name,
                                                             automaton.control_function.name,
                                                             parameter)
        else:
            sv = automaton.thread_variable()
            self._add_global_variable(sv, file, extern=True)
            return 'ldv_thread_create({}, {}, {});'.format('& ' + sv.name,
                                                           automaton.control_function.name,
                                                           parameter)

    def _join_cf(self, file, automaton):
        self._add_function_declaration(file, automaton.control_function, extern=True)

        if self._direct_cf_calls:
            return '/* Skip thread join call */'
        elif self._omit_all_states and self._nested_automata and self.__instance_modifier > 1:
            sv = automaton.thread_variable(self.__instance_modifier)
            self._add_global_variable(sv, file, extern=True)
            return 'ldv_thread_join_N({}, {});'.format('& ' + sv.name, automaton.control_function.name)
        else:
            sv = automaton.thread_variable()
            self._add_global_variable(sv, file, extern=True)
            return 'ldv_thread_join({}, {});'.format('& ' + sv.name, automaton.control_function.name)

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

    def _dispatch(self, analysis, automaton, state):
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
        self._add_function_definition(file, df)

        # Add declarations
        self._propogate_aux_function(analysis, automaton, df)

        return [
            '/* Dispatch {} */'.format(state.action.name),
            '{}({});'.format(df.name, ', '.join(df_parameters))
        ]

    def _action_base_block(self, analysis, automaton, state):
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

    def _merge_points(self, initial_states):
        # Terminal marking
        def add_terminal(terminal, out_value, split_points, subprocess=False):
            for split in out_value:
                for branch in out_value[split]:
                    if branch in split_points[split]['merge branches'] and subprocess:
                        split_points[split]['merge branches'].remove(branch)
                    if branch not in split_points[split]['terminals']:
                        split_points[split]['terminals'][branch] = set()
                    split_points[split]['terminals'][branch].add(terminal)

                split_points[split]['terminal merge sets'][terminal] = out_value[split]

        # Condition calculation
        def do_condition(states, terminal_branches, finals, merge_list, split, split_data, merge_points):
            # Set up branches
            condition = {'pending': list(), 'terminals': list()}
            largest_unintersected_mergesets = []
            while len(merge_list) > 0:
                merge = merge_list.pop(0)
                merged_states = split_data['split sets'][merge]
                terminal_branches -= merged_states
                diff = states - merged_states
                if len(diff) < len(states):
                    largest_unintersected_mergesets.append(merge)
                    if len(merged_states) == 1:
                        condition['pending'].append(next(iter(merged_states)))
                    elif len(merged_states) > 1:
                        sc_finals = set(merge_points[merge][split])
                        sc_terminals = set(split_data['terminals'].keys()).intersection(merged_states)
                        new_condition = do_condition(set(merged_states), sc_terminals, sc_finals, list(merge_list),
                                                     split, split_data, merge_points)
                        condition['pending'].append(new_condition)
                    else:
                        raise RuntimeError('Invalid merge')
                states = diff

            # Add rest independent branches
            if len(states) > 0:
                condition['pending'].extend(sorted(states))

            # Add predecessors of the latest merge sets if there are not covered in terminals
            for merge in largest_unintersected_mergesets:
                bad = False
                for terminal_branch in terminal_branches:
                    for terminal in split_data['terminals'][terminal_branch]:
                        if split_points[split]['split sets'][merge].\
                                issubset(split_data['terminal merge sets'][terminal]):
                            bad = True
                            break

                if not bad:
                    # Add predecessors
                    condition['terminals'].extend(merge_points[merge][split])
                    # Add terminal
                    terminal_branches.update(set(split_data['terminals'].keys()).
                                             intersection(split_data['split sets'][merge]))

            # Add terminals which are not belong to any merge set
            for branch in terminal_branches:
                condition['terminals'].extend(split_data['terminals'][branch])
            # Add provided
            condition['terminals'].extend(finals)

            # Return child condition if the last is not a condition
            if len(condition['pending']) == 1:
                condition = condition['pending'][0]

            # Save all branhces
            condition['branches'] = list(condition['pending'])

            # Save total number of branches
            condition['len'] = len(condition['pending'])

            return condition

        # Collect iformation about branches
        graph = dict()
        split_points = dict()
        merge_points = dict()
        processed = set()
        queue = sorted(initial_states, key=attrgetter('identifier'))
        merge_queue = list()
        while len(queue) > 0 or len(merge_queue) > 0:
            if len(queue) != 0:
                st = queue.pop(0)
            else:
                st = merge_queue.pop(0)

            # Add epson states
            if st.identifier not in graph:
                graph[st.identifier] = dict()

            # Calculate output branches
            out_value = dict()
            if st not in initial_states and len(st.predecessors) > 1 and \
                            len({s for s in st.predecessors if s.identifier not in processed}) > 0:
                merge_queue.append(st)
            else:
                if st not in initial_states:
                    if len(st.predecessors) > 1:
                        # Try to collect all branches first
                        for predecessor in st.predecessors:
                            for split in graph[predecessor.identifier][st.identifier]:
                                if split not in out_value:
                                    out_value[split] = set()
                                out_value[split].update(graph[predecessor.identifier][st.identifier][split])

                                for node in graph[predecessor.identifier][st.identifier][split]:
                                    split_points[split]['branch liveness'][node] -= 1

                        # Remove completely merged branches
                        for split in sorted(out_value.keys()):
                            for predecessor in (p for p in st.predecessors
                                                if split in graph[p.identifier][st.identifier]):
                                if len(out_value[split].symmetric_difference(
                                        graph[predecessor.identifier][st.identifier][split])) > 0 or \
                                   len(split_points[split]['merge branches'].
                                        symmetric_difference(graph[predecessor.identifier][st.identifier][split])) == 0:
                                     # Add terminal states for each branch
                                    if st.identifier not in merge_points:
                                        merge_points[st.identifier] = dict()
                                    merge_points[st.identifier][split] = \
                                        {p.identifier for p in st.predecessors
                                         if split in graph[p.identifier][st.identifier]}

                                    # Add particular set of merged bracnhes
                                    split_points[split]['split sets'][st.identifier] = out_value[split]

                                    # Remove, since all branches are merged
                                    if len(split_points[split]['merge branches'].
                                                   difference(out_value[split])) == 0 and \
                                       len({s for s in split_points[split]['total branches']
                                            if split_points[split]['branch liveness'][s] > 0}) == 0:
                                        # Merge these branches
                                        del out_value[split]
                                    break
                    elif len(st.predecessors) == 1:
                        # Just copy meta info from the previous predecessor
                        out_value = dict(graph[list(st.predecessors)[0].identifier][st.identifier])
                        for split in out_value:
                            for node in out_value[split]:
                                split_points[split]['branch liveness'][node] -= 1

                # If it is a split point, create meta information on it and start tracking its branches
                if len(st.successors) > 1:
                    split_points[st.identifier] = {
                        'total branches': {s.identifier for s in st.successors},
                        'merge branches': {s.identifier for s in st.successors},
                        'split sets': dict(),
                        'terminals': dict(),
                        'terminal merge sets': dict(),
                        'branch liveness': {s.identifier: 0 for s in st.successors}
                    }
                elif len(st.successors) == 0:
                    add_terminal(st.identifier, out_value, split_points)

                # Assign branch tracking information to an each output branch
                for successor in st.successors:
                    if successor not in graph:
                        graph[successor.identifier] = dict()
                    # Assign branches from the previous split points
                    graph[st.identifier][successor.identifier] = dict(out_value)

                    # Branches with subprocesses has no merge point
                    if type(successor.action) is Subprocess:
                        add_terminal(successor.identifier, out_value, split_points, subprocess=True)
                    else:
                        if st.identifier in split_points:
                            # Mark new branch
                            graph[st.identifier][successor.identifier][st.identifier] = {successor.identifier}

                        for split in graph[st.identifier][successor.identifier]:
                            for branch in graph[st.identifier][successor.identifier][split]:
                                # Do not expect to find merge point for this branch
                                split_points[split]['branch liveness'][branch] += 1

                        if len(successor.predecessors) > 1:
                            if successor not in merge_queue:
                                merge_queue.append(successor)
                        else:
                            if successor not in queue:
                                queue.append(successor)

                    processed.add(st.identifier)

        # Do sanity check
        conditions = dict()
        for split in split_points:
            for branch in split_points[split]['branch liveness']:
                if split_points[split]['branch liveness'][branch] > 0:
                    raise RuntimeError('Incorrect merge point detection')

            # Calculate conditions then
            conditions[split] = list()

            # Check merge points number
            left = set(split_points[split]['total branches'])
            merge_list = sorted(split_points[split]['split sets'].keys(),
                                key=lambda y: len(split_points[split]['split sets'][y]), reverse=True)
            condition = do_condition(left, split_points[split]['terminals'].keys(), set(), merge_list, split,
                                     split_points[split], merge_points)
            conditions[split] = condition

        return conditions

    def _label_sequence(self, analysis, automaton, initial_state, ret_expression):
        ### Subroutines ###
        # Start a conditional branch
        def start_branch(tab, f_code, condition):
            if condition['len'] == 2:
                if len(condition['pending']) == 1:
                    f_code.append('\t' * tab + 'if (ldv_undef_int()) {')
                elif len(condition['pending']) == 0:
                    f_code.append('\t' * tab + 'else {')
                else:
                    raise ValueError('Invalid if conditional left states: {}'.
                                     format(len(condition['pending'])))
                tab += 1
            elif condition['len'] > 2:
                index = condition['len'] - len(condition['pending'])
                f_code.append('\t' * tab + 'case {}: '.format(index) + '{')
                tab += 1
            else:
                raise ValueError('Invalid condition branch number: {}'.format(condition['len']))
            return tab

        # Close a conditional branch
        def close_branch(tab, f_code, condition):
            if condition['len'] == 2:
                tab -= 1
                f_code.append('\t' * tab + '}')
            elif condition['len'] > 2:
                f_code.append('\t' * tab + 'break;')
                tab -= 1
                f_code.append('\t' * tab + '}')
            else:
                raise ValueError('Invalid condition branch number: {}'.format(condition['len']))
            return tab

        def start_condition(tab, f_code, condition, conditional_stack, state_stack):
            conditional_stack.append(condition)

            if len(conditional_stack[-1]['pending']) > 2:
                f_code.append('\t' * tab + 'switch (ldv_undef_int()) {')
                tab += 1
            tab = process_next_branch(tab, f_code, conditional_stack, state_stack)
            return tab

        def close_condition(tab, f_code, conditional_stack):
            # Close the last branch
            tab = close_branch(tab, f_code, conditional_stack[-1])

            # Close conditional statement
            if conditional_stack[-1]['len'] > 2:
                f_code.append('\t' * tab + 'default: ldv_stop();')
                tab -= 1
                f_code.append('\t' * tab + '}')
            conditional_stack.pop()
            return tab

        # Start processing the next conditional branch
        def process_next_branch(tab, f_code, conditional_stack, state_stack):
            # Try to add next branch
            next_branch = conditional_stack[-1]['pending'].pop()
            tab = start_branch(tab, f_code, conditional_stack[-1])

            if type(next_branch) is dict:
                # Open condition
                tab = start_condition(tab, f_code, next_branch, conditional_stack, state_stack)
            else:
                # Just add a state
                next_state = automaton.fsa.resolve_state(next_branch)
                state_stack.append(next_state)
            return tab

        def print_block(tab, f_code, code):
            for stm in code:
                f_code.append('\t' * tab + stm)

        # Add code of the action
        def print_action_code(tab, f_code, code, state, conditional_stack):
            if len(conditional_stack) > 0 and state.identifier in conditional_stack[-1]['branches']:
                if state.code and len(state.code['guard']) > 0:
                    f_code.append('\t' * tab + 'ldv_assume({});'.format(' && '.join(sorted(state.code['guard']))))
                print_block(tab, f_code, code)
            else:
                f_code.append('')
                if state.code and len(state.code['guard']) > 0:
                    f_code.append('\t' * tab + 'if ({}) '.format(' && '.join(state.code['guard'])) + '{')
                    tab += 1
                    print_block(tab, f_code, code)
                    tab -= 1
                    f_code.append('\t' * tab + '}')
                else:
                    print_block(tab, f_code, code)
            return tab

        def require_merge(state, processed_states, condition):
            if len(condition['pending']) == 0 and state.identifier in condition['terminals'] and len(set(condition['terminals']) - processed_states) == 0:
                return True
            else:
                return False

        f_code = []
        v_code = []

        # Add artificial state if input copntains more than one state
        state_stack = [initial_state]

        # First calculate merge points
        conditions = self._merge_points(list(state_stack))

        processed_states = set()
        conditional_stack = []
        tab = 0
        while len(state_stack) > 0:
            state = state_stack.pop()
            processed_states.add(state.identifier)

            if type(state.action) is Subprocess:
                code = [
                    '/* Jump to subprocess {} initial state */'.format(state.action.name),
                    'goto ldv_{}_{};'.format(state.action.name, automaton.identifier)
                ]
            else:
                new_v_code, code = state.code['final block']
                v_code.extend(new_v_code)

            # If this is a terminal state - quit control function
            if type(state.action) is not Subprocess and len(state.successors) == 0:
                code.extend([
                    "/* Terminal state */",
                    ret_expression
                ])
            tab = print_action_code(tab, f_code, code, state, conditional_stack)

            # If this is a terminal state before completely closed merge point close the whole merge
            while len(conditional_stack) > 0 and require_merge(state, processed_states, conditional_stack[-1]):
                # Close the last branch and the condition
                tab = close_condition(tab, f_code, conditional_stack)

            # Close branch of the last condition
            if len(conditional_stack) > 0 and state.identifier in conditional_stack[-1]['terminals']:
                # Close this branch
                tab = close_branch(tab, f_code, conditional_stack[-1])
                # Start new branch
                tab = process_next_branch(tab, f_code, conditional_stack, state_stack)
            elif type(state.action) is not Subprocess:
                # Add new states in terms of the current branch
                if len(state.successors) > 1:
                    # Add new condition
                    condition = conditions[state.identifier]
                    tab = start_condition(tab, f_code, condition, conditional_stack, state_stack)
                elif len(state.successors) == 1:
                    # Just add the next state
                    state_stack.append(next(iter(state.successors)))

        if len(conditional_stack) > 0:
            raise RuntimeError('Cannot leave unclosed conditions')

        return [v_code, f_code]

    def _label_cfunction(self, analysis, automaton, aspect=None):
        self.logger.info('Generate label-based control function for automaton {} based on process {} of category {}'.
                         format(automaton.identifier, automaton.process.name, automaton.process.category))
        v_code = ["/* Control function based on process '{}' generated for interface category '{}' */".
                  format(automaton.process.name, automaton.process.category)]
        f_code = []

        # Check necessity to return a value
        ret_expression = 'return;'
        if aspect:
            kfunction_obj = analysis.get_kernel_function(aspect)
            if kfunction_obj.declaration.return_value and kfunction_obj.declaration.return_value.identifier != 'void':
                ret_expression = 'return $res;'

        # Generate function definition
        cf = self._init_control_function(analysis, automaton, v_code, f_code, aspect)

        for var in automaton.variables():
            if type(var.declaration) is Pointer and self.__allocate_external:
                definition = var.declare() + " = external_allocated_data();"
            elif type(var.declaration) is Primitive and var.value:
                definition = var.declare_with_init() + ";"
            else:
                definition = var.declare() + ";"
            v_code.append(definition)

        main_v_code, main_f_code = self._label_sequence(analysis, automaton, list(automaton.fsa.initial_states)[0],
                                                        ret_expression)
        v_code.extend(main_v_code)
        f_code.extend(main_f_code)
        f_code.append("/* End of the process */")
        f_code.append(ret_expression)

        processed = []
        for subp in [s for s in sorted(automaton.fsa.states, key=lambda s: s.identifier)
                     if type(s.action) is Subprocess]:
            if subp.action.name not in processed:
                sp_v_code, sp_f_code = self._label_sequence(analysis, automaton, list(subp.successors)[0],
                                                            ret_expression)

                v_code.extend(sp_v_code)
                f_code.extend([
                    '',
                    '/* Sbprocess {} */'.format(subp.action.name),
                    'ldv_{}_{}:'.format(subp.action.name, automaton.identifier)
                ])
                f_code.extend(sp_f_code)
                f_code.append("/* End of the subprocess '{}' */".format(subp.action.name))
                f_code.append(ret_expression)
                processed.append(subp.action.name)

        if not self._nested_automata and not aspect:
            self._add_global_variable(automaton.state_variable, self._choose_file(analysis, automaton), extern=False)
        elif not aspect:
            if self._nested_automata and self.__instance_modifier > 1:
                self._add_global_variable(automaton.thread_variable(self.__instance_modifier),
                                          self._choose_file(analysis, automaton), extern=False)
            else:
                self._add_global_variable(automaton.thread_variable(), self._choose_file(analysis, automaton),
                                          extern=False)

        cf.body.extend(v_code + f_code)
        automaton.control_function = cf

        if not aspect:
            self._add_function_definition(self._choose_file(analysis, automaton), cf)
            self._add_function_declaration(self.entry_file, cf, extern=True)
        return cf.name

    def _init_control_function(self, analysis, automaton, v_code, f_code, aspect=None):
        # Function type
        cf = automaton.control_function
        if not aspect and self._nested_automata:
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
                        var = automaton.determine_variable(receiver_access.label, interface.identifier)
                        receiver_expr = receiver_access.access_with_variable(var)

                        param_declarations.append(var.declaration)
                        param_expressions.append(receiver_expr)
                    break

        automaton.control_function = cf
        return cf

    def _state_switch(self, states, file):
        key = ''.join(sorted([str(i) for i in states]))
        if key in self.__switchers_cache:
            self._add_function_declaration(file, self.__switchers_cache[key]['function'], extern=True)
            return self.__switchers_cache[key]['call']

        # Generate switch function
        name = 'ldv_switch_{}'.format(len(list(self.__switchers_cache.keys())))
        function = FunctionDefinition(name, self.entry_file, 'int f(void)', False)

        # Generate switch body
        code = list()
        code.append('switch (ldv_undef_int()) {')
        for index in range(len(states)):
            code.append('\tcase {}: '.format(index) + '{')
            code.append('\t\treturn {};'.format(states[index]))
            code.append('\t\tbreak;')
            code.append('\t}')
        code.append('\tdefault: ldv_stop();')
        code.append('}')
        function.body.extend(code)

        # Add function
        self._add_function_definition(self.entry_file, function)

        invoke = '{}()'.format(name)
        self.__switchers_cache[key] = {
            'call': invoke,
            'function':  function
        }
        return invoke

    def _state_sequences(self, automaton):
        blocks_stack = sorted(list(automaton.fsa.initial_states), key=lambda f: f.identifier)
        blocks = {}
        while len(blocks_stack) > 0:
            origin = blocks_stack.pop()
            block = []
            state_stack = [origin]
            no_jump = True

            while len(state_stack) > 0:
                state = state_stack.pop()
                block.append(state)
                no_jump = (type(state.action) not in self.jump_types) and no_jump

                if len(state.successors) == 1 and (no_jump or type(list(state.successors)[0].action)
                                                   not in self.jump_types) \
                        and type(state.action) is not Receive:
                    state_stack.append(list(state.successors)[0])

            blocks[origin.identifier] = block

            for state in [st for st in sorted(list(state.successors), key=lambda f: f.identifier)
                          if st.identifier not in blocks and st not in blocks_stack]:
                blocks_stack.append(state)

        return blocks

    def _switch_state_code(self, analysis, automaton, state):
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
            if self._nested_automata:
                code.append('goto out_{};'.format(automaton.identifier))

        return code

    def _state_sequence_code(self, analysis, automaton, state_block):
        first = True
        code = []
        v_code = []

        for state in state_block:
            new_v_code, block = state.code['final block']
            v_code.extend(new_v_code)

            if state.code and len(state.code['guard']) > 0 and first:
                code.append('ldv_assume({});'.format(
                    ' && '.join(sorted(state.code['guard']))))
                code.extend(block)
                first = False
            elif state.code and len(state.code['guard']) > 0:
                code.append('if({}) '.format(
                    ' && '.join(sorted(state.code['guard']))) + '{')
                for st in block:
                    code.append('\t' + st)
                code.append('}')
            else:
                code.extend(block)
            code.append('')

        if self._nested_automata or type(state_block[0].action) is not Receive:
            code.extend(self._switch_state_code(analysis, automaton, state))
        else:
            code.append('/* Omit state transition for a receive */')

        return v_code, code

    def _state_cfunction(self, analysis, automaton):
        self.logger.info('Generate state-based control function for automaton {} based on process {} of category {}'.
                         format(automaton.identifier, automaton.process.name, automaton.process.category))
        v_code = []
        f_code = []
        tab = 0

        # Generate function definition
        cf = self._init_control_function(analysis, automaton, v_code, f_code, None)

        # Add a loop for nested case
        if self._nested_automata:
            f_code.extend(self._set_initial_state(automaton))
            f_code.append('while (1) {')
            tab += 1

        if len(list(automaton.state_blocks.keys())) == 0:
            f_code.append('/* Empty control function */')
        else:
            if len(list(automaton.state_blocks)) == 1:
                new_v_code, new_f_code = self._state_sequence_code(analysis, automaton,
                                                                   list(automaton.state_blocks.values())[0])
                v_code.extend(new_v_code)
                f_code.extend(['\t' * tab + stm for stm in new_f_code])
            elif len(list(automaton.state_blocks)) == 2:
                first = True
                tab += 1
                for key in sorted(list(automaton.state_blocks.keys())):
                    if first:
                        f_code.append('\t' * (tab - 1) + 'if (ldv_undef_int()) {')
                        first = False
                    else:
                        f_code.append('\t' * (tab - 1) + 'else {')

                    new_v_code, new_f_code = self._state_sequence_code(analysis, automaton,
                                                                       list(automaton.state_blocks.values())[0])
                    v_code.extend(new_v_code)
                    f_code.append('\t' * tab + 'ldv_assume({} == {});'.format(automaton.state_variable.name, key))
                    f_code.extend(['\t' * tab + stm for stm in new_f_code])
                    f_code.append('\t' * tab + '}')
            else:
                f_code.append('\t' * tab + 'switch ({}) '.format(automaton.state_variable.name) + '{')
                tab += 1
                for case in sorted(list(automaton.state_blocks.keys())):
                    f_code.append('\t' * tab + 'case {}: '.format(case) + '{')
                    tab += 1
                    new_v_code, new_f_code = self._state_sequence_code(analysis, automaton,
                                                                       automaton.state_blocks[case])
                    v_code.extend(new_v_code)
                    f_code.extend(['\t' * tab + stm for stm in new_f_code])
                    f_code.append('\t' * tab + 'break;')
                    tab -= 1
                    f_code.append('\t' * tab + '}')
                f_code.append('\t' * tab + 'default: ldv_stop;')
                tab -= 1
                f_code.append('\t' * tab + '}')

        # Add loop for nested case
        if self._nested_automata:
            f_code.append('}')
            tab -= 1
            f_code.append('out_{}:'.format(automaton.identifier))
            f_code.append('return;')
            if self.__instance_modifier > 1:
                self._add_global_variable(automaton.thread_variable(self.__instance_modifier),
                                          self._choose_file(analysis, automaton), extern=False)
            else:
                self._add_global_variable(automaton.thread_variable(), self._choose_file(analysis, automaton),
                                          extern=False)
            v_code.append(automaton.state_variable.declare() + " = 0;")
        else:
            self._add_global_variable(automaton.state_variable, self._choose_file(analysis, automaton), extern=False)
            self._add_global_variable(automaton.state_variable, self.entry_file, extern=True)
        cf.body.extend(v_code + f_code)

        for var in automaton.variables():
            self._add_global_variable(var, self._choose_file(analysis, automaton), extern=False)
        self._add_function_definition(self._choose_file(analysis, automaton), cf)
        self._add_function_declaration(self.entry_file, cf, extern=True)
        return cf.name

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

                if len(self.additional_aspects) > 0:
                    lines.append("\n")
                    lines.append("/* EMG additional aspects */\n")
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
                        for function in sorted(self.files[file]["declarations"].keys()):
                            if cc_extra_full_desc_file["in file"] == file:
                                lines.extend(self.files[file]["declarations"][function])

                lines.append("\n")
                lines.append("/* EMG variable declarations */\n")
                for file in sorted(self.files):
                    if "variables" in self.files[file]:
                        for variable in sorted(self.files[file]["variables"].keys()):
                            if cc_extra_full_desc_file["in file"] == file:
                                lines.append(self.files[file]["variables"][variable])

                lines.append("\n")
                lines.append("/* EMG variable initialization */\n")
                for file in sorted(self.files):
                    if "initializations" in self.files[file]:
                        for variable in sorted(self.files[file]["initializations"].keys()):
                            if cc_extra_full_desc_file["in file"] == file:
                                lines.append(self.files[file]["initializations"][variable])

                lines.append("\n")
                lines.append("/* EMG function definitions */\n")
                for file in sorted(self.files):
                    if "functions" in self.files[file]:
                        for function in sorted(self.files[file]["functions"].keys()):
                            if cc_extra_full_desc_file["in file"] == file:
                                lines.extend(self.files[file]["functions"][function])
                                lines.append("\n")

                lines.append("}\n")
                lines.append("/* EMG kernel function models */\n")
                for aspect in self.model_aspects:
                    lines.extend(aspect.get_aspect())
                    lines.append("\n")

                name = "aspects/ldv_{}.aspect".format(os.path.splitext(
                    os.path.basename(cc_extra_full_desc_file["in file"]))[0])
                with open(name, "w", encoding="utf8") as fh:
                    fh.writelines(lines)

                path = os.path.relpath(name, self.conf['main working directory'])
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

    def __yeild_identifier(self):
        self.__identifier_cnt += 1
        return self.__identifier_cnt

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'


