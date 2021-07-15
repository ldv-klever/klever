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

from klever.core.vtg.emg.common.process import Process
from klever.core.vtg.emg.decomposition.scenario import Scenario
from klever.core.vtg.emg.common.process.actions import Subprocess, Receive
from klever.core.vtg.emg.decomposition.modelfactory import Selector, ModelFactory, remove_process, \
    all_transitive_dependencies, is_required, transitive_restricted_deps, satisfy_deps


def _must_contain_scenarios(must_contain_conf, scenario_model):
    """
    Return a set of scenarios and process names that are entries of must contain configuration.

    :param must_contain_conf: dict.
    :param scenario_model: ScenarioModel.
    :return: set of process names, set of Scenario objects.
    """
    names = set()
    scenarios = set()
    for entry in must_contain_conf:
        if entry in scenario_model.environment and scenario_model.environment[entry]:
            names.add(entry)
            scenarios.add(scenario_model.environment[entry])
    return names, scenarios


class SelectiveSelector(Selector):

    def __call__(self, *args, **kwargs):
        must_contain = self.conf.get("must contain", dict())
        must_not_contain = self.conf.get("must not contain", dict())
        cover_conf = self.conf.get("cover scenarios", dict())
        greedy = self.conf.get("greedy selection", False)

        self._sanity_check_must_contain(must_contain)
        self._sanity_check_must_not_contain(must_not_contain)

        self.logger.info("Collect dependencies between processes")
        self._add_peers_as_requirements(self.model)

        # Prepare coverage
        self.logger.info("Prepare detailed coverage descriptions per process")
        coverage = self._prepare_coverage(cover_conf)

        deleted_processes, order, dep_order = self._calculate_process_order(must_contain, must_not_contain, coverage)
        self.logger.info("Order of process iteration is: " + ', '.join(order))

        # Prepare the initial base models
        first_model = self._make_base_model()
        for process_name in deleted_processes:
            remove_process(first_model, process_name)

        # Iterate over processes
        model_pool = []
        processed = set()
        while order:
            process_name = order.pop(0)
            processed.add(process_name)
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

                # Remove savepoints if this process is not required to cover
                if process_name in local_coverage:
                    scenarios_items_for_model = set(scenarios_items)
                else:
                    scenarios_items_for_model = {s for s in scenarios_items
                                                 if not isinstance(s, Scenario) or not s.savepoint}

                # Filter scenarios with savepoints if there is one already
                scenarios_items_for_model = self._filter_by_model(model, process_name, scenarios_items_for_model,
                                                                  dep_order)

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

    def _add_peers_as_requirements(self, model):
        model.establish_peers()
        for process in model.environment.values():
            receives = set(map(str, process.actions.filter(include={Receive})))

            for peer, dispatches in process.peers.items():
                if peer in model.environment and dispatches.issubset(receives):
                    for dispatch in dispatches:
                        self.logger.debug(f"Add requirement {peer}:{dispatch} to process {str(process)}")
                        process.actions[dispatch].add_required_process(peer, {dispatch})

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

                    assert isinstance(item, str) and item in map(str, self.model.environment[process_name].savepoints),\
                           f"There is no savepoint {item} in {process_name}"

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

                    assert isinstance(item, str) and item in map(str, self.model.environment[process_name].savepoints),\
                        f"There is no savepoint {item} in {process_name}"

    def _calculate_process_order(self, must_contain, must_not_contain, coverage):
        # Detect order using transitive dependencies
        todo = set(self.model.environment.keys())

        # Check contraversal configurations
        for process_name in todo:
            if process_name in must_not_contain and len(must_not_contain[process_name].keys()) == 0 and \
                    process_name in must_contain:
                raise ValueError(f'Cannot cover {process_name} as it is given in "must not contain" configuration '
                                 f'and required by other configurations')

        dep_order = []
        deps = all_transitive_dependencies(set(self.model.environment.values()))
        while todo and deps:
            free = []
            for entry in todo:
                if not is_required(deps, self.model.environment[entry]):
                    free.append(entry)
            for selected in free:
                dep_order.append(selected)
                todo.remove(selected)
                del deps[selected]

        # These processes will be deleted from models at all
        deleted_processes = set()
        for process_name in (p for p in must_not_contain if len(must_not_contain[p].keys()) == 0):
            deleted_processes.add(process_name)
            if process_name in todo:
                todo.remove(process_name)

            if process_name in dep_order:
                for process_covered in (p for p in dep_order[:dep_order.index(process_name)] if p in coverage):
                    # Check savepoints
                    if len(coverage[process_covered].keys()) == 1:
                        raise ValueError(f'Cannot cover {process_covered} as {process_name} should be deleted')
                # Delete rest
                for name in dep_order[:dep_order.index(process_name)]:
                    dep_order.remove(name)
        else:
            self.logger.info(f"Delete processes: " + ", ".join(sorted(deleted_processes)))

        # Check cover first, then dependencies
        order = [p for p in dep_order if p in coverage] + \
                [p for p in dep_order if p not in coverage]

        # Add from rest list
        order.extend([p for p in todo if p in coverage])
        todo = [p for p in todo if p not in order]

        # Sort rest by coverage
        order = order + [p for p in todo if p in coverage] + [p for p in todo if p not in coverage]

        return deleted_processes, order, dep_order

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
                assert (isinstance(cover_conf[process_name]['actions except'], list))
                for item in cover_conf[process_name]['actions except']:
                    assert isinstance(item, str) and item in self.model.environment[process_name].actions, \
                        f"There is no action {item} in {process_name}"
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

    def _filter_by_model(self, model, process_name, scenarios_items, dep_order):
        # Check that there is a savepoint in the model and required by must contain
        exists_savepoint = False
        for scenario in model.environment.values():
            if isinstance(scenario, Scenario) and scenario.savepoint:
                exists_savepoint = True
                self.logger.debug(f"Model {model.attributed_name} has a savepoint already")
                break

        if exists_savepoint:
            new_scenarios_items = {s for s in scenarios_items if isinstance(s, Process) or not s.savepoint}
        else:
            new_scenarios_items = set(scenarios_items)

        # Edit deps order
        deps = transitive_restricted_deps(self.model, model, self.model.environment[process_name], dep_order)

        selected_items = set()
        for scenario in new_scenarios_items:
            if satisfy_deps(deps, self.model.environment[process_name], scenario):
                self.logger.debug(f"Scenario {scenario.name} meets model {model.attributed_name}")
                selected_items.add(scenario)
            else:
                self.logger.debug(f"Scenario {scenario.name} don't meet model {model.attributed_name}")
        new_scenarios_items = selected_items
        return new_scenarios_items

    def _obtain_ordered_scenarios(self, scenarios_set, coverage=None, greedy=False):
        new_scenario_list = [s for s in scenarios_set if isinstance(s, Scenario)]
        if coverage:
            # Split into two parts that contain forbidden actions and not
            good = [s for s in new_scenario_list if not set(s.actions.keys()).difference(coverage)]
            bad = [s for s in new_scenario_list if s not in good]
            new_scenario_list = sorted(good, key=lambda x: len(set(x.actions.keys()).intersection(coverage)),
                                       reverse=greedy)
            new_scenario_list.extend(sorted(bad, key=lambda x: len(set(x.actions.keys()).difference(coverage))))
        else:
            new_scenario_list = sorted(new_scenario_list, key=lambda x: len(x.actions.keys()), reverse=greedy)
        new_scenario_list.extend([x for x in scenarios_set if x not in new_scenario_list])
        return new_scenario_list

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
