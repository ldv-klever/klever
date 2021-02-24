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

from klever.core.vtg.emg.decomposition.scenario import ScenarioExtractor
from klever.core.vtg.emg.decomposition.separation import SeparationStrategy
from klever.core.vtg.emg.common.process.actions import Choice, Subprocess, Actions


class LinearExtractor(ScenarioExtractor):

    def __init__(self, actions: Actions):
        super().__init__(actions)
        self._extra_scenarios = list()

    def _process_choice(self, scenario, beh, operator=None):
        assert isinstance(beh, Choice), type(beh).__name__
        subp = {a.name for a in self._actions.filter(include={Subprocess}) if a.name not in scenario.actions}

        def process_child(scn, child):
            # Check recursion
            names = self._actions.first_actions(child)
            if names.issubset(subp):
                return None

            # Check upper operator
            return self._fill_top_down(scenario, child, operator)

        first = beh[0]
        if len(beh) > 1:
            rest = beh[1:]
        else:
            rest = []

        parent = process_child(scenario, first)
        for another in rest:
            new_scenario = scenario.clone()
            parent = process_child(new_scenario, another)
            if parent:
                self._extra_scenarios.append(new_scenario)

        return parent

    def _get_scenarios_for_root_savepoints(self, root):
        for new in super()._get_scenarios_for_root_savepoints(root):
            yield new
        # Yield additional cases
        while not self._extra_scenarios:
            yield self._extra_scenarios.pop()


class LinearStrategy(SeparationStrategy):

    strategy = LinearExtractor
