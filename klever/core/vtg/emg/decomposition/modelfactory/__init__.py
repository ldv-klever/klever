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

import logging

from klever.core.vtg.emg.common.process.actions import Receive
from klever.core.vtg.emg.decomposition.scenario import Scenario
from klever.core.vtg.emg.common.process import Process, ProcessCollection


class ScenarioCollection:
    """
    This is a collection of scenarios. The factory generated the model with processes that have provided keys. If a
    process have a key in the collection but the value is None, then the factory will use the origin process. Otherwise,
    it will use a provided scenario.
    """

    def __init__(self, name, entry=None, models=None, environment=None):
        assert isinstance(name, str) or isinstance(name, int)
        self.name = name
        self.entry = entry
        self.models = models if isinstance(models, dict) else dict()
        self.environment = environment if isinstance(environment, dict) else dict()


class Selector:
    """
    A simple implementation that chooses a scenario with a savepoint and uses only it for a new model. Other processes
    are kept without changes. An origin model is also used.
    """

    def __init__(self, logger: logging.Logger, conf: dict, processes_to_scenarios: dict, model: ProcessCollection):
        self.conf = conf
        self.logger = logger
        self.model = model
        self.processes_to_scenarios = processes_to_scenarios

    def __call__(self, *args, **kwargs):
        if not self.conf.get('skip origin model'):
            yield self._make_base_model()
        if not self.conf.get('skip savepoints'):
            for scenario in self._scenarions_with_savepoint:
                new = ScenarioCollection(scenario.name)
                new.entry = scenario

                for model in self.model.models:
                    new.models[str(model)] = None
                for process in self.model.environment:
                    if scenario not in self.processes_to_scenarios[process]:
                        new.environment[str(process)] = None
                yield new

    @property
    def _scenarios(self):
        return {s for group in self.processes_to_scenarios.values() for s in group}

    @property
    def _scenarions_with_savepoint(self):
        return {s for s in self._scenarios if s.savepoint}

    def _make_base_model(self):
        new = ScenarioCollection(0)
        for model in self.model.models:
            new.models[str(model)] = None
        for process in self.model.environment:
            new.environment[str(process)] = None
        return new


class ModelFactory:
    """
    The factory gets a map from processes to scenarios. It runs a strategy that chooses scenarios per a model and
    generates then final models.
    """

    strategy = Selector

    def __init__(self, logger: logging.Logger, conf: dict):
        self.conf = conf
        self.logger = logger

    def __call__(self, processes_to_scenarios: dict, model: ProcessCollection):
        selector = self.strategy(self.logger, self.conf, processes_to_scenarios, model)
        for batch in selector():
            new = ProcessCollection(batch.name)

            if batch.entry:
                new.entry = self._process_from_scenario(batch.entry, model.entry)
            else:
                new.entry = self._process_copy(model.entry)

            for attr in ('models', 'environment'):
                collection = getattr(batch, attr)
                for key, scenario in collection.items():
                    if scenario:
                        collection[key] = self._process_from_scenario(scenario, getattr(model, attr)[key])

            new.establish_peers()
            self._remove_unused_processes(new)

            yield new

    def _process_copy(self, process: Process):
        return process.clone()

    def _process_from_scenario(self, scenario: Scenario, process: Process):
        new_process = process.clone()
        new_process.actions = scenario.actions

        new = new_process.add_condition('savepoint', [], scenario.savepoint.statements,
                                        f'Save point {str(scenario.savepoint)}')

        firsts = scenario.actions.first_actions()
        for name in firsts:
            new_process.replace_action(new_process.actions[name], new)

        return new_process

    def _remove_unused_processes(self, model: ProcessCollection):
        for key, process in model.environment.items():
            receives = set(map(str, process.actions.filter(include={Receive})))
            all_peers = {a for acts in process.peers.values() for a in acts}

            if not receives.intersection(all_peers):
                del model.environment[key]

        model.establish_peers()
