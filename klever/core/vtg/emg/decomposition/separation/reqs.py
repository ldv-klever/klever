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

from klever.core.vtg.emg.decomposition.scenario import Scenario, ScenarioCollection
from klever.core.vtg.emg.decomposition.separation import SeparationStrategy, ScenarioExtractor
from klever.core.vtg.emg.common.process import Process, ProcessCollection
from klever.core.vtg.emg.common.process.actions import Actions, Choice, Operator, Concatenation, BaseAction, \
    Requirements, Savepoint


class ScenarioRequirements(Requirements):

    def __init__(self, relevant_savepoint: str):
        assert isinstance(relevant_savepoint, str)

        super().__init__()
        self._relevant_savepoint = relevant_savepoint

    @property
    def relevant_savepoint(self):
        return self._relevant_savepoint

    def clone(self):
        new = ScenarioRequirements(self.relevant_savepoint)
        new._required_actions = copy.deepcopy(self._required_actions)
        new._required_processes = copy.copy(self._required_processes)
        return new

    def compatible_with_model(self, model, restrict_to=None):
        """
        Check that all requirements are compatible with the given model. The second parameter can limit which
        processes to check, since the model can be incomplete by the moment of the check.

        :param model: ProcessCollection.
        :param restrict_to: Set of Process names.
        :return: Bool
        """
        passes = super().compatible_with_model(model, restrict_to)
        if isinstance(model, ScenarioCollection) and model.savepoint:
            if self.relevant_savepoint != str(model.savepoint):
                return False
        else:
            return passes

    def compatible_scenario(self, scenario):
        """
        Check that scenario has the same relevant savepoint.

        :param scenario: Process or Scenario.
        :return: Bool
        """
        compatible = super().compatible(str(scenario), scenario.actions)
        if compatible:
            if isinstance(scenario, ScenarioWithRelevance):
                return scenario.relevant_savepoint == self._relevant_savepoint or \
                       (scenario.savepoint and str(scenario.savepoint) == self._relevant_savepoint)
            elif isinstance(scenario, Scenario):
                return (not (str(scenario) in self.relevant_processes)) or \
                       (scenario.savepoint and str(scenario.savepoint) == self._relevant_savepoint)
            else:
                return not (str(scenario) in self.relevant_processes)
        return compatible

    @classmethod
    def override_requirement(cls, obj, savepoint):
        new = ScenarioRequirements(savepoint)
        new._required_actions = copy.deepcopy(obj._required_actions)
        new._required_processes = copy.copy(obj._required_processes)
        return new

    @property
    def is_empty(self):
        return False


class ScenarioWithRelevance(Scenario):

    def __init__(self, parent, relevant_savepoint: str, scenario_requirement: ScenarioRequirements,
                 savepoint: Savepoint = None, name: str = None):
        assert isinstance(relevant_savepoint, str)
        assert isinstance(scenario_requirement, ScenarioRequirements)

        super().__init__(parent, savepoint, name)
        if savepoint:
            assert str(savepoint) == relevant_savepoint
        self._scenario_requirement = scenario_requirement
        self._relevant_savepoint = relevant_savepoint

    @property
    def relevant_savepoint(self):
        return self._relevant_savepoint

    @property
    def requirements(self):
        """
        Collect and yield all requirements of the process.

        :return: An iterator over requirements.
        """
        yield from super().requirements
        yield self._scenario_requirement

    def clone(self):
        new = ScenarioWithRelevance(self.process, self._relevant_savepoint, self._scenario_requirement,
                                    self.savepoint, self.name)
        new.actions = self.actions.clone()
        new.__initial_action = new.actions.initial_action
        return new

    def _broken_defined_processes(self, requirement, processes, model):
        broken = set()
        for name, process in processes.items():
            if not requirement.compatible(name, process.actions):
                broken.add(name)
            elif isinstance(requirement, ScenarioRequirements) and not requirement.compatible_scenario(process) and \
                    (model.savepoint and str(model.savepoint) != requirement.relevant_savepoint):
                broken.add(name)
        return broken


class ReqsExtractor(ScenarioExtractor):
    """
    The factory creates scenarios according to requirements in savepoints.
    """
    # todo: Implement cutting of sequences of subprocesses by checking terminal actions for an operator
    # todo: Remove redundant parentheses if there is a signle action inside

    def __init__(self, logger, process: Process, model: ProcessCollection):
        super().__init__(logger, process, model)
        self._action_requirements = None

    def _process_choice(self, scenario: Scenario, behaviour: Choice, operator: Operator = None):
        assert isinstance(behaviour, Operator), type(behaviour).__name__

        if self._action_requirements:
            # Collect all first actions
            all_first_actions = set()
            options = []
            for child in behaviour:
                next_actions = self._actions.first_actions(root=child, enter_subprocesses=True)
                all_first_actions.update(next_actions)
                options.append((child, next_actions))

            # Check which of them are relevant
            selected = []
            if self._action_requirements[0] in all_first_actions:
                tmp_requirements = list(self._action_requirements)
                while tmp_requirements and tmp_requirements[0] in all_first_actions:
                    option = tmp_requirements[0]
                    for case, first_actions in options:
                        if option in first_actions and case not in selected:
                            selected.append(case)

                            if len(first_actions) == 1 and option in self._action_requirements:
                                # This is a single branch
                                self._action_requirements.remove(option)
                            tmp_requirements.pop(0)
            else:
                selected = [o[0] for o in options]

            # Determine the operator
            if len(selected) == 0:
                raise ValueError(f"Cannot generate scenario for savepoint '{scenario.name}' as requirements are too "
                                 f"strong and do not allow finding a suitable path to a terminal action.")
            elif len(selected) == 1:
                # We use a sequential combination here
                parent = Concatenation()
                scenario.actions.add_process_action(parent)
                operator.append(parent)
            else:
                # We can leave choice here
                parent = scenario.add_action_copy(behaviour, operator)

            for child in selected:
                self._fill_top_down(scenario, child, parent)

            return parent
        else:
            return super()._process_choice(scenario, behaviour, operator)

    def _get_scenarios_for_root_savepoints(self, root: BaseAction):
        # Process savepoints first
        first_actual = self._actions.first_actions(root)
        assert len(first_actual) == 1, 'Support only the one first action'
        actual = self._actions.behaviour(first_actual.pop())
        assert len(actual) == 1, f'Support only the one first action behaviour'
        actual = actual.pop()
        if actual.description.savepoints:
            for savepoint in actual.description.savepoints:
                if str(self._process) in savepoint.requirements.required_processes:
                    action_requirements = savepoint.requirements.required_actions(str(self._process))
                else:
                    action_requirements = []

                self._action_requirements = action_requirements
                new = self._new_scenario_with_relevance(self._actions.initial_action, savepoint, savepoint)
                assert new.name
                yield new

        # Add additional scenarios created for savepoints in other processes
        for process in (p for p in self._model.environment.values() if str(p) != str(self._process)):
            for savepoint in process.savepoints:
                if str(self._process) in savepoint.requirements.required_processes:
                    actions = savepoint.requirements.required_actions(str(self._process))
                    if actions:
                        self._action_requirements = actions
                    else:
                        self._action_requirements = []
                    new = self._new_scenario_with_relevance(self._actions.initial_action, savepoint, None)
                    yield new

    def _new_scenario_with_relevance(self, root: Operator, relevant_savepoint: Savepoint, savepoint: Savepoint = None):
        assert isinstance(relevant_savepoint, Savepoint)
        if savepoint:
            assert str(savepoint) == str(relevant_savepoint)

        relevant_requirements = ScenarioRequirements.override_requirement(relevant_savepoint.requirements,
                                                                          str(relevant_savepoint))

        nsc = ScenarioWithRelevance(self._process, str(relevant_savepoint), relevant_requirements, savepoint)
        if not self._action_requirements:
            path_name = 'base'
        else:
            path_name = '_'.join(self._action_requirements)

        nsc.initial_action = root
        for child in root:
            self._fill_top_down(nsc, child, nsc.initial_action)

        if savepoint:
            nsc.name = f"{str(savepoint)} with {path_name}"
        else:
            nsc.name = f"{path_name} for {str(relevant_savepoint)}"

        return nsc


class ReqsStrategy(SeparationStrategy):
    """
    Strategy that creates Scenario instances for a provided Process instance. Each scenario is used to replace an origin
    process in environment model variants.
    """
    strategy = ReqsExtractor
