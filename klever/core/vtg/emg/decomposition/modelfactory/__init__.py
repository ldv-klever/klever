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

from klever.core.vtg.emg.decomposition.scenario import Scenario
from klever.core.vtg.emg.common.process import Dispatch

# todo: Annotate arguments
# todo: Write doc
# todo: What about deterministic choices from sets?
class ModelFactory:

    def __init__(self, logger, conf, model):
        self.conf = conf
        self.logger = logger
        self.origin_model = model

    def generate_models(self, processes_to_scenarios):
        return []

    def _choose_scenarios_for_model(self, processes_to_scenarios):
        root_process = self.origin_model.entry
        pass

    def _find_process_peers(self):
        # todo: Implement a tactic to choose scenarios
        pass

    def _clone_process(self, process):
        # todo: Copy the process completely
        pass

    def _replace_actions(self, process, scenario):
        # todo: Replace actions by the actions from the scenario
        # todo: Find unused labels and delete them also
        pass

    def _prepare_savepoint_block(self, process, savepoint):
        # todo: Determine the initial action
        # todo: Remove it and add a new Block action instead of it
        pass

    def _replace_signal_peers(self, process, old_to_new):
        # todo: Replace old peers with the new ones
        pass


class Selector:

    def __init__(self, logger, conf, processes_to_scenarios):
        self.conf = conf
        self.logger = logger
        self.covered = set()
        self.processes_to_scenarios = processes_to_scenarios

    def generate_models(self):
        # Choose the scenarios with save points
        models = []

    @property
    def _scenarios(self):
        return {s for group in self.processes_to_scenarios.values() for s in group}

    @property
    def _scenarions_with_savepoint(self):
        return {s for s in self._scenarios if s.savepoint}

    @property
    def _uncovered(self):
        return {s for s in self._scenarios if s not in self.covered}

    def _collect_peers(self, sender: Scenario):
        peers = {}
        for dispatch in (d for d in sender.actions.filter(include={Dispatch}) if d.peers):
            for peer in dispatch.peers:
                peers.update(self.processes_to_scenarios[peer['process']])
        return peers

    def _choose_unique_peers(self, scenarios):
        result = set()

        # Get relevant processses
        processes = {p for p in self.processes_to_scenarios if self.processes_to_scenarios[p].intersection(scenarios)}

        # Choose relevant scenarios
        for p in processes:
            choice = self.processes_to_scenarios[p].intersection(scenarios)
            uncovered = choice.intersection(self.covered)
            if uncovered:
                result.add(uncovered.pop())
            else:
                result.add(choice.pop())

        return result

    def _transitive_peers_adding(self, model, entry_scenario):
        senders = [entry_scenario]

        while senders:
            sender = senders.pop()
            receivers = self._collect_peers(sender)
            unique = self._choose_unique_peers(receivers)

            model.environment.update(unique)
            self.covered.update(unique)
            senders.extend([s for s in unique if s not in senders])

    def _cover_savepoints(self):
        # Choose the scenarios with save points
        # todo: We need to add here processes from other categries also
        models = []

        # Cover savepoints
        for s in self._scenarions_with_savepoint:
            models.append(ScenarioCollection(s))
            self.covered.add(s)

        return models

    def _choose_random(self, model, pool: set):
        # todo: Use this in the model broadly
        # todo: Use deterministic choice
        assert pool
        any_random = set(pool).pop()
        self._select_scenario(model, any_random)

    def _select_scenario(self, model, scenario: Scenario):
        assert scenario
        assert scenario not in model.environment
        self.covered.add(scenario)
        model.environment.add(scenario)

    def _cover_rest(self):
        # todo: Reimplement the function to use it for adding scenarios from different categries to models wit savepoint
        # entries
        models = []

        # We must cover all scenarios, so do this in the loop
        while self._uncovered:
            # Create a new model
            new_model = ScenarioCollection()

            # Get the list of categories that have at least one environment process
            categories = {p.category for p in self.processes_to_scenarios}
            scenario_to_category = {s: p.category for p in self.processes_to_scenarios
                                    for s in self.processes_to_scenarios[p].intersection(self._uncovered)}

            # Repeate for all categories fot this model (uncovered in the model!). Processes from different categories
            # can send signals implicitly from executed kernel functions. We cannot catch this from out data structures
            # so we must add processes from all categories.
            while categories:
                category = categories.pop()
                # Now we should choose a scenario that does not send anything. Check some uncovered processes and find a
                # suitable scenario.

                # First get the list od scenarios which are relevant to the category and uncovered.
                relevant = {s for s in scenario_to_category
                            if scenario_to_category[s] == category}.intersection(self._uncovered)
                if relevant:
                    # Select one that has no dispatches.
                    without_dispatches = {s for s in relevant if not s.actions.filter(include={Dispatch})}
                    if without_dispatches:
                        choice = without_dispatches.pop()
                        self._select_scenario(new_model, choice)
                    else:
                        # Ok, then choose one that send signals to uncvered processes
                        for scenario in relevant:
                            peers = self._collect_peers(scenario)
                            if peers:
                                unique = self._choose_unique_peers(peers)
                                if unique:
                                    new_model.environment.update(unique)
                                    self.covered.update(unique)
                                    break
                        else:
                            # Ok, we do not have any interesting processes. Then add any
                            self._choose_random(new_model, relevant)
                else:
                    # Hmm, seems that we can choose any
                    self._choose_random(new_model, relevant)

        return models


class ScenarioCollection:

    def __init__(self, entry=None, models=None, environment=None):
        self.entry = entry
        self.models = models if isinstance(models, set) else set()
        self.environment = environment if isinstance(environment, set) else set()
