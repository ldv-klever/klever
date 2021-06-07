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
from klever.core.vtg.emg.common.process.actions import Subprocess
from klever.core.vtg.emg.decomposition.modelfactory import Selector, ModelFactory


class SelectiveSelector(Selector):

    def __call__(self, *args, **kwargs):
        must_contain = self.conf.get("must contain", dict())
        must_not_contain = self.conf.get("must not contain", dict())
        cover_conf = self.conf.get("cover scenarios", dict())

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
            del first_model.environment[process_name]

        # Iterate over processes
        model_pool = [first_model]
        while order:
            process_name = order.pop(0)

            # Get all scenarios
            scenarios_items = set(list(self.processes_to_scenarios[process_name]) +
                                  [self.model.environment[process_name]])

            # Filter by "must contain"
            scenarios_items = self._filter_must_contain_actions(process_name, scenarios_items, must_contain)
            scenarios_items = self._filter_must_contain_savepoints(process_name, scenarios_items, must_contain)

            # Filter by "must not contain"
            scenarios_items = self._filter_must_not_contain_actions(process_name, scenarios_items, must_not_contain)
            scenarios_items = self._filter_must_not_contain_savepoints(process_name, scenarios_items, must_not_contain)

            next_model_pool = list()
            for model in model_pool:
                self.logger.info(f"Consider adding scenarios to model {model.name}")
                local_model_pool = list()

                # Filter scenarios with savepoints if there is one already
                scenarios_items_for_model = self._filter_by_savepoints_in_model(model, scenarios_items)

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
                                        f'model {model.name}, deleting it')
                    del model.environment[process_name]
                    next_model_pool.append(model)
                    continue
                elif not scenarios_items_for_model and process_name in must_contain:
                    raise ValueError(f"Cannot delete required process {process_name} as it has no suitable scenarios "
                                     f"for {model.name}")

                scenarios_items_for_model = self._obtain_ordered_scenarios(
                    scenarios_items_for_model,
                    list(coverage[process_name].values())[-1] if process_name in coverage else None, greedy)
                while (process_name in coverage or not local_model_pool) and scenarios_items_for_model:
                    scenario = scenarios_items_for_model.pop(0)

                    if process_name not in coverage:
                        new = self._clone_model_with_scenario(process_name, model, scenario)
                        self.logger.info(f"Process {process_name} can be covered by any scenario as it is not required "
                                         f"to cover")
                        local_model_pool.append(new)
                        break
                    elif self._check_coverage_impact(process_name, coverage[process_name], scenario):
                        new = self._clone_model_with_scenario(process_name, model, scenario)
                        self.logger.info(f'Add a new model {new.name}')
                        local_model_pool.append(new)
                    else:
                        self.logger.info(f'Skip scenario {str(scenario)} of {process_name} '
                                         f'as it has no coverage impact')
                next_model_pool.extend(local_model_pool)

            model_pool = next_model_pool

        for model in model_pool:
            related_process = None
            for process_name in (p for p, s in model.environment.items() if s and s.savepoint):
                related_process = process_name
                break
            yield model, related_process

    def _extract_dependecnies(self):
        # This map contains a map from processes to actions that contains requirements
        dependencies_map = dict()

        # This map allows to determine which processes are required by any other. Such required processes are set as
        # keys
        dependant_map = dict()
        for process in self.model.environment.values():
            action_names = [str(a) for a in process.actions if process.actions[a].requires]
            if action_names:
                self.logger.info(f"Process {process} has requirements in the following actions: " +
                                 ", ".join(action_names))
                dependencies_map[str(process)] = action_names

                for action in action_names:
                    for dependant in process.actions[action].requires.keys():
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
            actions = set(str(a) for a in self.model.environment[process_name].actions.filter(exclude={Subprocess}))
            savepoints = {str(sp) for ac in self.model.environment[process_name].actions.values()
                          for sp in ac.savepoints}

            if cover_conf[process_name].get('actions'):
                actions_to_cover = set(cover_conf[process_name]['actions'])
            else:
                actions_to_cover = actions

            if cover_conf[process_name].get('actions except'):
                actions_to_cover.difference_update(cover_conf[process_name]['actions except'])

            if cover_conf[process_name].get('savepoints'):
                sp_to_cover = set(cover_conf[process_name]['savepoints'])
            else:
                sp_to_cover = savepoints

            if cover_conf[process_name].get('savepoints except'):
                sp_to_cover.difference_update(cover_conf[process_name]['savepoints except'])

            self.logger.info(f"Cover the following actions from the process {process_name}: " +
                             ", ".join(sorted(actions_to_cover)))
            self.logger.info(f"Cover the following savepoints from the process {process_name}: " +
                             ", ".join(sorted(sp_to_cover)))

            # Now split coverage according to required savepoints
            coverage[process_name] = {process_name: set(actions_to_cover)}
            for sp in sp_to_cover:
                coverage[process_name][sp] = set(actions_to_cover)

        return coverage

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
            new_scenarios_items = {s for s in scenarios_items if not isinstance(s, Scenario) or not s.savepoint}
            return new_scenarios_items
        else:
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
                                   actions_with_requirements[a].requires.get(process_name)):
                        self.logger.debug(f'Found requirements for {process_name} in {action} of {proc_with_reqs}')
                        if not set(actions_with_requirements[action].requires[process_name]["includes"]). \
                                issubset(set(suitable.actions.keys())):
                            self.logger.info(f"Cannot add {str(suitable)} of {process_name} because "
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
                    for asked_process in scenario.actions[action_name].requires:
                        if asked_process in deleted:
                            self.logger.info(f"Cannot add {str(scenario)} of {process_name} because "
                                             f"{asked_process} is deleted")
                            add_flag = False
                            continue
                        if asked_process in order:
                            # Have not been considered yet
                            continue

                        required_actions = scenario.actions[action_name].requires[asked_process]["includes"]
                        considered_actions = model.environment[asked_process].actions  \
                            if model.environment[asked_process] else self.model.environment[asked_process].actions
                        if not set(required_actions).issubset(set(considered_actions.keys())):
                            self.logger.info(f"Cannot add {str(scenario)} of {process_name} because "
                                             f"{asked_process} does not satisfy required creteria of inclusion: " +
                                             ", ".join(required_actions))
                            add_flag = False

                if add_flag:
                    new_scenario_items.add(scenario)

            return new_scenario_items
        else:  # Has no dependencies
            return scenario_items

    def _obtain_ordered_scenarios(self, scenarios_set):
        new_scenario_set = [s for s in scenarios_set if isinstance(s, Scenario)]
        new_scenario_set = sorted(new_scenario_set, key=lambda x: len(x.actions))
        new_scenario_set.extend([x for x in scenarios_set if x not in new_scenario_set])
        return new_scenario_set

    def _check_coverage_impact(self, process_name, coverage, scenario):
        if (isinstance(scenario, Scenario) and not scenario.savepoint) or not isinstance(scenario, Scenario):
            uncovered_actions = coverage[process_name]
        elif isinstance(scenario, Scenario) and scenario.savepoint and str(scenario.savepoint) in coverage:
            uncovered_actions = coverage[str(scenario.savepoint)]
        else:
            return False

        if uncovered_actions and uncovered_actions.intersection(set(scenario.actions.keys())):
            uncovered_actions.difference_update(set(scenario.actions.keys()))

            if isinstance(scenario, Scenario) and scenario.savepoint and str(scenario.savepoint) in coverage and \
                    not uncovered_actions:
                del coverage[str(scenario.savepoint)]

            return True
        else:
            return False

    def _clone_model_with_scenario(self, process_name, model, scenario):
        self.logger.info(f'Add scenario {str(scenario)} of {process_name} '
                         f'as it has coverage impact')

        if isinstance(scenario, Scenario):
            name = (str(model.name) + f'_{scenario.name}') \
                if scenario.name != 'base' or model.name != 'base' else scenario.name
        else:
            name = str(model.name)

        new = model.clone(name)
        new.environment[process_name] = scenario if isinstance(scenario, Scenario) else None
        return new


class SelectiveFactory(ModelFactory):

    strategy = SelectiveSelector
