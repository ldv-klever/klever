import copy
import os
import graphviz

from psi.avtg.emg.translator import AbstractTranslator
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
                self.automata.append(Automata(self.logger, len(self.automata), self.entry_file, process))

        # Create directory for automata
        self.logger.info("Create working directory for automata '{}'".format("automata"))
        os.makedirs("automata", exist_ok=True)

        # Generate states
        for automata in self.automata:
            automata.generate_automata()
        return

    def __generate_automata(self, ri, process):
        ri["implementations"] = {}
        process_automata = []

        # Set containers
        for callback in ri["callbacks"]:
            if type(process.labels[callback[0]].interface) is list:
                interfaces = process.labels[callback[0]].interface
            else:
                interfaces = [process.labels[callback[0]].interface]
            for interface in interfaces:
                intfs = self.__get_interfaces(process, interface, callback)
                for index in range(len(intfs)):
                    ri["implementations"][intfs[index].full_identifier] = \
                        self.__get_implementations(intfs[index].full_identifier)

        # Set resources
        for resource in ri["resources"]:
            ri["implementations"][resource.interface] = self.__get_implementations(resource.interface)

        # Copy processes
        labels = [process.labels[name] for name in process.labels if process.labels[name].container
                  and process.labels[name].interface
                  and process.labels[name].interface in ri["implementations"]
                  and ri["implementations"][process.labels[name].interface]]
        if len(labels) == 0:
            for index in range(self.unmatched_constant):
                au = Automata(self.logger, len(self.automata) + len(process_automata), self.entry_file, process)
                au.label_map = ri
                process_automata.append(au)
        else:
            summ = []
            au = Automata(self.logger, len(self.automata), self.entry_file, process)
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
                            retval.append(self.analysis.implementations[path][variable][field])

        if len(retval) == 0:
            return None
        else:
            return retval

    def __get_interfaces(self, process, interface, access):
        ret = [self.analysis.interfaces[interface]]
        for index in range(1, len(access)):
            category = ret[-1].category
            identifier = ret[-1].fields[access[index]]
            identifier = "{}.{}".format(category, identifier)
            ret.append(self.analysis.interfaces[identifier])
        return ret


class Automata:

    def __init__(self, logger, identifier, file, process):
        self.logger = logger
        self.identifier = identifier
        self.file = file
        self.process = process
        self.label_map = {}
        self.state_variable = {}
        self.__state_transitions = []
        self.__state_counter = 0
        self.__checked_ast = {}
        self.__ast_counter = 0
        self.__checked_subprocesses = {}

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
        for transition in self.__state_transitions:
            graph.edge(
                str(transition["in"]),
                str(transition["out"]),
                "{}: {}".format(transition["subprocess"].type, transition["subprocess"].name)
            )

        # Save ad draw
        graph.save("automata/{}.dot".format(graph.name))
        graph.render()

        return

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
                    self.__state_transitions.append(transition)
            else:
                self.__state_counter += 1
                for origin in self.__resolve_state(predecessor):
                    transition = {
                        "ast": ast[key],
                        "subprocess": self.process.subprocesses[ast[key]["name"]],
                        "in": origin,
                        "out": self.__state_counter
                    }
                    self.__state_transitions.append(transition)
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
                self.__state_transitions.append(transition)

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
                    self.__state_transitions.append(transition)
                    
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

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'