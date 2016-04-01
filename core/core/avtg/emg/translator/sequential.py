import copy
import os
import re

from core.avtg.emg.translator import AbstractTranslator, Aspect
from core.avtg.emg.translator.automaton import FSA
from core.avtg.emg.common.interface import Container, Callback
from core.avtg.emg.common.process import Receive, Dispatch, Call, CallRetval, Condition, Subprocess, \
    get_common_parameter
from core.avtg.emg.common.code import Variable, FunctionDefinition, FunctionModels


def text_processor(analysis, automaton, statement):
        # Replace model functions
        mm = FunctionModels()
        accesses = automaton.process.accesses()

        statements = [statement]
        for access in accesses:
            new_statements = []
            for text in list(statements):
                processed = False
                for option in sorted(accesses[access], key=lambda ac: ac.expression):
                    if option.interface:
                        signature = option.label.get_declaration(option.interface.identifier)
                    else:
                        signature = option.label.prior_signature

                    if signature:
                        if option.interface:
                            var = automaton.determine_variable(analysis, option.label,
                                                               option.list_interface[0].identifier)
                        else:
                            var = automaton.determine_variable(analysis, option.label)

                        try:
                            tmp = mm.replace_models(option.label.name, signature, text)
                            tmp = option.replace_with_variable(tmp, var)
                            new_statements.append(tmp)
                            processed = True
                        except ValueError:
                            processed = True

                if not processed:
                    new_statements.append(text)
            statements = new_statements

        # Filter out statements without processes expressions
        final = set()
        for stm in list(statements):
            if '%' not in stm and '$' not in statements:
                final.add(stm)

        return list(final)


class Translator(AbstractTranslator):

    def _generate_code(self, analysis, model):
        # Initialize additional attributes
        self.__callback_fsa = []
        self.__model_fsa = []
        self.__entry_fsa = None
        self.__instance_modifier = 1
        self.__identifier_cnt = -1

        # Read translation options
        if "translation options" not in self.conf:
            self.conf["translation options"] = {}
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

        # Determine how many instances is required for a model
        self.logger.info("Determine how many instances is required to add to an environment model for each process")
        for process in model.event_processes:
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
                base_list = [copy.copy(process) for i in range(self.__instance_modifier)]
            else:
                base_list = [process]
            self.logger.info("Prepare {} instances for {} undefined labels of process {} with category {}".
                             format(len(base_list), len(undefined_labels), process.name, process.category))

            base_list = self.__instanciate_processes(analysis, base_list, process)

            self.logger.info("Generate {} FSA instances for process {} with category {}".
                             format(len(base_list), process.name, process.category))
            for instance in base_list:
                fsa = Automaton(self.logger, instance, self.__yeild_identifier())
                fsa.variables(analysis)
                self.__callback_fsa.append(fsa)

        # Generate automata for models
        for process in model.model_processes:
            self.logger.info("Generate FSA for kernel model process {}".format(process.name))
            processes = self.__instanciate_processes(analysis, [process], process)
            for instance in processes:
                fsa = Automaton(self.logger, instance, self.__yeild_identifier())
                fsa.variables(analysis)
                self.__model_fsa.append(fsa)

        # Generate state machine for init an exit
        # todo: multimodule automaton (issues #6563, #6571, #6558)
        self.logger.info("Generate FSA for module initialization and exit functions")
        self.__entry_fsa = Automaton(self.logger, model.entry_process, self.__yeild_identifier())
        self.__entry_fsa.variables(analysis)

        # Save digraphs
        automaton_dir = "automaton"
        self.logger.info("Save automata to directory {}".format(automaton_dir))
        os.mkdir(automaton_dir)
        for automaton in self.__callback_fsa + self.__model_fsa + [self.__entry_fsa]:
            automaton.save_digraph(automaton_dir)

        # Generate variables
        for automaton in self.__callback_fsa + self.__model_fsa + [self.__entry_fsa]:
            variables = automaton.variables(analysis)
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
        for automaton in self.__callback_fsa + [self.__entry_fsa]:
            self.generate_control_function(analysis, model, automaton)

        # Generate model control function
        for name in (pr.name for pr in model.model_processes):
            automata = (a for a in self.__model_fsa if a.process.name == name)
            self.generate_model_aspect(analysis, model, automata, name)

        for automaton in self.__callback_fsa + self.__model_fsa + [self.__entry_fsa]:
            for function in automaton.functions:
                if function.file not in self.files:
                    self.files[function.file] = {"functions": {}, "variables": {}}
                self.files[function.file]["functions"][function.name] = function

        # Generate entry point function
        ep = self.generate_entry_function()
        self.files[self.entry_file]["functions"][ep.name] = ep

    def __yeild_identifier(self):
        self.__identifier_cnt += 1
        return self.__identifier_cnt

    def __instanciate_processes(self, analysis, instances, process):
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
                    for intf in [intf for intf in inst_access.complete_list_interface if type(intf) is Container and
                                 len(analysis.implementations(intf)) > 1]:
                        relevant_multi_containers.add(intf)

        # Copy instances for each implementation of a container
        if len(relevant_multi_containers) > 0:
            self.logger.info("Found {} relevant containers with several implementations for process {} for category {}".
                             format(str(len(relevant_multi_containers)), process.name, process.category))
            for interface in relevant_multi_containers:
                new_base_list = []
                implementations = analysis.implementations(interface)

                for implementation in implementations:
                    for instance in base_list:
                        newp = copy.copy(instance)
                        self.logger.debug("Forbiding implementations")
                        newp.forbide_except(analysis, implementation)
                        new_base_list.append(newp)

                base_list = list(new_base_list)
        else:
            self.logger.info("Have not found any relevant containers with several implementations for process {} "
                             "for category {}".
                             format(str(len(relevant_multi_containers)), process.name, process.category))

        new_base_list= []
        for instance in base_list:
            # Copy callbacks or resources which are not tied to a container
            accesses = instance.accesses()
            relevant_multi_leafs = set()
            self.logger.debug("Calculate relevant non-containers with several implementations for an instance of "
                              "process {} for category {}".
                              format(process.name, process.category))
            for access in [accesses[name] for name in sorted(accesses.keys())]:
                relevant_multi_leafs.update([inst for inst in access if inst.interface and
                                             type(inst.interface) is Callback and
                                             len(instance.get_implementations(analysis, inst)) > 1])

            if len(relevant_multi_leafs) > 0:
                self.logger.info("Found {} relevant non-containers with several implementations for an instance of "
                                 "process {} for category {}".
                                 format(str(len(relevant_multi_leafs)), process.name, process.category))
                for access in relevant_multi_leafs:
                    for implementation in analysis.implementations(access.interface):
                        newp = copy.copy(instance)
                        self.logger.debug("Forbiding implementations")
                        newp.forbide_except(analysis, implementation)
                        new_base_list.append(newp)
            else:
                self.logger.info("Have not found {} relevant non-containers with several implementations for "
                                 "an instance of process {} for category {}".
                                 format(str(len(relevant_multi_leafs)), process.name, process.category))
                new_base_list.append(instance)

        base_list = new_base_list

        return base_list

    def generate_entry_function(self):
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

        automata = self.__callback_fsa + [self.__entry_fsa]
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

    def generate_control_function(self, analysis, model, automaton):
        self.logger.info("Generate control function for automata {} with process {}".
                         format(automaton.identifier, automaton.process.name))

        # Generate case for each transition
        cases = []
        for edge in automaton.fsa.state_transitions:
            new = self.generate_case(analysis, model, automaton, edge)
            cases.extend(new)
        if len(cases) == 0:
            raise RuntimeError("Cannot generate control function for automata {} with process {}".
                               format(automaton.identifier, automaton.process.name))

        # Create FunctionDefinition
        cf = FunctionDefinition(
            "emg_{}_{}_control_function".format(automaton.process.name, automaton.identifier),
            self.entry_file,
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

    def generate_model_aspect(self, analysis, model, automata, name):
        # Create function
        model_signature = analysis.kernel_functions[name].declaration
        cf = Aspect(name, model_signature)

        bodies = []
        for automaton in automata:
            # Generate case for each transition
            cases = []
            for edge in automaton.fsa.state_transitions:
                new = self.generate_case(analysis, model, automaton, edge)
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

    def determine_callback_implementations(self, analysis, model, automaton, subprocess, case):
        accesses = automaton.process.resolve_access(subprocess.callback)
        callbacks = []

        for access in accesses:
            new_case = copy.deepcopy(case)

            if access.interface:
                signature = access.interface.declaration
                implementations = automaton.process.get_implementations(analysis, access)

                if len(implementations) > 1:
                    raise NotImplementedError("Cannot process fsm with several implementations of a single callback")
                elif len(implementations) == 1:
                    invoke = '(' + implementations[0].value + ')'
                    file = implementations[0].file
                    check = False
                elif signature.clean_declaration:
                    invoke = '(' + \
                              access.access_with_variable(automaton.determine_variable(analysis, access.label,
                                                          access.list_interface[0].identifier)) +\
                              ')'
                    file = self.entry_file
                    check = True
                else:
                    invoke = None
            else:
                signature = access.label.prior_signature

                if access.label.value:
                    invoke = '(' + access.label.value + ')'
                    file = self.entry_file
                    check = False
                else:
                    variable = automaton.determine_variable(analysis, access.label)
                    if variable:
                        invoke = access.access_with_variable()
                        file = self.entry_file
                        check = True
                    else:
                        invoke = None

            if invoke:
                additional_check = self.registration_intf_check(analysis, model, invoke)
                if additional_check:
                    new_case["guard"] += " && {}".format(additional_check)

                callbacks.append([new_case, signature, invoke, file, check])

        return callbacks

    def generate_case(self, analysis, model, automaton, edge):
        action = edge["subprocess"]
        cases = []
        base_case = {
            "guard": "{} == {}".format(automaton.state_variable.name, edge["in"]),
            "body": [],
        }

        if type(action) is Call:
            callbacks = self.determine_callback_implementations(analysis, model, automaton, action, base_case)

            for case, signature, invoke, file, check in callbacks:
                # Generate function call and corresponding function
                fname = "emg_{}_{}_{}_{}".\
                    format(automaton.identifier, automaton.process.name, action.name, len(automaton.functions))

                params = []
                local_vars = []

                # Determine parameters
                for index in range(len(signature.points.parameters)):
                    parameter = signature.points.parameters[index]
                    expression = None

                    # Try to find existing variable
                    ids = [intf.identifier for intf in
                                  analysis.resolve_interface(parameter, edge['automaton'].process.category)]
                    if len(ids) > 0:
                        for candidate in action.parameters:
                            accesses = automaton.process.resolve_access(candidate)
                            suits = [acc for acc in accesses if acc.interface and
                                     acc.interface.identifier in ids]
                            if len(suits) == 1:
                                var = automaton.determine_variable(analysis, suits[0].label,
                                                                   suits[0].list_interface[0].identifier)
                                expression = suits[0].access_with_variable(var)
                                break
                            elif len(suits) > 1:
                                raise NotImplementedError("Cannot set two different parameters")

                    # Generate new variable
                    if not expression:
                        tmp = Variable("emg_param_{}".format(index), None, signature.points.parameters[index], False)
                        local_vars.append(tmp)
                        expression = tmp.name

                    # Add string
                    params.append(expression)

                # Generate special function with call
                function = FunctionDefinition(fname, file, "void {}(void)".format(fname), True)
                for var in local_vars:
                    definition = var.declare_with_init(self.conf["translation options"]["pointer initialization"],
                                                       init=True) + ";"
                    function.body.concatenate(definition)

                # Generate return value assignment
                retval = ""
                ret_subprocess = [automaton.process.actions[name] for name in sorted(automaton.process.actions.keys())
                                  if type(automaton.process.actions[name]) is CallRetval and
                                  automaton.process.actions[name].callback == action.callback and
                                  automaton.process.actions[name].retlabel]
                if ret_subprocess:
                    ret_access = automaton.process.resolve_access(ret_subprocess[0].retlabel)
                    retval = ret_access[0].access_with_variable(
                            automaton.determine_variable(analysis, ret_access[0].label))
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
                for var in local_vars:
                    expr = var.free_pointer(self.conf["translation options"]["pointer free"])
                    if expr:
                        function.body.concatenate(expr + ";")
                automaton.functions.append(function)

                # Generate comment
                case["body"].append("/* Call callback {} */".format(action.name))
                case["body"].append("{}();".format(fname))
                cases.append(case)
        elif type(action) is Dispatch:
            # Generate dispatch function
            if len(action.peers) > 0:

                # Do call only if model which can be called will not hang
                automata_peers = {}
                self.__extract_relevant_automata(automata_peers, action.peers, Receive)
                checks = self.__generate_state_pair(automata_peers)
                if len(checks) > 0:
                    # Generate dispatch function
                    df = FunctionDefinition(
                        "emg_{}_{}_dispatch_{}".format(automaton.identifier, automaton.process.name, action.name),
                        self.entry_file,
                        "void f(void)",
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
                        for index in range(len(action.parameters)):
                            # Determine dispatcher parameter
                            interface = get_common_parameter(action, automaton.process, index)

                            # Determine receiver parameter
                            receiver_access = check[1]["automaton"].process.\
                                resolve_access(check[1]["subprocess"].parameters[index], interface.identifier)
                            receiver_expr = receiver_access.\
                                access_with_variable(check[1]["automaton"].
                                                     determine_variable(analysis, receiver_access.label,
                                                                        interface.identifier))

                            # Determine dispatcher parameter
                            dispatcher_access = automaton.process.\
                                resolve_access(action.parameters[index], interface.identifier)
                            dispatcher_expr = dispatcher_access.\
                                access_with_variable(automaton.determine_variable(analysis, dispatcher_access.label,
                                                                                  interface.identifier))

                            # Replace guard
                            receiver_condition = [stm.replace("$ARG{}".format(index + 1), dispatcher_expr) for stm
                                                  in receiver_condition]

                            # Generate assignment
                            tmp_body.append("\t{} = {};".format(receiver_expr, dispatcher_expr))

                        if action.broadcast:
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
                                new_receiver_condition.extend(text_processor(analysis, check[1]["automaton"], stm))
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
                    base_case["body"].append("/* Dispatch {} */".format(action.name))
                    base_case["body"].append("{}();".format(df.name))

                    # Generate guard
                    base_case["guard"] += ' && (' + " || ".join(["{} == {}".format(var, tr["in"])
                                                                 for var, tr in checks]) + ')'
                elif len(list(automata_peers.keys())) > 0:
                    raise RuntimeError("No dispatches are generated for dispatch {} but it can be received".
                                       format(action.name))
            else:
                # Generate comment
                base_case["body"].append("/* Dispatch {} is not expected by any process, skip it */".
                                         format(action.name))
            cases.append(base_case)
        elif type(action) is CallRetval:
            base_case["body"].append("/* Should wait for return value of {} here, "
                                     "but in sequential model it is not necessary */".format(action.name))
            cases.append(base_case)
        elif type(action) is Receive:
            # Generate comment
            base_case["body"].append("/* Receive signal {} */".format(action.name))
            cases.append(base_case)
            # Do not chenge state there
            return cases
        elif type(action) is Condition:
            # Generate comment
            base_case["body"].append("/* Code or condition insertion {} */".format(action.name))

            # Add additional condition
            if action.condition and len(action.condition) > 0:
                for statement in action.condition:
                    cn = text_processor(analysis, automaton, statement)
                    base_case["guard"] = " && ".join([base_case["guard"]] + cn)

            if action.statements:
                for statement in action.statements:
                    base_case["body"].extend(text_processor(analysis, automaton, statement))
            cases.append(base_case)
        elif type(action) is Subprocess:
            # Generate comment
            base_case["body"].append("/* Start subprocess {} */".format(action.name))
            cases.append(base_case)
        else:
            raise ValueError("Unexpected state machine edge type: {}".format(action.type))

        for case in cases:
            case["body"].append("{} = {};".format(automaton.state_variable.name, edge["out"]))
        return cases

    def registration_intf_check(self, analysis, model, function_call):
        name_re = re.compile("\(?\s*&?\s*(\w+)\s*\)?$")
        check = []

        if name_re.match(function_call):
            name = name_re.match(function_call).group(1)

            # Caclulate relevant models
            if name in analysis.modules_functions:
                relevant_models = analysis.collect_relevant_models(name)

                # Get list of models
                process_models = [model for model in model.model_processes if model.name in relevant_models]

                # Check relevant state machines for each model
                automata_peers = {}
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
                    self.__extract_relevant_automata(automata_peers, peers)

                check.extend(["({} == {} || {} == 0)".format(var, tr["in"], var) for var, tr
                              in self.__generate_state_pair(automata_peers)])
        else:
            self.logger.warning("Cannot find module function for callback '{}'".format(function_call))

        return " && ".join(check)

    def __extract_relevant_automata(self, automata_peers, peers, sb_type=None):
        for peer in peers:
            relevant_automata = [automaton for automaton in self.__callback_fsa
                                 if automaton.process.name == peer["process"].name]
            for automaton in relevant_automata:
                if automaton.identifier not in automata_peers:
                    automata_peers[automaton.identifier] = {
                        "automaton": automaton,
                        "subprocesses": []
                    }
                if peer["subprocess"] not in automata_peers[automaton.identifier]["subprocesses"]:
                    if not sb_type or isinstance(peer["subprocess"], sb_type):
                        automata_peers[automaton.identifier]["subprocesses"].append(peer["subprocess"])

    @staticmethod
    def __generate_state_pair(automata_peers):
        check = []
        # Add state checks
        for ap in [automata_peers[name] for name in sorted(automata_peers.keys())]:
            for transition in ap["automaton"].fsa.state_transitions:
                if transition["subprocess"].name in [subp.name for subp in ap["subprocesses"]]:
                    check.append([ap["automaton"].state_variable.name, transition])

        return check


class Automaton:

    def __init__(self, logger, process, identifier):
        # Set default values
        self.control_function = None
        self.functions = []
        self.__state_variable = None
        self.__variables = []
        self.__label_variables = {}

        # Set given values
        self.logger = logger
        self.process = process
        self.identifier = identifier

        # Generate FSA itself
        self.logger.info("Generate states for automaton {} based on process {} with category {}".
                         format(self.identifier, self.process.name, self.process.category))
        self.fsa = FSA(self, self.process)

    @property
    def state_variable(self):
        if not self.__state_variable:
            statev = Variable("emgfsa_state_{}".format(self.identifier), None, "int a", export=True)
            statev.value = "0"
            statev.use = 1
            self.logger.debug("Add state variable for automata {} with process {}: {}".
                              format(self.identifier, self.process.name, statev.name))
            self.__state_variable = statev

        return self.__state_variable

    def variables(self, analysis):
        if len(self.__variables) == 0:
            # Generate state variable
            self.__variables.append(self.state_variable)

            # Generate variable for each label
            for label in [self.process.labels[name] for name in sorted(self.process.labels.keys())]:
                if label.interfaces:
                    for interface in label.interfaces:
                        self.__variables.append(self.determine_variable(analysis, label, interface))
                else:
                    var = self.determine_variable(analysis, label)
                    if var:
                        self.__variables.append(self.determine_variable(analysis, label))

        return self.__variables

    def determine_variable(self, analysis, label, interface=None):
        if not interface:
            if label.name in self.__label_variables and "default" in self.__label_variables[label.name]:
                return self.__label_variables[label.name]["default"]
            else:
                if label.prior_signature:
                    var = Variable("emgfsa_{}_{}_{}".format(self.identifier, label.name, "default"), None,
                                   label.prior_signature, export=True)
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
                    category, short_id = interface.split(".")
                    implementations = self.process.get_implementations(analysis, access)
                    var = Variable("emgfsa_{}_{}_{}".format(self.identifier, label.name, short_id), None,
                                   label.get_declaration(interface), export=True)

                    if len(implementations) == 1:
                        var.value = implementations[0].adjusted_value(var.declaration)

                        # Change file according to the value
                        var.file = implementations[0].file

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

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
