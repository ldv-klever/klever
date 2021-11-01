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
    """
    The class represents a savepoint - description of an initialization used if there is no receiver for a process.
    """

    def __init__(self, name, statements, comment=None):
        self._name = name
        self.comment = comment if comment else name.capitalize()
        self.statements = list(statements)
        self._required_actions = dict()
        self._required_processes = dict()

    def __str__(self):
        return str(self._name)

    def __hash__(self):
        return hash(str(self))

    def require_process(self, name, require_process=True, actions=None, append=True):
        self._required_processes[name] = require_process

        if require_process and actions:
            if append:
                self._required_actions.setdefault(name, list())
                self._required_actions[name].append(actions)
            else:
                self._required_actions[name] = [actions]

    def remove_requirement(self, name):
        assert name in self._required_processes
        del self._required_processes[name]

        if name in self._required_actions:
            del self._required_actions[name]

    @property
    def required_processes(self):
        return dict(self._required_processes)

    def required_actions(self, process):
        assert process in self._required_processes
        actions = self._required_actions.get(process, list())

        # It is important to return copies
        return [list(l) for l in actions]


class OperatorDescriptor:
    """
    The descriptor guards the work with operators. It is error prone to directly clean and set dependencies between
    actions and the descriptor helps to catch errors.
    """

    def __init__(self):
        self._my_operator = None

    def __set__(self, obj, value):
        assert value is not self, 'Prevent recursive operator dependency'
        assert isinstance(value, Operator) or value is None,\
            f"Cannot set as operator a non-operator object '{repr(value)}'"
        assert not value or not self._my_operator, \
            f"Has operator '{repr(self._my_operator)}' at '{repr(obj)}' before setting '{repr(value)}'"
        self._my_operator = value

    def __get__(self, obj, objtype):
        return self._my_operator


class BaseAction:
    """
    Base class for actions which can be executed in terms of a Process. Each action of a process is executed strictly
    one after another. All they are executed in the same context (depending on chosen translator).
    """

    my_operator = OperatorDescriptor()

    def __new__(cls, *args, **kwards):
        # This is required to do deepcopy
        self = super().__new__(cls)
        self.my_operator = None
        return self

    def __str__(self):
        return str(id(self))

    def __hash__(self):
        return hash(str(self))

    def clone(self):
        """
        Copy the object and return a copy with empty my_operator attribute.

        :return: BaseAction.
        """
        tmp = self.my_operator
        self.my_operator = None
        new = copy.copy(self)
        self.my_operator = tmp
        return new

    @property
    def my_operator(self):
        """Returns the operator that joins this action with the others in the process."""
        return self._my_operator

    @my_operator.setter
    def my_operator(self, new):
        assert new is not self, 'Prevent recursive operator dependency'
        assert isinstance(new, Operator) or new is None, f"Cannot set as operator a non-operator object '{repr(new)}'"
        assert not new or not self._my_operator,\
            f"Has operator '{repr(self._my_operator)}' at '{repr(self)}' before setting '{repr(new)}'"
        self._my_operator = new


class Behaviour(BaseAction):
    """
    Behaviour class helps to represent individual actions in a transition system. There can be several actions with
    the same name and all they should have a common description implemented by an Action class."""

    def __init__(self, name, accepted_class):
        assert accepted_class is not None and issubclass(accepted_class, Action)
        super().__init__()
        self._name = name
        self._description = None
        self.specific_attributes = []
        self._accepted_class = accepted_class

    def __repr__(self):
        """Print the representation of the action in process DSL."""
        if self.description:
            return repr(self.description)
        else:
            return repr(self._accepted_class(self.name))

    def clone(self):
        """
        Copy the instance. Remember, that the my_operator field is clean.

        :return: Behaviour.
        """
        new = super().clone()
        new._description = None
        return new

    @property
    def kind(self):
        """
        Return the class of the expected description even if it is not set yet.

        :return: Action.
        """
        return self._accepted_class

    @property
    def name(self):
        """Name of the description and this action. It is not a unique key!"""
        return self._name

    @property
    def description(self):
        """Description Action."""
        return self._description

    @description.setter
    def description(self, item):
        """Save a new description."""
        assert isinstance(item, self.kind), f"Got '{type(item).__name__}' instead of '{self.kind.__name__}'"
        assert str(item) == self.name

        for name, value in self.specific_attributes:
            setattr(item, name, value)
        self._description = item


class Operator(BaseAction, collections.UserList):
    """The class represents an abstract operator with actions. It is iterable and is based on a list implementation."""

    def __init__(self):
        super().__init__()
        self.data = []

    def __getitem__(self, position):
        return self.data[position]

    def __setitem__(self, position, value):
        assert isinstance(value, BaseAction), f"Only actions can be added but got '{type(value).__name__}'"
        assert value not in self.data, f"Attempt to add an existing object '{repr(value)}'"

        # First clean the existing action
        if self.data[position]:
            old = self.data[position]
            assert old.my_operator
            self.data[position] = None
            self._unpair(old)

        # Chain the actions
        self._pair(value)

        self.data[position] = value

    def __delitem__(self, position):
        old = self.data[position]
        assert old.my_operator
        del self.data[position]
        self._unpair(old)

    def __len__(self):
        return len(self.data)

    def insert(self, position, value):
        self._pair(value)
        self.data.insert(position, value)

    def remove(self, value):
        assert value in self.data, f"There is no '{repr(value)}' in '{repr(self)}'"
        index = self.data.index(value)
        del self[index]

    def replace(self, old, value):
        assert old in self.data, f"There is no '{repr(old)}' in '{repr(self)}'"
        index = self.data.index(old)
        self[index] = value

    def index(self, value, **kwargs):
        return self.data.index(value)

    def append(self, value):
        assert not value.my_operator

        self._pair(value)
        self.data.append(value)

    def clone(self):
        new = super().clone()
        new.data = []
        return new

    def _pair(self, action):
        assert not action.my_operator or action.my_operator is self
        if not action.my_operator:
            action.my_operator = self

    def _unpair(self, action):
        action.my_operator = None


class Parentheses(Operator):
    """
    This class represent an open parenthesis symbol to simplify serialization and import.
    """
    def __repr__(self):
        return '()' if not self.data else f'({repr(self.data[0])})'

    def __setitem__(self, position, value):
        assert position == 0 and len(self) > 0
        super().__setitem__(position, value)

    def __delitem__(self, position):
        assert position == 0 and len(self) > 0
        super().__delitem__(position)

    def insert(self, position, value):
        assert position == 0 and len(self) == 0
        super().insert(position, value)

    def append(self, value):
        assert len(self) == 0
        super().append(value)


class Concatenation(Operator):
    """
    The class represents a sequence of actions.
    """

    def __repr__(self):
        return '.'.join(map(repr, self.data))


class Choice(Operator):

    def __repr__(self):
        return '|'.join(map(repr, self.data))


class Action:
    """
    Base class for actions which can be executed in terms of a Process. Each action of a process is executed strictly
    one after another. All they are executed in the same context (depending on chosen translator).
    """

    def __init__(self, name):
        self.name = name
        self.condition = []
        self.trace_relevant = False
        self.savepoints = set()
        self.comment = ''
        self._require = dict()

    def __getnewargs__(self):
        # Return the arguments that *must* be passed to __new__ (required for deepcopy)
        return self.name,

    def __str__(self):
        return self.name

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return str(self) == str(other)

    def __lt__(self, other):
        return str(self) < str(other)

    @property
    def require(self):
        return copy.deepcopy(self._require)

    def add_required_process(self, process_name: str, actions: set):
        assert isinstance(process_name, str)
        assert isinstance(actions, set)
        for name in actions:
            assert isinstance(name, str)

        self._require.setdefault(process_name, dict())
        if actions:
            self._require[process_name].setdefault('include', set())
            self._require[process_name]['include'].update(set(actions))


class Subprocess(Action):
    """
    An action to direct the control flow. It implies execution of given sequence of actions instead of the current one.
    In contrast to C functions there is no any return or exit from the current process sequence given in the action.
    If the sequence is finite then the process just will stop execution of actions. It means that it is useless to
    place any actions after this one.

    An example of action string: "{mynewsequence}".
    """

    def __init__(self, name):
        super().__init__(name)
        self.action = None

    def __repr__(self):
        return '{%s}' % self.name

    @property
    def sequence(self):
        if self.action:
            return repr(self.action)
        else:
            return ''


class Signal(Action):
    """This is a common representation of signal actions: dispatches and receives."""

    def __init__(self, name):
        super().__init__(name)
        self.trace_relevant = True
        self.parameters = []


class Dispatch(Signal):
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

    def __repr__(self):
        return '[%s%s]' % ('@' if self.broadcast else '', str(self))


class Receive(Signal):
    """
    Class to represent receiver actions. Semantics of receiving is instant. If there is no sender at the moment then
    the action is skipped. If there is no sender at the moment then the process will sleep or do an another possible
    action.

    An example of action string: "(mysend)".
    """

    def __init__(self, name, replicative=False):
        super(Receive, self).__init__(name)
        self.replicative = replicative
        self.parameters = []

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


class Actions(collections.UserDict):

    def __init__(self):
        super(Actions, self).__init__()
        self._process_actions = dict()

    def __setitem__(self, key, value):
        assert isinstance(key, str) or isinstance(key, Action), f"Do not expect '{type(key).__name__}'"
        assert isinstance(value, Action), f"Accept only actions as values but got '{type(value).__name__}'"
        if isinstance(key, Action):
            key = str(key)

        self.data[key] = value
        if key != 'operator':
            for item in self._process_actions.get(key, set()):
                item.description = value

    def __getitem__(self, key):
        assert isinstance(key, str) or isinstance(key, Action), f"Do not expect '{type(key).__name__}'"
        return self.data[str(key)]

    def __delitem__(self, key):
        assert isinstance(key, str) or isinstance(key, Action), f"Do not expect '{type(key).__name__}'"
        if self._process_actions.get(key):
            for action in self._process_actions[key]:
                action.my_operator.remove(action)
                del self._process_actions[key]
        del self.data[key]

    @property
    def savepoints(self):
        return {p for a in self.values() for p in a.savepoints}

    @property
    def sequence(self):
        return repr(self.initial_action)

    def populate_with_empty_descriptions(self):
        """
        Create new descriptions for all behaviours that do not have them. New descriptions will have default values
        except the name attribute. All descriptions are added to the instance.

        :return: None
        """
        for baction in self.behaviour():
            if isinstance(baction, Behaviour) and not baction.description:
                desc = baction.kind(baction.name)
                self[baction.name] = desc

    def add_process_action(self, item: BaseAction, name='operator'):
        """
        To add a new Behaviour use this method. Dictionary representations is available only for descriptions.

        :param item: BaseAction.
        :param name: Name or 'operator'.
        :return: None
        """
        assert isinstance(item, BaseAction)
        assert name
        assert not isinstance(item, Operator) or name == 'operator'
        self._process_actions.setdefault(name, set())
        self._process_actions[name].add(item)

        if not isinstance(item, Operator) and self.data.get(name):
            item.description = self.data[name]

    def remove_process_action(self, obj: BaseAction):
        """
        Delete an existing Behaviour instance.

        :param obj: BaseAction.
        :return: None.
        """
        assert isinstance(obj, BaseAction)
        for key in self._process_actions:
            if obj in self._process_actions[key]:
                self._process_actions[key].remove(obj)

    def clone(self):
        """
        Recursively clone the collection of actions. It is not shallow one.

        :return: a new instance.
        """
        new = Actions()

        # Clone actions
        new.data = copy.copy(self.data)
        for action in self.data:
            new.data[action] = copy.copy(self.data[action])

        # Copy BehActions
        actions_map = dict()
        for key in self._process_actions:
            for item in self._process_actions[key]:
                new_item = item.clone()
                actions_map[item] = new_item
                new.add_process_action(new_item, key)

        # Replace operators
        for operator in filter(lambda x: isinstance(x, Operator), actions_map.keys()):
            for child in operator:
                actions_map[operator].append(actions_map[child])

        # Replace subprocesses
        for name, obj in new.items():
            if isinstance(obj, Subprocess):
                obj.action = actions_map[self.data[name].action]

        return new

    def filter(self, include=None, exclude=None):
        """
        Use the method to get descriptions with filters for description classes.

        :param include: Iterable with Action classes.
        :param exclude: Iterable with Action classes.
        :return: list with Action objects.
        """
        if not include:
            include = ()
        if not exclude:
            exclude = ()

        return sorted([x for x in self.data.values() if (not include or any(isinstance(x, t) for t in include)) and
                       (not exclude or all(not isinstance(x, t) for t in exclude))])

    def behaviour(self, name: str = None):
        """
        Find all behaviours in the collection or objects with a particular name.

        :param name: Str.
        :return: BaseAction.
        """
        if not name:
            return {a for k in self._process_actions for a in self._process_actions[k]}
        else:
            return {a for a in self._process_actions.get(name, set())}

    @property
    def initial_action(self):
        """
        Returns initial states of the process.

        :return: Sorted list with starting process Behaviour objects.
        """
        exclude = {a.action for a in self.filter(include={Subprocess})}
        acts = {a for a in self.behaviour() if not a.my_operator and isinstance(a, Operator) and a not in exclude}
        assert len(self.behaviour()) > 0, "There is no any actions in the process"
        assert len(acts) != 0,\
            'There is no any initial action. There are actions in total: {}'.\
            format('\n'.join(f"{repr(a)} parent: {repr(a.my_operator)}" for a in self.behaviour()))
        assert len(acts) == 1, 'There are more than one initial action: {}'.\
            format('\n'.join(f"{repr(a)} parent: {repr(a.my_operator)}" for a in acts))
        act, *_ = acts
        return act

    def first_actions(self, root=None, enter_subprocesses=True):
        assert isinstance(root, BaseAction) or root is None, type(root).__name__
        first = set()

        if not root:
            process = {self.initial_action}
        else:
            process = {root}
        while process:
            a = process.pop()

            if isinstance(a, Concatenation) and len(a) > 0:
                process.add(a[0])
            elif isinstance(a, Operator):
                for child in a:
                    process.add(child)
            elif isinstance(a, Behaviour) and a.kind is Subprocess and a.description and a.description.action and \
                    enter_subprocesses:
                process.add(a.description.action)
            else:
                first.add(a.name)

        return first

    def used_actions(self, root=None, enter_subprocesses=True):
        assert isinstance(root, BaseAction) or root is None, type(root).__name__
        used = set()

        if not root:
            process = {self.initial_action}
        else:
            process = {root}
        while process:
            a = process.pop()

            if isinstance(a, Operator) and len(a) > 0:
                for child in a:
                    process.add(child)
            elif isinstance(a, Behaviour) and a.kind is Subprocess and a.description and a.description.action and \
                    enter_subprocesses and a.name not in used:
                process.add(a.description.action)
                used.add(a.name)
            else:
                used.add(a.name)

        return used

    @property
    def final_actions(self):
        """
        Searches for terminal behaviour actions and return them in a set.

        :return: set of Behaviour actions.
        """
        return set(filter(lambda x: not isinstance(x, Operator), self.behaviour()))
