import copy
import os
import re

from core.avtg.emg.translator import AbstractTranslator, Aspect
from core.avtg.emg.common.process import Receive, Dispatch, Call, CallRetval, Condition, Subprocess, \
    get_common_parameter
from core.avtg.emg.common.code import Variable, FunctionDefinition


class Translator(AbstractTranslator):

    def _generate_variables(self, analysis):
        # Generate variables
        for automaton in self._callback_fsa + self._model_fsa + [self._entry_fsa]:
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

    def _aaa(self, analysis, model, automaton):
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

    def _generate_model_aspect(self, analysis, model, automata, name):
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
                elif len(implementations) == 1 and self.__callback_name(implementations[0].value):
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

                if access.label.value and self.__callback_name(access.label.value):
                    invoke = self.__callback_name(access.label.value)
                    file = self.entry_file
                    check = False
                else:
                    variable = automaton.determine_variable(analysis, access.label)
                    if variable:
                        invoke = access.access_with_variable(variable)
                        file = self.entry_file
                        check = True
                    else:
                        invoke = None

            if invoke:
                additional_check = self.__registration_intf_check(analysis, model, invoke)
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
                    if type(parameter) is not str:
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
                    definition = var.declare_with_init(self.conf["translation options"]["pointer initialization"]) + ";"
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

    def __callback_name(self, call):
        name_re = re.compile("\(?\s*&?\s*(\w+)\s*\)?$")
        if name_re.fullmatch(call):
            return name_re.fullmatch(call).group(1)
        else:
            return None

    def __registration_intf_check(self, analysis, model, function_call):
        check = []

        name = self.__callback_name(function_call)
        if name:
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
            relevant_automata = [automaton for automaton in self._callback_fsa
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


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
