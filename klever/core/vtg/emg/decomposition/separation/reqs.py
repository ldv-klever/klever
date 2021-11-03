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

from klever.core.vtg.emg.decomposition.scenario import Scenario
from klever.core.vtg.emg.decomposition.separation import SeparationStrategy, ScenarioExtractor
from klever.core.vtg.emg.common.process import Process, ProcessCollection
from klever.core.vtg.emg.common.process.actions import Choice, Operator, Concatenation, Savepoint, BaseAction


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

                            if len(first_actions) == 1:
                                # This is a single branch
                                self._action_requirements.pop(0)
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

                new = self._new_scenario(self._actions.initial_action, savepoint)
                assert new.name
                yield new

        # Add additional scenarios created for savepoints in other processes
        for process in (p for p in self._model.environment.values() if str(p) != str(self._process)):
            for savepoint in process.savepoints:
                if str(self._process) in savepoint.requirements.required_processes:
                    actions = savepoint.requirements.required_actions(str(self._process))
                    if actions:
                        self._action_requirements = actions
                        new = self._new_scenario(self._actions.initial_action, None)
                        new.name = f'for_{str(savepoint)}'
                        yield new


class ReqsStrategy(SeparationStrategy):
    """
    Strategy that creates Scenario instances for a provided Process instance. Each scenario is used to replace an origin
    process in environment model variants.
    """
    strategy = ReqsExtractor
