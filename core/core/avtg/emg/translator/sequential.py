import copy
import os
import re
import graphviz

from core.avtg.emg.translator import AbstractTranslator, Aspect
from core.avtg.emg.representations import Signature, Function, Variable, ModelMap


class Translator(AbstractTranslator):
    unmatched_constant = 2
    automata = []
    models = []

    def get_interfaces(self, interface, access):
        ret = [self.analysis.interfaces[interface]]
        for index in range(1, len(access)):
            category = ret[-1].category
            identifier = ret[-1].fields[access[index]]
            identifier = "{}.{}".format(category, identifier)
            ret.append(self.analysis.interfaces[identifier])
        return ret

    def _generate_entry_point(self):
        self.logger.info("Collect information about relevant interfaces for each process of the intermediate model")
        ri = {}
        for process in self.model["models"] + self.model["processes"]:
            ri[process.identifier] = process.collect_relevant_interfaces()
            ri[process.identifier] = self.__collect_ri(ri[process.identifier], process)

        # Generate automata
        self.automata = []
        for process in self.model["processes"]:
            if len(ri[process.identifier]["callbacks"]) > 0:
                self.automata.extend(self.__generate_automata(ri[process.identifier], process))
            else:
                self.automata.append(Automata(self.logger, len(self.automata), self.entry_file, process, self))

        # Generate automata for models
        for process in self.model["models"]:
            au = Automata(self.logger, len(self.automata), self.entry_file, process, self)
            au.label_map = ri[process.identifier]
            self.models.append(au)

        # Create directory for automata
        self.logger.info("Create working directory for automata '{}'".format("automata"))
        os.makedirs("automata", exist_ok=True)

        # Generate states
        for automaton in self.automata + self.models:
            self.logger.info("Calculate states of automata and generate image with state transitions of automata {} "
                             "with process {}".format(automaton.identifier, automaton.process.name))
            automaton.generate_automata()

        # Generate state machine for init/exit
        self.logger.info("Generate automata for module initialization and exit functions")
        ri = {
            "callbacks": [
                ['init'],
                ['exit']
            ],
            "implementations": {
                str(['init']): [[self.entry_file, self.model["entry"].labels["init"].value]],
                str(['exit']): [[self.entry_file, self.model["entry"].labels["exit"].value]]
            },
            "signatures": {
                str(['init']): self.model["entry"].labels["init"].signature,
                str(['exit']): self.model["entry"].labels["exit"].signature
            },
            "parameters": []
        }
        main = Automata(self.logger, len(self.automata), self.entry_file, self.model["entry"], self)
        main.label_map = ri
        main.generate_automata()
        self.automata.append(main)

        # Generate variables
        for automaton in self.automata + self.models:
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
            automaton.functions.append(cf)

        # Generate model control function
        for automaton in self.models:
            cf = automaton.model_aspect()
            self.model_aspects.append(cf)

        for automaton in self.models + self.automata:
            for function in automaton.functions:
                if function.file not in self.files:
                    self.files[function.file] = {"functions": {}, "variables": {}}
                self.files[function.file]["functions"][function.name] = function

        # Generate entry point function
        ep = self.__generate_entry_point()
        self.files[self.entry_file]["functions"][ep.name] = ep

    def __collect_ri(self, ri, process):
        ri["implementations"] = {}
        ri["signatures"] = {}

        # Set containers
        self.logger.info("Collect information about callbacks in process {}".format(process.name))
        for callback in ri["callbacks"]:
            interfaces = process.labels[callback[0]].interface

            for interface in interfaces:
                intfs = self.get_interfaces(interface, callback)
                for index in range(len(intfs)):
                    if str(callback[0:index + 1]) not in ri["implementations"]:
                        ri["implementations"][str(callback[0:index + 1])] = {}
                    ri["implementations"][str(callback[0:index + 1])][intfs[index].full_identifier] = \
                        self.__get_implementations(intfs[index].full_identifier)
                    if str(callback[0:index + 1]) not in ri["signatures"]:
                        ri["signatures"][str(callback[0:index + 1])] = {}
                    ri["signatures"][str(callback[0:index + 1])][intfs[index].full_identifier] = intfs[-1].signature

        # Get parameters and resources implementations
        self.logger.info("Collect information about resources in process {}".format(process.name))
        for label in ri["resources"]:
            for interface in label.interface:
                if str([label.name]) not in ri["implementations"]:
                    ri["implementations"][str([label.name])] = {}
                ri["implementations"][str([label.name])][interface] = self.__get_implementations(interface)
                if str([label.name]) not in ri["signatures"]:
                    ri["signatures"][str([label.name])] = {}
                ri["signatures"][str([label.name])][interface] = label.signature(None, interface)

        # Get parameters and resources implementations
        self.logger.info("Collect information about parameters in process {}".format(process.name))
        for parameter in ri["parameters"]:
            for interface in process.labels[parameter[0]].interface:
                intf = self.get_interfaces(interface, parameter)
                for index in range(len(intf)):
                    if str(parameter[0:index + 1]) not in ri["implementations"]:
                        ri["implementations"][str(parameter[0:index + 1])] = {}
                    ri["implementations"][str(parameter[0:index + 1])][intf[index].full_identifier] = \
                        self.__get_implementations(intf[index].full_identifier)
                    if str(parameter[0:index + 1]) not in ri["signatures"]:
                        ri["signatures"][str(parameter[0:index + 1])] = {}
                    ri["signatures"][str(parameter[0:index + 1])][intf[index].full_identifier] = intf[index].signature
        return ri

    def __generate_automata(self, ri, process):
        nonimplemented_containers = []
        for container in ri["containers"]:
            if container.interface:
                for intf in container.interface:
                    pass
            elif not container.value:
                nonimplemented_containers.append(container)

        # Copy processes
        process_automata = []
        labels = [process.labels[name] for name in process.labels if process.labels[name].container
                  and process.labels[name].interface
                  and str([name]) in ri["implementations"]
                  and len(set(process.labels[name].interface) & set(ri["implementations"][str([name])].keys())) > 0
                  and ri["implementations"][str([name])][process.labels[name].interface]]
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
                    # Expect that variable is not a pointer
                    retval.append([file, "& {}".format(variable)])
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
                            # Expect function pointer
                            retval.append([path,  self.analysis.implementations[path][variable][field]])

        if len(retval) == 0:
            return None
        else:
            return retval

    def __generate_entry_point(self):
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

        for index in range(len(self.automata)):
            body.extend(
                [
                    "\t\tcase {}: ".format(index),
                    "\t\t\t{}();".format(self.automata[index].control_function.name),
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
        self.functions = []

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
            statev.value = "0"
            self.state_variable = statev
            self.logger.debug("Add state variable for automata {} with process {}: {}".
                              format(self.identifier, self.process.name, statev.name))
            self.__variables.append(statev)

            # Generate variable for each label
            self.label_map["labels"] = {}
            for label in [self.process.labels[name] for name in self.process.labels]:
                if label.signature:
                    var = Variable("emg_sm_{}_{}".format(self.identifier, label.name), self.file,
                                   label.signature, export=True)
                    if label.value:
                        var.value = label.value
                    else:
                        # Find implementations
                        if "implementations" in self.label_map\
                                and label.interface and str([label.name]) in self.label_map["implementations"] \
                                and label.interface in self.label_map["implementations"][str([label.name])]\
                                and self.label_map["implementations"][str([label.name])][label.interface]:
                            impl = self.label_map["implementations"][str([label.name])][label.interface][0][1]

                            # todo: do this carefully
                            if self.translator.analysis.interfaces[label.interface].signature.pointer \
                                    == var.signature.pointer:
                                var.value = impl
                            elif self.translator.analysis.interfaces[label.interface].signature.pointer:
                                var.value = "* " + impl
                            else:
                                var.value = "& " + impl

                    self.label_map["labels"][label.name] = var
                    self.__variables.append(var)
                elif not label.signature and label.interface:
                    self.logger.warning("Cannot create variable without signature for automata {} for process {}".
                                        format(self.identifier, self.process.name))
                else:
                    raise ValueError("Need signature to be determined for label {} in process {}".
                                     format(label.name, self.process.name))

        return self.__variables

    @property
    def control_function(self):
        if not self.__control_function:
            self.logger.info("Generate control function for automata {} with process {}".
                             format(self.identifier, self.process.name))

            # Generate case for each transition
            cases = []
            for edge in self.state_transitions:
                new = self.__generate_case(edge)
                cases.extend(new)
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
            self.__control_function.body.concatenate(body)
            self.functions.append(self.__control_function)

        # Return control function
        return self.__control_function

    def model_aspect(self):
        if not self.__control_function:
            self.logger.info("Generate model control function for automata {} with process {}".
                             format(self.identifier, self.process.name))

            # Generate case for each transition
            cases = []
            for edge in self.state_transitions:
                new = self.__generate_case(edge)
                cases.extend(new)
            if len(cases) == 0:
                raise RuntimeError("Cannot generate model control function for automata {} with process {}".
                                   format(self.identifier, self.process.name))

            # Create Function
            model_signature = self.translator.analysis.kernel_functions[self.process.name]["signature"]
            self.__control_function = Aspect(self.process.name, model_signature)

            # Calculate terminals
            in_states = [transition["in"] for transition in self.state_transitions]
            terminals = [tr["out"] for tr in self.state_transitions if tr["out"] not in in_states]
            condition = ' || '.join(["{} == {}".format(self.state_variable.name, st) for st in terminals])

            # Create body
            body = [
                "while (!({}))".format(condition) + "{",
                "\tswitch(ldv_undef_int()) {"
            ]
            for index in range(len(cases)):
                body.extend(
                    [
                        "\t\tcase {}: ".format(index) + '{',
                        "\t\t\tif ({}) ".format(cases[index]["guard"]) + '{'
                    ]
                )
                body.extend([(3 * "\t" + statement) for statement in cases[index]["body"]])
                body.extend(
                    [
                        "\t\t\t}",
                        "\t\t}",
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
            self.__control_function.body.concatenate(body)

        # Return control function
        return self.__control_function

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
                        "out": state,
                        "automata": self
                    }
                    self.state_transitions.append(transition)
            else:
                self.__state_counter += 1
                for origin in self.__resolve_state(predecessor):
                    transition = {
                        "ast": ast[key],
                        "subprocess": self.process.subprocesses[ast[key]["name"]],
                        "in": origin,
                        "out": self.__state_counter,
                        "automata": self
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
                    "out": self.__state_counter,
                    "automata": self
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
                        "out": self.__state_counter + 1,
                        "automata": self
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

    def __determine_callback_implementation(self, case, subprocess, interface):
        signature = self.label_map["signatures"][str(subprocess.callback)][interface]
        file = None
        check = False

        # Extract label name
        label = subprocess.callback[0]
        if str(subprocess.callback) in self.label_map["implementations"]\
                and interface in self.label_map["implementations"][str(subprocess.callback)]\
                and self.label_map["implementations"][str(subprocess.callback)][interface]:
            file = self.label_map["implementations"][str(subprocess.callback)][interface][0][0]
            invoke = "({})".format(self.label_map["implementations"][str(subprocess.callback)][interface][0][1])
            additional_check = self.__registration_guard_check(
                self.label_map["implementations"][str(subprocess.callback)][interface][0][1])
            if additional_check:
                case["guard"] += " && ({})".format(additional_check)
        else:
            if label in self.label_map["labels"]:
                invoke = self.label_map["labels"][label].name
                if len(subprocess.callback) > 1:
                    # todo: do it analyzing each dereference
                    if self.process.labels[label].signature.pointer:
                        invoke += '->' + '->'.join(subprocess.callback[1:])
                    else:
                        invoke += '.' + '->'.join(subprocess.callback[1:])
                    check = True
            else:
                self.logger.warning("Seems that label {} does not have signature but it must, ignore this callback".
                                    format(label))
                return None
        if not file:
            file = self.file
        return [case, signature, invoke, file, check]

    def __generate_callback_call(self, case):
        pass

    def __generate_case(self, edge):
        subprocess = edge["subprocess"]
        cases = []
        base_case = {
            "guard": "{} == {}".format(self.state_variable.name, edge["in"]),
            "body": [],
        }

        if subprocess.type == "dispatch" and subprocess.callback:
            callbacks = []

            # Extract label name
            label = self.process.labels[subprocess.callback[0]]
            if len(subprocess.callback) > 1:
                if label.interface and type(label.interface) is list:
                    raise RuntimeError("Cannot match several callbacks for {} of process {}".
                                              format(str(subprocess.name, self.process.name)))
                elif not label.interface:
                    raise RuntimeError("Need to know container interface to resolve callback {} of process {}".
                                              format(str(subprocess.name, self.process.name)))
                else:
                    intfs = self.translator.get_interfaces(label.interface, subprocess.callback)
                    pack = self.__determine_callback_implementation(copy.deepcopy(base_case), subprocess,
                                                                    intfs[-1].full_identifier)
                    if pack:
                        callbacks.append(pack)
            else:
                if label.interface:
                    if type(label.interface) is list:
                        if label.signature or label.value:
                            raise NotImplementedError("Cannot determine callback {} which has exact signature but "
                                                      "several interfaces in process {}".
                                                      format(str(subprocess.name, self.process.name)))
                        else:
                            for intf in label.interface:
                                pack = self.__determine_callback_implementation(copy.deepcopy(base_case), subprocess, intf)
                                if pack:
                                    callbacks.append(pack)
                    else:
                        pack = self.__determine_callback_implementation(copy.deepcopy(base_case), subprocess, label.interface)
                        if pack:
                            callbacks.append(pack)
                else:
                    if label.signature:
                        casecopy = copy.deepcopy(base_case)
                        invoke = self.label_map["labels"][label.name].name
                        file = self.file
                        callbacks.append([casecopy, label.signature, invoke, file, True])
                    else:
                        raise RuntimeError("Need to know signature or interface to resolve callback {} of "
                                           "process {}".format(str(subprocess.name, self.process.name)))

            for case, signature, invoke, file, check in callbacks:
                # Generate function call and corresponding function
                fname = "emg_sm{}_{}_{}".format(self.identifier, subprocess.name, len(self.functions))

                params = []
                vars = []

                # Determine parameters
                for index in range(len(signature.parameters)):
                    param = None
                    for key in self.label_map["signatures"]:
                        for interface in self.label_map["signatures"][key]:
                            if signature.parameters[index].\
                                    compare_signature(self.label_map["signatures"][key][interface]):
                                access = [access for access in self.label_map["parameters"] if str(access) == key][0]
                                #if signature.parameters[index].pointer != \
                                #        self.label_map["signatures"][key][interface].pointer:
                                #    param = "(*{})".format(self.label_map["labels"][access[0]].name)
                                #else:
                                param = self.label_map["labels"][access[0]].name
                                if len(access) > 1:
                                    # todo: analyze each element
                                    if self.process.labels[access[0]].signature.pointer:
                                        param += '->' + "->".join(access[1:])
                                    else:
                                        param += '.' + ".".join(access[1:])
                                break
                    if param:
                        params.append(param)
                    else:
                        tmp = Variable("emg_param_{}".format(index), None, signature.parameters[index], False)
                        vars.append(tmp)
                        params.append(tmp.name)

                # Generate special function with call
                function = Function(fname, file, Signature("void {}(void)".format(fname)), True)
                for var in vars:
                    function.body.concatenate(var.declare_with_init(init=True) + ";")

                # Generate return value assignment
                retval = ""
                ret_subprocess = [self.process.subprocesses[name] for name in self.process.subprocesses
                                  if self.process.subprocesses[name].callback and
                                  self.process.subprocesses[name].callback == subprocess.callback and
                                  self.process.subprocesses[name].type == "receive" and
                                  self.process.subprocesses[name].callback_retval]
                if ret_subprocess:
                    retval = ret_subprocess[0].callback_retval
                    if len(retval) == 1:
                        retval = self.label_map["labels"][retval[0]].name + " = "
                    else:
                        # todo: check that it is not a pointer
                        retval = self.label_map["labels"][retval[0]].name + ".".join(retval[1:]) + " = "

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
                for var in [var for var in vars if var.signature.type_class in ["struct", "primitive"]
                            and var.signature.pointer]:
                    function.body.concatenate(var.free_pointer() + ";")
                self.functions.append(function)

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
                        "emg_{}_{}_dispatch_{}".format(self.identifier, self.process.name, subprocess.name),
                        self.file,
                        Signature("void %s(void)"),
                        False
                    )

                    body = []
                    for check in checks:
                        # todo: Implement broadcast dispatch without return statement
                        tmp_body = []

                        # Guard
                        guard = ""
                        if check[1]["subprocess"].condition:
                            guard = check[1]["subprocess"].condition

                        # Add parameters
                        for index in range(len(subprocess.parameters)):

                            my_label = self.process.labels[subprocess.parameters[index][0]]
                            label = check[1]["automata"].process.labels[check[1]["subprocess"].parameters[index][0]]

                            my_access = self.label_map["labels"][my_label.name].name
                            if label.name not in check[1]["automata"].label_map["labels"]:
                                raise RuntimeError("There is no variable for label {} in automata {} with process {}".
                                                   format(label.name, check[1]["automata"].identifier,
                                                          check[1]["automata"].process.name))
                            access = check[1]["automata"].label_map["labels"][label.name].name

                            if len(subprocess.parameters[index]) > 1:
                                # todo: add tail analyzing each entry
                                if my_label.signature.pointer:
                                    my_access += '->' + '->'.join(subprocess.parameters[index][1:])
                                else:
                                    my_access += '.' + '.'.join(subprocess.parameters[index][1:])
                            if len(check[1]["subprocess"].parameters[index]) > 1:
                                # todo: add tail analyzing each entry
                                if label.signature.pointer:
                                    access += '->' + '->'.join(check[1]["subprocess"].parameters[index][1:])
                                else:
                                    access += '.' + '.'.join(check[1]["subprocess"].parameters[index][1:])

                            # Replace guard
                            guard = guard.replace("$ARG{}".format(index + 1), access)

                            tmp_body.append("\t{} = {};".format(access, my_access))

                        tmp_body.extend(
                            [
                                "\treturn;",
                                "}"
                            ]
                        )

                        guard = check[1]["automata"].__text_processor(guard)
                        if guard != "":
                            guard = "{} == {}".format(check[0], check[1]["in"]) + ' && (' + guard + ')'
                        else:
                            guard = "{} == {}".format(check[0], check[1]["in"])

                        tmp_body =\
                            [
                                "/* Try receive according to {} */".format(check[1]["subprocess"].name),
                                "if({}) ".format(guard) + '{',
                                "\t{} = {};".format(check[0], check[1]["out"]),
                            ] + tmp_body
                        body.extend(tmp_body)
                    df.body.concatenate(body)
                    self.functions.append(df)

                    # Add dispatch expression
                    base_case["body"].append("/* Dispatch {} */".format(subprocess.name))
                    base_case["body"].append("{}();".format(df.name))

                    # Generate guard
                    base_case["guard"] += ' && (' + " || ".join(["{} == {}".format(var, tr["in"])
                                                                 for var, tr in checks]) + ')'
            else:
                # Generate comment
                base_case["body"].append("/* Dispatch {} is not expected by any process, skip it".format(subprocess.name))
            cases.append(base_case)
        elif subprocess.type == "receive" and subprocess.callback:
            base_case["body"].append("/* Should wait for return value of {} here, "
                                "but in sequential model it is not necessary */".format(subprocess.name))
            cases.append(base_case)
        elif subprocess.type == "receive":
            # Generate comment
            base_case["body"].append("/* Receive signal {} */".format(subprocess.name))
            cases.append(base_case)
        elif subprocess.type == "condition":
            # Generate comment
            base_case["body"].append("/* Code or condition insertion {} */".format(subprocess.name))

            # Add additional condition
            if subprocess.condition and subprocess.condition != "":
                cn = self.__text_processor(subprocess.condition)
                base_case["guard"] += " && {}".format(cn)
            if subprocess.statements:
                for statement in subprocess.statements:
                    base_case["body"].append(self.__text_processor(statement))
            cases.append(base_case)
        elif subprocess.type == "subprocess":
            # Generate comment
            base_case["body"].append("/* Start subprocess {} */".format(subprocess.name))
            cases.append(base_case)
        else:
            raise ValueError("Unexpected state machine edge type: {}".format(subprocess.type))

        for case in cases:
            case["body"].append("{} = {};".format(self.state_variable.name, edge["out"]))
        return cases

    def __text_processor(self, statement):
        # Replace model functions
        mm = ModelMap()
        statement = mm.replace_models(self.process, statement)

        # Replace labels
        for match in self.process.label_re.finditer(statement):
            access = match.group(0).replace('%', '')
            access = access.split(".")
            if access[0] not in self.label_map["labels"]:
                raise KeyError("Variable for label {} has not been defined from statement {}".format(access[0],
                                                                                                     statement))
            replacement = self.label_map["labels"][access[0]].name
            if len(access) > 0:
                replacement += ".".join(access[1:])
            statement = statement.replace(match.group(0), replacement)
        return statement

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

                check.extend(["{} == {}".format(var, tr["in"]) for var, tr
                              in self.__generate_state_pair(automata_peers)])
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

    def __generate_state_pair(self, automata_peers):
        check = []
        # Add state checks
        for ap in automata_peers.values():
            for transition in ap["automaton"].state_transitions:
                if transition["subprocess"].name in ap["subprocesses"]:
                    check.append([ap["automaton"].state_variable.name, transition])

        return check

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'