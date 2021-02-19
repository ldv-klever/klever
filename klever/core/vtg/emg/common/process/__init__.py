#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
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

import re
import copy
import graphviz
import collections
import sortedcontainers

from klever.core.vtg.emg.common.process.labels import Label, Access
from klever.core.vtg.emg.common.process.actions import Actions, Subprocess, Action, Dispatch, Receive, Block, Operator,\
    Signal, Behaviour, Parentheses, Choice, Concatenation


Peer = collections.namedtuple('Peer', 'process action')
# todo: write docs


class Process:
    """
    Represents a process.

    The process is a part of an environment. It can be a separate thread, a process or just a function which is
    executed within the same program context (Model of non-defined function). A process has a state which consists of
    labels and a process which specifies a sequence (potentially it can be infinite) of actions. An action can send or
    receive data across processes,  just contain a code to execute or represent an operator to direct control flow.
    """

    label_re = re.compile(r'%(\w+)((?:\.\w*)*)%')
    _name_re = re.compile(r'\w+')

    def __init__(self, name, category: str = None):
        if not self._name_re.fullmatch(name):
            raise ValueError("Process identifier {!r} should be just a simple name string".format(name))

        self._name = name
        self._category = category

        self.file = 'environment model'
        self.comment = None
        self.cfiles = sortedcontainers.SortedSet()
        self.headers = list()
        self.actions = Actions()
        self.peers = dict()
        self.labels = sortedcontainers.SortedDict()
        self.declarations = sortedcontainers.SortedDict()
        self.definitions = sortedcontainers.SortedDict()
        self._accesses = sortedcontainers.SortedDict()

    def __str__(self):
        return '%s/%s' % (self._category, self._name)

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, other):
        if isinstance(other, Process):
            return str(self) == str(other)
        else:
            return False

    def __lt__(self, other):
        if isinstance(other, Process):
            return str(self) < str(other)
        else:
            return False

    def clone(self):
        inst = copy.copy(self)

        # Set simple attributes
        for att, val in self.__dict__.items():
            if isinstance(val, list) or isinstance(val, dict):
                setattr(inst, att, copy.copy(val))
            else:
                setattr(inst, att, val)

        inst.actions = self.actions.clone()

        # Change declarations and definition keys
        for collection in (self.declarations, self.definitions):
            for item in collection:
                collection[item] = copy.copy(collection[item])

        # Copy labels
        inst.labels = {l.name: copy.copy(l) for l in self.labels.values()}
        return inst

    @property
    def name(self):
        return self._name

    @property
    def category(self):
        return self._category

    @property
    def unused_labels(self):
        """
        Returns a set of label names which are not referenced in the process description. They are candidates to be
        deleted.

        :return: A set of label names.
        """
        used_labels = set()

        def extract_labels(expr):
            for m in self.label_re.finditer(expr):
                used_labels.add(self.labels[m.group(1)])

        for action in (a for a in self.actions.values() if isinstance(a, Action)):
            if isinstance(action, Signal):
                for param in action.parameters:
                    extract_labels(param)
            if isinstance(action, Block):
                for statement in action.statements:
                    extract_labels(statement)
            if action.condition:
                for statement in action.condition:
                    extract_labels(statement)

        return sorted(set(self.labels.values()).difference(used_labels))

    def accesses(self, accesses=None, exclude=None, no_labels=False):
        """
        Go through the process description or retrieve from the cache dictionary with possible label accesses.

        :param accesses: Add to the cache an existing dictionary with accesses (Dictionary: {'%blblb%': [Access objs]}).
        :param exclude: Exclude accesses from descriptions of actions of given types (List of Action class names).
        :param no_labels: Exclude accesses based on labels which are not referred anywhere (Bool).
        :return:
        """
        # todo: Do not like this method. Prefer seeing it as property
        if not exclude:
            exclude = list()

        if not accesses:
            accss = sortedcontainers.SortedDict()

            if len(self._accesses) == 0 or len(exclude) > 0 or no_labels:
                # Collect all accesses across process subprocesses
                for action in self.actions.filter(include={Action}, exclude=exclude):
                    if isinstance(action, Receive) or isinstance(action, Dispatch):
                        for index in range(len(action.parameters)):
                            accss[action.parameters[index]] = None
                    if isinstance(action, Block):
                        for statement in action.statements:
                            for match in self.label_re.finditer(statement):
                                accss[match.group()] = None
                    if action.condition:
                        for statement in action.condition:
                            for match in self.label_re.finditer(statement):
                                accss[match.group()] = None

                # Add labels with interfaces
                if not no_labels:
                    for label in [self.labels[name] for name in self.labels.keys()]:
                        access = '%{}%'.format(label.name)
                        if not accss.get(access):
                            accss[access] = []
                            new = Access(access)
                            new.label = label
                            new.list_access = [label.name]
                            accss[access] = new

                if not self._accesses and len(exclude) == 0 and not no_labels:
                    self._accesses = accss
            else:
                accss = self._accesses

            return accss
        else:
            self._accesses = accesses

    def establish_peers(self, process):
        """
        Peer these two processes if they can send signals to each other.

        :param process: Process object
        :return: None
        """
        if str(self) in process.peers:
            del process.peers[str(self)]
        if str(process) in self.peers:
            del self.peers[str(process)]

        # Find suitable peers
        for action in self.actions.filter(include={Signal}):
            if action in process.actions and \
                    isinstance(process.actions[action], Signal) and\
                    not isinstance(process.actions[action], type(self.actions[action])) and \
                    len(process.actions[action].parameters) == len(self.actions[action].parameters) and \
                    str(action) not in self.peers.get(str(process), set()):

                # Compare signatures of parameters
                for num, p in enumerate(self.actions[action].parameters):
                    access1 = self.resolve_access(p)
                    access2 = process.resolve_access(process.actions[action].parameters[num])
                    if not access1 or not access2 or not access1.label or not access2.label:
                        raise RuntimeError("Strange accesses {!r} and {!r} in {!r}".
                                           format(p, process.actions[action].parameters[num], str(process)))
                    if access1.label.declaration != access2.label.declaration:
                        break
                else:
                    # All parameters match each other
                    for p1, p2 in ((self, process), (process, self)):
                        p1.peers.setdefault(str(p2), set())
                        p1.peers[str(p2)].add(str(action))

    def resolve_access(self, access):
        """
        Get a string access and return a matching list of Access objects.

        :param access: String access like "%mylabel%".
        :return: List with Access objects.
        """
        if isinstance(access, Label):
            string = repr(access)
        elif isinstance(access, str):
            string = access
        else:
            raise TypeError('Unsupported access token')
        return self._accesses[string]

    def add_declaration(self, file, name, string):
        """
        Add a C declaration which should be added to the environment model as a global variable alongside with the code
        generated for this process.

        :param file: File to add ("environment model" if it is not a particular program file).
        :param name: Variable or function name to add.
        :param string: String with the declaration.
        :return: None.
        """
        if file not in self.declarations:
            self.declarations[file] = sortedcontainers.SortedDict()

        if name not in self.declarations[file]:
            self.declarations[file][name] = string

    def add_definition(self, file, name, strings):
        """
        Add a C function definition which should be added to the environment model alongside with the code generated
        for this process.

        :param file: File to add ("environment model" if it is not a particular program file).
        :param name: Function name.
        :param strings: Strings with the definition.
        :return: None.
        """
        if file is None:
            raise ValueError("You have to give file name to add definition of function {!r}".format(name))

        if file not in self.definitions:
            self.definitions[file] = sortedcontainers.SortedDict()

        if name not in self.definitions[file]:
            self.definitions[file][name] = strings

    def add_label(self, name, declaration, value=None):
        """
        Add to the process a new label. Do not rewrite existing labels - it is a more complicated operation, since it
        would require updating of accesses in the cache and actions.

        :param name: Label name.
        :param declaration: Declaration object.
        :param value: Value string or None.
        :return: New Label object.
        """
        lb = Label(name)
        lb.declaration = declaration
        if value:
            lb.value = value
        self.labels[name] = lb
        acc = Access('%{}%'.format(name))
        acc.label = lb
        acc.list_access = [lb._name]
        self._accesses[acc.expression] = acc
        return lb

    def add_condition(self, name, condition, statements, comment):
        """
        Add new Condition action. Later you can add it to a particular place to execute using an another method.

        :param name: Action name.
        :param condition: List of conditional expresstions.
        :param statements: List with statements to execute.
        :param comment: A comment for the action (A short sentence).
        :return: A new Condition object.
        """
        new = Block(name)
        self.actions[name] = new

        new.condition = condition
        new.statements = statements
        new.comment = comment
        return new

    def replace_action(self, old, new, purge=True):
        """
        Replace in actions graph the given action.

        :param old: BaseAction object.
        :param new: BaseAction object.
        :param purge: Delete an object from collection.
        :return: None
        """
        assert isinstance(old, Action), f'Expect strictly an Action to replace but got {repr(old)}'
        assert isinstance(new, Action), f'Expect strictly an Action to replace with {repr(new)}'
        self.actions[str(new)] = new

        for entry in self.actions.behaviour(str(old)):
            new_entry = Behaviour(str(new), type(new))
            self.actions.add_process_action(new_entry, str(new))
            operator = entry.my_operator
            operator.replace(entry, new_entry)
            self.actions.remove_process_action(entry)

        if purge:
            del self.actions[str(old)]

    def insert_action(self, new, target, before=False):
        """
        Insert an existing action before or after the given target action.

        :param new: Action object.
        :param target: Action object.
        :param before: True if append left ot append to  the right end.
        """
        assert isinstance(new, Action), f'Got non-action object {str(new)}'
        assert isinstance(target, Action), f'Got non-action object {str(target)}'
        if str(new) not in self.actions:
            self.actions[str(new)] = new

        for entry in self.actions.behaviour(str(target)):
            new_entry = Behaviour(str(new), type(new))
            self.actions.add_process_action(new_entry, str(new))
            operator = entry.my_operator
            position = operator.index(entry)
            if not before:
                position += 1
            operator.insert(position, new_entry)


class ProcessDescriptor:

    EXPECTED_CATEGORY = 'entry point'

    def __set__(self, obj, value):
        assert isinstance(value, Process) or value is None, f'Got {type(value).__name__} instead of a process'
        if value:
            # Warning: this is becouse there is no setter in the class and this is normal
            value._category = self.EXPECTED_CATEGORY
        obj._entry = value

    def __get__(self, obj, objtype):
        return obj._entry


class ProcessDict(sortedcontainers.SortedDict):

    def __setitem__(self, key, value):
        assert isinstance(value, Process), f'Expect a Process as a value bug got {type(value).__name__}'
        if value.category and value.category == 'functions models':
            assert key == value.name, f'Function models should be assigned by its name ({value.name}) but got {key}'
        else:
            assert key == str(value), f'Environment processes should be saved by its string representation' \
                                      f' ({str(value)}) but got {key}'
        super().__setitem__(key, value)

    def __getitem__(self, item):
        if isinstance(item, Process):
            if item.category and item.category == 'functions models':
                item = item.name
            else:
                item = str(item)
        return super().__getitem__(item)


class ProcessCollection:
    """
    This class represents collection of processes for an environment model generators. Also it contains methods to
    import or export processes in the JSON format. The collection contains function models processes, generic
    environment model processes that acts as soon as they receives replicative signals and a main process.
    """

    entry = ProcessDescriptor()

    def __init__(self):
        self._entry = None
        self.models = ProcessDict()
        self.environment = ProcessDict()

    @property
    def processes(self):
        return sorted(list(self.models.values())) + sorted(list(self.environment.values())) + \
               ([self.entry] if self.entry else [])

    @property
    def process_map(self):
        return {str(p): p for p in self.processes}

    def find_process(self, identifier):
        if str(self.entry) == identifier:
            return self.entry
        elif identifier in self.models:
            return self.models[identifier]
        elif identifier.split('/')[-1] in self.models:
            return self.models[identifier.split('/')[-1]]
        elif identifier in self.environment:
            return self.environment[identifier]
        else:
            raise KeyError('Cannot find process {!r} \nwhere there are processes: {}\n and models: {}'.
                           format(identifier, ', '.join(self.models.keys()), ', '.join(self.environment.keys())))

    def peers(self, process, signals=None, processes=None):
        assert isinstance(process, Process), f'Got {type(process).__name__}'
        if signals:
            for signal in signals:
                assert isinstance(signal, str), f'Signal {str(signal)} has type {type(process).__name__} instead of str'
        if processes:
            for name in processes:
                assert isinstance(name, str), f'Process name {str(name)} has type {type(process).__name__}'

        peers = []
        for agent_name in (n for n in process.peers if processes is None or n in processes):
            agent = self.find_process(agent_name)

            for action_name in (n for n in process.peers[agent_name] if signals is None or n in signals):
                peers.append(Peer(agent, agent.actions[action_name]))

        return peers

    def establish_peers(self):
        """
        Get processes and guarantee that all peers are correctly set for both receivers and dispatchers. The function
        replaces dispatches expressed by strings to object references as it is expected in translation.

        :return: None
        """
        # Delete all previous peers to avoid keeping the old deleted processes
        for process in self.processes:
            process.peers.clear()

        # Fisrt check models
        for model in self.models.values():
            for process in list(self.environment.values()) + ([self.entry] if self.entry else []):
                model.establish_peers(process)

        processes = list(self.environment.values()) + ([self.entry] if self.entry else [])
        for i, process in enumerate(processes):
            for pair in processes[i+1:]:
                process.establish_peers(pair)

    def save_digraphs(self, directory):
        """
        Method saves Automaton with code in doe format in debug purposes. This functionality can be turned on by setting
        corresponding configuration property. Each action is saved as a node and for each possible state transition
        an edge is added. This function can be called only if code blocks for each action of all automata are already
        generated.

        :parameter directory: Name of the directory to save graphs of processes.
        :return: None
        """
        covered_subprocesses = set()

        def process_next(prevs, action):
            if isinstance(action, Behaviour):
                for prev in prevs:
                    graph.edge(str(hash(prev)), str(hash(action)))

                if action.kind is Subprocess:
                    if action.description.action not in covered_subprocesses:
                        graph.node(str(hash(action.description)), r'Begin subprocess {}\l'.format(repr(a)))
                        covered_subprocesses.add(action.description.action)
                        process_next({action.description}, action.description.action)
                    graph.edge(str(hash(action)), str(hash(action.description)))
                    return {}
                else:
                    return {action}
            elif isinstance(action, Parentheses):
                return process_next(prevs, action[0])
            elif isinstance(action, Choice):
                new_prevs = set()
                for act in action:
                    new_prevs.update(process_next(prevs, act))
                return new_prevs
            elif isinstance(action, Concatenation):
                for act in action:
                    prevs = process_next(prevs, act)
                return prevs
            else:
                raise NotImplementedError

        # Dump separetly all automata
        for process in self.processes:
            dg_file = "{}/{}.dot".format(directory, str(process))

            graph = graphviz.Digraph(
                name=str(process),
                format="png"
            )

            for a in process.actions.final_actions:
                graph.node(str(hash(a)), r'{}\l'.format(repr(a)))
            process_next(set(), process.actions.initial_action)

            # Save to dg_file
            graph.save(dg_file)
            graph.render()
