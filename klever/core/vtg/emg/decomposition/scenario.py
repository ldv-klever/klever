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

from klever.core.vtg.emg.common.process import Process, ProcessCollection
from klever.core.vtg.emg.common.process.actions import Savepoint, BaseAction, Operator, Behaviour, Actions, Subprocess,\
    WeakRequirements, Receive


class ScenarioCollection(ProcessCollection):
    """
    This is a collection of scenarios. The factory generated the model with processes that have provided keys. If a
    process have a key in the collection but the value is None, then the factory will use the origin process. Otherwise,
    it will use a provided scenario.
    """

    entry = None

    def __init__(self, original_model, name='base', entry=None, models=None, environment=None):
        super().__init__(name)
        assert isinstance(name, str)
        self.entry = entry
        self.original_model = original_model
        self.models = models if isinstance(models, dict) else {}
        self.environment = environment if isinstance(environment, dict) else {}

    def __hash__(self):
        return hash(str(self.attributed_name))

    def clone(self, new_name: str):
        """
        Copy the collection with a new name.

        :param new_name: Name string.
        :return: ScenarioCollection instance.
        """
        new = ScenarioCollection(self.original_model, new_name)
        new.attributes = dict(self.attributes)
        new.entry = self.entry.clone() if self.entry else None
        for collection in ('models', 'environment'):
            for key in getattr(self, collection):  # pylint: disable=not-an-iterable
                if getattr(self, collection)[key]:  # pylint: disable=unsubscriptable-object
                    # pylint: disable=not-an-iterable, unsubscriptable-object, unsupported-assignment-operation
                    getattr(new, collection)[key] = getattr(self, collection)[key].clone()
                else:
                    getattr(new, collection)[key] = None  # pylint: disable=not-an-iterable, unsupported-assignment-operation
        return new

    @property
    def non_models(self):
        """Return environment processes with an entry process"""
        ret = dict(self.environment)
        if self.original_model.entry:
            ret[str(self.original_model.entry)] = self.entry
        return ret

    @property
    def defined_processes(self):
        return [self.original_model.models[i] for i in sorted(self.models.keys())] + \
               [self.environment[i] for i in sorted(self.environment.keys()) if self.environment[i]] + \
               ([self.entry] if self.entry else [])

    @property
    def processes(self):
        """Returns a sorted list of all processes from the model."""
        return [self.original_model.models[i] for i in sorted(self.models.keys())] + \
               [self.environment[i] if self.environment[i] else self.original_model.environment[i]
                for i in sorted(self.environment.keys())] + \
               ([self.entry] if self.entry else ([self.original_model.entry] if self.original_model.entry else []))

    @property
    def savepoint(self):
        """If there is a scenario with a savepoint, find it."""
        for s in self.processes:
            if isinstance(s, Scenario) and s.savepoint:
                return s.savepoint

        return None

    def delete_with_deps(self, process_name, dep_order, processed):
        # Check that there is a savepoint in the model and required by must contain
        savepoint = str(self.savepoint.parent) if self.savepoint else None

        # Edit deps order
        requiring_processes = self.requiring_processes(process_name, processed)
        if not requiring_processes:
            selected_items = {process_name}
        else:
            selected_items = requiring_processes
            if savepoint:
                saved_order = dep_order[:dep_order.index(savepoint)+1]
                for p in saved_order:
                    if p in selected_items:
                        selected_items.remove(p)
            selected_items.add(process_name)

        # Now delete processes
        for p in selected_items:
            self.remove_process(p)

    def broken_dependencies_by_adding_scenario(self, process_name, scenario, dep_order, processed):
        # Check that there is a savepoint in the model and required by must contain
        savepoint = None if not self.savepoint else str(self.savepoint.parent)

        if process_name in dep_order:
            if savepoint and savepoint not in dep_order:
                broken = {savepoint}
            elif savepoint and isinstance(scenario, Scenario) and scenario.savepoint:
                # We remove the savepoint and add the scenario, just need to be sure about all broken things
                broken = {savepoint}
                requiring_pr = self.requiring_processes(process_name, processed)
                requiring_sp = self.requiring_processes(savepoint, processed)
                broken_by_savepoint = requiring_sp.difference(requiring_pr)
                broken.update(broken_by_savepoint)
            else:
                broken = set()

            # Now check if some actions are broken
            processed = set(processed)
            if process_name in processed:
                processed.remove(process_name)
            broken.update(self.broken_processes(process_name, scenario.actions))
            return broken
        if savepoint and savepoint in dep_order:
            requiring_sp = self.requiring_processes(savepoint, processed)
            if requiring_sp:
                broken = {savepoint}
                for child in (p for p in dep_order[:dep_order.index(savepoint)]
                              if p in requiring_sp):
                    broken.add(child)
                return broken

            return set()
        if savepoint:
            # Only savepoint is broken
            return {savepoint}

        # Nothing is broken
        return set()


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
        new.__initial_action = new.actions.initial_action  # pylint: disable=unused-private-member
        return new

    @property
    def peers_as_requirements(self):
        """
        Represent peers as a Requirements object.

        :return: Requirements object
        """
        new = WeakRequirements()
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
            if isinstance(action, Receive) and action.replicative and self.savepoint:
                # Skip the signal receiving if there is a savepoint
                continue

            if action.requirements and not action.requirements.is_empty:
                yield action.requirements
            if action.weak_requirements and not action.weak_requirements.is_empty:
                yield action.weak_requirements

        if self.savepoint:
            new = self.savepoint.requirements
        else:
            new = self.peers_as_requirements

        if not new.is_empty:
            yield new

    relevant_requirements = Process.relevant_requirements

    def compatible_with_model(self, model, restrict_to=None):
        """
        Check that the model contains all necessary for this process. Do not check that the process has all necessary
        for the model.

        :param model: ProcessCollection.
        :param restrict_to: None or set of Process names.
        :return: Bool
        """
        if isinstance(model, ScenarioCollection):
            assert restrict_to is None or isinstance(restrict_to, set)
            processes = {str(p): p for p in model.processes if restrict_to is None or str(p) in restrict_to}

            for requirement in self.requirements:
                if not requirement.compatible_with_model(model, restrict_to):
                    if not requirement.get_missing_processes(model, processes, restrict_to):
                        return False

                    # Check defined processes
                    broken = self._broken_defined_processes(requirement, processes, model)

                    if broken.intersection(set(map(str, model.defined_processes))):
                        return False
            return True

        return Process.compatible_with_model(self, model, restrict_to)

    def _broken_defined_processes(self, requirement, processes, model):  # pylint:disable=unused-argument
        broken = set()
        for name, actions in ((name, process.actions) for name, process in processes.items()):
            if not requirement.compatible(name, actions):
                broken.add(name)
        return broken

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
