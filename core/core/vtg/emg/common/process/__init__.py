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
import copy
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

    def __copy__(self):
        inst = type(self)(self.name, self.category)

        # Set simple attributes
        for att, val in self.__dict__.items():
            if isinstance(val, list) or isinstance(val, dict) or isinstance(val, Actions):
                setattr(inst, att, copy.copy(val))
            else:
                setattr(inst, att, val)

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
        # todo: Do not like this method. Prefer seeing it as property
        if not exclude:
            exclude = list()

        if not accesses:
            accss = dict()

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
                    self.actions[action].peers.append({'process': process, 'action': process.actions[action]})
                    process.actions[action].peers.append({'process': self, 'action': self.actions[action]})

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

    def replace_action(self, old, new, purge=True):
        """
        Replace in actions graph the given action.

        :param old: BaseAction object.
        :param new: BaseAction object.
        :param purge: Delete an object from collection.
        :return: None
        """
        operator = old.my_operator
        if operator:
            if isinstance(operator, Parentheses):
                operator.action = None
                operator.action = new
            elif isinstance(operator, Choice):
                operator.remove_action(old)
                operator.add_action(new)
            elif isinstance(operator, Concatenation):
                index = operator.actions.index(old)
                operator.remove_action(old)
                operator.add_action(new, position=index)
            else:
                raise RuntimeError('unsupported operator')
        else:
            raise RuntimeError('Expect operator')

        if purge:
            del self.actions[str(old)]
            self.actions[str(new)] = new

    def insert_action(self, new, target, before=False):
        """
        Insert an existing action before or after the given target action.

        :param new: Action object.
        :param target: Action object.
        :param before: True if append left ot append to  the right end.
        """
        operator = target.my_operator
        if isinstance(operator, Concatenation):
            position = operator.actions.index(target)
            if before:
                operator.add_action(new, position=position)
            else:
                operator.add_action(new, position=position+1)
        elif isinstance(operator, Parentheses):
            conc = Concatenation(str(len(self.actions.keys()) + 1))
            operator.action = None
            if before:
                conc.actions = [new, target]
            else:
                conc.actions = [target, new]
            operator.action = conc
        elif isinstance(operator, Choice):
            operator.remove_action(target)
            if before:
                actions = [new, target]
            else:
                actions = [target, new]
            conc = Concatenation(str(len(self.actions.keys()) + 1))
            conc.actions = actions
            operator.add_action(conc)
        else:
            raise ValueError("Unknown operator {!r}".format(str(type(operator).__name__)))

    def insert_alternative_action(self, new, target):
        """
        Insert an existing action as an alternative choice for a given one.

        :param new: Action object.
        :param target: Action object.
        """
        operator = target.my_operator
        if isinstance(operator, Concatenation):
            index = operator.actions.index(target)
            operator.remove_action(target)
            choice = Choice(str(len(self.actions.keys()) + 1))
            choice.actions = {new, target}
            operator.add_action(choice, position=index)
        elif isinstance(operator, Parentheses):
            choice = Choice(str(len(self.actions.keys()) + 1))
            operator.action = None
            choice.actions = {target, new}
            operator.action = choice
        elif isinstance(operator, Choice):
            operator.add_action(new)
        else:
            raise ValueError("Unknown operator {!r}".format(str(type(operator).__name__)))


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

    def __copy__(self):
        new = Actions()

        # Copy items
        new.data = {n: copy.copy(v) for n, v in self.data.items()}

        # Explicitly clear operators (replacement forbidden by the API)
        # todo: Avoid using private methods. But now this is the simplest wat to clean values
        for action in new.data.values():
            action.my_operator = None
            if isinstance(action, Receive) or isinstance(action, Dispatch):
                # They contain references to other processes in peers
                action.parameters = copy.copy(action.parameters)
            elif isinstance(action, Parentheses) or isinstance(action, Subprocess):
                action._action = None
            elif isinstance(action, Concatenation):
                action._actions = collections.deque()
            elif isinstance(action, Choice):
                action._actions = set()

        # Set new references
        for action in self.data.values():
            if isinstance(action, Parentheses) or isinstance(action, Subprocess):
                new.data[action.name].action = new.data[action.action.name]
            elif isinstance(action, Concatenation):
                new.data[action.name].actions = [new.data[act.name] for i, act in enumerate(action.actions)]
            elif isinstance(action, Choice):
                new.data[action.name].actions = {new.data[act.name] for act in action.actions}

        return new

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
        acts = {s for s in self.data.values() if not s.my_operator}
        acts.difference_update({s.action for s in self.filter(include={Subprocess}) if s.action})
        if len(acts) != 1:
            raise ValueError('Process %s contains more than one action'.format(str(self)))
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

    def __new__(cls, name: str, **kwards):
        # This is required to do deepcopy
        self = super().__new__(cls)
        self.name = name
        self._my_operator = None
        return self

    def __getnewargs__(self):
        # Return the arguments that *must* be passed to __new__ (required for deepcopy)
        return self.name,

    def __str__(self):
        return self.name

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return self.name == other.name

    @property
    def my_operator(self):
        return self._my_operator

    @my_operator.setter
    def my_operator(self, new):
        if (not self._my_operator and new) or (self._my_operator and not new):
            if not isinstance(new, Action):
                self._my_operator = new
            else:
                raise RuntimeError(
                    "Cannot set action {!r} as operator for {!r}".format(str(type(new).__name__), str(self)))
        elif self._my_operator and new:
            raise RuntimeError('Explicitly clean first operator field')


class Action(BaseAction):
    """
    Base class for actions which can be executed in terms of a Process. Each action of a process is executed strictly
    one after another. All they are executed in the same context (depending on chosen translator).
    """

    def __init__(self, name):
        super(Action, self).__init__()
        self.condition = []
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

    def __init__(self, name, reference_name=None):
        super(Subprocess, self).__init__(name)
        self.process = None
        self.reference_name = reference_name
        self._action = None
        self.fsa = None

    @property
    def action(self):
        return self._action

    @action.setter
    def action(self, new):
        if (not self._action and new) or (self._action and not new):
            if new:
                new.my_operator = None
            self._action = new
        else:
            raise RuntimeError('Explicitly clean first operator field')

    def __repr__(self):
        return '{%s}' % str(self.reference_name if self.reference_name else self.name)


class Dispatch(Action):
    """
    An action that implies to send a signal to an another environmental process. It allows to save values from labels
    of the dispatcher in labels of the receiver via parameters. If there is no peer receivers then the signal will not
    be sent. If there is no receiver at the moment the semantics of sending would be sleeping. If it is possible to send
    a signal or do an another action then it still can be executed.

    An example of action string: "[mysend]".
    """

    def __init__(self, name, broadcast=False):
        super(Dispatch, self).__init__(name)
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

    def __init__(self, name, repliative=False):
        super(Receive, self).__init__(name)
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

    def __init__(self, name):
        super(Block, self).__init__(name)
        self.statements = []
        self.condition = []

    def __repr__(self):
        return '<%s>' % str(self)


class Parentheses(BaseAction):
    """
    This class represent an open parenthese symbol to simplify serialization and import.
    """

    def __init__(self, name):
        super(Parentheses, self).__init__()
        self._action = None

    @property
    def action(self):
        return self._action

    @action.setter
    def action(self, new):
        if (not self._action and new) or (self._action and not new):
            if self._action:
                self._action.my_operator = None
            if new:
                new.my_operator = self
            self._action = new
        else:
            raise RuntimeError('Explicitly clean first operator field')

    def __repr__(self):
        return '{%s}' % str(self.reference_name if self.reference_name else self.name)


class Concatenation(BaseAction):
    """
    The class represents a sequence of actions.
    """

    def __init__(self, name):
        super(Concatenation, self).__init__()
        self._actions = collections.deque()

    @property
    def actions(self):
        return list(self._actions)

    @actions.setter
    def actions(self, actions):
        if self._actions and actions:
            raise RuntimeError('First clean actions before setting new ones')
        for item in list(self._actions):
            self.remove_action(item)
        if actions:
            for item in actions:
                self.add_action(item)
        else:
            self._actions = collections.deque()

    def add_action(self, action, position=None):
        if action in self._actions:
            raise RuntimeError('An action already present')
        action.my_operator = self
        if not isinstance(position, int):
            self._actions.append(action)
        else:
            self._actions.insert(position, action)

    def remove_action(self, action):
        if action in self._actions:
            self._actions.remove(action)
            action.my_operator = None
        else:
            raise ValueError('There is no such action')


class Choice(BaseAction):
    """
    The class represents a choice between actions.
    """

    def __init__(self, name):
        super(Choice, self).__init__()
        self._actions = set()

    @property
    def actions(self):
        return set(self._actions)

    @actions.setter
    def actions(self, actions):
        if self._actions and actions:
            raise RuntimeError('First clean actions before setting new ones')
        for item in list(self._actions):
            self.remove_action(item)
        if actions:
            for item in actions:
                self.add_action(item)
        else:
            self._actions = collections.deque()

    def add_action(self, action):
        if action in self._actions:
            raise RuntimeError('An action already present')
        action.my_operator = self
        self._actions.add(action)

    def remove_action(self, action):
        if action in self._actions:
            self._actions.remove(action)
            action.my_operator = None
        else:
            raise ValueError('There is no such action')


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

    @property
    def process_map(self):
        return {str(p): p for p in self.processes}

    def establish_peers(self, strict=False):
        """
        Get processes and guarantee that all peers are correctly set for both receivers and dispatchers. The function
        replaces dispatches expressed by strings to object references as it is expected in translation.

        :param strict: Raise exception if a peer process identifier is unknown (True) or just ignore it (False).
        :return: None
        """
        # Then check peers. This is because in generated processes there no peers set for manually written processes
        for process in self.processes:
            self.__establist_peers_of_process(process, strict)

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

    def __establist_peers_of_process(self, process, strict=False):
        # Then check peers. This is because in generated processes there no peers set for manually written processes
        process_map = self.process_map
        for action in [process.actions[a] for a in process.actions.filter(include={Receive, Dispatch})
                       if process.actions[a].peers]:
            new_peers = list()
            for peer in action.peers:
                if isinstance(peer, str):
                    if peer in process_map:
                        target = process_map[peer]
                        new_peer = {'process': target, 'action': target.actions[action.name]}
                        new_peers.append(new_peer)

                        opposite_peers = [str(p['process']) if isinstance(p, dict) else p
                                          for p in target.actions[action.name].peers]
                        if str(process) not in opposite_peers:
                            target.actions[action.name].peers.append({'process': process, 'action': action})
                    elif strict:
                        raise KeyError("Process {!r} tries to send a signal {!r} to {!r} but there is no such "
                                       "process in the model".format(str(process), str(action), peer))
                else:
                    new_peers.append(peer)

            action.peers = new_peers
