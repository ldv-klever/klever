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
        assert isinstance(name, str)
        self.name = name
        self.entry = entry
        self.models = models if isinstance(models, dict) else dict()
        self.environment = environment if isinstance(environment, dict) else dict()

    def clone(self, new_name: str):
        """
        Copy the collection with a new name.

        :param new_name: Name string.
        :return: ScenarioCollection instance.
        """
        new = ScenarioCollection(new_name)
        new.entry = self.entry.clone() if self.entry else None
        for collection in ('models', 'environment'):
            for key in getattr(self, collection):
                if getattr(self, collection)[key]:
                    getattr(new, collection)[key] = getattr(self, collection)[key].clone()
                else:
                    getattr(new, collection)[key] = None
        return new


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
        yield from self._iterate_over_base_models(include_base_model=not self.conf.get('skip origin model'),
                                                  include_savepoints=not self.conf.get('skip savepoints'))

    def _iterate_over_base_models(self, include_base_model=True, include_savepoints=True):
        if include_base_model:
            yield self._make_base_model(), None
        if include_savepoints:
            for scenario, related_process in self._scenarions_with_savepoint.items():
                new = ScenarioCollection(scenario.name)
                new.entry = scenario

                for model in self.model.models:
                    new.models[model] = None
                for process in self.model.environment:
                    if str(process) == related_process:
                        continue
                    if scenario not in self.processes_to_scenarios[process]:
                        new.environment[str(process)] = None
                yield new, related_process

    @property
    def _scenarios(self):
        return {s: p for p, group in self.processes_to_scenarios.items() for s in group}

    @property
    def _scenarions_with_savepoint(self):
        return {s: p for s, p in self._scenarios.items() if s.savepoint}

    def _make_base_model(self):
        new = ScenarioCollection('base')
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
        for batch, related_process in selector():
            new = ProcessCollection(batch.name)

            if batch.entry:
                new.entry = self._process_from_scenario(batch.entry, model.environment[related_process])
            else:
                new.entry = self._process_copy(model.entry)

            for attr in ('models', 'environment'):
                batch_collection = getattr(batch, attr)
                collection = getattr(new, attr)
                for key in getattr(model, attr):
                    if key in batch_collection:
                        if batch_collection[key]:
                            collection[key] = self._process_from_scenario(batch_collection[key],
                                                                          getattr(model, attr)[key])
                        else:
                            collection[key] = self._process_copy(getattr(model, attr)[key])
                    else:
                        self.logger.debug(f"Skip process {key} in {new.name}")

            new.establish_peers()
            self._remove_unused_processes(new)

            yield new

    def _process_copy(self, process: Process):
        clone = process.clone()
        return clone

    def _process_from_scenario(self, scenario: Scenario, process: Process):
        new_process = process.clone()

        if len(list(process.labels.keys())) == 0 and len(list(new_process.labels.keys())) == 0:
            assert False, str(new_process)

        new_process.actions = scenario.actions
        new_process.accesses(refresh=True)

        if scenario.savepoint:
            self.logger.debug(f'Replace the first action in the process {str(process)} by the savepoint'
                              f' {str(scenario.savepoint)}')
            new = new_process.add_condition('savepoint', [], scenario.savepoint.statements,
                                            f'Save point {str(scenario.savepoint)}')

            firsts = scenario.actions.first_actions()
            for name in firsts:
                if isinstance(scenario.actions[name], Receive):
                    new_process.replace_action(new_process.actions[name], new)
                else:
                    new_process.insert_action(new, new_process.actions[name], before=True)
        else:
            self.logger.debug(f'Keep the process {str(process)} created for the scenario {str(scenario.name)} as is')

        return new_process

    def _remove_unused_processes(self, model: ProcessCollection):
        for key, process in model.environment.items():
            receives = set(map(str, process.actions.filter(include={Receive})))
            all_peers = {a for acts in process.peers.values() for a in acts}

            if not receives.intersection(all_peers):
                self.logger.info(f'Delete process {key} from the model {model.name} as it has no peers')
                del model.environment[key]

        model.establish_peers()
