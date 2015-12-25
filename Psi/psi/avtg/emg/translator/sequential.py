import copy
import os
import re
import graphviz

from psi.avtg.emg.translator import AbstractTranslator, Variable, Function, ModelMap
from psi.avtg.emg.interfaces import Signature


class Translator(AbstractTranslator):
    unmatched_constant = 2
    automata = []

    def _generate_entry_point(self):
        ri = {}
        for process in self.model["models"] + self.model["processes"]:
            ri[process.identifier] = process.collect_relevant_interfaces()

        # Generate automatas
        self.automata = []
        for process in self.model["processes"]:
            if len(ri[process.identifier]["callbacks"]) > 0:
                self.automata.extend(self.__generate_automata(ri[process.identifier], process))
            else:
                self.automata.append(Automata(self.logger, len(self.automata), self.entry_file, process, self))

        # Create directory for automata
        self.logger.info("Create working directory for automata '{}'".format("automata"))
        os.makedirs("automata", exist_ok=True)

        # Generate states
        for automaton in self.automata:
            self.logger.info("Calculate states of automata and generate image with state transitions of automata {} "
                             "with process {}".format(automaton.identifier, automaton.process.name))
            automaton.generate_automata()

        # Generate variables
        for automaton in self.automata:
            variables = automaton.variables
            for variable in variables:
                if variable.file not in self.files:
                    self.files[variable.file] = {
                        "variables": {},
                        "functions": {}
                    }
                self.files[variable.file]["variables"][variable.name] = variable

        # Generate automata control function
        for automaton in self.automata:
            cf = automaton.control_function
            self.files[automaton.file]["functions"][cf.name] = cf

        return

    def __generate_automata(self, ri, process):
        ri["implementations"] = {}
        ri["signatures"] = {}
        process_automata = []

        # Set containers
        for callback in ri["callbacks"]:
            if type(process.labels[callback[0]].interface) is list:
                interfaces = process.labels[callback[0]].interface
            else:
                interfaces = [process.labels[callback[0]].interface]
            for interface in interfaces:
                intfs = self.__get_interfaces(interface, callback)
                ri["implementations"][str(callback)] = self.__get_implementations(intfs[-1].full_identifier)
                ri["signatures"][str(callback)] = intfs[-1].signature

        # Get parameters and resources implementations
        for label in ri["resources"]:
            ri["implementations"][str([label.name])] = self.__get_implementations(label.interface)
            ri["signatures"][str([label.name])] = label.signature

        # Get parameters and resources implementations
        for parameter in ri["parameters"]:
            intf = self.__get_interfaces(process.labels[parameter[0]].interface, parameter)
            ri["implementations"][str(parameter)] = self.__get_implementations(intf[-1].full_identifier)
            ri["signatures"][str(parameter)] = intf[-1].signature

        # Copy processes
        labels = [process.labels[name] for name in process.labels if process.labels[name].container
                  and process.labels[name].interface
                  and process.labels[name].interface in ri["implementations"]
                  and ri["implementations"][process.labels[name].interface]]
        if len(labels) == 0:
            for index in range(self.unmatched_constant):
                au = Automata(self.logger, len(self.automata) + len(process_automata), self.entry_file, process, self)
                au.label_map = ri
                process_automata.append(au)
        else:
            summ = []
            au = Automata(self.logger, len(self.automata), self.entry_file, process, self)
            au.label_map = ri
            summ.append(au)

            for label in [process.labels[name] for name in process.labels if process.labels[name].container
                          and process.labels[name] not in labels]:
                new = []
                new.extend(summ)
                for au in summ:
                    cp = copy.copy(au)
                    cp.identifier = len(self.automata) + len(new)
                    new.extend(cp)
                summ.extend(new)
            process_automata.extend(summ)

        return process_automata

    def __get_implementations(self, identifier):
        retval = []
        if self.analysis.interfaces[identifier].signature.type_class == "struct" \
                and self.analysis.interfaces[identifier].implementations:
            for file in self.analysis.interfaces[identifier].implementations:
                for variable in self.analysis.interfaces[identifier].implementations[file]:
                    retval.append([file, variable])
        elif self.analysis.interfaces[identifier].signature.type_class == "function":
            category = self.analysis.interfaces[identifier].category
            interface = self.analysis.interfaces[identifier]
            for container in [self.analysis.categories[category]["containers"][name] for name in
                              self.analysis.categories[category]["containers"]
                              if self.analysis.categories[category]["containers"][name].implementations and
                              interface.identifier in
                                              self.analysis.categories[category]["containers"][name].fields.values()]:
                field = list(container.fields.keys())[list(container.fields.values()).index(interface.identifier)]
                for path in container.implementations:
                    for variable in container.implementations[path]:
                        if field in self.analysis.implementations[path][variable]:
                            retval.append([path, self.analysis.implementations[path][variable][field]])

        if len(retval) == 0:
            return None
        else:
            return retval

    def __get_interfaces(self, interface, access):
        ret = [self.analysis.interfaces[interface]]
        for index in range(1, len(access)):
            category = ret[-1].category
            identifier = ret[-1].fields[access[index]]
            identifier = "{}.{}".format(category, identifier)
            ret.append(self.analysis.interfaces[identifier])
        return ret


class Automata:

    def __init__(self, logger, identifier, file, process, translator):
        self.logger = logger
        self.identifier = identifier
        self.file = file
        self.process = process
        self.translator = translator
        self.label_map = {}
        self.state_variable = {}
        self.state_transitions = []
        self.__control_function = None
        self.__state_counter = 0
        self.__checked_ast = {}
        self.__ast_counter = 0
        self.__checked_subprocesses = {}
        self.__variables = []
        self.__functions = []

    def generate_automata(self):
        if "identifier" not in self.process.process_ast:
            # Enumerate AST
            self.logger.info("Enumerate AST nodes of automata {}".format(self.identifier))
            nodes = [self.process.subprocesses[name].process_ast for name in self.process.subprocesses
                     if self.process.subprocesses[name].process_ast] + [self.process.process_ast]
            while len(nodes) > 0:
                ast = nodes.pop()
                new = self.__enumerate_ast(ast)
                nodes.extend(new)

        # Generate states
        self.logger.info("Generate states for automata {}".format(self.identifier))
        transitions = [[self.process.process_ast, None]]
        while len(transitions) > 0:
            ast, predecessor = transitions.pop()
            new = self.__process_ast(ast, predecessor)
            transitions.extend(new)

        # Generate graph
        self.logger.info("Generate graph in the working directory automata {}".format(self.identifier))
        graph = graphviz.Digraph(
            name="{}_{}_{}".format(self.process.name, self.process.identifier, self.identifier),
            comment="Process {} with identifier {} which corresponds to automata {}".
                    format(self.process.name, self.process.identifier, self.identifier),
            format="png"
        )

        # Add process description
        graph.node(
            self.process.name,
            "Process: {}".format(self.process.process),
            {
                "shape": "rectangle"
            }
        )

        # Add subprocess description
        for subprocess in [self.process.subprocesses[name] for name in self.process.subprocesses
                           if self.process.subprocesses[name].process]:
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

        # Save ad draw
        graph.save("automata/{}.dot".format(graph.name))
        graph.render()

        return

    @property
    def variables(self):
        if len(self.__variables) == 0:
            # Generate state variable
            statev = Variable("emg_sm_state_{}".format(self.identifier), self.file, Signature("int %s"), export=True)
            self.state_variable = statev
            self.logger.debug("Add state variable for automata {} with process {}: {}".
                              format(self.identifier, self.process.name, statev.name))
            self.__variables.append(statev)

            # Generate variable for each label
            self.label_map["labels"] = {}
            for label in [self.process.labels[name] for name in self.process.labels]:
                var = Variable("emg_sm_{}_{}".format(self.identifier, label.name), self.file,
                               label.signature, export=True)
                if label.value:
                    var.value = label.value
                self.label_map["labels"][label.name] = var
                self.__variables.append(var)
        return self.__variables

    @property
    def control_function(self):
        if not self.__control_function:
            self.logger.info("Generate control function for automata {} with process {}".
                             format(self.identifier, self.process.name))

            # Generate case for each transition
            cases = []
            for edge in self.state_transitions:
                case = self.__generate_case(edge)
                cases.append(case)
            if len(cases) == 0:
                raise RuntimeError("Cannot generate control function for automata {} with process {}".
                                   format(self.identifier, self.process.name))

            # Create Function
            self.__control_function = Function(
                "emg_{}_{}_control_function".format(self.process.name, self.identifier),
                self.file,
                Signature("void %s(void)"),
                export=False
            )

            # Create body
            body = ["switch(__VERIFIER_nondet_int()) {"]
            for index in range(len(cases)):
                body.extend(
                    [
                        "    case {}: ".format(index) + '{',
                        "       if ({}) ".format(case["guard"]) + '{'
                    ]
                )
                body.extend([3 * "\t" + statement for statement in case["body"]])
                body.extend(
                    [
                        "      }",
                        "   }",
                        "break;"
                    ]
                )
            body.extend(
                [
                    "   default: break;"
                    "}"
                ]
            )
            self.__control_function.body.concatenate(body)

        # Return control function
        return self.__control_function

    @property
    def functions(self):
        if not self.__control_function:
            self.control_function

        return self.__functions

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

    def __process_ast(self, ast, predecessor):
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
                        "subprocess": self.process.subprocesses[ast[key]["name"]],
                        "in": origin,
                        "out": state
                    }
                    self.state_transitions.append(transition)
            else:
                self.__state_counter += 1
                for origin in self.__resolve_state(predecessor):
                    transition = {
                        "ast": ast[key],
                        "subprocess": self.process.subprocesses[ast[key]["name"]],
                        "in": origin,
                        "out": self.__state_counter
                    }
                    self.state_transitions.append(transition)
                self.__checked_subprocesses[ast[key]["name"]] = self.__state_counter
                self.__checked_ast[ast["identifier"]] = self.__state_counter

                # Add subprocess to process
                to_process.append([self.process.subprocesses[ast[key]["name"]].process_ast, ast["identifier"]])
            self.__checked_ast[ast["identifier"]] = {"process": True, "name": ast[key]["name"]}
        elif key in ["receive", "dispatch", "condition"]:
            number = ast[key]["number"]
            self.__state_counter += 1
            for origin in self.__resolve_state(predecessor):
                transition = {
                    "ast": ast[key],
                    "subprocess": self.process.subprocesses[ast[key]["name"]],
                    "in": origin,
                    "out": self.__state_counter
                }
                self.state_transitions.append(transition)

            if number:
                if type(number) is str:
                    # Expect labe
                    label = self.process.extract_label(number)
                    if label.value:
                        iterations = int(label.value) - 1
                    else:
                        raise ValueError("Provide exact value for label {} of ptocess {}".
                                         format(label.name, self.process.name))
                else:
                    iterations = int(number - 1)
                for index in range(iterations):
                    transition = {
                        "ast": ast[key],
                        "subprocess": self.process.subprocesses[ast[key]["name"]],
                        "in": self.__state_counter,
                        "out": self.__state_counter + 1
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

    def __generate_case(self, edge):
        subprocess = edge["subprocess"]
        case = {
            "guard": "{} == {}".format(self.state_variable.name, edge["in"]),
            "body": [],
        }

        if subprocess.type == "dispatch" and subprocess.callback:
            fname = "emg_sm{}_callback_{}".format(self.identifier, subprocess.name)

            # Check function with callback call
            if fname not in [function.name for function in self.__functions]:
                signature = None
                invoke = None
                file = None
                params = []
                vars = []

                # Determine function
                signature = self.label_map["signatures"][str(subprocess.callback)]
                if str(subprocess.callback) in self.label_map["implementations"] \
                        and self.label_map["implementations"][str(subprocess.callback)]:
                    if len(self.label_map["implementations"][str(subprocess.callback)]) == 1:
                        file = self.label_map["implementations"][str(subprocess.callback)][0][0]
                        invoke = "({})".format(self.label_map["implementations"][str(subprocess.callback)][0][1])
                    else:
                        raise NotImplementedError("Do not expect several implementations for callback")

                    additional_check = self.__registration_guard_check(
                        self.label_map["implementations"][str(subprocess.callback)][0][1])
                    if additional_check:
                        case["guard"] += " && {}".format(additional_check)
                else:
                    invoke = self.label_map["labels"][subprocess.callback[0]].name + ".".join(subprocess.callback[1:])

                # Determine parameters
                params = []
                for index in range(len(signature.parameters)):
                    param = None
                    for key in self.label_map["signatures"]:
                        if signature.parameters[index].compare_signature(self.label_map["signatures"][key]):
                            access = [access for access in self.label_map["parameters"] if str(access) == key][0]
                            if str(access) in self.label_map["implementations"] and \
                                    self.label_map["implementations"][str(access)]:
                                if not file:
                                    file = self.label_map["implementations"][str(access)][0]
                                param = self.label_map["implementations"][str(access)][1]
                            else:
                                param = self.label_map["labels"][access[0]].name + ".".join(access[1:])
                            break
                    if param:
                        params.append(param)
                    else:
                        tmp = Variable("emg_param_{}".format(index), None, signature.parameters[index], False)
                        vars.append(tmp)
                        params.append(tmp.name)

                # Be sure file is set
                if not file:
                    file = self.file

                # Check return type to provide back returned value
                if signature.return_value:
                    ret_type = signature.return_value.expression
                    ret_type = ret_type.replace("%s", "")
                else:
                    ret_type = "void"

                # Generate special function with call
                function = Function(fname, file, "{} {}(void)".format(ret_type, fname), True)
                for var in vars:
                    function.body.concatenate(var.declare_with_init())
                function.body.concatenate("")
                function.body.concatenate('\t return ' + invoke + '(' + ",".join(params) + ");")
                self.__functions.append(function)

            # Generate comment
            case["body"].append("/* Call callback {} */".format(subprocess.name))

            # Add return value
            ret_subprocess = [self.process.subprocesses[name] for name in self.process.subprocesses
                              if self.process.subprocesses[name].callback and
                              self.process.subprocesses[name].callback == subprocess.callback and
                              self.process.subprocesses[name].type == "receive" and
                              self.process.subprocesses[name].callback_retval]
            code = ""
            if ret_subprocess:
                retval = ret_subprocess[0].callback_retval
                if len(retval) == 1:
                    retval = self.label_map["labels"][retval[0]].name
                else:
                    retval = self.label_map["labels"][retval[0]].name + ".".join(retval[1:])

                code += "{} = ".format(retval)
            code += "{}();".format(fname)
            case["body"].append(code)
        elif subprocess.type == "dispatch":
            # Generate dispatch function
            if subprocess.peers and len(subprocess.peers) > 0:
                automata_peers = {}
                self.__extract_relevant_automata(automata_peers, subprocess.peers, ["receive"])
                checks = self.__generate_state_check(automata_peers)

                if len(checks) > 0:
                    case["guard"] += '(' + " || ".join(checks) + ')'
            else:
                # Generate comment
                case["body"].append("/* Dispatch {} is not expected by any process, skip it".format(subprocess.name))
        elif subprocess.type == "receive" and subprocess.callback:
            case["body"].append("/* Should wait for return value of {} here, "
                                "but in sequential model it is not necessary*/".format(subprocess.name))
        elif subprocess.type == "receive":
            # Generate comment
            case["body"].append("/* Receive signal {} */".format(subprocess.name))
        elif subprocess.type == "condition":
            # Generate comment
            case["body"].append("/* Code or condition insertion {} */".format(subprocess.name))

            # Add additional condition
            if subprocess.condition:
                subprocess.condition = self.__text_processor(subprocess.condition)
                case["guard"] += " && {}".format(subprocess.condition)
            if subprocess.statements:
                for statement in subprocess.statements:
                    case["body"].append(self.__text_processor(statement))
                case["body"].append("")
        elif subprocess.type == "subprocess":
            # Generate comment
            case["body"].append("/* Start subprocess {} */".format(subprocess.name))
        else:
            raise ValueError("Unexpected state machine edge type: {}".format(subprocess.type))

        case["body"].append("{} = {};".format(self.state_variable.name, edge["out"]))
        return case

    def __text_processor(self, statement):
        # Replace model functions
        statement = self.translator.model_map.replace_models(self.process, statement)

        # Replace labels
        for match in self.process.label_re.finditer(statement):
            access = match.group(0).replace('%', '')
            access = access.split(".")
            replacement = self.label_map["labels"][access[0]].name
            if len(access) > 0:
                replacement += ".".join(access[1:])
            statement = statement.replace(match.group(0), replacement)

    def __registration_guard_check(self, function_call):
        name_re = re.compile("\s*\&?\s*(\w+)\s*$")
        check = []
        if name_re.match(function_call):
            name = name_re.match(function_call).group(1)

            # Caclulate relevant models
            if name in self.translator.analysis.modules_functions:
                relevant_models = self.__collect_relevant_models(name)

                # Get list of models
                process_models = [model for model in self.translator.model["models"] if model.name in relevant_models]

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

                check.extend(self.__generate_state_check(automata_peers))
        else:
            self.logger.warning("Cannot find module function for callback '{}'".format(function_call))

        if len(check) > 0:
            check = '(' + ' || '.join(check) + ')'
        else:
            check = None
        return check

    def __collect_relevant_models(self, name):
        relevant = []
        if name in self.translator.analysis.modules_functions:
            for file in self.translator.analysis.modules_functions[name]["files"]:
                for called in self.translator.analysis.modules_functions[name]["files"][file]["calls"]:
                    if called in self.translator.analysis.modules_functions:
                        relevant.extend(self.__collect_relevant_models(called))
                    elif called in self.translator.analysis.kernel_functions:
                        relevant.append((called))
        return relevant

    def __extract_relevant_automata(self, automata_peers, peers, types):
        for peer in peers:
            relevant_automata = [automaton for automaton in self.translator.automata
                                 if automaton.process.name == peer["process"].name
                                 and automaton.identifier != self.identifier]
            for automaton in relevant_automata:
                if automaton.identifier not in automata_peers:
                    automata_peers[automaton.identifier] = {
                        "automaton": automaton,
                        "subprocesses": []
                    }
                if peer["subprocess"] not in automata_peers[automaton.identifier]["subprocesses"]:
                    subprocess = \
                        automata_peers[automaton.identifier]["automaton"].process.subprocesses[peer["subprocess"]]
                    if not types or (types and subprocess.type in types):
                        automata_peers[automaton.identifier]["subprocesses"].append(peer["subprocess"])

    def __generate_state_check(self, automata_peers):
        check = []
        # Add state checks
        for ap in automata_peers.values():
            for transition in ap["automaton"].state_transitions:
                if transition["subprocess"].name in ap["subprocesses"]:
                    check.append("{} == {}".format(ap["automaton"].state_variable.name, str(transition["in"])))

        return check

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'