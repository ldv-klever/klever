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

from klever.core.vtg.emg.decomposition.scenario import Scenario
from klever.core.vtg.emg.common.process.actions import Subprocess
from klever.core.vtg.emg.decomposition.modelfactory import Selector, ModelFactory, remove_process


class SelectiveSelector(Selector):

    def __call__(self, *args, **kwargs):
        must_contain = self.conf.get("must contain", dict())
        must_not_contain = self.conf.get("must not contain", dict())
        cover_conf = self.conf.get("cover scenarios", dict())
        greedy = self.conf.get("greedy selection", False)

        self._sanity_check_must_contain(must_contain)
        self._sanity_check_must_not_contain(must_not_contain)

        self.logger.info("Collect dependencies between processes")
        dependencies_map, dependant_map = self._extract_dependecnies()

        deleted_processes, order = self._calculate_process_order(must_contain, must_not_contain, cover_conf,
                                                                 dependant_map)
        self.logger.info("Order of process iteration is: " + ', '.join(order))

        # Prepare coverage
        self.logger.info("Prepare detailed coverage descriptions per process")
        coverage = self._prepare_coverage(cover_conf)

        # Prepare the initial base models
        first_model = self._make_base_model()
        for process_name in deleted_processes:
            remove_process(first_model, process_name)

        # Iterate over processes
        model_pool = []
        while order:
            process_name = order.pop(0)
            self.logger.info(f"Consider scenarios of process {process_name}")

            # Get all scenarios
            scenarios_items = set(list(self.processes_to_scenarios[process_name]) +
                                  [self.model.environment[process_name]])

            # Filter by "must contain"
            scenarios_items = self._filter_must_contain_base_process(process_name, scenarios_items, must_contain)
            scenarios_items = self._filter_must_contain_actions(process_name, scenarios_items, must_contain)
            scenarios_items = self._filter_must_contain_savepoints(process_name, scenarios_items, must_contain)

            # Filter by "must not contain"
            scenarios_items = self._filter_must_not_contain_actions(process_name, scenarios_items, must_not_contain)
            scenarios_items = self._filter_must_not_contain_savepoints(process_name, scenarios_items, must_not_contain)

            next_model_pool = list()
            if not model_pool:
                self.logger.info("Expect this is a first considered process")
                iterate_over_models = [first_model]
            else:
                # Do not modify model pool by adding the very first model, it is undesirable
                iterate_over_models = model_pool

            for model in iterate_over_models:
                self.logger.info(f"Consider adding scenarios to model {model.attributed_name}")
                local_model_pool = list()
                local_coverage = copy.deepcopy(coverage)

                if process_name in local_coverage:
                    # Filter scenarios with savepoints if there is one already
                    scenarios_items_for_model = self._filter_by_savepoints_in_model(model, scenarios_items)
                else:
                    # Remove savepoints if this process is not required to cover
                    scenarios_items_for_model = {s for s in scenarios_items
                                                 if not isinstance(s, Scenario) or not s.savepoint}

                # Filter by requirements of already added processes
                scenarios_items_for_model = self._filter_by_requirements_from_model(
                    process_name, model, scenarios_items_for_model, dependant_map, dependencies_map, order,
                    deleted_processes)

                # Filter by requirements from considered scenarios
                scenarios_items_for_model = self._check_by_requirements_of_scenario(
                    process_name, model, scenarios_items_for_model, dependencies_map, order, deleted_processes)

                # Iteratively copy models to fill the coverage
                if not scenarios_items_for_model and process_name not in must_contain:
                    self.logger.warning(f'Cannot find any suitable scenarios of process {process_name} suitable for '
                                        f'model {model.attributed_name}, deleting it')
                    remove_process(model, process_name)
                    next_model_pool.append(model)
                    continue
                elif not scenarios_items_for_model and process_name in must_contain:
                    raise ValueError(f"Cannot delete required process {process_name} as it has no suitable scenarios "
                                     f"for {model.attributed_name}")

                scenarios_items_for_model = self._obtain_ordered_scenarios(
                    scenarios_items_for_model,
                    list(local_coverage[process_name].values())[-1] if process_name in local_coverage else None, greedy)
                while (process_name in local_coverage or not local_model_pool) and scenarios_items_for_model:
                    scenario = scenarios_items_for_model.pop(0)

                    if process_name not in local_coverage:
                        new = self._clone_model_with_scenario(process_name, model, scenario)
                        self.logger.info(f"Process {process_name} can be covered by any scenario as it is not required "
                                         f"to cover")
                        local_model_pool.append(new)
                        break
                    elif self._check_coverage_impact(process_name, local_coverage[process_name], scenario):
                        new = self._clone_model_with_scenario(process_name, model, scenario)
                        self.logger.info(f'Add a new model {new.attributed_name}')
                        local_model_pool.append(new)
                    else:
                        self.logger.info(f'Skip scenario {scenario.name} of {process_name} '
                                         f'as it has no coverage impact')
                next_model_pool.extend(local_model_pool)

            model_pool = next_model_pool

        if not model_pool:
            self.logger.info('No models have been selected, use the base one')
            model_pool = [first_model]
        for model in model_pool:
            related_process = None
            for process_name in (p for p, s in model.environment.items() if s and s.savepoint):
                related_process = process_name
                break

            if not related_process and not self.model.entry:
                self.logger.warning(f"Skip model {model.attributed_name} as it has no savepoints and the entry process")
                continue

            self.logger.info(f"Finally return a batch for model {model.attributed_name}")
            yield model, related_process

    def _sanity_check_must_contain(self, must_contain):
        for process_name in must_contain:
            assert process_name in self.model.environment, f'There is no process {process_name} in the model'

            if 'actions' in must_contain[process_name]:
                assert isinstance(must_contain[process_name]['actions'], list), 'Provide a list of lists to the ' \
                                                                                '"must contain" parameter'

                for item in must_contain[process_name].get('actions', []):
                    assert isinstance(item, list), 'Provide a list of lists to the "must contain" parameter'

                    for action_name in item:
                        assert isinstance(action_name, str) and \
                               action_name in self.model.environment[process_name].actions, \
                               f"There is no action {action_name} in {process_name}"

            if 'savepoints' in must_contain[process_name]:
                assert isinstance(must_contain[process_name]['savepoints'], list), \
                    'Provide a list of savepoints to the "must contain" parameter'

                for item in must_contain[process_name]['savepoints']:
                    assert isinstance(item, str), \
                           "Provide a list of savepoints' names to the 'must contain' parameter"

    def _sanity_check_must_not_contain(self, must_not_contain):
        for process_name in must_not_contain:
            assert process_name in self.model.environment, f'There is no process {process_name} in the model'

            for item in must_not_contain[process_name].get('actions', []):
                assert isinstance(item, list), 'Provide a list of lists to the "must not contain" parameter'

                for action_name in item:
                    assert isinstance(action_name, str) and \
                           action_name in action_name in self.model.environment[process_name].actions, \
                           f"There is no action {action_name} in {process_name}"

            if 'savepoints' in must_not_contain[process_name]:
                assert isinstance(must_not_contain[process_name]['savepoints'], list), \
                    'Provide a list of savepoints to the "must not contain" parameter'

                for item in must_not_contain[process_name]['savepoints']:
                    assert isinstance(item, str), \
                        "Provide a list of savepoints' names to the 'must not contain' parameter"

    def _extract_dependecnies(self):
        # This map contains a map from processes to actions that contains requirements
        dependencies_map = dict()

        # This map allows to determine which processes are required by any other. Such required processes are set as
        # keys
        dependant_map = dict()
        for process in self.model.environment.values():
            action_names = [str(a) for a in process.actions if process.actions[a].require]
            if action_names:
                self.logger.info(f"Process {process} has requirements in the following actions: " +
                                 ", ".join(action_names))
                dependencies_map[str(process)] = action_names

                for action in action_names:
                    for dependant in process.actions[action].require.keys():
                        dependant_map.setdefault(dependant, set())
                        dependant_map[dependant].add(str(process))

        return dependencies_map, dependant_map

    def _calculate_process_order(self, must_contain, must_not_contain, cover_conf, dependant_map):
        # These processes will be deleted from models at all
        deleted_processes = set()

        # Determine the order to iterate over the processes
        todo = set(self.model.environment.keys())
        to_cover = todo.intersection(cover_conf.keys())
        todo.difference_update(to_cover)
        order = []
        for process_name in to_cover:
            if process_name in must_not_contain and len(must_not_contain[process_name].keys()) == 0:
                if process_name in must_contain or process_name in dependant_map:
                    raise ValueError(f'Cannot cover {process_name} as it is given in "must not contain" configuration '
                                     f'and required by other configurations')
                else:
                    continue
            else:
                order.append(process_name)

        for process_name in (p for p in list(todo) if p in must_not_contain and len(must_not_contain[p].keys()) == 0):
            deleted_processes.add(process_name)
            todo.remove(process_name)
        else:
            self.logger.info(f"Delete processes: " + ", ".join(sorted(deleted_processes)))

        order.extend(list(todo))
        return deleted_processes, order

    def _prepare_coverage(self, cover_conf):
        coverage = dict()
        for process_name in cover_conf:
            # Subprocesses may not be covered in scenarios, so avoid adding the origin process to cover them
            assert process_name in self.model.environment, f'There is no process {process_name} in the model'
            actions = set(str(a) for a in self.model.environment[process_name].actions.filter(exclude={Subprocess}))
            savepoints = {str(sp) for ac in self.model.environment[process_name].actions.values()
                          for sp in ac.savepoints}

            if 'actions' in cover_conf[process_name]:
                assert(isinstance(cover_conf[process_name]['actions'], list))
                for item in cover_conf[process_name]['actions']:
                    assert isinstance(item, str) and item in self.model.environment[process_name].actions, \
                        f"There is no action {item} in {process_name}"
                actions_to_cover = set(cover_conf[process_name]['actions'])
            else:
                actions_to_cover = actions

            if cover_conf[process_name].get('actions except'):
                actions_to_cover.difference_update(set(cover_conf[process_name]['actions except']))

            if 'savepoints' in cover_conf[process_name]:
                assert (isinstance(cover_conf[process_name]['savepoints'], list))
                for item in cover_conf[process_name]['savepoints']:
                    assert isinstance(item, str) and item in map(str, self.model.environment[process_name].savepoints),\
                        f"There is no savepoint {item} in {process_name}"
                sp_to_cover = set(cover_conf[process_name]['savepoints'])
            else:
                sp_to_cover = savepoints

            if cover_conf[process_name].get('savepoints except'):
                assert (isinstance(cover_conf[process_name]['savepoints except'], list))
                for item in cover_conf[process_name]['savepoints except']:
                    assert isinstance(item, str) and item in map(str, self.model.environment[process_name].savepoints),\
                        f"There is no savepoint {item} in {process_name}"
                sp_to_cover.difference_update(set(cover_conf[process_name]['savepoints except']))

            self.logger.info(f"Cover the following actions from the process {process_name}: " +
                             ", ".join(sorted(actions_to_cover)))
            self.logger.info(f"Cover the following savepoints from the process {process_name}: " +
                             ", ".join(sorted(sp_to_cover)))

            # Now split coverage according to required savepoints
            coverage[process_name] = {process_name: set(actions_to_cover)}
            for sp in sp_to_cover:
                coverage[process_name][sp] = set(actions_to_cover)

        return coverage

    def _filter_must_contain_base_process(self, process_name, scenarios_items, must_contain):
        if process_name not in must_contain or must_contain[process_name].get('scenarios only', True):
            self.logger.debug(f"Remove base process {process_name} as only scenarios can be selected")
            return {s for s in scenarios_items if isinstance(s, Scenario)}
        else:
            return scenarios_items

    def _filter_must_contain_actions(self, process_name, scenarios_items, must_contain):
        if process_name in must_contain and must_contain[process_name].get('actions'):
            new_scenarios_items = set()

            for suitable in scenarios_items:
                for action_set in must_contain[process_name]['actions']:
                    if set(action_set).issubset(set(suitable.actions.keys())):
                        new_scenarios_items.add(suitable)
            self.logger.debug(f"{process_name.capitalize()} has the fowllowing scenarios with required actions: " +
                              ', '.join(list(map(str, new_scenarios_items))))
            return new_scenarios_items
        else:
            return scenarios_items

    def _filter_must_contain_savepoints(self, process_name, scenarios_items, must_contain):
        if process_name in must_contain and must_contain[process_name].get('savepoints'):
            new_scenarios_items = set()

            for suitable in (s for s in scenarios_items if isinstance(s, Scenario) and
                             str(s.savepoint) in must_contain[process_name]['savepoints']):
                new_scenarios_items.add(suitable)

            self.logger.debug(f"{process_name.capitalize()} has the fowllowing scenarios with required savepoints: " +
                              ', '.join(list(map(str, new_scenarios_items))))
            return new_scenarios_items
        else:
            return scenarios_items

    def _filter_must_not_contain_actions(self, process_name, scenarios_items, must_not_contain):
        if process_name in must_not_contain and must_not_contain[process_name].get('actions'):
            new_scenarios_items = set()

            for suitable in scenarios_items:
                add_flag = True

                for action_set in must_not_contain[process_name]['actions']:
                    if set(action_set).issubset(set(suitable.actions.keys())):
                        add_flag = False

                if add_flag:
                    new_scenarios_items.add(suitable)

            self.logger.debug(f"{process_name.capitalize()} has the fowllowing scenarios without forbidden actions: " +
                              ', '.join(list(map(str, new_scenarios_items))))
            return new_scenarios_items
        else:
            return scenarios_items

    def _filter_must_not_contain_savepoints(self, process_name, scenarios_items, must_not_contain):
        if process_name in must_not_contain and must_not_contain[process_name].get('savepoints'):
            new_scenarios_items = set()

            for suitable in scenarios_items:
                if isinstance(suitable, Scenario) and \
                        str(suitable.savepoint) in must_not_contain[process_name]['savepoints']:
                    continue
                else:
                    new_scenarios_items.add(suitable)

            self.logger.debug(f"{process_name.capitalize()} has the fowllowing scenarios without forbidden "
                              f"savepoints: " + ', '.join(list(map(str, new_scenarios_items))))
            return new_scenarios_items
        else:
            return scenarios_items

    def _filter_by_savepoints_in_model(self, model, scenarios_items):
        exists_savepoint = False
        for scenario in model.environment.values():
            if isinstance(scenario, Scenario) and scenario.savepoint:
                exists_savepoint = True
                break

        if exists_savepoint:
            self.logger.debug(f"Model {model.attributed_name} has a savepoint already")
            new_scenarios_items = {s for s in scenarios_items if not isinstance(s, Scenario) or not s.savepoint}
            return new_scenarios_items
        else:
            self.logger.debug(f"Model {model.attributed_name} has not a savepoint")
            return scenarios_items

    def _filter_by_requirements_from_model(self, process_name, model, scenarios_items, dependant_map, dependencies_map,
                                           order, deleted):
        if process_name in dependant_map:
            new_scenarios_items = set()

            for suitable in scenarios_items:
                accept_flag = True

                for proc_with_reqs in dependant_map[process_name]:
                    if proc_with_reqs in order or proc_with_reqs in deleted:   # We not traversed it or deleted
                        self.logger.debug(f"Skip requirements of {proc_with_reqs} for {process_name}")
                        continue

                    # Actions of the process with requirements
                    actions_with_requirements = model.environment[proc_with_reqs].actions \
                        if model.environment[proc_with_reqs] else self.model.environment[proc_with_reqs].actions

                    for action in (a for a in dependencies_map[proc_with_reqs]
                                   if a in actions_with_requirements and
                                   actions_with_requirements[a].require.get(process_name)):
                        self.logger.debug(f'Found requirements for {process_name} in {action} of {proc_with_reqs}')
                        if not set(actions_with_requirements[action].require[process_name]["include"]). \
                                issubset(set(suitable.actions.keys())):
                            self.logger.info(f"Cannot add {suitable.name} of {process_name} because "
                                             f"of {action} of {proc_with_reqs}")
                            accept_flag = False

                if accept_flag:
                    new_scenarios_items.add(suitable)

            return new_scenarios_items
        else:
            return scenarios_items

    def _check_by_requirements_of_scenario(self, process_name, model, scenario_items, dependencies_map, order, deleted):
        if process_name in dependencies_map:
            new_scenario_items = set()

            for scenario in scenario_items:
                add_flag = True

                for action_name in (a for a in dependencies_map[process_name] if a in scenario.actions):
                    for asked_process in scenario.actions[action_name].require:
                        if asked_process in deleted:
                            self.logger.info(f"Cannot add {scenario.name} of {process_name} because "
                                             f"{asked_process} is deleted")
                            add_flag = False
                            continue
                        if asked_process in order:
                            # Have not been considered yet
                            continue

                        required_actions = scenario.actions[action_name].require[asked_process]["include"]
                        if asked_process in model.environment:
                            considered_actions = model.environment[asked_process].actions \
                                if model.environment[asked_process] else self.model.environment[asked_process].actions
                        elif asked_process == str(self.model.entry):
                            considered_actions = model.entry.actions if model.entry else self.model.entry.actions
                        else:
                            raise ValueError(f'Cannot find a process with name {asked_process} in the model at all')
                        if not set(required_actions).issubset(set(considered_actions.keys())):
                            self.logger.info(f"Cannot add {scenario.name} of {process_name} because "
                                             f"{asked_process} does not satisfy required creteria of inclusion: " +
                                             ", ".join(required_actions))
                            add_flag = False

                if add_flag:
                    new_scenario_items.add(scenario)

            return new_scenario_items
        else:  # Has no dependencies
            return scenario_items

    def _obtain_ordered_scenarios(self, scenarios_set, coverage=None, greedy=False):
        new_scenario_set = [s for s in scenarios_set if isinstance(s, Scenario)]
        if coverage:
            new_scenario_set = sorted(new_scenario_set, key=lambda x: len(set(x.actions.keys()).intersection(coverage)),
                                      reverse=greedy)
        else:
            new_scenario_set = sorted(new_scenario_set, key=lambda x: len(x.actions.keys()), reverse=greedy)
        new_scenario_set.extend([x for x in scenarios_set if x not in new_scenario_set])
        return new_scenario_set

    def _check_coverage_impact(self, process_name, coverage, scenario):
        if (isinstance(scenario, Scenario) and not scenario.savepoint) or not isinstance(scenario, Scenario):
            uncovered_actions = coverage[process_name]
        elif isinstance(scenario, Scenario) and scenario.savepoint and str(scenario.savepoint) in coverage:
            uncovered_actions = coverage[str(scenario.savepoint)]
        else:
            return False

        impact = uncovered_actions.intersection(set(scenario.actions.keys()))
        if uncovered_actions and impact:
            self.logger.debug(f"Coverage impact of scenario {scenario.name} of {process_name} is: " + ', '.join(impact))
            uncovered_actions.difference_update(impact)

            if isinstance(scenario, Scenario) and scenario.savepoint and str(scenario.savepoint) in coverage and \
                    not uncovered_actions:
                self.logger.debug(f"Covered {str(scenario.savepoint)} of {process_name}")
                del coverage[str(scenario.savepoint)]

            return True
        else:
            return False

    def _clone_model_with_scenario(self, process_name, model, scenario):
        self.logger.info(f'Add scenario {scenario.name} of {process_name} to model "{model.attributed_name}"'
                         f' as it has coverage impact')
        new = model.clone(model.name)
        # This should change the name of the model
        self._assign_scenario(new, scenario if isinstance(scenario, Scenario) else None, process_name)
        return new


class SelectiveFactory(ModelFactory):

    strategy = SelectiveSelector
