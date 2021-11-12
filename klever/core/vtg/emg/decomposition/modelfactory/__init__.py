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
from klever.core.vtg.emg.common.process import Process, ProcessCollection
from klever.core.vtg.emg.decomposition.scenario import Scenario, ScenarioCollection


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
            for scenario, related_process in self._scenarios_with_savepoint.items():
                new = ScenarioCollection(self.model, scenario.name)
                for process in self.model.environment:
                    new.environment[str(process)] = None
                    if scenario in self.processes_to_scenarios[process]:
                        self._assign_scenario(new, scenario, str(process))
                yield new, related_process

    @property
    def _scenarios(self):
        return {s: p for p, group in self.processes_to_scenarios.items() for s in group}

    @property
    def _scenarios_with_savepoint(self):
        return {s: p for s, p in self._scenarios.items() if s.savepoint}

    def _make_base_model(self):
        new = ScenarioCollection(self.model, 'base')
        for model in self.model.models:
            new.models[str(model)] = None
        for process in self.model.environment:
            new.environment[str(process)] = None
        return new

    def _assign_scenario(self, batch: ScenarioCollection, scenario=None, process_name=None):
        if scenario and scenario is not None:
            assert scenario not in batch.environment.values()

        if not process_name:
            batch.entry = scenario
        elif process_name in batch.environment:
            batch.environment[process_name] = scenario
        else:
            raise ValueError(f"Cannot set scenario '{scenario.name}' to deleted process '{process_name}'")

        if scenario:
            assert scenario.name
            assert len(tuple(s for s in batch.environment.values() if isinstance(s, Scenario) and s.savepoint)) <= 1
            batch.extend_model_name(process_name, scenario.name)
        elif batch.attributes.get(process_name):
            del batch.attributes[process_name]
        self.logger.info(f"The new model name is '{batch.attributed_name}'")


def process_dependencies(process):
    """
    Collect dependencies (p->actions) for a given process.

    :param process: Process.
    :return: {p: {actions}}
    """
    # TODO: Remove it
    dependencies_map = dict()
    for action in (a for a in process.actions.values() if a.requirements.relevant_processes):
        for name, v in action.requirements.items():
            dependencies_map.setdefault(name, set())
            dependencies_map[name].update(v.get('include', set()))

    return dependencies_map


def check_process_deps_aginst_model(model, process):
    """
    We have a model and would like to know about its consistency. We would take each process and check that it has all
    necessary in the model.

    :param model: ProcessCollection.
    :param process: Process object.
    :return: Bool
    """
    # TODO: Remove it
    dependencies = process_dependencies(process)
    processes = {str(p): (model.environment[p] if p in model.environment else model.entry)
                 for p, v in model.attributes.items()
                 if v != 'Removed'}
    if not dependencies:
        return True

    for required in dependencies:
        if required in processes and dependencies[required].issubset(set(processes[required].actions.keys())):
            return True
    else:
        return False


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
        yield from self._cached_yield(self._factory_iterator(processes_to_scenarios, model))

    def _factory_iterator(self, processes_to_scenarios: dict, model: ProcessCollection):
        selector = self.strategy(self.logger, self.conf, processes_to_scenarios, model)
        for batch, related_process in selector():
            new = ProcessCollection(batch.name)
            new.attributes = copy.deepcopy(batch.attributes)
            original_name = batch.attributed_name

            # Do sanity check to catch several savepoints in a model
            sp_scenarios = {s for s in batch.environment.values() if isinstance(s, Scenario) and s.savepoint}
            assert len(sp_scenarios) < 2

            # Set entry process
            if related_process and batch.environment[related_process] and batch.environment[related_process].savepoint:
                # There is an environment process with a savepoint
                new.entry = self._process_from_scenario(batch.environment[related_process],
                                                        model.environment[related_process])
                del batch.environment[related_process]
                new.rename_notion(related_process, str(new.entry))

                # Move declarations and definitions
                if model.entry:
                    new.copy_declarations_to_init(model.entry)
            elif batch.entry:
                # The entry process has a scenario
                new.entry = self._process_from_scenario(batch.entry, model.entry)
            elif model.entry:
                # Keep as is
                new.entry = self._process_copy(model.entry)
            else:
                new.entry = None

            # Add models if no scenarios provided
            for function_model in model.models:
                if not batch.models.get(function_model):
                    batch.models[function_model] = None

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
                        self.logger.debug(f"Skip process '{key}' in '{new.attributed_name}'")
                        new.copy_declarations_to_init(getattr(model, attr)[key])

            new.establish_peers()
            self._remove_unused_processes(new)

            if new.consistent:
                if new.attributed_name != original_name:
                    self.logger.info("Reduced batch {!r} to {!r}".format(original_name, new.attributed_name))

                # Add missing attributes to the model
                for process_name in model.environment:
                    added_attributes = []
                    if process_name not in new.attributes:
                        added_attributes.append(process_name)
                        new.extend_model_name(process_name, 'base')
                    added_attributes = ', '.join(added_attributes)
                    self.logger.debug(
                        f"Add to model '{new.attributed_name}' the following attributes: '{added_attributes}'")

                yield new
            else:
                self.logger.debug(f"Obtained model '{new.attributed_name}' is inconsistent")

    def _cached_yield(self, model_iterator):
        model_cache = set()
        for model in model_iterator:
            if model.attributed_name not in model_cache:
                model_cache.add(model.attributed_name)
                yield model
            else:
                self.logger.info("Skip cached model {!r}".format(model.attributed_name))
                continue

    def _process_copy(self, process: Process):
        clone = process.clone()
        return clone

    def _process_from_scenario(self, scenario: Scenario, process: Process):
        new_process = process.clone()

        if len(list(process.labels.keys())) != 0 and len(list(new_process.labels.keys())) == 0:
            assert False, str(new_process)

        new_process.actions = scenario.actions
        new_process.accesses(refresh=True)

        if scenario.savepoint:
            self.logger.debug(f"Replace the first action in the process '{str(process)}' by the savepoint"
                              f" '{str(scenario.savepoint)}'")
            new = new_process.actions.add_condition(str(scenario.savepoint), [], scenario.savepoint.statements,
                                            scenario.savepoint.comment if scenario.savepoint.comment else
                                            f"Save point '{str(scenario.savepoint)}'")
            new.trace_relevant = True
            new._require = scenario.savepoint.requirements
            new._weak_require = scenario.savepoint.weak_requirements

            firsts = scenario.actions.first_actions()
            for name in firsts:
                if isinstance(scenario.actions[name], Receive):
                    new_process.actions.replace_action(new_process.actions[name], new)
                else:
                    new_process.actions.insert_action(new, new_process.actions[name], before=True)
        else:
            self.logger.debug(
                f"Keep the process '{str(process)}' created for the scenario '{str(scenario.name)}' as is")

        return new_process

    def _remove_unused_processes(self, model: ProcessCollection):
        deleted = model.remove_unused_processes()
        deleted_names = ', '.join(map(str, deleted))
        self.logger.info(f"The following processes were deleted from the model '{model.attributed_name}':"
                         f" {deleted_names}")
