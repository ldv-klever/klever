import graphviz

from core.avtg.emg.common.process import Subprocess


class FSA:

    def __init__(self, automaton, process):
        self.__state_counter = 0
        self.__checked_ast = {}
        self.__ast_counter = 0
        self.__checked_actions = {}
        self.state_transitions = []

        # Generate AST states
        self.__generate_states(automaton, process)

    def __generate_states(self, automaton, process):
        if "identifier" not in process.process_ast:
            # Enumerate AST
            nodes = [process.actions[name].process_ast for name in sorted(process.actions.keys())
                     if type(process.actions[name]) is Subprocess] + [process.process_ast]
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
        key = list(set(ast.keys()) - set(['identifier']))[0]
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
        key = list(set(ast.keys()) - set(['identifier']))[0]
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
            if ast[key]["name"] in self.__checked_actions:
                state = self.__checked_actions[ast[key]["name"]]
                for origin in self.__resolve_state(predecessor):
                    transition = {
                        "ast": ast[key],
                        "subprocess": process.actions[ast[key]["name"]],
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
                        "subprocess": process.actions[ast[key]["name"]],
                        "in": origin,
                        "out": self.__state_counter,
                        "automaton": automaton
                    }
                    self.state_transitions.append(transition)
                self.__checked_actions[ast[key]["name"]] = self.__state_counter
                self.__checked_ast[ast["identifier"]] = self.__state_counter

                # Add subprocess to process
                to_process.append([process.actions[ast[key]["name"]].process_ast, ast["identifier"]])
            self.__checked_ast[ast["identifier"]] = {"process": True, "name": ast[key]["name"]}
        elif key in ["receive", "dispatch", "condition"]:
            number = ast[key]["number"]
            self.__state_counter += 1
            for origin in self.__resolve_state(predecessor):
                transition = {
                    "ast": ast[key],
                    "subprocess": process.actions[ast[key]["name"]],
                    "in": origin,
                    "out": self.__state_counter,
                    "automaton": automaton
                }
                self.state_transitions.append(transition)

            if number:
                if type(number) is str:
                    # Expect label
                    label = process.extract_label(number)
                    if label.value:
                        iterations = int(label.value) - 1
                    else:
                        raise ValueError("Provide exact value for label {} of process {}".
                                         format(label.name, process.name))
                else:
                    iterations = int(number - 1)
                for index in range(iterations):
                    transition = {
                        "ast": ast[key],
                        "subprocess": process.actions[ast[key]["name"]],
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
                ret = [self.__checked_actions[self.__checked_ast[identifier]["name"]]]
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
        for subprocess in [process.actions[name] for name in sorted(process.actions.keys())
                           if type(process.actions[name]) is Subprocess]:
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
                "{}: {}".format(transition["subprocess"].__class__.__name__, transition["subprocess"].name)
            )

        # Save to file
        graph.save(file)
        graph.render()

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
