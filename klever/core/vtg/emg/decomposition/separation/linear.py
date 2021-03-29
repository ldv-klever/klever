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

import collections

from klever.core.vtg.emg.decomposition.separation import SeparationStrategy
from klever.core.vtg.emg.decomposition.scenario import ScenarioExtractor, Scenario
from klever.core.vtg.emg.common.process.actions import Choice, Actions, Operator, Concatenation, BaseAction, Action


class LinearExtractor(ScenarioExtractor):
    """
    This class implements a factory that generates Scenario instances that do not have choices. Instead the factory
    provides more scenarios that should cover all alternatives from the provided process.
    """

    def __init__(self, actions: Actions):
        super().__init__(actions)
        # This is a list of lists of choice options that we should chooce to reach some uncovered new choices.
        self.__scenario_choices = []
        self.__children_paths = collections.OrderedDict()
        self.__uncovered = None

        # Collect all choices
        self.__reset_covered()

    def _process_choice(self, scenario: Scenario, beh: BaseAction, operator: Operator = None):
        assert isinstance(beh, Choice), type(beh).__name__

        uncovered_children = [c for c in beh[:] if c in self.__uncovered]
        if uncovered_children:
            # Save paths to uncovered choices
            for unovered_child in uncovered_children[1:]:
                self.__children_paths[unovered_child] = list(self.__scenario_choices)
            new_choice = uncovered_children[0]
            self.__uncovered.remove(new_choice)
            if new_choice in self.__children_paths:
                del self.__children_paths[new_choice]
        else:
            current_target = list(self.__children_paths.keys())[0]
            for item in beh:
                if item in self.__children_paths[current_target]:
                    new_choice = item
                    break
            else:
                raise RuntimeError(f'Unknown choice at path to {current_target}')

        self.__scenario_choices.append(new_choice)

        if isinstance(new_choice, Operator):
            return self._fill_top_down(scenario, new_choice, operator)
        else:
            new_operator = scenario.add_action_copy(Concatenation(), operator)
            return self._fill_top_down(scenario, new_choice, new_operator)

    def _get_scenarios_for_root_savepoints(self, root: Action):
        def new_scenarios(rt, svp=None):
            self.__reset_covered()
            while len(self.__uncovered) > 0:
                current = len(self.__uncovered)
                self.__scenario_choices = []
                nsc = self._new_scenario(rt, svp)
                assert len(self.__uncovered) < current, 'Deadlock found'
                yield nsc

        first_actual = self._actions.first_actions(root)
        assert len(first_actual) == 1, 'Support only the one first action'
        actual = self._actions.behaviour(first_actual.pop())
        assert len(actual) == 1, f'Support only the one first action behaviour'
        actual = actual.pop()

        if actual.description.savepoints:
            for savepoint in actual.description.savepoints:
                if self.__uncovered is not None:
                    yield from new_scenarios(self._actions.initial_action, savepoint)
                else:
                    yield new_scenarios(self._actions.initial_action, savepoint)
        else:
            if self.__uncovered is not None:
                yield from new_scenarios(self._actions.initial_action)
            else:
                yield new_scenarios(self._actions.initial_action)

    def __reset_covered(self):
        # Collect all choices
        choices = filter(lambda x: isinstance(x, Choice), self._actions.behaviour())
        if choices:
            self.__uncovered = list()
            for choice in choices:
                self.__uncovered.extend(choice[:])


class LinearStrategy(SeparationStrategy):

    strategy = LinearExtractor
