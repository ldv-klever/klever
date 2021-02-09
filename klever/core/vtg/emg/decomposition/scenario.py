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

from klever.core.vtg.emg.common.process.actions import Actions, Subprocess, Concatenation, Choice, Parentheses, Operator


class Scenario:

    def __init__(self, savepoint=None):
        self.savepoint = savepoint
        self.actions = Actions()
        self.__initial_action = None

    def set_initial_action(self, action):
        if not self.__initial_action:
            new = self._add_action_copy(action)
            self.__initial_action = new
        else:
            raise ValueError(f'An initial action {str(self.__initial_action)} is already set')

    def add_action_copy(self, action, operator):
        assert operator in self.actions.values()

        new_copy = self._add_action_copy(action)

        if isinstance(operator, Parentheses):
            assert not operator.action, 'Parent already has a child'
            operator.action = new_copy
        elif isinstance(operator, Choice):
            operator.add_action(new_copy)
        elif isinstance(operator, Concatenation):
            operator.add_action(new_copy)
        else:
            raise RuntimeError(f'Unknown operator {type(action).__name__} at copying action {str(action)}')

        return new_copy

    def _add_action_copy(self, action):
        new_copy = copy.deepcopy(action)
        self.actions[str(new_copy)] = new_copy
        new_copy.my_operator = None

        if isinstance(new_copy, Operator):
            new_copy.clean()

        return new_copy


class ScenarioExtractor:

    def __init__(self, actions):
        self._actions = actions
        self._roots = {self._actions.initial_action}

    def __call__(self, model):
        return self.__create_scenarios()

    def _process_subprocess(self, scenario, action, operator=None):
        self.__process_operator(scenario, action, operator)

    def _process_concatenation(self, scenario, action, operator=None):
        self.__process_operator(scenario, action, operator)

    def _process_choice(self, scenario, action, operator=None):
        self.__process_operator(scenario, action, operator)

    def _process_parentheses(self, scenario, action, operator=None):
        self.__process_operator(scenario, action, operator)

    def _process_leaf_action(self, scenario, action, operator=None):
        assert operator
        scenario.add_action_copy(action, operator)

    def _get_scenarios_for_root_savepoints(self, root):
        for savepoint in root.savepoints:
            new_scenario = Scenario(savepoint)
            new_scenario.set_initial_action(root)
            self._fill_top_down(new_scenario, root)
            yield new_scenario

    def _fill_top_down(self, scenario, action, operator=None):
        if isinstance(action, Concatenation):
            processing_method = self._process_concatenation
        elif isinstance(action, Choice):
            processing_method = self._process_choice
        elif isinstance(action, Parentheses):
            processing_method = self._process_parentheses
        elif isinstance(action, Subprocess):
            processing_method = self._process_subprocess
        else:
            processing_method = self._process_leaf_action

        processing_method(scenario, action, operator)

    def __create_scenarios(self):
        scenarios = set()
        while self._roots:
            root = self._roots.pop()

            for new_scenario in self._get_scenarios_for_root_savepoints(root):
                scenarios.add(new_scenario)
        return scenarios

    def __process_operator(self, scenario, action, operator=False):
        if operator:
            parent = scenario.add_action_copy(action, operator)
        else:
            parent = scenario.actions.initial_action

        if hasattr(action, 'action'):
            self._fill_top_down(scenario, action.action, parent)
        elif hasattr(action, 'actions'):
            for child in action.actions.values():
                self._fill_top_down(scenario, child, parent)
        else:
            raise ValueError(f'Operator {type(action).__name__} {str(action)} has not childen')
