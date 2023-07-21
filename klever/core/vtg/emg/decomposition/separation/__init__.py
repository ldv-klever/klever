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

import copy
import logging

from klever.core.vtg.emg.common.process import Process, ProcessCollection
from klever.core.vtg.emg.decomposition.scenario import Scenario
from klever.core.vtg.emg.common.process.actions import Savepoint, BaseAction, Operator, Behaviour, Concatenation, \
    Choice, Parentheses, Subprocess, Actions


class ScenarioExtractor:
    """
    This is a simple extractor that returns a scenario as is in the given process. However, it implements main features
    to explore actions and this is a foundation for the next implementations.
    """

    def __init__(self, logger, process: Process, model: ProcessCollection):
        self.logger = logger
        self._process = process
        self._actions = process.actions
        self._model = model
        self._roots = {self._actions.initial_action}

    def __call__(self):
        scenarios = self.__create_scenarios()
        return scenarios

    def _process_subprocess(self, scenario: Scenario, behaviour: BaseAction, operator: Operator = None):
        assert isinstance(behaviour, Behaviour)
        assert behaviour.kind is Subprocess

        new = self._process_leaf_action(scenario, behaviour, operator)
        if len(scenario.actions.behaviour(new.name)) == 1:
            child = behaviour.description.action
            new_action = self._fill_top_down(scenario, child)
            new.description.action = new_action
        return new

    def _process_concatenation(self, scenario: Scenario, beh: Concatenation, operator: Operator = None):
        return self.__process_operator(scenario, beh, operator)

    def _process_choice(self, scenario: Scenario, behaviour: Choice, operator: Operator = None):
        return self.__process_operator(scenario, behaviour, operator)

    def _process_parentheses(self, scenario: Scenario, beh: Parentheses, operator: Operator = None):
        return self.__process_operator(scenario, beh, operator)

    def _process_leaf_action(self, scenario: Scenario, beh: Behaviour, operator: Operator = None):
        assert isinstance(beh, Behaviour)

        cpy = scenario.add_action_copy(beh, operator)
        if beh.name not in scenario.actions:
            new_description = copy.copy(self._actions[beh.name])
            scenario.actions[beh.name] = new_description
        return cpy

    def _get_scenarios_for_root_savepoints(self, root: BaseAction):
        first_actual = self._actions.first_actions(root)
        assert len(first_actual) == 1, 'Support only the one first action'
        actual = self._actions.behaviour(first_actual.pop())
        assert len(actual) == 1, 'Support only the one first action behaviour'
        actual = actual.pop()
        if actual.description.savepoints:
            for savepoint in actual.description.savepoints:
                new = self._new_scenario(self._actions.initial_action, savepoint)
                assert new.name
                yield new

    def _new_scenario(self, root: Operator, savepoint: Savepoint = None):
        nsc = Scenario(self._process, savepoint)
        nsc.initial_action = root
        for child in root:
            self._fill_top_down(nsc, child, nsc.initial_action)
        return nsc

    def _fill_top_down(self, scenario: Scenario, beh: BaseAction, operator: Operator = None):
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
        scenarios = []
        while self._roots:
            root = self._roots.pop()

            for new_scenario in self._get_scenarios_for_root_savepoints(root):
                scenarios.append(new_scenario)
        return scenarios

    def __process_operator(self, scenario: Scenario, behaviour: Operator, operator: Operator = None):
        assert isinstance(behaviour, Operator), type(behaviour).__name__
        parent = scenario.add_action_copy(behaviour, operator)

        for child in behaviour:
            self._fill_top_down(scenario, child, parent)

        return parent


class SeparationStrategy:
    """
    Strategy that creates Scenario instances for a provided Process instance. Each scenario is used to replace an origin
    process in environment model variants.
    """

    strategy = ScenarioExtractor

    def __init__(self, logger: logging.Logger, conf: dict):
        self.logger = logger
        self.conf = conf

    def __call__(self, process: Process, model: ProcessCollection):
        new = self.strategy(self.logger, process, model)
        return new()
