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

from klever.core.vtg.emg.common.process.actions import Savepoint, BaseAction, Operator, Behaviour, Concatenation, \
    Choice, Parentheses, Subprocess, Actions


class Scenario:

    def __init__(self, savepoint: Savepoint = None):
        assert isinstance(savepoint, Savepoint) or savepoint is None,\
            f'Receive incorrect object of type {type(savepoint).__name__}'

        self.savepoint = savepoint
        self.actions = Actions()
        self.__initial_action = None

    @property
    def initial_action(self):
        return self.__initial_action

    @initial_action.setter
    def initial_action(self, behaviour: Operator):
        assert isinstance(behaviour, Operator), \
            f'Expect an operator instead of {type(behaviour).__name__}'

        if not self.__initial_action:
            new = self._add_action_copy(behaviour)
            self.__initial_action = new
        else:
            raise ValueError(f'An initial action {str(self.__initial_action)} is already set')

    def add_action_copy(self, action: BaseAction, operator: Operator = None):
        assert isinstance(operator, Operator) or operator is None
        new_copy = self._add_action_copy(action)

        if operator is not None:
            assert operator in self.actions.behaviour()
            operator.append(new_copy)

        return new_copy

    def clone(self):
        new = Scenario(self.savepoint)
        new.actions = self.actions.clone()
        new.__initial_action = new.actions.initial_action
        return new

    def _add_action_copy(self, behaviour: BaseAction):
        assert isinstance(behaviour, BaseAction), \
            f'Expect a base action instead of {type(behaviour).__name__}'

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


class ScenarioExtractor:

    def __init__(self, actions: Actions):
        self._actions = actions
        self._roots = {self._actions.initial_action}

    def __call__(self):
        scenarios = self.__create_scenarios()
        return scenarios

    def _process_subprocess(self, scenario, beh, operator=None):
        assert isinstance(beh, Behaviour)
        assert beh.kind is Subprocess

        new = self._process_leaf_action(scenario, beh, operator)
        if len(scenario.actions.behaviour(new.name)) == 1:
            child = beh.description.action
            new_action = self._fill_top_down(scenario, child)
            new.description.action = new_action
        return new

    def _process_concatenation(self, scenario, beh, operator=None):
        return self.__process_operator(scenario, beh, operator)

    def _process_choice(self, scenario, beh, operator=None):
        return self.__process_operator(scenario, beh, operator)

    def _process_parentheses(self, scenario, beh, operator=None):
        return self.__process_operator(scenario, beh, operator)

    def _process_leaf_action(self, scenario, beh, operator=None):
        assert isinstance(beh, Behaviour)

        cpy = scenario.add_action_copy(beh, operator)
        if beh.name not in scenario.actions:
            new_description = copy.copy(self._actions[beh.name])
            scenario.actions[beh.name] = new_description
        return cpy

    def _get_scenarios_for_root_savepoints(self, root):
        def new_scenario(rt, svp=None):
            nsc = Scenario(svp)
            nsc.initial_action = rt
            for child in rt:
                self._fill_top_down(nsc, child, nsc.initial_action)
            return nsc

        first_actual = self._actions.first_actions(root)
        assert len(first_actual) == 1, 'Support only the one first action'
        actual = self._actions.behaviour(first_actual.pop())
        assert len(actual) == 1, f'Support only the one first action behaviour'
        actual = actual.pop()
        if actual.description.savepoints:
            for savepoint in actual.description.savepoints:
                yield new_scenario(self._actions.initial_action, savepoint)
        else:
            yield new_scenario(self._actions.initial_action)

    def _fill_top_down(self, scenario: Scenario, beh: Behaviour, operator: Operator = None):
        assert isinstance(beh, BaseAction)
        assert isinstance(operator, Operator) or operator is None
        assert beh not in scenario.actions.behaviour()
        if operator:
            assert operator in scenario.actions.behaviour()

        if isinstance(beh, Concatenation):
            processing_method = self._process_concatenation
        elif isinstance(beh, Choice):
            processing_method = self._process_choice
        elif isinstance(beh, Parentheses):
            processing_method = self._process_parentheses
        elif isinstance(beh, Behaviour) and beh.kind is Subprocess:
            processing_method = self._process_subprocess
        else:
            processing_method = self._process_leaf_action

        return processing_method(scenario, beh, operator)

    def __create_scenarios(self):
        scenarios = list()
        while self._roots:
            root = self._roots.pop()

            for new_scenario in self._get_scenarios_for_root_savepoints(root):
                scenarios.append(new_scenario)
        return scenarios

    def __process_operator(self, scenario, behaviour, operator=None):
        assert isinstance(behaviour, Operator), type(behaviour).__name__
        parent = scenario.add_action_copy(behaviour, operator)

        for child in behaviour:
            self._fill_top_down(scenario, child, parent)

        return parent
