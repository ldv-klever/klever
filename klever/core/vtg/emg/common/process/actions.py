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

import copy
import collections


class Savepoint:

    def __init__(self, name, statements):
        self.name = name
        self.statements = statements

    def __str__(self):
        return str(self.name)

    def __hash__(self):
        return str(self)


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

    def __lt__(self, other):
        return str(self) < str(other)

    @property
    def my_operator(self):
        """Returns the operator that joins this actiosn with the others in the process."""
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
        self.savepoints = []
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
        self.trace_relevant = True
        self.parameters = []
        # todo: Add a new class (Namedtuple) to implement peers
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
        self.trace_relevant = False

    def __repr__(self):
        return '<%s>' % str(self)


class Operator(BaseAction):
    # todo: Use it in more places
    """
    The class represents an abstract operator with actions.
    """

    def __init__(self, name):
        super(Operator, self).__init__()
        self._actions = collections.deque()

    @property
    def actions(self):
        return copy.copy(self._actions)

    @property
    def filled(self):
        return True if self._actions else False

    def clean(self):
        for action in self.actions:
            self.remove_action(action)
        self.actions = collections.deque()

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
        self._actions.append(action)

    def remove_action(self, action):
        if action in self._actions:
            self._actions.remove(action)
            action.my_operator = None
        else:
            raise ValueError('There is no such action')


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


class Concatenation(Operator):
    """
    The class represents a sequence of actions.
    """

    def add_action(self, action, position=None):
        if action in self._actions:
            raise RuntimeError('An action already present')
        action.my_operator = self
        if not isinstance(position, int):
            self._actions.append(action)
        else:
            self._actions.insert(position, action)


class Choice(Operator):
    pass


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

    def __hash__(self):
        return '_'.join(map(str, sorted(self.keys())))

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
                action._actions = collections.deque()

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

        return sorted([x for x in self.data.values() if (not include or any(isinstance(x, t) for t in include)) and
                       (not exclude or all(not isinstance(x, t) for t in exclude))])

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
    def final_actions(self):
        return list(filter(lambda x: isinstance(x, Action) and not isinstance(x, Subprocess), self.data.values()))

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
