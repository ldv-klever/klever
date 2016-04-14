import abc
import os
import copy


from core.avtg.emg.common.code import FunctionDefinition, FunctionBody
from core.avtg.emg.common.interface import Container, Callback
from core.avtg.emg.translator.fsa import Automaton
from core.avtg.emg.common.process import Receive, Dispatch


class AbstractTranslator(metaclass=abc.ABCMeta):

    def __init__(self, logger, conf, avt, header_lines=None, aspect_lines=None):
        self.logger = logger
        self.conf = conf
        self.task = avt
        self.files = {}
        self.aspects = {}
        self.entry_file = None
        self.model_aspects = []
        self._callback_fsa = []
        self._model_fsa = []
        self._entry_fsa = None
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

        # Generate variables
        self._generate_variables(analysis)

        # Generates base code
        for automaton in self._callback_fsa + self._model_fsa + [self._entry_fsa]:
            for state in list(automaton.fsa.states):
                automaton.generate_code(analysis, model, self, state)

        # Save digraphs
        automaton_dir = "automaton"
        self.logger.info("Save automata to directory {}".format(automaton_dir))
        os.mkdir(automaton_dir)
        for automaton in self._callback_fsa + self._model_fsa + [self._entry_fsa]:
            automaton.save_digraph(automaton_dir)

        self._generate_functions()

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
            for interface in relevant_multi_containers:
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
                for access in relevant_multi_leafs:
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
                check = automata_peers
        else:
            self.logger.warning("Cannot find module function for callback '{}'".format(function_call))

        return automata_peers

    def _copy_process(self, process):
        inst = copy.deepcopy(process)
        if self.__max_instances == 0:
            raise RuntimeError('EMG tries to generate more instances than it is allowed by configuration ({})'.
                               format(int(self.conf["translation options"]["max instances number"])))
        elif self.__max_instances:
            self.__max_instances -= 1
        return inst

    def __yeild_identifier(self):
        self.__identifier_cnt += 1
        return self.__identifier_cnt

    def _generate_variables(self, analysis):
        raise NotImplementedError('Implement variables generation')

    def _generate_functions(self):
        raise NotImplementedError('Implement function generation')

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

    def __generate_aspects(self):
        aspect_dir = "aspects"
        self.logger.info("Create directory for aspect files {}".format("aspects"))
        os.makedirs(aspect_dir, exist_ok=True)

        for grp in self.task['grps']:
            # Generate function declarations
            self.logger.info('Add aspects to C files of group "{0}"'.format(grp['id']))
            for cc_extra_full_desc_file in sorted(grp['cc extra full desc files'],
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

                # After file
                lines.append('after: file ("$this")\n')
                lines.append('{\n')
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
                                         sorted(self.files[file]["variables"].keys())
                                         if self.files[file]["variables"][name].use > 0]:
                            if variable.export and cc_extra_full_desc_file["in file"] != file:
                                lines.extend([variable.declare(extern=True) + ";\n"])
                            else:
                                lines.extend([variable.declare(extern=False) + ";\n"])

                lines.append("\n")
                lines.append("/* EMG variable initialization */\n")
                for file in sorted(self.files):
                    if "variables" in self.files[file]:
                        for variable in [self.files[file]["variables"][name] for name in
                                         sorted(self.files[file]["variables"].keys())
                                         if self.files[file]["variables"][name].use > 0]:
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

                if len(self.additional_aspects) > 0:
                    lines.append("\n")
                    lines.append("/* EMG additional non-generated aspects */\n")
                    lines.extend(self.additional_aspects)
                    lines.append("\n")

                name = "aspects/emg_{}.aspect".format(os.path.splitext(
                    os.path.basename(cc_extra_full_desc_file["in file"]))[0])
                with open(name, "w", encoding="ascii") as fh:
                    fh.writelines(lines)

                path = os.path.relpath(os.path.abspath(name), os.path.realpath(self.conf['source tree root']))
                self.logger.info("Add aspect file {}".format(path))
                self.aspects[cc_extra_full_desc_file["in file"]] = path

    def __add_aspects(self):
        for grp in self.task['grps']:
            self.logger.info('Add aspects to C files of group "{0}"'.format(grp['id']))
            for cc_extra_full_desc_file in sorted(grp['cc extra full desc files'],
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


class Aspect(FunctionDefinition):

    def __init__(self, name, declaration, aspect_type="after"):
        self.name = name
        self.declaration = declaration
        self.aspect_type = aspect_type
        self.__body = None

    @property
    def body(self, body=None):
        if not body:
            body = []

        if not self.__body:
            self.__body = FunctionBody(body)
        else:
            self.__body.concatenate(body)
        return self.__body

    def get_aspect(self):
        lines = list()
        lines.append("{}: call({}) ".format(self.aspect_type, "$ {}(..)".format(self.name)) +
                     " {\n")
        lines.extend(self.body.get_lines(1))
        lines.append("}\n")
        return lines


class Entry:

    def __init__(self, logger, modules):
        self.logger = logger
        self.modules = modules

    def __load_order(self, modules):
        sorted_list = []

        unmarked = list(modules)
        self.marked = {}
        while len(unmarked) > 0:
            selected = unmarked.pop(0)
            if selected not in self.marked:
                self.__visit(selected, sorted_list)

        return sorted_list

    def __visit(self, selected, sorted_list):
        if selected in self.marked and self.marked[selected] == 0:
            self.logger.debug('Given graph is not a DAG')

        elif selected not in self.marked:
            self.marked[selected] = 0

            if selected in self.modules:
                for module in sorted(self.modules[selected]):
                    self.__visit(module, sorted_list)

            self.marked[selected] = 1
            sorted_list.append(selected)

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'


