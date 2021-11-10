#
# Copyright (c) 2021 ISP RAS (http://www.ispras.ru)
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

import collections

from klever.core.vtg.emg.common.process import Process
from klever.core.vtg.emg.common.process.actions import Savepoint, BaseAction, Operator, Behaviour, Actions, Subprocess,\
    Requirements, Receive


class Path(collections.UserList):

    def __init__(self, initlist=None, name=None):
        super().__init__(initlist)
        if name:
            self.name = name
        elif isinstance(initlist, Path) and initlist.name:
            self.name = initlist.name
        else:
            self.name = None

    def __hash__(self):
        return hash(','.join([a.name for a in self.data]))

    def __eq__(self, other):
        assert isinstance(other, Path)
        return hash(self) == hash(other)

    def __add__(self, other):
        assert isinstance(other, Path)

        new = Path(self.data + other.data if self.terminal else self.data[:-1] + other.data)
        if self.name:
            new.add_name_suffix(self.name)
        if other.name:
            new.add_name_suffix(other.name)
        return new

    def __iadd__(self, other):
        assert isinstance(other, Path)
        if not self.terminal:
            self.data.pop()

        self.data += other.data
        if other.name:
            self.add_name_suffix(other.name)
        return self

    def __repr__(self):
        return 'Path([' + ', '.join(list(map(repr, self.data))) + f'], {self.name})'

    @property
    def terminal(self):
        if not self.data:
            return True
        else:
            return self.data[-1].kind is not Subprocess

    def included(self, path):
        """
        Check that the given subprocess and this subprocess have a common part except the last possible jump. Examples:
        a, b, {d} included in a, b, f
        a, b, {c} not includes a, t
        a, b, c not included in a, c, f or a, b, c, d, f

        :param path: Path
        :return: Bool
        """
        assert isinstance(path, Path)
        assert not self.terminal

        if len(self) == 1:
            return False

        if (len(path) + 1) < len(self):
            return False

        for index, action in enumerate(self[:-1]):
            if path[index].name != action.name:
                return False

        return True

    def add_name_suffix(self, name):
        assert name
        if self.name:
            self.name = f"{self.name}_{name}"
        else:
            self.name = name


class Scenario:
    """Main data structure that implements an order of actions without any extra details and descriptions."""

    def __init__(self, parent, savepoint: Savepoint = None, name: str = None):
        assert isinstance(parent, Process)
        assert isinstance(name, str) or name is None
        assert isinstance(savepoint, Savepoint) or savepoint is None,\
            f"Receive incorrect object of type '{type(savepoint).__name__}'"

        self.savepoint = savepoint
        if name:
            self.name = name
        elif savepoint and str(savepoint) and str(savepoint) != 'None':
            self.name = str(savepoint)
        else:
            self.name = None
        self.process = parent
        self.actions = Actions()
        self.__initial_action = None

    def __str__(self):
        """Be very accurate with it! It returns the name of the parent process to make requirements working smoothly."""
        return str(self.process)

    @property
    def initial_action(self):
        return self.__initial_action

    @initial_action.setter
    def initial_action(self, behaviour: Operator):
        assert isinstance(behaviour, Operator), \
            f"Expect an operator instead of '{type(behaviour).__name__}'"

        if not self.__initial_action:
            new = self._add_action_copy(behaviour)
            self.__initial_action = new
        else:
            raise ValueError(f"An initial action '{str(self.__initial_action)}' is already set")

    def add_action_copy(self, action: BaseAction, operator: Operator = None):
        assert isinstance(operator, Operator) or operator is None
        new_copy = self._add_action_copy(action)

        if operator is not None:
            assert operator in self.actions.behaviour()
            operator.append(new_copy)

        return new_copy

    def clone(self):
        new = Scenario(self.process, self.savepoint, self.name)
        new.actions = self.actions.clone()
        new.__initial_action = new.actions.initial_action
        return new

    @property
    def peers_as_requirements(self):
        """
        Represent peers as a Requirements object.

        :return: Requirements object
        """
        new = Requirements()
        for peer, signal_actions in self.process.incoming_peers.items():
            if signal_actions.intersection(set(self.actions.keys())):
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
                if isinstance(action, Receive) and action.replicative and self.savepoint:
                    # Skip the signal receiving if there is a savepoint
                    continue
                else:
                    yield action.requirements
        if self.savepoint:
            yield self.savepoint.requirements
        else:
            yield self.peers_as_requirements

    relevant_requirements = Process.relevant_requirements

    compatible_with_model = Process.compatible_with_model

    def _add_action_copy(self, behaviour: BaseAction):
        assert isinstance(behaviour, BaseAction), \
            f"Expect a base action instead of '{type(behaviour).__name__}'"

        new_copy = behaviour.clone()
        new_copy.my_operator = None
        if isinstance(behaviour, Operator):
            new_copy.clear()
            self.actions.add_process_action(new_copy)
        elif isinstance(behaviour, Behaviour):
            self.actions.add_process_action(new_copy, new_copy.name)
        else:
            raise NotImplementedError
        return new_copy
