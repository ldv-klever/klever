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
import string
import graphviz
import collections
import sortedcontainers

from klever.core.vtg.emg.common.process.labels import Label, Access
from klever.core.vtg.emg.common.process.actions import Actions, Subprocess, Action, Dispatch, Receive, Block, Operator,\
    Signal, Behaviour, Parentheses, Choice, Concatenation, Requirements, WeakRequirements


"""Represent a signal peer."""
Peer = collections.namedtuple('Peer', 'process action')


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
        """
        Copy the instance and return a new one. The copy method is recursive, to get a shallow copy use the copy.copy
        method.

        :return: Process.
        """
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
        inst.labels = {lbl.name: copy.copy(lbl) for lbl in self.labels.values()}

        # Recalculate accesses
        inst.accesses(refresh=True)

        return inst

    @property
    def name(self):
        """
        The name attribute is used at pretty printing mostly. To distinguish processes use the string representation
        that also include a category.

        :return: Str.
        """
        return self._name

    @property
    def category(self):
        """
        It is forbidden to change the category. Category unifies processes that work with the same interfaces.

        :return: Str.
        """
        return self._category

    @property
    def savepoints(self):
        """
        Quickly get all process savepoints.
        :return: Set with savepoints.
        """
        return {s for a in self.actions.values() for s in a.savepoints}

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
            if action.savepoints:
                for savepoint in action.savepoints:
                    if savepoint.statements:
                        for statement in savepoint.statements:
                            extract_labels(statement)

        return sorted(set(self.labels.values()).difference(used_labels))

    def accesses(self, accesses=None, exclude=None, no_labels=False, refresh=False):
        """
        Go through the process description or retrieve from the cache dictionary with possible label accesses.

        :param accesses: Add to the cache an existing dictionary with accesses (Dictionary: {'%blblb%': [Access objs]}).
        :param exclude: Exclude accesses from descriptions of actions of given types (List of Action class names).
        :param no_labels: Exclude accesses based on labels which are not referred anywhere (Bool).
        :param refresh: enforce recalculation of accesses (Bool).
        :return:
        """
        # todo: Do not like this method. Prefer seeing it as property
        if not exclude:
            exclude = list()

        if not accesses:
            accss = sortedcontainers.SortedDict()

            if refresh or (len(self._accesses) == 0 or len(exclude) > 0 or no_labels):
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
                    for label in self.labels.values():
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
        Peer these two processes if they can send signals to each other. As a result the process attribute 'peers'
        gets a new key with the name of the peer process and a set of peered actions. Each call of the method cleans
        previous values that are relevant to the given process.

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
                    assert access1, f"No access '{p}' in process '{str(self)}'"
                    assert access1.label, f"Access '{p}' of process '{str(self)}' does not connected to any label"
                    access2 = process.resolve_access(process.actions[action].parameters[num])
                    assert access2, f"No access '{process.actions[action].parameters[num]}' in process '{str(process)}'"
                    assert access2.label, f"Access '{process.actions[action].parameters[num]}' of process" \
                                          f" '{str(process)}' does not connected to any label"

                    if access1.label.declaration != access2.label.declaration:
                        break
                else:
                    # All parameters match each other
                    for p1, p2 in ((self, process), (process, self)):
                        p1.peers.setdefault(str(p2), set())
                        p1.peers[str(p2)].add(str(action))

    @property
    def incoming_peers(self):
        """Get only peers that can activate the process."""
        registrations = {a for a in self.actions.filter(include={Receive}) if a.replicative}
        return {peer: registrations.intersection(signals) for peer, signals in self.peers.items()
                if registrations.intersection(signals)}

    def resolve_access(self, access):
        """
        Get a string access and return a matching list of Access objects.

        :param access: String access like "%mylabel%".
        :return: List with Access objects.
        """
        if isinstance(access, Label):
            name = repr(access)
        elif isinstance(access, str):
            name = access
        else:
            raise TypeError('Unsupported access token')
        return self._accesses[name]

    def add_declaration(self, file, name, declaration):
        """
        Add a C declaration which should be added to the environment model as a global variable alongside with the code
        generated for this process.

        :param file: File to add ("environment model" if it is not a particular program file).
        :param name: Variable or function name to add.
        :param declaration: String with the declaration.
        :return: None.
        """
        if file not in self.declarations:
            self.declarations[file] = sortedcontainers.SortedDict()

        if name not in self.declarations[file]:
            self.declarations[file][name] = declaration

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
        label = Label(name)
        label.declaration = declaration
        if value:
            label.value = value
        self.labels[name] = label
        acc = Access('%{}%'.format(name))
        acc.label = label
        acc.list_access = [label._name]
        self._accesses[acc.expression] = acc
        return label

    @property
    def peers_as_requirements(self):
        """
        Represent peers as a Requirements object.

        :return: Requirements object
        """
        new = WeakRequirements()
        for peer, signal_actions in self.incoming_peers.items():
            new.add_requirement(peer)
            new.add_actions_requirement(peer, sorted(list(signal_actions)))
        return new

    @property
    def requirements(self):
        """
        Collect and yield all requirements of the process.

        :return: An iterator over requirements.
        """
        for action in self.actions.values():
            if action.requirements and not action.requirements.is_empty:
                yield action.requirements
            if action.weak_requirements and not action.weak_requirements.is_empty:
                yield action.weak_requirements
        yield self.peers_as_requirements

    def relevant_requirements(self, name):
        """
        Return a set of Requirement object which ask to add the process with a given name.

        :param name: Process name.
        :return: Set of Requirements objects
        """
        assert isinstance(name, str)

        return {r for r in self.requirements if name in r.required_processes}

    def compatible_with_model(self, model, restrict_to=None):
        """
        Check that the model contains all necessary for this process. Do not check that the process has all necessary
        for the model.

        :param model: ProcessCollection.
        :param restrict_to: None or set of Process names.
        :return: Bool
        """
        assert isinstance(model, ProcessCollection)
        assert restrict_to is None or isinstance(restrict_to, set)

        for requirement in self.requirements:
            if not requirement.compatible_with_model(model, restrict_to):
                return False
        return True


class ProcessDescriptor:
    """The descriptor forbids to set non-Process values."""

    EXPECTED_CATEGORY = 'entry_point'

    def __set__(self, obj, value):
        assert isinstance(value, Process) or value is None, f"Got '{type(value).__name__}' instead of a process"
        if value:
            # Warning: this is because there is no setter in the class and this is normal
            value._category = self.EXPECTED_CATEGORY
        obj._entry = value

    def __get__(self, obj, objtype):
        return obj._entry


class ProcessDict(sortedcontainers.SortedDict):
    """The collection implements a dictionary with Processes (str -> Process)."""

    def __setitem__(self, key, value):
        assert isinstance(value, Process), f"Expect a Process as a value bug got '{type(value).__name__}'"

        if value.category and value.category == 'functions models':
            assert key == value.name, f"Function models should be assigned by its name ('{value.name}') but got '{key}'"
        else:
            assert key == str(value), f"Environment processes should be saved by its string representation" \
                                      f" ({str(value)}) but got '{key}'"
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

    def __init__(self, name='base'):
        self._entry = None
        self.models = ProcessDict()
        self.environment = ProcessDict()
        self.name = name
        self.attributes = dict()

    @property
    def attributed_name(self):
        """Generate name that can be used to create directories"""
        if self.attributes:
            name = ', '.join((f"{p}:{self.attributes[p]}" for p in sorted(self.attributes.keys())))
        else:
            name = str(self.name)

        remove_punctuation_map = dict((ord(char), '_') for char in string.punctuation)
        remove_punctuation_map[ord(' ')] = '_'
        return name.translate(remove_punctuation_map)

    @property
    def processes(self):
        """Returns a sorted list of all processes from the model."""
        return sorted(list(self.models.values())) + sorted(list(self.environment.values())) + \
               ([self.entry] if self.entry else [])

    @property
    def defined_processes(self):
        return self.processes

    @property
    def process_map(self):
        """Returns a dict with all processes from the model."""
        return {str(p): p for p in self.processes}

    def find_process(self, identifier: str):
        """
        Get an identifier and search the process in models, environment and entry attributes.

        :param identifier: String representation of the process.
        :return: Process.
        """
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

    def peers(self, process: Process, signals=None, processes=None):
        """
        Collect peers of the given process and return a list of Peer objects. The last two arguments helps to filter
        the result.

        :param process: Process.
        :param signals: Iterable of names of possible signals.
        :param processes: Iterable of possible processes names.
        :return: list of Peer objects.
        """
        assert isinstance(process, Process), f"Got '{type(process).__name__}'"
        if signals:
            for signal in signals:
                assert isinstance(signal, str), \
                    f"Signal '{str(signal)}' has type '{type(process).__name__}' instead of str"
        if processes:
            for name in processes:
                assert isinstance(name, str), f"Process name '{str(name)}' has type '{type(process).__name__}'"

        peers = []
        for agent_name in (n for n in process.peers if processes is None or n in processes):
            agent = self.find_process(agent_name)

            for action_name in (n for n in process.peers[agent_name] if signals is None or n in signals):
                peers.append(Peer(agent, agent.actions[action_name]))

        return peers

    def remove_unused_processes(self):
        # We need more iterations to detect all processes that can be deleted
        iterate = True
        deleted = set()
        while iterate:
            iterate = False
            for key, process in self.environment.items():
                receives = set(map(str, (a for a in process.actions.filter(include={Receive}) if a.replicative)))
                all_peers = {a for acts in process.peers.values() for a in acts}

                if not receives.intersection(all_peers) or \
                        not process.compatible_with_model(self):
                    self.copy_declarations_to_init(self.environment[key])
                    self.remove_process(key)
                    deleted.add(key)
                    iterate = True

            if iterate:
                self.establish_peers()

        return deleted

    def extend_model_name(self, process_name, attribute):
        assert isinstance(process_name, str)
        assert isinstance(attribute, str) or attribute is None
        self.attributes[process_name] = attribute

    def remove_process(self, process_name):
        assert process_name and process_name in self.environment
        del self.environment[process_name]
        self.extend_model_name(process_name, 'Removed')

    def copy_declarations_to_init(self, process: Process):
        """Copy declarations and definitions from a given process to the entry one."""
        assert process
        for attr in ('declarations', 'definitions'):
            for file in getattr(process, attr):
                getattr(self.entry, attr).setdefault(file, dict())
                getattr(self.entry, attr)[file].update(getattr(process, attr)[file])

    def establish_peers(self):
        """
        Get processes and guarantee that all peers are correctly set for both receivers and dispatchers. The function
        replaces dispatches expressed by strings to object references as it is expected in translation.

        :return: None
        """
        # Delete all previous peers to avoid keeping the old deleted processes
        for process in self.processes:
            process.peers.clear()

        # First check models
        for model in self.models.values():
            for process in list(self.environment.values()) + ([self.entry] if self.entry else []):
                model.establish_peers(process)

        processes = self.processes
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

        # Dump separately all automata
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

    @property
    def consistent(self):
        for process in self.processes:
            for requirement in process.requirements:
                if not requirement.compatible_with_model(self):
                    return False
        else:
            return True

    def requiring_processes(self, name, restrict_to=None):
        """
        Provide the set of process names for processes that require this one recursively.

        :param name: Process name.
        :param restrict_to: Processes that are considred as possible dependencies.
        :return: Set of Process names.
        """
        assert isinstance(name, str)
        assert restrict_to is None or isinstance(restrict_to, set)

        requiring = {name}
        continue_iteration = True
        while continue_iteration:
            continue_iteration = False

            # Collect processes that requires collected
            iterate_over = [p for p in self.processes
                            if (restrict_to is None or str(p) in restrict_to) and str(p) not in requiring]
            for process in iterate_over:
                for requirement in process.requirements:
                    if requirement.required_processes.intersection(requiring):
                        requiring.add(str(process))
                        continue_iteration = True
                        break

        requiring.remove(name)
        return requiring

    def broken_processes(self, name, process_actions):
        """
        Check which processes would have unmet dependencies because of the process recursively.

        :param name: Process name.
        :param process_actions: Actions obj.
        :return: Set of Process names.
        """
        assert isinstance(name, str)
        assert isinstance(process_actions, Actions)

        # First collect processes that are incompatible with this one
        broken = set()
        for process in (p for p in self.processes if str(p) != name):
            for requirement in process.requirements:
                if not requirement.compatible(name, process_actions):
                    broken.add(str(process))
                    break

        # Then iteratively check other dependencies.
        for broken_process in sorted(broken):
            more_broken = self.requiring_processes(broken_process)
            broken.update(more_broken)

        return broken

    def rename_notion(self, previous: str, new: str):
        for process in self.processes:
            for requirement in process.requirements:
                requirement.rename_notion(previous, new)

    @property
    def dependency_order(self):
        """
        Try to get the order of environment processes with respect to their dependencies. First processes should depend
        on others that do not require preceding processes. Note, that it is not always strictly possible to obtain
        a good order. There can be independent connected processes in the model. Do not rely to much on it and it is
        better to get rid of using this function.

        :return:
        """
        dep_order = []
        todo = set(self.environment.keys())
        while todo:
            free = []
            for entry in sorted(todo):
                if not self._transitive_is_required(entry, set(todo)):
                    free.append(entry)
            for selected in free:
                dep_order.append(selected)
                todo.remove(selected)

        return dep_order

    def _transitive_is_required(self, process_name, restrict_to=None):
        """
        Check that given process is required by anybody in the given set of processes.

        :param process_name: Process name.
        :param restrict_to: Process iterable.
        :return: Bool
        """
        assert isinstance(process_name, str)
        assert restrict_to is None or isinstance(restrict_to, set)

        if restrict_to:
            processes = set(restrict_to).intersection(set(map(str, self.processes)))
        else:
            processes = set(map(str, self.processes))

        for process in (p for p in self.processes if str(p) in processes and str(p) != process_name):
            for requirement in process.requirements:
                if process_name in requirement.required_processes:
                    return True
        return False
