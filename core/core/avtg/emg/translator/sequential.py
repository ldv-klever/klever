import copy
import os
import re
import graphviz

from core.avtg.emg.translator import AbstractTranslator, Aspect
from core.avtg.emg.representations import Signature, Function, Variable, ModelMap


def text_processor(automaton, statement):
        # Replace model functions
        mm = ModelMap()
        accesses = automaton.process.accesses()
        statements = [statement]

        for access in accesses:
            options = accesses[access]
            for option in options:
                new_statements = []
                for text in statements:
                    if option.interface:
                        signature = option.label.signature(None, option.interface.full_identifier)
                        var = automaton.variable(option.label, option.list_interface[0].full_identifier)
                    else:
                        signature = option.label.signature()
                        var = automaton.variable(option.label)

                    tmp = mm.replace_models(option.label.name, signature, text)
                    tmp = option.replace_with_variable(tmp, var)
                    new_statements.append(tmp)
                statements = new_statements
        return statements


class Translator(AbstractTranslator):

    def _generate_entry_point(self):
        # Initialize additional attributes
        self.instance_modifier = 2
        self.callback_fsa = []
        self.model_fsa = []
        self.entry_fsa = None
        self.__identifier_cnt = -1

        # Read translation options
        if "translation options" in self.conf:
            if "instance modifier" in self.conf["translation options"]:
                self.instance_modifier = self.conf["translation options"]["instance modifier"]

        # Determine how many instances is required for a model
        self.logger.info("Determine how many instances is required to add to an environment model for each process")
        for process in self.model["processes"]:
            undefined_labels = []
            # Determine nonimplemented containers
            self.logger.debug("Calculate number of not implemented labels and collateral values for process {} with "
                              "category {}".format(process.name, process.category))
            for label in [label for label in process.labels.values() if label.interfaces]:
                nonimplemented_intrerfaces = [interface for interface in label.interfaces
                                              if len(self.analysis.interfaces[interface].implementations) == 0]
                if len(nonimplemented_intrerfaces) > 0:
                    undefined_labels.append(label)

            # Determine is it necessary to make several instances
            if len(undefined_labels) > 0:
                base_list = [copy.deepcopy(process) for i in range(self.instance_modifier)]
            else:
                base_list = [process]
            self.logger.info("Prepare {} instances for {} undefined labels of process {} with category {}".
                             format(len(base_list), len(undefined_labels), process.name, process.category))

            base_list = self.__instanciate_processes(base_list, process)

            self.logger.info("Generate {} FSA instances for process {} with category {}".
                             format(len(base_list), process.name, process.category))
            for instance in base_list:
                fsa = Automaton(self.logger, instance, self.identifier)
                self.callback_fsa.append(fsa)

        # Generate automata for models
        for process in self.model["models"]:
            self.logger.info("Generate FSA for kernel model process {}".format(process.name))
            processes = self.__instanciate_processes([process], process)
            for instance in processes:
                fsa = Automaton(self.logger, instance, self.identifier)
                self.model_fsa.append(fsa)

        # Generate state machine for init an exit
        # todo: multimodule automaton (issues #6563, #6571, #6558)
        self.logger.info("Generate FSA for module initialization and exit functions")
        self.entry_fsa = Automaton(self.logger, self.model["entry"], self.identifier)

        # Save digraphs
        automaton_dir = "automaton"
        self.logger.info("Save automata to directory {}".format(automaton_dir))
        os.mkdir(automaton_dir)
        for automaton in self.callback_fsa + self.model_fsa + [self.entry_fsa]:
            automaton.save_digraph(automaton_dir)

        # Generate variables
        for automaton in self.callback_fsa + self.model_fsa + [self.entry_fsa]:
            variables = automaton.variables
            for variable in variables:
                if not variable.file:
                    variable.file = self.entry_file
                if variable.file not in self.files:
                    self.files[variable.file] = {
                        "variables": {},
                        "functions": {}
                    }
                self.files[variable.file]["variables"][variable.name] = variable

        # Generate automata control function
        self.logger.info("Generate control functions for the environment model")
        for automaton in self.callback_fsa + [self.entry_fsa]:
            self.generate_control_function(automaton)

        # Generate model control function
        models = []
        for name in (pr.name for pr in self.model["models"]):
            automata = (a for a in self.model_fsa if a.process.name == name)
            self.generate_model_aspect(automata, name)

        for automaton in self.callback_fsa + self.model_fsa + [self.entry_fsa]:
            for function in automaton.functions:
                if function.file not in self.files:
                    self.files[function.file] = {"functions": {}, "variables": {}}
                self.files[function.file]["functions"][function.name] = function

        # Generate entry point function
        ep = self.generate_entry_function()
        self.files[self.entry_file]["functions"][ep.name] = ep

    @property
    def identifier(self):
        self.__identifier_cnt += 1
        return self.__identifier_cnt

    def __instanciate_processes(self, instances, process):
        base_list = instances

        # Copy base instances for each known implementation
        relevant_multi_containers = []
        accesses = process.accesses()
        for access in accesses.values():
            for inst_access in [inst for inst in access if inst.interface]:
                if inst_access.interface.container and len(inst_access.interface.implementations) > 1 and \
                                inst_access.interface not in relevant_multi_containers:
                    relevant_multi_containers.append(inst_access.interface)
                elif len(inst_access.complete_list_interface) > 1:
                    for intf in [intf for intf in inst_access.complete_list_interface if intf.container and
                                 intf.implementations and len(intf.implementations) > 1 and
                                 intf not in relevant_multi_containers]:
                        relevant_multi_containers.append(intf)

        # Copy instances for each implementation of a container
        if len(relevant_multi_containers) > 0:
            new_base_list = []
            for interface in relevant_multi_containers:
                implementations = interface.implementations

                for implementation in implementations:
                    for instance in base_list:
                        newp = copy.deepcopy(instance)
                        accs = newp.accesses()
                        for access_list in accs.values():
                            for access in access_list:
                                # Replace not even container itself but other collateral interface implementaations
                                if access.interface and len(access.interface.implementations) > 0 and \
                                    len([impl for impl in access.interface.implementations
                                         if impl.base_container == interface.full_identifier]) > 0:
                                    new_values = [impl for impl in access.interface.implementations
                                                  if impl.base_container == interface.full_identifier and
                                                  impl.base_value == implementation.value]

                                    if len(new_values) == 0:
                                        access.interface.implementations = []
                                    elif len(new_values) == 1:
                                        access.interface.implementations = new_values
                                    else:
                                        raise RuntimeError("Seems two values spring from one variable")

                        new_base_list.append(newp)
                base_list = new_base_list

        # Copy callbacks or resources which are not tied to a container
        accesses = base_list[0].accesses()
        relevant_multi_leafs = []
        for access in accesses.values():
            relevant_multi_leafs.extend([inst for inst in access if inst.interface and
                                         len(inst.interface.implementations) > 1])
        if len(relevant_multi_leafs) > 0:
            for access in relevant_multi_leafs:
                new_base_list = []
                for implementation in access.interface.implementations:
                    for instance in base_list:
                        newp = copy.deepcopy(instance)
                        newp_accesses = newp.accesses()
                        modify_acc = [acc for acc in newp_accesses[access.expression]
                                      if acc.interface.full_identifier == access.interface.full_identifier][0]
                        modify_acc.interface.implementations = [implementation]
                        new_base_list.append(newp)

                base_list = new_base_list

        return base_list

    def generate_entry_function(self):
        self.logger.info("Finally generate entry point function {}".format(self.entry_point_name))
        # Function prototype
        ep = Function(
            self.entry_point_name,
            self.entry_file,
            Signature("void {}(void)".format(self.entry_point_name)),
            False
        )

        body = [
            "while(1) {",
            "\tswitch(ldv_undef_int()) {"
        ]

        automata = self.callback_fsa + [self.entry_fsa]
        for index in range(len(automata)):
            body.extend(
                [
                    "\t\tcase {}: ".format(index),
                    "\t\t\t{}();".format(automata[index].control_function.name),
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

    def generate_control_function(self, automaton):
        self.logger.info("Generate control function for automata {} with process {}".
                         format(automaton.identifier, automaton.process.name))

        # Generate case for each transition
        cases = []
        for edge in automaton.fsa.state_transitions:
            new = self.generate_case(automaton, edge)
            cases.extend(new)
        if len(cases) == 0:
            raise RuntimeError("Cannot generate control function for automata {} with process {}".
                               format(automaton.identifier, automaton.process.name))

        # Create Function
        cf = Function(
            "emg_{}_{}_control_function".format(automaton.process.name, automaton.identifier),
            self.entry_file,
            Signature("void %s(void)"),
            export=False
        )

        # Create body
        body = ["switch(ldv_undef_int()) {"]
        for index in range(len(cases)):
            body.extend(
                [
                    "\tcase {}: ".format(index) + '{',
                    "\t\tif ({}) ".format(cases[index]["guard"]) + '{'
                ]
            )
            body.extend([(3 * "\t" + statement) for statement in cases[index]["body"]])
            body.extend(
                [
                    "\t\t}",
                    "\t}",
                    "\tbreak;"
                ]
            )
        body.extend(
            [
                "\tdefault: break;",
                "}"
            ]
        )
        cf.body.concatenate(body)
        automaton.functions.append(cf)
        automaton.control_function = cf

    def generate_model_aspect(self, automata, name):
        # Create function
        model_signature = self.analysis.kernel_functions[name]["signature"]
        cf = Aspect(name, model_signature)

        bodies = []
        for automaton in automata:
            # Generate case for each transition
            cases = []
            for edge in automaton.fsa.state_transitions:
                new = self.generate_case(automaton, edge)
                cases.extend(new)
            if len(cases) == 0:
                raise RuntimeError("Cannot generate model control function for automata {} with process {}".
                                   format(automaton.identifier, automaton.process.name))

            # Calculate terminals
            in_states = [transition["in"] for transition in automaton.fsa.state_transitions]
            terminals = [tr["out"] for tr in automaton.fsa.state_transitions if tr["out"] not in in_states]
            condition = ' || '.join(["{} == {}".format(automaton.state_variable.name, st) for st in terminals])

            # Create body
            body = [
                "\twhile (!({}))".format(condition) + "{",
                "\t\tswitch(ldv_undef_int()) {"
            ]
            for index in range(len(cases)):
                body.extend(
                    [
                        "\t\t\tcase {}: ".format(index) + '{',
                        "\t\t\t\tif ({}) ".format(cases[index]["guard"]) + '{'
                    ]
                )
                body.extend([(5 * "\t" + statement) for statement in cases[index]["body"]])
                body.extend(
                    [
                        "\t\t\t\t}",
                        "\t\t\t}",
                        "\t\t\tbreak;"
                    ]
                )
            body.extend(
                [
                    "\t\t\tdefault: break;",
                    "\t\t}",
                    "\t}"
                ]
            )
            bodies.append(body)

        # Create body
        if len(bodies) > 1:
            body = [
                "switch(ldv_undef_int()) {"
            ]
            for index in range(len(bodies)):
                body.extend(
                    [
                        "\tcase {}: ".format(index) + '{',
                    ]
                )
                body.extend([(2 * "\t" + statement) for statement in bodies[index]])
                body.extend(
                    [
                        "\t}",
                        "\tbreak;"
                    ]
                )
            body.extend(
                [
                    "}"
                ]
            )
        else:
            body = bodies[0]
        cf.body.concatenate(body)
        self.model_aspects.append(cf)

    def determine_callback_implementations(self, automaton, subprocess, case):
        accesses = automaton.process.resolve_access(subprocess.callback)
        callbacks = []

        for access in accesses:
            new_case = copy.deepcopy(case)
            invoke = None

            if access.interface:
                signature = access.interface.signature

                if len(access.interface.implementations) > 1 and len(set(im.value for im in access.interface.implementations)) > 1:
                    raise NotImplementedError("Cannot process fsm with several implementations of a single callback")
                elif len(access.interface.implementations) == 1 or \
                        len(set(im.value for im in access.interface.implementations)):
                    invoke = '(' + access.interface.implementations[0].value + ')'
                    file = access.interface.implementations[0].file
                    check = False

                else:
                    invoke = '(*' +\
                             access.access_with_variable(
                                     automaton.variable(access.label, access.list_interface[0].full_identifier)) +\
                             ')'
                    file = self.entry_file
                    check = True
            else:
                signature = access.label.signature()

                if access.label.value:
                    invoke = '(' + access.label.value + ')'
                    file = self.entry_file
                    check = False
                elif access.label.signature():
                    invoke = access.access_with_variable(automaton.variable(access.label))
                    file = self.entry_file
                    check = True

            if invoke:
                additional_check = self.registration_intf_check(invoke)
                if additional_check:
                    new_case["guard"] += " && {}".format(additional_check)

                callbacks.append([new_case, signature, invoke, file, check])

        return callbacks

    def generate_case(self, automaton, edge):
        subprocess = edge["subprocess"]
        cases = []
        base_case = {
            "guard": "{} == {}".format(automaton.state_variable.name, edge["in"]),
            "body": [],
        }

        if subprocess.type == "dispatch" and subprocess.callback:
            callbacks = self.determine_callback_implementations(automaton, subprocess, base_case)

            for case, signature, invoke, file, check in callbacks:
                # Generate function call and corresponding function
                fname = "emg_{}_{}_{}_{}".\
                    format(automaton.identifier, automaton.process.name, subprocess.name, len(automaton.functions))

                params = []
                local_vars = []

                # Determine parameters
                for index in range(len(signature.parameters)):
                    parameter = signature.parameters[index]
                    expression = None

                    # Try to find existing variable
                    if parameter.interface:
                        for candidate in subprocess.parameters:
                            accesses = automaton.process.resolve_access(candidate)
                            suits = [acc for acc in accesses if acc.interface and
                                     acc.interface.full_identifier == parameter.interface.full_identifier]
                            if len(suits) == 1:
                                var = automaton.variable(suits[0].label, suits[0].list_interface[0].full_identifier)
                                expression = suits[0].access_with_variable(var)
                                break
                            elif len(suits) > 1:
                                raise NotImplementedError("Cannot set two different parameters")

                    # Generate new variable
                    if not expression:
                        tmp = Variable("emg_param_{}".format(index), None, signature.parameters[index], False)
                        local_vars.append(tmp)
                        expression = tmp.name

                    # Add string
                    params.append(expression)

                # Generate special function with call
                function = Function(fname, file, Signature("void {}(void)".format(fname)), True)
                for var in local_vars:
                    if var.signature.type_class == "struct" and var.signature.pointer:
                        definition = var.declare_with_init(init=True) + ";"
                    else:
                        var.signature.type_class = "primitive"
                        definition = var.declare(False) + ";"
                    function.body.concatenate(definition)

                # Generate return value assignment
                retval = ""
                ret_subprocess = [automaton.process.subprocesses[name] for name in automaton.process.subprocesses
                                  if automaton.process.subprocesses[name].callback and
                                  automaton.process.subprocesses[name].callback == subprocess.callback and
                                  automaton.process.subprocesses[name].type == "receive" and
                                  automaton.process.subprocesses[name].callback_retval]
                if ret_subprocess:
                    ret_access = automaton.process.resolve_access(ret_subprocess[0].callback_retval)
                    retval = ret_access[0].access_with_variable(automaton.variable(ret_access[0].label))
                    retval += " = "

                # Generate callback call
                if check:
                    function.body.concatenate(
                        [
                            "if ({})".format(invoke),
                            "\t" + retval + invoke + '(' + ", ".join(params) + ");"
                        ]
                    )
                else:
                    function.body.concatenate(
                        retval + invoke + '(' + ", ".join(params) + ");"
                    )

                # Free allocated memory
                for var in [var for var in local_vars if var.signature.type_class in ["struct", "primitive"] and
                            var.signature.pointer]:
                    function.body.concatenate(var.free_pointer() + ";")
                automaton.functions.append(function)

                # Generate comment
                case["body"].append("/* Call callback {} */".format(subprocess.name))
                case["body"].append("{}();".format(fname))
                cases.append(case)
        elif subprocess.type == "dispatch":
            # Generate dispatch function
            if subprocess.peers and len(subprocess.peers) > 0:

                # Do call only if model which can be called will not hang
                automata_peers = {}
                self.__extract_relevant_automata(automata_peers, subprocess.peers, ["receive"])
                checks = self.__generate_state_pair(automata_peers)
                if len(checks) > 0:
                    # Generate dispatch function
                    df = Function(
                        "emg_{}_{}_dispatch_{}".format(automaton.identifier, automaton.process.name, subprocess.name),
                        self.entry_file,
                        Signature("void %s(void)"),
                        False
                    )

                    body = []
                    for check in checks:
                        tmp_body = []
                        dispatch_condition = "{} == {}".format(check[0], str(check[1]["in"]))

                        # Receiver condition
                        receiver_condition = []
                        if check[1]["subprocess"].condition:
                            receiver_condition = check[1]["subprocess"].condition

                        # Add parameters
                        for index in range(len(subprocess.parameters)):
                            # Determine dispatcher parameter
                            interface = subprocess.get_common_interface(automaton.process, index)

                            # Determine receiver parameter
                            receiver_access = check[1]["automaton"].process.\
                                resolve_access(check[1]["subprocess"].parameters[index], interface)
                            receiver_expr = receiver_access.\
                                access_with_variable(check[1]["automaton"].variable(receiver_access.label, interface))

                            # Determine dispatcher parameter
                            dispatcher_access = automaton.process.\
                                resolve_access(subprocess.parameters[index], interface)
                            dispatcher_expr = dispatcher_access.\
                                access_with_variable(automaton.variable(dispatcher_access.label, interface))

                            # Replace guard
                            receiver_condition = [stm.replace("$ARG{}".format(index + 1), dispatcher_expr) for stm
                                                  in receiver_condition]

                            # Generate assignment
                            tmp_body.append("\t{} = {};".format(receiver_expr, dispatcher_expr))

                        if subprocess.broadcast:
                            tmp_body.extend(
                                [
                                    "}"
                                ]
                            )
                        else:
                            tmp_body.extend(
                                [
                                    "\treturn;",
                                    "}"
                                ]
                            )

                        if len(receiver_condition) > 0:
                            new_receiver_condition = []
                            for stm in receiver_condition:
                                new_receiver_condition.extend(text_processor(check[1]["automaton"], stm))
                            receiver_condition = new_receiver_condition
                            dispatcher_condition = [dispatch_condition] + receiver_condition
                        else:
                            dispatcher_condition = [dispatch_condition]

                        tmp_body =\
                            [
                                "/* Try receive according to {} */".format(check[1]["subprocess"].name),
                                "if({}) ".format(" && ".join(dispatcher_condition)) + '{',
                                "\t{} = {};".format(check[0], check[1]["out"]),
                            ] + tmp_body
                        body.extend(tmp_body)
                    df.body.concatenate(body)
                    automaton.functions.append(df)

                    # Add dispatch expression
                    base_case["body"].append("/* Dispatch {} */".format(subprocess.name))
                    base_case["body"].append("{}();".format(df.name))

                    # Generate guard
                    base_case["guard"] += ' && (' + " || ".join(["{} == {}".format(var, tr["in"])
                                                                 for var, tr in checks]) + ')'
                elif len(list(automata_peers.keys())) > 0:
                    raise RuntimeError("No dispatches are generated for dispatch {} but it can be received".
                                       format(subprocess.name))
            else:
                # Generate comment
                base_case["body"].append("/* Dispatch {} is not expected by any process, skip it */".
                                         format(subprocess.name))
            cases.append(base_case)
        elif subprocess.type == "receive" and subprocess.callback:
            base_case["body"].append("/* Should wait for return value of {} here, "
                                     "but in sequential model it is not necessary */".format(subprocess.name))
            cases.append(base_case)
        elif subprocess.type == "receive":
            # Generate comment
            base_case["body"].append("/* Receive signal {} */".format(subprocess.name))
            cases.append(base_case)
            # Do not chenge state there
            return cases
        elif subprocess.type == "condition":
            # Generate comment
            base_case["body"].append("/* Code or condition insertion {} */".format(subprocess.name))

            # Add additional condition
            if subprocess.condition and len(subprocess.condition) > 0:
                for statement in subprocess.condition:
                    cn = text_processor(automaton, statement)
                    base_case["guard"] = " && ".join([base_case["guard"]] + cn)

            if subprocess.statements:
                for statement in subprocess.statements:
                    base_case["body"].extend(text_processor(automaton, statement))
            cases.append(base_case)
        elif subprocess.type == "subprocess":
            # Generate comment
            base_case["body"].append("/* Start subprocess {} */".format(subprocess.name))
            cases.append(base_case)
        else:
            raise ValueError("Unexpected state machine edge type: {}".format(subprocess.type))

        for case in cases:
            case["body"].append("{} = {};".format(automaton.state_variable.name, edge["out"]))
        return cases

    def registration_intf_check(self, function_call):
        name_re = re.compile("\(?\s*&?\s*(\w+)\s*\)?$")
        check = []

        if name_re.match(function_call):
            name = name_re.match(function_call).group(1)

            # Caclulate relevant models
            if name in self.analysis.modules_functions:
                relevant_models = self.__collect_relevant_models(name)

                # Get list of models
                process_models = [model for model in self.model["models"] if model.name in relevant_models]

                # Check relevant state machines for each model
                automata_peers = {}
                for model in process_models:
                    signals = [model.subprocesses[name] for name in model.subprocesses
                               if len(model.subprocesses[name].peers) > 0 and model.subprocesses[name].type
                               in ["dispatch", "receive"]]

                    # Get all peers in total
                    peers = []
                    for signal in signals:
                        peers.extend(signal.peers)

                    # Add relevant state machines
                    self.__extract_relevant_automata(automata_peers, peers, None)

                check.extend(["({} == {} || {} == 0)".format(var, tr["in"], var) for var, tr
                              in self.__generate_state_pair(automata_peers)])
        else:
            self.logger.warning("Cannot find module function for callback '{}'".format(function_call))

        return " && ".join(check)

    def __collect_relevant_models(self, function):
        process_names = [function]
        processed_names = []
        relevant = []
        while len(process_names) > 0:
            name = process_names.pop()

            if name in self.analysis.modules_functions:
                for file in self.analysis.modules_functions[name]["files"]:
                    for called in self.analysis.modules_functions[name]["files"][file]["calls"]:
                        if called in self.analysis.modules_functions and called not in processed_names and \
                                called not in process_names:
                            process_names.append(called)
                        elif called in self.analysis.kernel_functions:
                            relevant.append(called)

            processed_names.append(name)
        return relevant

    def __extract_relevant_automata(self, automata_peers, peers, types):
        for peer in peers:
            relevant_automata = [automaton for automaton in self.callback_fsa
                                 if automaton.process.name == peer["process"].name and
                                 automaton.identifier != self.identifier]
            for automaton in relevant_automata:
                if automaton.identifier not in automata_peers:
                    automata_peers[automaton.identifier] = {
                        "automaton": automaton,
                        "subprocesses": []
                    }
                if peer["subprocess"] not in automata_peers[automaton.identifier]["subprocesses"]:
                    if not types or (types and peer["subprocess"].type in types):
                        automata_peers[automaton.identifier]["subprocesses"].append(peer["subprocess"])

    @staticmethod
    def __generate_state_pair(automata_peers):
        check = []
        # Add state checks
        for ap in automata_peers.values():
            for transition in ap["automaton"].fsa.state_transitions:
                if transition["subprocess"].name in [subp.name for subp in ap["subprocesses"]]:
                    check.append([ap["automaton"].state_variable.name, transition])

        return check


class Automaton:

    def __init__(self, logger, process, identifier):
        # Set default values
        self.control_function = None
        self.functions = []
        self.__variables = []
        self.__label_variables = {}
        self.__state_variable = None

        # Set given values
        self.logger = logger
        self.process = process
        self.identifier = identifier

        # Generate FSA itself
        self.logger.info("Generate states for automaton {} based on process {} with category {}".
                         format(self.identifier, self.process.name, self.process.category))
        self.fsa = FSA(self, self.process)

        # Generate variables
        self.variables

    @property
    def state_variable(self):
        if not self.__state_variable:
            statev = Variable("emgfsa_state_{}".format(self.identifier), None, Signature("int %s"), export=True)
            statev.value = "0"
            statev.use = 1
            self.logger.debug("Add state variable for automata {} with process {}: {}".
                              format(self.identifier, self.process.name, statev.name))
            self.__state_variable = statev

        return self.__state_variable

    @property
    def variables(self):
        if len(self.__variables) == 0:
            # Generate state variable
            self.__variables.append(self.state_variable)

            # Generate variable for each label
            for label in self.process.labels.values():
                if label.interfaces:
                    for interface in label.interfaces:
                        self.__variables.append(self.variable(label, interface))
                else:
                    var = self.variable(label)
                    if var:
                        self.__variables.append(self.variable(label))

        return self.__variables

    def variable(self, label, interface=None):
        if not interface:
            if label.name in self.__label_variables and "default" in self.__label_variables[label.name]:
                return self.__label_variables[label.name]["default"]
            else:
                if label.signature():
                    var = Variable("emgfsa_{}_{}_{}".format(self.identifier, label.name, "default"), None,
                                   label.signature(), export=True)
                    if label.value:
                        var.value = label.value

                    if label.name not in self.__label_variables:
                        self.__label_variables[label.name] = {}
                    self.__label_variables[label.name]["default"] = var
                    return self.__label_variables[label.name]["default"]
                else:
                    self.logger.warning("Cannot create variable for label which is not matched with interfaces and does"
                                        " not have signature")
                    return None
        else:
            if label.name in self.__label_variables and interface in self.__label_variables[label.name]:
                return self.__label_variables[label.name][interface]
            else:
                if interface not in label.interfaces:
                    raise KeyError("Label {} is not matched with interface {}".format(label.name, interface))
                else:
                    access = self.process.resolve_access(label, interface)
                    label_signature = label.signature(None, access.interface.full_identifier)
                    category, short_id = interface.split(".")
                    var = Variable("emgfsa_{}_{}_{}".format(self.identifier, label.name, short_id), None,
                                   label_signature, export=True)

                    if len(access.interface.implementations) == 1:
                        if access.interface.signature.pointer == label_signature.pointer:
                            var.value = access.interface.implementations[0].value
                        else:
                            if label_signature.pointer:
                                var.value = "& " + access.interface.implementations[0].value
                            else:
                                var.value = "* " + access.interface.implementations[0].value

                        # Change file according to the value
                        var.file = access.interface.implementations[0].file
                    elif len(access.interface.implementations) > 1:
                        raise ValueError("Cannot initialize label {} with several values".format(label.name))

                    if label.name not in self.__label_variables:
                        self.__label_variables[label.name] = {}
                    self.__label_variables[label.name][interface] = var
                    return self.__label_variables[label.name][interface]

    def save_digraph(self, directory):
        # Generate graph
        self.logger.info("Generate graph for automaton based on process {} with category {}".
                         format(self.process.name, self.process.category))
        dg_file = "{}/{}.dot".format(directory, "{}_{}_{}".
                                     format(self.process.category, self.process.name, self.identifier))
        self.fsa.save_fsa_digraph(dg_file, self.identifier, self.process)


class FSA:

    def __init__(self, automaton, process):
        self.__state_counter = 0
        self.__checked_ast = {}
        self.__ast_counter = 0
        self.__checked_subprocesses = {}
        self.state_transitions = []

        # Generate AST states
        self.__generate_states(automaton, process)

    def __generate_states(self, automaton, process):
        if "identifier" not in process.process_ast:
            # Enumerate AST
            nodes = [process.subprocesses[name].process_ast for name in process.subprocesses
                     if process.subprocesses[name].process_ast] + [process.process_ast]
            while len(nodes) > 0:
                ast = nodes.pop()
                new = self.__enumerate_ast(ast)
                nodes.extend(new)

        # Generate states
        transitions = [[process.process_ast, None]]
        while len(transitions) > 0:
            ast, predecessor = transitions.pop()
            new = self.__process_ast(automaton, process, ast, predecessor)
            transitions.extend(new)

    def __enumerate_ast(self, ast):
        key = list(ast.keys())[0]
        to_process = []

        if key in ["sequence", "options"]:
            for action in reversed(ast[key]):
                to_process.append(action)
        elif key in ["process"]:
            to_process.append(ast[key])
        elif key not in ["subprocess", "receive", "dispatch", "condition", "null"]:
            raise RuntimeError("Unknown operator in process AST: {}".format(key))

        ast["identifier"] = int(self.__ast_counter)
        self.__ast_counter += 1
        return to_process

    def __process_ast(self, automaton, process, ast, predecessor):
        key = list(ast.keys())[0]
        to_process = []

        if key == "sequence":
            new = []
            previous = predecessor
            for action in ast[key]:
                new.append([action, previous])
                previous = action["identifier"]
            self.__checked_ast[ast["identifier"]] = {"sequence": True, "last": new[-1][0]["identifier"]}
            to_process.extend(reversed(new))
        elif key == "options":
            for option in ast[key]:
                to_process.append([option, predecessor])
            self.__checked_ast[ast["identifier"]] = {
                "options": True,
                "children": [option["identifier"] for option in ast[key]]
            }
        elif key == "process":
            to_process.append([ast[key], predecessor])
            self.__checked_ast[ast["identifier"]] = {"brackets": True, "follower": ast[key]["identifier"]}
        elif key == "subprocess":
            if ast[key]["name"] in self.__checked_subprocesses:
                state = self.__checked_subprocesses[ast[key]["name"]]
                for origin in self.__resolve_state(predecessor):
                    transition = {
                        "ast": ast[key],
                        "subprocess": process.subprocesses[ast[key]["name"]],
                        "in": origin,
                        "out": state,
                        "automaton": automaton
                    }
                    self.state_transitions.append(transition)
            else:
                self.__state_counter += 1
                for origin in self.__resolve_state(predecessor):
                    transition = {
                        "ast": ast[key],
                        "subprocess": process.subprocesses[ast[key]["name"]],
                        "in": origin,
                        "out": self.__state_counter,
                        "automaton": automaton
                    }
                    self.state_transitions.append(transition)
                self.__checked_subprocesses[ast[key]["name"]] = self.__state_counter
                self.__checked_ast[ast["identifier"]] = self.__state_counter

                # Add subprocess to process
                to_process.append([process.subprocesses[ast[key]["name"]].process_ast, ast["identifier"]])
            self.__checked_ast[ast["identifier"]] = {"process": True, "name": ast[key]["name"]}
        elif key in ["receive", "dispatch", "condition"]:
            number = ast[key]["number"]
            self.__state_counter += 1
            for origin in self.__resolve_state(predecessor):
                transition = {
                    "ast": ast[key],
                    "subprocess": process.subprocesses[ast[key]["name"]],
                    "in": origin,
                    "out": self.__state_counter,
                    "automaton": automaton
                }
                self.state_transitions.append(transition)

            if number:
                if type(number) is str:
                    # Expect labe
                    label = process.extract_label(number)
                    if label.value:
                        iterations = int(label.value) - 1
                    else:
                        raise ValueError("Provide exact value for label {} of ptocess {}".
                                         format(label.name, process.name))
                else:
                    iterations = int(number - 1)
                for index in range(iterations):
                    transition = {
                        "ast": ast[key],
                        "subprocess": process.subprocesses[ast[key]["name"]],
                        "in": self.__state_counter,
                        "out": self.__state_counter + 1,
                        "automaton": automaton
                    }
                    self.__state_counter += 1
                    self.state_transitions.append(transition)

            self.__checked_ast[ast["identifier"]] = {"terminal": True, "state": self.__state_counter}
        elif key != "null":
            raise RuntimeError("Unknown operator in process AST: {}".format(key))
        return to_process

    def __resolve_state(self, identifier):
        ret = []
        if not identifier:
            ret = [0]
        elif identifier not in self.__checked_ast:
            raise TypeError("Cannot find state {} in processed automaton states".format(identifier))
        else:
            if "sequence" in self.__checked_ast[identifier]:
                ret = self.__resolve_state(self.__checked_ast[identifier]["last"])
            elif "options" in self.__checked_ast[identifier]:
                for child in self.__checked_ast[identifier]["children"]:
                    ret.extend(self.__resolve_state(child))
            elif "brackets" in self.__checked_ast[identifier]:
                ret = self.__resolve_state(self.__checked_ast[identifier]["follower"])
            elif "terminal" in self.__checked_ast[identifier]:
                ret = [self.__checked_ast[identifier]["state"]]
            elif "process" in self.__checked_ast[identifier]:
                ret = [self.__checked_subprocesses[self.__checked_ast[identifier]["name"]]]
            else:
                raise ValueError("Unknown AST type {}".format(str(self.__checked_ast[identifier])))
        return ret

    def save_fsa_digraph(self, file, identifier, process):
        graph = graphviz.Digraph(
            name=str(identifier),
            comment="Digraph for FSA {} based on process {} with category {}".
                    format(identifier, process.name, process.category),
            format="png"
        )

        # Add process description
        graph.node(
            process.name,
            "Process: {}".format(process.name),
            {
                "shape": "rectangle"
            }
        )

        # Add subprocess description
        for subprocess in [process.subprocesses[name] for name in process.subprocesses
                           if process.subprocesses[name].process]:
            graph.node(
                subprocess.name,
                "Subprocess {}: {}".format(subprocess.name, subprocess.process),
                {
                    "shape": "rectangle"
                }
            )

        # Addd nodes
        for index in range(self.__state_counter + 1):
            graph.node(str(index), "State {}".format(index))

        # Add edges
        for transition in self.state_transitions:
            graph.edge(
                str(transition["in"]),
                str(transition["out"]),
                "{}: {}".format(transition["subprocess"].type, transition["subprocess"].name)
            )

        # Save to file
        graph.save(file)
        graph.render()

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
