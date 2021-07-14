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


def extend_model_name(model, process_name, attribute):
    assert model
    assert isinstance(model, (ProcessCollection, ScenarioCollection))
    assert isinstance(process_name, str) and isinstance(attribute, str)
    model.attributes[process_name] = attribute


def remove_process(model, process_name):
    assert process_name and process_name in model.environment
    del model.environment[process_name]
    extend_model_name(model, process_name, 'Removed')


def process_dependencies(process):
    """
    Collect dependnecies (p->actions) for a given process.

    :param process: Process.
    :return: {p: {actions}}
    """
    dependencies_map = dict()
    for action in (a for a in process.actions.values() if a.require):
        for name, v in action.require.items():
            dependencies_map.setdefault(name, set())
            dependencies_map[name].update(v.get('include', set()))

    return dependencies_map


def all_dependencies(processes: set):
    """
    Collect dependencies of all processes together.

    :param processes: set of Process objects.
    :return: {p: {required: {required_actions}}}
    """
    dependencies_map = dict()
    for process in processes:
        dependencies_map.setdefault(str(process), dict())
        dependencies_map[str(process)].update(process_dependencies(process))

    return dependencies_map


def process_transitive_dependencies(processes: set, process: Process, scenario: Scenario = None):
    """
    Collect dependencies transitively of a given process.

    :param processes: Set of Process objects to search dependencies.
    :param process: Process object.
    :param scenario: Its scenario that may have less actions.
    :return: {required: {required_actions}}
    """
    assert process in processes or scenario in processes
    processes_map = {str(p): p for p in processes}

    name = str(process)
    if not scenario:
        scenario = process
    processes_map[name] = scenario

    ret_deps = dict()
    processed = set()
    todo = [name]
    while todo:
        p_name = todo.pop()
        p = processes_map[p_name]
        deps = process_dependencies(p)
        for required_name in deps:
            if required_name in processed:
                raise RecursionError(f'Recursive dependencies for {required_name} calculated for {str(scenario)}')
            elif required_name in todo:
                pass
            else:
                todo.append(required_name)

            ret_deps.setdefault(required_name, set())
            ret_deps[required_name].update(deps[required_name])
    return ret_deps


def all_transitive_dependencies(processes: set, selected: set = None):
    """
    Collect transitive dependencies for selected processes/scenarios. If selected = None, then all processes are
    selected.

    :param processes: Set of Process objects.
    :param selected: Set of Process objects for which is needed to search dependencies.
    :return: {p: {required: {required_actions}}}
    """
    if not selected:
        selected = processes
    assert selected.issubset(processes)

    deps = dict()
    for selected_process in selected:
        selected_deps = process_transitive_dependencies(processes, selected_process)
        deps[str(selected_process)] = selected_deps
    return deps


def is_required(dependencies: dict, process: Process, scenario: Scenario = None):
    """
    Check that particular process or even its scenario is required by anybody in given dependencies.

    :param dependencies: Dict created by functions defined above.
    :param process: Process.
    :param scenario: Scenario object.
    :return: bool.
    """
    name = str(process)
    actions = set((scenario.actions if scenario else process.actions).keys())

    for entry in dependencies:
        if name in dependencies[entry] and dependencies[entry][name].issubset(actions):
            return True
    return False


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
        self.attributes = dict()

    attributed_name = ProcessCollection.attributed_name

    def clone(self, new_name: str):
        """
        Copy the collection with a new name.

        :param new_name: Name string.
        :return: ScenarioCollection instance.
        """
        new = ScenarioCollection(new_name)
        new.attributes = dict(self.attributes)
        new.entry = self.entry.clone() if self.entry else None
        for collection in ('models', 'environment'):
            for key in getattr(self, collection):
                if getattr(self, collection)[key]:
                    getattr(new, collection)[key] = getattr(self, collection)[key].clone()
                else:
                    getattr(new, collection)[key] = None
        return new

    @property
    def defined_processes(self):
        return {name for name, val in self.environment.items() if val}


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
                for process in self.model.environment:
                    new.environment[str(process)] = scenario
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

    def _assign_scenario(self, batch: ScenarioCollection, scenario=None, process_name=None):
        if not process_name:
            batch.entry = scenario
        elif process_name in batch.environment:
            batch.environment[process_name] = scenario
        else:
            raise ValueError(f'Cannot set scenario {scenario.name} to deleted process {process_name}')

        if scenario:
            assert scenario.name
            extend_model_name(batch, process_name, scenario.name)
        self.logger.info(f'The new model name is "{batch.attributed_name}"')


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
                # There is an environment process with a scenario
                new.entry = self._process_from_scenario(batch.environment[related_process],
                                                        model.environment[related_process])
                del batch.environment[related_process]
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
                        self.logger.debug(f"Skip process {key} in {new.attributed_name}")

            new.establish_peers()
            self._remove_unused_processes(new)

            if new.attributed_name != original_name:
                self.logger.info('Reduced batch {!r} to {!r}'.format(original_name, new.attributed_name))
            yield new

    def _cached_yield(self, model_iterator):
        model_cache = set()
        for model in model_iterator:
            if model.attributed_name not in model_cache:
                model_cache.add(model.attributed_name)
                yield model
            else:
                self.logger.info('Skip cached model {!r}'.format(model.attributed_name))
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
            self.logger.debug(f'Replace the first action in the process {str(process)} by the savepoint'
                              f' {str(scenario.savepoint)}')
            new = new_process.add_condition(str(scenario.savepoint), [], scenario.savepoint.statements,
                                            scenario.savepoint.comment if scenario.savepoint.comment else
                                            f'Save point {str(scenario.savepoint)}')
            new.trace_relevant = True

            firsts = scenario.actions.first_actions()
            for name in firsts:
                if isinstance(scenario.actions[name], Receive):
                    new_process.replace_action(new_process.actions[name], new)
                else:
                    new_process.insert_action(new, new_process.actions[name], before=True)
        else:
            self.logger.debug(f'Keep the process "{str(process)}" created for the scenario "{str(scenario.name)}" as is')

        return new_process

    def _remove_unused_processes(self, model: ProcessCollection):
        for key, process in model.environment.items():
            receives = set(map(str, process.actions.filter(include={Receive})))
            all_peers = {a for acts in process.peers.values() for a in acts}

            if not receives.intersection(all_peers):
                self.logger.info(f'Delete process {key} from the model {model.attributed_name} as it has no peers')
                remove_process(model, key)

        model.establish_peers()
