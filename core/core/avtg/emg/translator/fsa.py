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
import graphviz
from operator import attrgetter

from core.avtg.emg.common.signature import Primitive, Pointer
from core.avtg.emg.common.process import Subprocess, Receive, Dispatch, Call, CallRetval, Condition
from core.avtg.emg.translator.code  import Variable, FunctionModels


class FSA:

    def __init__(self, process):
        self.process = process
        self.states = set()
        self._initial_states = set()
        self.__id_cnt = 0

        # Generate AST states
        sp_asts = dict()
        sp_processed = set()
        asts = list()

        # Generate states
        def generate_nodes(self, process, pr_ast):
            asts = [[pr_ast, True]]
            initial_states = set()

            while len(asts) > 0:
                ast, initflag = asts.pop()

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
                    node = State(ast, self.__yield_id())

                    if ast['name'] not in process.actions:
                        raise KeyError("Process '{}' does not have action description '{}'".
                                       format(process.name, ast['name']))
                    node.action = process.actions[ast['name']]
                    if type(process.actions[ast['name']]) is Receive:
                        node.action.replicative = node.desc['replicative']
                    if type(process.actions[ast['name']]) is Dispatch:
                        node.action.broadcast = node.desc['broadcast']

                    self.states.add(node)
                    ast['node'] = node

                    if initflag:
                        initial_states.add(node)

            return initial_states

        for name in [name for name in sorted(process.actions.keys()) if type(process.actions[name]) is Subprocess]:
            ast = copy.copy(process.actions[name].process_ast)
            generate_nodes(self, process, ast)
            sp_asts[name] = ast
        p_ast = copy.copy(process.process_ast)
        self._initial_states = generate_nodes(self, process, p_ast)
        asts.append([p_ast, None])

        def resolve_last(pr_ast):
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

        while len(asts) > 0:
            ast, prev = asts.pop()

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
                        sp_processed.add(pair)
                        asts.append([sp_asts[ast['name']], ast])

                last = resolve_last(prev)
                if len(last) > 0 and prev['type'] != "subprocess":
                    # Filter out subprocesses if there are
                    last = [s for s in last if type(s.action) is not Subprocess]

                for pre_state in last:
                    ast['node'].insert_predecessor(pre_state)

        # Normalize fsa to make life easier for code generators
        # Keep subprocess states as jumb points
        # Insert process and subprocess entry states
        for subprocess in (a for a in self.process.actions.values() if type(a) is Subprocess):
            new = self.__new_state(None)

            # Insert state
            jump_states = sorted([s for s in self.states if s.action and s.action.name == subprocess.name],
                                  key=attrgetter('identifier'))
            for jump in jump_states:
                for successor in jump.successors:
                    successor.replace_predecessor(jump, new)
                    jump.replace_successor(successor, new)

        # Add initial state if necessary
        if len(self._initial_states) > 1:
            new = self.__new_state(None)
            for initial in self._initial_states:
                initial.insert_predecessor(new)

            self._initial_states = set([new])

        return

    @property
    def initial_states(self):
        return sorted(self._initial_states, key=attrgetter('identifier'))

    def resolve_state(self, identifier):
        for state in (s for s in self.states if s.identifier == identifier):
            return state

        raise KeyError("State '{}' does not exist in process '{}' of category '{}'".
                       format(identifier, self.process.name, self.process.category))

    def clone_state(self, node):
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
        new = self.__new_state(action)

        for pred in node.predecessors:
            pred.replace_successor(node, new)

        node.insert_predecessor(new)
        return new

    def add_new_successor(self, node, action):
        new = self.__new_state(action)

        for succ in node.successors:
            succ.replace_predecessor(node, new)

        node.insert_successor(new)
        return new

    def __new_state(self, action):
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

    def __init__(self, desc, identifier):
        self.identifier = identifier
        self.desc = desc
        self._predecessors = set()
        self._successors = set()
        self.action = None
        self.code = None

    @property
    def successors(self):
        return sorted(self._successors, key=attrgetter('identifier'))

    @property
    def predecessors(self):
        return sorted(self._predecessors, key=attrgetter('identifier'))

    def insert_successor(self, new):
        self.add_successor(new)
        new.add_predecessor(self)

    def insert_predecessor(self, new):
        self.add_predecessor(new)
        new.add_successor(self)

    def replace_successor(self, old, new):
        self.remove_successor(old)
        old.remove_predecessor(self)
        self.add_successor(new)
        new.add_predecessor(self)

    def replace_predecessor(self, old, new):
        self.remove_predecessor(old)
        old.remove_successor(self)
        self.add_predecessor(new)
        new.add_successor(self)

    def add_successor(self, new):
        self._successors.add(new)

    def add_predecessor(self, new):
        self._predecessors.add(new)

    def remove_successor(self, old):
        if old in self._successors:
            self._successors.remove(old)

    def remove_predecessor(self, old):
        if old in self._predecessors:
            self._predecessors.remove(old)


class Automaton:

    def __init__(self, process, identifier):
        # Set default values
        self.__label_variables = {}
        self.__file = None

        # Set given values
        self.process = process
        self.identifier = identifier

        # Generate FSA itself
        self.fsa = FSA(self.process)
        self.variables()

    @property
    def file(self):
        if self.__file:
            return self.__file
        files = set()

        # Try to determine base values
        base_values = set()
        change = True
        while change:
            change = False

            for expr in self.process.allowed_implementations:
                for impl in (impl for impl in self.process.allowed_implementations[expr].values() if impl):
                    if impl.base_value and impl.base_value not in base_values:
                        base_values.add(impl.base_value)
                        change = True
                    elif not impl.base_value and impl.value not in base_values:
                        base_values.add(impl.value)
                        change = True

                    if impl.value in base_values and impl.file not in files:
                        files.add(impl.file)
                        change = True

        # If no base values then try to find callback call files
        files.update(set([s.code['file'] for s in self.fsa.states if s.code and 'file' in s.code]))

        if len(files) > 0:
            chosen_one = sorted(list(files))[0]
            self.__file = chosen_one
        else:
            self.__file = None

        return self.__file

    def variables(self):
        variables = []

        # Generate variable for each label
        for label in [self.process.labels[name] for name in sorted(self.process.labels.keys())]:
            if label.interfaces:
                for interface in label.interfaces:
                    variables.append(self.determine_variable(label, interface))
            else:
                var = self.determine_variable(label)
                if var:
                    variables.append(self.determine_variable(label))

        return variables

    def new_param(self, name, declaration, value):
        lb = self.process.add_label(name, declaration, value)
        lb.resource = True
        vb = self.determine_variable(lb)
        return lb, vb

    def determine_variable(self, label, interface=None):
        if not interface:
            if label.name in self.__label_variables and "default" in self.__label_variables[label.name]:
                return self.__label_variables[label.name]["default"]
            else:
                if label.prior_signature:
                    var = Variable("ldv_{}_{}_{}".format(self.identifier, label.name, "default"), None,
                                   label.prior_signature, export=True)
                    if label.value:
                        var.value = label.value
                    if label.file:
                        var.file = label.file

                    if label.name not in self.__label_variables:
                        self.__label_variables[label.name] = {}
                    self.__label_variables[label.name]["default"] = var
                    return self.__label_variables[label.name]["default"]
                else:
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
                    implementation = self.process.get_implementation(access)
                    var = Variable("ldv_{}_{}_{}".format(self.identifier, label.name, short_id), None,
                                   label.get_declaration(interface), export=True)

                    if implementation:
                        var.value = implementation.adjusted_value(var.declaration)

                        # Change file according to the value
                        var.file = implementation.file

                    if label.name not in self.__label_variables:
                        self.__label_variables[label.name] = {}
                    self.__label_variables[label.name][interface] = var
                    return self.__label_variables[label.name][interface]


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
