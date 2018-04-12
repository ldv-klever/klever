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
import copy
from operator import attrgetter

from core.vtg.emg.common.process import Subprocess, Receive, Dispatch
from core.vtg.emg.common.c import Variable


class FSA:
    """
    Class intended for representing finite state machine (FSA) genereated from a process of an intermediate model.
    Translation is based on extraction semantycs from ASTs given within the Process objects.
    """

    def __init__(self, process):
        """
        Import Process object and generate finite state machine on base of it.

        :param process: Process object
        """
        self.process = process
        self.states = set()
        self.__id_cnt = 0

        # Generate AST states
        sp_asts = dict()
        sp_processed = set()
        asts = list()

        def generate_nodes(process, pr_ast):
            """
            Generates states on base of FSA nodes but do not assign any edges. It explores AST node dictionary
            extracting all particular actions from there like Dispatches, Calls, etc. It also attaches all generated
            states on each atomic action to the corresponding node in AST.

            :param process:
            :param pr_ast: AST node dictionary.
            :return: Initial states of the process.
            """
            asts = [[pr_ast, True]]
            initial_states = set()

            while len(asts) > 0:
                ast, initflag = asts.pop()

                # Unwind AST nodes with operators and atomic actions
                if ast['type'] == 'choice':
                    for action in ast['actions']:
                        asts.append([action, initflag])
                elif ast['type'] == 'concatenation':
                    for action in ast['actions']:
                        if initflag:
                            asts.append([action, initflag])
                            initflag = False
                        else:
                            asts.append([action, initflag])
                else:
                    # Generate State for atomic action
                    node = State(ast, self.__yield_id())

                    if ast['name'] not in process.actions:
                        raise KeyError("Process {!r} does not have action description {!r}".
                                       format(process.name, ast['name']))
                    node.action = process.actions[ast['name']]
                    if isinstance(process.actions[ast['name']], Receive):
                        node.action.replicative = node.desc['replicative']
                    if isinstance(process.actions[ast['name']], Dispatch):
                        node.action.broadcast = node.desc['broadcast']

                    # Save State in AST
                    self.states.add(node)
                    ast['node'] = node

                    if initflag:
                        initial_states.add(node)

            return initial_states

        # Generate nodes for subprocesses first
        for name in [name for name in process.actions.keys() if isinstance(process.actions[name], Subprocess)]:
            # Make copy of the original AST to allow making changes there for more convinient exploration
            ast = copy.copy(process.actions[name].process_ast)
            generate_nodes(process, ast)
            sp_asts[name] = ast

        # Copy main process AST to allow changes introducing
        p_ast = copy.copy(process.process_ast)

        # Generates states exploring the AST of the process itself
        generate_nodes(process, p_ast)
        asts.append([p_ast, None])

        def resolve_last(pr_ast):
            """
            Get the AST (tree or subtree) and tries to determine which actions from this AST are the latest. It unwinds
            choises and sequences until gets atomic action like Dispatch, Call, etc.

            :param pr_ast: AST dictionary.
            :return: Set of State objects.
            """
            if not pr_ast:
                return set()

            asts = [pr_ast]
            last = set()

            while len(asts) > 0:
                ast = asts.pop()

                if ast['type'] == 'choice':
                    for action in ast['actions']:
                        asts.append(action)
                elif ast['type'] == 'concatenation':
                    asts.append(ast['actions'][-1])
                else:
                    last.add(ast['node'])

            return last

        # Explore AST and determine order of action invocating. Exploration goes from the latest action to the first
        # one (ones). Order is set up by adding successors and predecessors to each State.
        while len(asts) > 0:
            ast, prev = asts.pop()

            # Unwind AST nodes
            if ast['type'] == 'choice':
                for action in ast['actions']:
                    asts.append([action, prev])
            elif ast['type'] == 'concatenation':
                for action in ast['actions']:
                    asts.append([action, prev])
                    prev = action
            else:
                if ast['type'] == 'subprocess':
                    pair = "{} {}".format(ast['name'], str(prev))
                    if pair not in sp_processed:
                        # Mark processed state
                        sp_processed.add(pair)
                        asts.append([sp_asts[ast['name']], ast])

                # Determine particular predecessors
                last = resolve_last(prev)
                if len(last) > 0 and prev['type'] != "subprocess":
                    # Filter out subprocesses if there are
                    last = [s for s in last if not isinstance(s.action, Subprocess)]

                for pre_state in last:
                    ast['node'].insert_predecessor(pre_state)

        return

    @property
    def initial_states(self):
        """
        Returns initial states of the process.

        :return: Sorted list with starting process State objects.
        """
        initial_states = sorted([s for s in self.states if len(s.predecessors) == 0], key=attrgetter('identifier'))
        if len(initial_states) == 0:
            raise ValueError('FSA generated for process {!r} and category {!r} has no entry strates'.
                             format(self.process.name, self.process.category))
        return initial_states

    def resolve_state(self, identifier):
        """
        Resolve and returns process State object by its identifier.
        :param identifier: Int identifier
        :return: State object.
        """
        for state in (s for s in self.states if s.identifier == identifier):
            return state

        raise KeyError("State '{}' does not exist in process '{}' of category '{}'".
                       format(identifier, self.process.name, self.process.category))

    def clone_state(self, node):
        """
        Copy given State object, assign new identifier and place it as an alternative action with the same successors
        and predecessors in FSA.
        :param node: State object to copy
        :return: New State object
        """

        new_desc = copy.copy(node.desc)
        new_id = self.__yield_id()

        new_state = State(new_desc, new_id)
        new_state.action = node.action

        for pred in node.predecessors:
            new_state.insert_predecessor(pred)

        for succ in node.successors:
            new_state.insert_successor(succ)

        self.states.add(new_state)

        return new_state

    def add_new_predecessor(self, node, action):
        """
        Add new predecessor State creating it from the action object (Condition, Dispatch, etc.)
        
        :param node: State object to which new predecessor should be attached.
        :param action: action object (Condition, Dispatch, etc.).
        :return: New State object.
        """
        new = self.new_state(action)

        for pred in node.predecessors:
            pred.replace_successor(node, new)

        node.insert_predecessor(new)
        return new

    def add_new_successor(self, node, action):
        """
        Add new successor State creating it from the action object (Condition, Dispatch, etc.)
        
        :param node: State object to which new successor should be attached.
        :param action: action object (Condition, Dispatch, etc.).
        :return: New State object.
        """
        new = self.new_state(action)

        for succ in node.successors:
            succ.replace_predecessor(node, new)

        node.insert_successor(new)
        return new

    def new_state(self, action):
        """
        Generates new State object for given action. Action can be None to create artificial states in FSA.

        :param action: None or process action (Condition, Dispatch, etc.) object.
        :return: New State object.
        """
        if action:
            desc = {
                'label': '<{}>'.format(action.name)
            }
        else:
            desc = {
                'label': 'Artificial state'
            }
        new = State(desc, self.__yield_id())
        new.action = action
        self.states.add(new)
        return new

    def __yield_id(self):
        self.__id_cnt += 1
        return self.__id_cnt


class State:
    """Represent action node in FSA generated by process AST."""

    def __init__(self, desc, identifier):
        self.identifier = identifier
        self.desc = desc
        self._predecessors = set()
        self._successors = set()
        self.action = None
        self.code = None

    @property
    def successors(self):
        """
        Returns deterministically list with all next states.

        :return: List with State objects.
        """
        return sorted(self._successors, key=attrgetter('identifier'))

    @property
    def predecessors(self):
        """
        Returns deterministically list with all previous states.

        :return: List with State objects.
        """
        return sorted(self._predecessors, key=attrgetter('identifier'))

    def insert_successor(self, new):
        """
        Link given State object to be a successor of this state.

        :param new: New next State object.
        :return: None
        """
        self.add_successor(new)
        new.add_predecessor(self)

    def insert_predecessor(self, new):
        """
        Link given State object to be a predecessor of this state.

        :param new: New previous State object.
        :return: None
        """
        self.add_predecessor(new)
        new.add_successor(self)

    def replace_successor(self, old, new):
        """
        Replace given successor State object with a new State object.

        :param old: Old next State object.
        :param new: New next State object.
        :return: None
        """
        self.remove_successor(old)
        old.remove_predecessor(self)
        self.add_successor(new)
        new.add_predecessor(self)

    def replace_predecessor(self, old, new):
        """
        Replace given predecessor State object with a new State object.

        :param old: Old predecessor State object.
        :param new: New predecessor State object.
        :return: None
        """
        self.remove_predecessor(old)
        old.remove_successor(self)
        self.add_predecessor(new)
        new.add_successor(self)

    def add_successor(self, new):
        """
        Link given State object to be a successor.

        :param new: New next State object.
        :return: None
        """
        self._successors.add(new)

    def add_predecessor(self, new):
        """
        Link given State object to be a predecessor.

        :param new: New previous State object.
        :return: None
        """
        self._predecessors.add(new)

    def remove_successor(self, old):
        """
        Unlink given State object and remove it from successors.

        :param old: State object.
        :return: None
        """
        if old in self._successors:
            self._successors.remove(old)

    def remove_predecessor(self, old):
        """
        Unlink given State object and remove it from predecessors.

        :param old: State object.
        :return: None
        """
        if old in self._predecessors:
            self._predecessors.remove(old)


class Automaton:
    """
    This is a more abstract representation of FSA. It contins both FSA object generated for the process object and
    process object itself. It also contains variables generated for labels of the process and simplifies work with
    them.
    """

    def __init__(self, process, identifier):
        # Set default values
        self.__label_variables = {}
        self.__file = None

        # Set given values
        self.process = process
        self.identifier = identifier
        self.self_parallelism = True

        # Generate FSA itself
        self.fsa = FSA(self.process)
        self.variables()

    def variables(self, only_used=False):
        """
        Generate a variable for each process label or just return an already generated list of variables.

        :return: List with Variable objects.
        """
        variables = []

        # Generate variable for each label
        for label in [self.process.labels[name] for name in self.process.labels.keys()]:
            var = self.determine_variable(label, shadow_use=True)
            if var:
                variables.append(self.determine_variable(label, shadow_use=True))

        if only_used:
            variables = [v for v in variables if v.use > 0]
        return variables

    def determine_variable(self, label, shadow_use=False):
        """
        Get Label object and generate a variable for it or just return an existing Variable object. Also increase a
        counter of the variable usages.

        :param label: Label object.
        :param shadow_use: Do not increase the counter of usages of the variable if True.
        :return: Variable object which corresponds to the label.
        """
        if label.name in self.__label_variables and "default" in self.__label_variables[label.name]:
            if not shadow_use:
                self.__label_variables[label.name]["default"].use += 1
            return self.__label_variables[label.name]["default"]
        else:
            if label.declaration:
                var = Variable("ldv_{}_{}".format(self.identifier, label.name), label.declaration)
                if label.value:
                    var.value = label.value

                if label.name not in self.__label_variables:
                    self.__label_variables[label.name] = {}
                self.__label_variables[label.name]["default"] = var
                if not shadow_use:
                    self.__label_variables[label.name]["default"].use += 1
                return self.__label_variables[label.name]["default"]
            else:
                return None
