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
    def my_operator(self): # pylint: disable=function-redefined
        """Returns the operator that joins this action with the others in the process."""
        return self._my_operator

    @my_operator.setter
    def my_operator(self, new):
        assert new is not self, 'Prevent recursive operator dependency'
        assert isinstance(new, Operator) or new is None, f"Cannot set as operator a non-operator object '{repr(new)}'"
        # pylint: disable=access-member-before-definition
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
        self.specific_attributes = []
        self.repeat = None
        self._name = name
        self._description = None
        self._accepted_class = accepted_class

    def __repr__(self):
        """Print the representation of the action in process DSL."""
        res = None
        if self.description:
            res = repr(self.description)
        else:
            res = repr(self._accepted_class(self.name))

        # Repeat may be specified only for jump action in two forms: either {jump[N]} or {jump[%flag%]}.
        if self.repeat is not None:
            res = res[:-1] + '[{}]}}'.format(self.repeat)

        return res

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

    def insert(self, i, item):
        self._pair(item)
        self.data.insert(i, item)

    def remove(self, item):
        assert item in self.data, f"There is no '{repr(item)}' in '{repr(self)}'"
        index = self.data.index(item)
        del self[index]

    def replace(self, old, item):
        assert old in self.data, f"There is no '{repr(old)}' in '{repr(self)}'"
        index = self.data.index(old)
        self[index] = item

    def index(self, item, *args):
        return self.data.index(item)

    def append(self, item):
        assert not item.my_operator

        self._pair(item)
        self.data.append(item)

    def clone(self):
        new = super().clone()
        new.data = []
        return new

    def _pair(self, action):
        assert not action.my_operator or action.my_operator is self
        if not action.my_operator:
            action.my_operator = self

    @staticmethod
    def _unpair(action):
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

    def insert(self, i, item):
        assert i == 0 and len(self) == 0
        super().insert(i, item)

    def append(self, item):
        assert len(self) == 0
        super().append(item)


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
        self._require = Requirements()
        self._weak_require = WeakRequirements()

    def __getnewargs__(self):
        # Return the arguments that *must* be passed to __new__ (required for deepcopy)
        return self.name,  # pylint: disable=trailing-comma-tuple

    def __str__(self):
        return self.name

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return str(self) == str(other)

    def __lt__(self, other):
        return str(self) < str(other)

    @property
    def requirements(self):
        return self._require

    @property
    def weak_requirements(self):
        return self._weak_require

    def clone(self):
        new = copy.copy(self)
        new.savepoints = {s.clone() for s in self.savepoints}
        new._require = self.requirements.clone()
        new._weak_require = self.weak_requirements.clone()
        return new


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
        super().__init__(name)
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
        super().__init__(name)
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
        super().__init__(name)
        self.statements = []
        self.condition = []
        self.trace_relevant = False

    def __repr__(self):
        return '<%s>' % str(self)


class Actions(collections.UserDict):

    def __init__(self):
        super().__init__()
        self._process_actions = {}

    def __setitem__(self, key, value):
        assert isinstance(key, (str, Action)), f"Do not expect '{type(key).__name__}'"
        assert isinstance(value, Action), f"Accept only actions as values but got '{type(value).__name__}'"
        if isinstance(key, Action):
            key = str(key)

        self.data[key] = value
        if key != 'operator':
            for item in self._process_actions.get(key, set()):
                item.description = value

    def __getitem__(self, key):
        assert isinstance(key, (str, Action)), f"Do not expect '{type(key).__name__}'"
        return self.data[str(key)]

    def __delitem__(self, key):
        assert isinstance(key, (str, Action)), f"Do not expect '{type(key).__name__}'"
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
        for item in self._process_actions.values():
            if obj in item:
                item.remove(obj)

    def clone(self):
        """
        Recursively clone the collection of actions. It is not shallow one.

        :return: a new instance.
        """
        new = Actions()

        # Clone actions
        new.data = copy.copy(self.data)
        for action in self.data:
            new.data[action] = self.data[action].clone()

        # Copy BehActions
        actions_map = {}
        for key, items in self._process_actions.items():
            for item in items:
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
            return {a for k, items in self._process_actions.items() for a in items}

        return set(self._process_actions.get(name, set()))

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

    def add_condition(self, name, condition, statements, comment):
        """
        Add new Condition action. Later you can add it to a particular place to execute using an another method.

        :param name: Action name.
        :param condition: List of conditional expressions.
        :param statements: List with statements to execute.
        :param comment: A comment for the action (A short sentence).
        :return: A new Condition object.
        """
        new = Block(name)
        self.data[name] = new

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
        assert isinstance(old, Action), f"Expect strictly an Action to replace but got '{repr(old)}'"
        assert isinstance(new, Action), f"Expect strictly an Action to replace with '{repr(new)}'"
        self.data[str(new)] = new

        for entry in self.behaviour(str(old)):
            new_entry = Behaviour(str(new), type(new))
            self.add_process_action(new_entry, str(new))
            operator = entry.my_operator
            operator.replace(entry, new_entry)
            self.remove_process_action(entry)

        if purge:
            del self.data[str(old)]

    def insert_action(self, new, target, before=False):
        """
        Insert an existing action before or after the given target action.

        :param new: Action object.
        :param target: Action object.
        :param before: True if append left ot append to  the right end.
        """
        assert isinstance(new, Action), f"Got non-action object '{str(new)}'"
        assert isinstance(target, Action), f"Got non-action object '{str(target)}'"
        if str(new) not in self.data:
            self.data[str(new)] = new

        for entry in self.behaviour(str(target)):
            new_entry = Behaviour(str(new), type(new))
            self.add_process_action(new_entry, str(new))
            operator = entry.my_operator
            if isinstance(operator, Choice):
                new_conc = Concatenation()
                operator.replace(entry, new_conc)
                if before:
                    new_conc.append(new_entry)
                    new_conc.append(entry)
                else:
                    new_conc.append(entry)
                    new_conc.append(new_entry)
            elif isinstance(operator, Concatenation):
                position = operator.index(entry)
                if not before:
                    position += 1
                operator.insert(position, new_entry)
            else:
                raise NotImplementedError

    def insert_alternative_action(self, new, target):
        """
        Insert an existing action as an alternative choice for a given one.

        :param new: Action object.
        :param target: Action object.
        """
        assert isinstance(new, Action), f"Got non-action object '{str(new)}'"
        assert isinstance(target, Action), f"Got non-action object '{str(target)}'"
        if str(new) not in self:
            self.data[str(new)] = new

        for entry in self.behaviour(str(target)):
            operator = entry.my_operator
            newb = Behaviour(str(new), type(new))
            self.add_process_action(newb, str(new))

            if isinstance(operator, Concatenation) and isinstance(operator.my_operator, Choice) and operator[0] is entry:
                operator = operator.my_operator
                operator.append(newb)
            elif isinstance(operator, Concatenation):
                new_par = Parentheses()
                operator.replace(entry, new_par)
                choice = Choice()
                new_par.append(choice)
                choice.append(newb)
                choice.append(entry)
            elif isinstance(operator, Parentheses):
                choice = Choice()
                operator.replace(entry, choice)
                choice.append(newb)
                choice.append(entry)
            elif isinstance(operator, Choice):
                operator.append(newb)
            else:
                raise ValueError("Unknown operator {!r}".format(type(operator).__name__))


class Requirements:
    """The class represent requirement of a process, scenario or savepoint."""

    def __init__(self):
        self._required_actions = {}
        self._required_processes = {}

    def __iter__(self):
        yield "processes", dict(self._required_processes)
        yield "actions", {name: list(actions) for name, actions in self._required_actions.items()}

    @classmethod
    def from_dict(cls, desc: dict, me: str):
        assert isinstance(desc, dict)

        new = cls()

        for name, flag in desc.get('processes', {}).items():
            if not isinstance(flag, bool):
                raise ValueError(f"Expect bool value instead of '{type(flag).__name__}' for member '{name}'")

            new._required_processes[name] = flag

        if me not in new._required_processes:
            new._required_processes[me] = True

        for name, actions in desc.get('actions', {}).items():
            if not isinstance(actions, list):
                raise ValueError(f"Expect list of actions but got '{type(actions).__name__}' for member '{name}'")
            assert new._required_processes.get(name), \
                f"Set process requirement for '{name}' besides adding requirements for actions"

            new._required_actions.setdefault(name, [])
            for action in actions:
                if not isinstance(action, str):
                    raise ValueError(f"Expect names of actions, bug got '{type(action).__name__}' for member '{name}'")

                new._required_actions[name].append(action)

        return new

    @property
    def required_processes(self):
        """Set of required processes"""
        return {name for name, flag in self._required_processes.items() if flag}

    @property
    def forbidden_processes(self):
        """Set of forbidden processes"""
        return {name for name, flag in self._required_processes.items() if not flag}

    @property
    def relevant_processes(self):
        """Joint set of all required or forbidden processes."""
        return set(self._required_processes.keys())

    @property
    def is_empty(self):
        return not self._required_processes

    def clone(self):
        new = Requirements()
        new._required_actions = copy.deepcopy(self._required_actions)
        new._required_processes = copy.copy(self._required_processes)
        return new

    def add_requirement(self, name: str, require: bool = True):
        """
        Add the requirement to include or exclude a process with the given name.

        :param name: Process name.
        :param require: True/False
        :return: None
        """
        assert require or name not in self._required_actions, \
            f"Cannot add a requirement for process '{name}' as there are already contradicting requirements to " \
            f"its actions"
        self._required_processes[name] = require

    def remove_requirement(self, name: str):
        """
        Remove the requirement for a certain process.

        :param name: Process name.
        :return: None
        """
        assert name in self._required_processes
        del self._required_processes[name]

        if name in self._required_actions:
            del self._required_actions[name]

    def add_actions_requirement(self, name: str, actions: list, replace: bool = False):
        """
        Add the requirement regarding actions of a process to include.

        :param name: Process name.
        :param actions: A list of actions.
        :param replace: Replace the existing requirement or extend the list of required actions.
        :return: None
        """
        assert isinstance(actions, list)
        assert name in self._required_processes, f"First add the process requirement for process '{name}'"

        if replace:
            self._required_actions[name] = list(actions)
        else:
            self._required_actions.setdefault(name, [])
            self._required_actions[name].extend(actions)

    def required_actions(self, name: str):
        """Provide a list of required actions for the given process name."""
        assert name in self._required_processes

        return self._required_actions.get(name, [])

    def compatible(self, name: str, actions: Actions):
        """
        Check that the given process with provided actions is compatible with this one. The provided process should
        contain all necessary actions required by this process and should not be forbidden.

        :param name: Process name.
        :param actions: Actions obj.
        :return: Bool
        """
        assert isinstance(name, str)
        assert isinstance(actions, Actions)

        if name in self.required_processes and name in self._required_actions:
            return set(self.required_actions(name)).issubset(set(actions.keys()))
        if name in self.required_processes:
            return True
        if name in self.forbidden_processes:
            return False

        return True

    def compatible_with_model(self, model, restrict_to=None):
        """
        Check that all processes of the model are compatible with the given model. The second parameter can limit which
        processes to check, since the model can be incomplete by the moment of the check.

        :param model: ProcessCollection.
        :param restrict_to: Set of Process names.
        :return: Bool
        """
        assert restrict_to is None or isinstance(restrict_to, set)

        processes = {str(p): p for p in model.processes if restrict_to is None or str(p) in restrict_to}

        # Check actions
        for name, actions in ((name, process.actions) for name, process in processes.items()):
            if not self.compatible(name, actions):
                return False

        # Check missing processes
        return self.get_missing_processes(model, processes, restrict_to)

    def rename_notion(self, previous: str, new: str):
        if previous in self._required_processes:
            self._required_processes[new] = self._required_processes[previous]
            del self._required_processes[previous]
        if previous in self._required_actions:
            self._required_actions[new] = self._required_actions[previous]
            del self._required_actions[previous]

    def get_missing_processes(self, model, processes_map, restrict_to=None):
        """
        Find if the provided processes dict has missing processes required by this object.

        :param model: ProcessCollection obj.
        :param processes_map: {Process name -> Process obj}.
        :param restrict_to: Set of Process names.
        :return: bool
        """
        if restrict_to is None:
            required_processes = self.required_processes
        else:
            required_processes = self.required_processes.intersection(restrict_to)
        missing_processes = required_processes.difference(
            set(processes_map.keys()).union({n for n, v in model.attributes.items() if v != 'Removed'}))
        if missing_processes:
            return False
        return True


class WeakRequirements(Requirements):
    """
    This is a specific class that allows us to define weak requirements. It asks to keep not all processes listed
    in the requirement but at least one. If there is a requirement to actions that they should be met by the model.
    """

    def clone(self):
        new = WeakRequirements()
        new._required_actions = copy.deepcopy(self._required_actions)
        new._required_processes = copy.copy(self._required_processes)
        return new

    def compatible_with_model(self, model, restrict_to=None):
        """
        Check that all processes of the model are compatible with the given model. The second parameter can limit which
        processes to check, since the model can be incomplete by the moment of the check.

        :param model: ProcessCollection.
        :param restrict_to: Set of Process names.
        :return: Bool
        """
        assert restrict_to is None or isinstance(restrict_to, set)

        processes = {str(p): p for p in model.processes if restrict_to is None or str(p) in restrict_to}

        # Check actions
        single_suiting = False
        for name, actions in ((name, process.actions) for name, process in processes.items()):
            if self.compatible(name, actions):
                single_suiting = True
                break

        if single_suiting:
            # Check missing processes
            return self.get_missing_processes(model, processes, restrict_to)

        return False

    def get_missing_processes(self, model, processes_map, restrict_to=None):
        """
        Find if the provided processes dict has missing processes required by this object.

        :param model: ProcessCollection obj.
        :param processes_map: {Process name -> Process obj}.
        :param restrict_to: Set of Process names.
        :return: True if no missing processes.
        """
        if restrict_to is None:
            required_processes = self.required_processes
        else:
            required_processes = self.required_processes.intersection(restrict_to)

        if not required_processes:
            return True

        found_processes = required_processes.intersection(
            set(processes_map.keys()).union({n for n, v in model.attributes.items() if v != 'Removed'}))
        if found_processes:
            return True
        return False


class Savepoint:
    """
    The class represents a savepoint - description of an initialization used if there is no receiver for a process.
    """

    def __init__(self, name, parent, statements, comment=None):
        self._name = name
        self.comment = comment
        self.statements = list(statements)
        self.parent = parent
        self._require = Requirements()
        self._weak_require = WeakRequirements()

    def __str__(self):
        return str(self._name)

    def __hash__(self):
        return hash(str(self))

    @property
    def requirements(self):
        return self._require

    @property
    def weak_requirements(self):
        return self._weak_require

    def clone(self):
        new = Savepoint(str(self), self.parent, self.statements, self.comment)
        new._require = self._require.clone()
        new._weak_require = self._weak_require.clone()
        return new
