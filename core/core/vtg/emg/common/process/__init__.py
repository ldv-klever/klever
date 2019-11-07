#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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
import graphviz
import collections


class Access:
    """
    Class to represent expressions based on labels from process descriptions.

    For instance: %mylabel%.
    """

    def __init__(self, expression):
        self.expression = expression
        self.label = None
        self.list_access = None

    def __str__(self):
        return self.expression


class Label:
    """
    The class represent Label from process descriptions.

    A label is a C variable without a strictly given scope. It can be local, global depending on translation of the
    environment model to C code. Process state consists of labels and from current action.
    """
    def __init__(self, name: str):
        self.value = None
        self.declaration = None
        self._name = name

    @property
    def name(self):
        return self._name

    def __str__(self):
        return self._name

    def __repr__(self):
        return '%{}%'.format(self._name)

    def __eq__(self, other):
        if self.declaration and other.declaration:
            return self.declaration == other.declaration
        else:
            return False

    def __hash__(self):
        return hash(self._name)


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
        self.cfiles = list()
        self.headers = list()
        self.labels = dict()
        self.actions = Actions()
        self.declarations = dict()
        self.definitions = dict()
        self._accesses = dict()

    def __str__(self):
        return '%s/%s' % (self._category, self._name)

    def __hash__(self):
        return hash(str(self))

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

        for action in (a for a in self.actions if isinstance(a, Action)):
            if isinstance(action, Receive) or isinstance(action, Dispatch):
                for param in action.parameters:
                    extract_labels(param)
            if isinstance(action, Block):
                for statement in action.statements:
                    extract_labels(statement)
            if action.condition:
                for statement in action.condition:
                    extract_labels(statement)

        return set(self.labels.values()).difference(used_labels)

    def accesses(self, accesses=None, exclude=None, no_labels=False):
        """
        Go through the process description or retrieve from the cache dictionary with possible label accesses.

        :param accesses: Add to the cache an existing dictionary with accesses (Dictionary: {'%blblb%': [Access objs]}).
        :param exclude: Exclude accesses from descriptions of actions of given types (List of Action class names).
        :param no_labels: Exclude accesses based on labels which are not referred anywhere (Bool).
        :return:
        """
        if not exclude:
            exclude = list()

        if not accesses:
            accss = dict()

            if len(self._accesses) == 0 or len(exclude) > 0 or no_labels:
                # Collect all accesses across process subprocesses
                for action in [self.actions[name] for name in self.actions.keys()]:
                    tp = type(action)
                    if tp not in exclude:
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
        # Find suitable peers
        for action in (a for a in self.actions
                       if isinstance(self.actions[a], Receive) or isinstance(self.actions[a], Dispatch)):
            if action in process.actions and \
                    (isinstance(process.actions[action], Receive) or isinstance(process.actions[action], Dispatch)) and\
                    not isinstance(process.actions[action], type(self.actions[action])) and \
                    len(process.actions[action].parameters) == len(self.actions[action].parameters) and \
                    self._name not in (p['process'] for p in process.actions[action].peers):
                # Compare signatures of parameters
                for num, p in enumerate(self.actions[action].parameters):
                    access1 = self.resolve_access(p)
                    access2 = process.resolve_access(process.actions[action].parameters[num])
                    if not access1 or not access2 or not access1.label or not access2.label:
                        raise RuntimeError("Strange accesses {!r} and {!r} in {!r} and {!r}".
                                           format(p, process.actions[action].parameters[num], process.pretty_id,
                                                  process.pretty_id))
                    if not access1.label.declaration.compare(access2.label.declaration):
                        break
                else:
                    # All parameters match each other
                    self.actions[action].peers.append({'process': process, 'subprocess': process.actions[action]})
                    process.actions[action].peers.append({'process': self, 'subprocess': self.actions[action]})

    def resolve_access(self, access):
        """
        Get a string access and return a matching list of Access objects.

        :param access: String access like "%mylabel%".
        :return: List with Access objects.
        """
        if isinstance(access, Label):
            string = '%{}%'.format(access._name)
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
            self.declarations[file] = dict()

        if name not in self.declarations:
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
            self.definitions[file] = dict()

        if name not in self.definitions:
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

    def add_choice(self, name, actions):
        new = Choice(name)
        self.actions[new] = new

        for action in actions:
            new.add_first(action)

        return new

    def add_concatenation(self, name, actions):
        new = Concatenation(name)
        self.actions[new] = new

        for action in actions:
            new.add_first(action)

        return new

    def add_parenthenses(self, name, action):
        new = Parentheses(name, action)
        self.actions[new] = new
        return new


class Actions(collections.UserDict):

    def __setitem__(self, key, value):
        if isinstance(key, BaseAction):
            key = str(key)
        elif isinstance(key, str):
            pass
        else:
            raise KeyError('Do not provide any other type than string or {}'.format(BaseAction.__name__))

        if not isinstance(value, BaseAction):
            raise ValueError('Accept only actions as values but got {}'.format(type(value).__name__))

        self.data[key] = value

    def __getitem__(self, item):
        if isinstance(item, BaseAction):
            return self.data[str(item)]
        else:
            return self.data[item]

    def filter(self, include=None, exclude=None):
        if not include:
            include = ()
        if not exclude:
            exclude = ()

        return (x for x in self.data.values() if (not include or any(isinstance(x, t) for t in include)) and
                (not exclude or all(not isinstance(x, t) for t in exclude)))

    @property
    def initial_action(self):
        """
        Returns initial states of the process.

        :return: Sorted list with starting process State objects.
        """
        acts = [s for s in self.data.values() if not s.predecessors]
        assert len(acts) == 1
        act, *_ = acts
        return act

    @property
    def unmatched_receives(self):
        """
        Returns Receive actions that do not have peers.

        :return: A list of Action objects.
        """
        return (act for act in self.filter(include={Receive}) if not act.peers)

    @property
    def unmatched_dispatches(self):
        """
        Returns Dispatch actions that do not have peers.

        :return: A list of Action objects.
        """
        return (act for act in self.filter(include={Dispatch}) if not act.peers)


class BaseAction:
    """
        Base class for actions which can be executed in terms of a Process. Each action of a process is executed strictly
        one after another. All they are executed in the same context (depending on chosen translator).
        """

    def __init__(self, name: str):
        self.name = name
        self._predecessors = set()
        self._successors = set()

    def __str__(self):
        return self.name

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return self.name == other.name

    @property
    def successors(self):
        """
        Returns deterministically list with all next states.

        :return: List with State objects.
        """
        return tuple(self._successors)

    @property
    def predecessors(self):
        """
        Returns deterministically list with all previous states.

        :return: List with State objects.
        """
        return tuple(self._predecessors)

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


class Action(BaseAction):
    """
    Base class for actions which can be executed in terms of a Process. Each action of a process is executed strictly
    one after another. All they are executed in the same context (depending on chosen translator).
    """

    def __init__(self, name, number=1):
        super(Action, self).__init__(name)
        self.number = number
        self.condition = None
        self.trace_relevant = False
        self.comment = ''


class Subprocess(Action):
    """
    An action to direct the control flow. It implies execution of given sequence of actions instead of the current one.
    In contrast to C functions there is no any return or exit from the current process sequence given in the action.
    If the sequence is finite then the process just will stop execution of actions. It means that it is useless to
    place any actions after this one.

    An example of action string: "{mynewsequence}".
    """

    def __init__(self, name, number=1):
        super(Subprocess, self).__init__(name, number)
        self.process = None
        self.fsa = None

    def __repr__(self):
        return '{%s}' % str(self)


class Dispatch(Action):
    """
    An action that implies to send a signal to an another environmental process. It allows to save values from labels
    of the dispatcher in labels of the receiver via parameters. If there is no peer receivers then the signal will not
    be sent. If there is no receiver at the moment the semantics of sending would be sleeping. If it is possible to send
    a signal or do an another action then it still can be executed.

    An example of action string: "[mysend]".
    """

    def __init__(self, name, number=1, broadcast=False):
        super(Dispatch, self).__init__(name, number)
        self.broadcast = broadcast
        self.parameters = []
        self.peers = []

    def __repr__(self):
        return '[%s%s]' % ('@' if self.broadcast else '', str(self))


class Receive(Action):
    """
    Class to represent receiver actions. Semantics of receiving is instant. If there is no sender at the moment then
    the action is skipped. If there is no sender at the moment then the process will sleep or do an another possible
    action.

    An example of action string: "(mysend)".
    """

    def __init__(self, name, number=1, repliative=False):
        super(Receive, self).__init__(name, number)
        self.replicative = repliative
        self.parameters = []
        self.peers = []

    def __repr__(self):
        return '(%s%s)' % ('!' if self.replicative else '', str(self))


class Block(Action):
    """
    Class represents a C code base block with some code. You also can add a condition. In contrast to other actions
    if a condition is not satisfied and the action is the one possible action in a choose operator (|) then this
    conditional branch will not be chosen. Note then in other actions the whole action is just skipped.

    An example of action string: "<mycondition>".
    """

    def __init__(self, name, number=1):
        super(Block, self).__init__(name, number)
        self.statements = []
        self.condition = []

    def __repr__(self):
        return '<%s>' % str(self)


class Parentheses(BaseAction):
    """
    This class represent an open parenthese symbol to simplify serialization and import.
    """

    def __init__(self, name, action: BaseAction = None):
        super(Parentheses, self).__init__(name)
        self.action = action
        self.insert_successor(action)


class Concatenation(BaseAction):
    """
    The class represents a sequence of actions.
    """

    def __init__(self, name):
        super(Concatenation, self).__init__(name)
        self.actions = collections.deque()

    def add_first(self, action: BaseAction):
        self.insert_successor(action)
        if self.actions:
            self.actions[0].replace_predecessor(self, action)
        self.actions.appendleft(action)


class Choice(BaseAction):
    """
    The class represents a choice between actions.
    """

    def __init__(self, name):
        super(Choice, self).__init__(name)
        self.actions = set()

    def add_first(self, action: BaseAction):
        action.insert_predecessor(self)
        self.actions.add(action)


class ProcessCollection:
    """
        This class represents collection of processes for an environment model generators. Also it contains methods to
        import or export processes in the JSON format. The collection contains function models processes, generic
        environment model processes that acts as soon as they receives replicative signals and a main process.

        """

    def __init__(self):
        self.entry = None
        self.models = dict()
        self.environment = dict()

    @property
    def processes(self):
        return list(self.models.values()) + list(self.environment.values()) + ([self.entry] if self.entry else [])

    def establish_peers(self, strict=False):
        """
        Get processes and guarantee that all peers are correctly set for both receivers and dispatchers. The function
        replaces dispatches expressed by strings to object references as it is expected in translation.

        :param strict: Raise exception if a peer process identifier is unknown (True) or just ignore it (False).
        :return: None
        """
        # Then check peers. This is because in generated processes there no peers set for manually written processes
        process_map = {str(p): p for p in self.processes}
        for process in self.processes:
            for action in [process.actions[a] for a in process.actions.filter(include={Receive, Dispatch})
                           if process.actions[a].peers]:
                new_peers = set()
                for peer in action.peers:
                    if isinstance(peer, str):
                        if peer in process_map:
                            target = process_map[peer]
                            new_peer = {'process': target, 'subprocess': target.actions[action.name]}
                            new_peers.add(new_peer)

                            opposite_peers = [str(p['process']) if isinstance(p, dict) else p
                                              for p in target.actions[action.name].peers]
                            if str(process) not in opposite_peers:
                                target.actions[action.name].peers.append({'process': process, 'subprocess': action})
                        elif strict:
                            raise KeyError("Process {!r} tries to send a signal {!r} to {!r} but there is no such "
                                           "process in the model".format(str(process), str(action), peer))
                    else:
                        new_peers.add(peer)

                action.peers = new_peers

    def save_digraphs(self, directory):
        """
        Method saves Automaton with code in doe format in debug purposes. This functionality can be turned on by setting
        corresponding configuration property. Each action is saved as a node and for each possible state transition
        an edge is added. This function can be called only if code blocks for each action of all automata are already
        generated.

        :parameter directory: Name of the directory to save graphs of processes.
        :return: None
        """
        def process_next(prevs, action):
            if isinstance(action, Action):
                for prev in prevs:
                    graph.edge(str(prev), str(action))
                return {action}
            if isinstance(action, Choice):
                new_prevs = set()
                for act in action.actions:
                    new_prevs.update(process_next(prevs, act))
                return new_prevs
            elif isinstance(action, Concatenation):
                for act in action.actions:
                    if isinstance(act, Action):
                        for prev in prevs:
                            graph.edge(str(prev), str(act))
                        prevs = {act}
                    else:
                        prevs = process_next(prevs, act)
                return prevs
            elif isinstance(action, Parentheses):
                process_next(prevs, action.action)
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

            for a in process.actions.filter(include={Action}, exclude={Subprocess}):
                graph.node(str(a), r'{}\l'.format(repr(a)))
            process_next(set(), process.actions.initial_action)

            # Save to dg_file
            graph.save(dg_file)
            graph.render()
