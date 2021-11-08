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
    all_transitive_dependencies, is_required, transitive_restricted_deps, satisfy_deps, transitive_deps, \
    process_dependencies


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

        # Check controversial requirements
        self._check_controversial_requirements(deleted_processes, must_contain, coverage)

        # Prepare the initial base models
        first_model = self._make_base_model()
        for process_name in deleted_processes:
            first_model.remove_process(process_name)

        # Iterate over processes
        model_pool = set()
        processed = set()
        while order:
            process_name = order.pop(0)
            processed.add(process_name)
            self.logger.info(f"Consider scenarios of process '{process_name}'")

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

            next_model_pool = set()
            if not model_pool:
                self.logger.info("Expect this is a first considered process")
                iterate_over_models = {first_model}
            else:
                # Do not modify model pool by adding the very first model, it is undesirable
                iterate_over_models = model_pool

            for model in sorted(iterate_over_models, key=lambda x: x.attributed_name):
                self.logger.info(f"Consider adding scenarios to model '{model.attributed_name}'")
                local_model_pool = set()
                local_coverage = copy.deepcopy(coverage)

                if process_name not in model.environment:
                    self.logger.warning(
                        f"Skip processing model '{model.attributed_name}' as it does not require '{process_name}'")
                    next_model_pool.add(model)
                    continue

                # Remove savepoints if this process is not required to cover
                if process_name in local_coverage:
                    scenarios_items_for_model = set(scenarios_items)
                else:
                    # Do we have already savepoint?
                    # Have we covered required processes?
                    if process_name in dep_order and not any(True for p in dep_order[dep_order.index(process_name):]
                                                             if p in coverage and p in model.environment):
                        self.logger.debug(f"Now we have covered all required processes and can enable savepoints for "
                                          f"'{process_name}'")
                        if any(True for s in model.environment.values() if s and s.savepoint):
                            self.logger.debug(f"Model '{model.attributed_name}' has a savepoint already")
                            scenarios_items_for_model = {s for s in scenarios_items
                                                         if not isinstance(s, Scenario) or not s.savepoint}
                        else:
                            scenarios_items_for_model = set(scenarios_items)
                    else:
                        self.logger.debug(f"We still have processes to cover and '{process_name}' is not allowed to"
                                          f" have savepoints")
                        scenarios_items_for_model = {s for s in scenarios_items
                                                     if not isinstance(s, Scenario) or not s.savepoint}

                # Filter scenarios with savepoints if there is one already
                scenarios_items_for_model = self._filter_by_model(model, process_name, scenarios_items_for_model,
                                                                  dep_order, must_contain, processed,
                                                                  process_name in coverage)

                # Iteratively copy models to fill the coverage
                if not scenarios_items_for_model and process_name not in must_contain:
                    self.logger.warning(f"Cannot find any suitable scenarios of process '{process_name}' suitable for "
                                        f"model '{model.attributed_name}', deleting it")
                    self.delete_with_deps(model, process_name, dep_order, processed)
                    next_model_pool.add(model)
                    continue
                elif not scenarios_items_for_model and process_name in must_contain:
                    raise ValueError(f"Cannot delete required process '{process_name}' as it has no suitable scenarios "
                                     f"for '{model.attributed_name}'")

                scenarios_items_for_model = self._obtain_ordered_scenarios(
                    scenarios_items_for_model,
                    list(local_coverage[process_name].values())[-1] if process_name in local_coverage else None, greedy)
                added = 0
                while (process_name in local_coverage or not local_model_pool) and scenarios_items_for_model:
                    scenario = scenarios_items_for_model.pop(0)

                    # TODO: Add an option to add models without unnecessary processes
                    if process_name not in local_coverage:
                        new = self._clone_model_with_scenario(process_name, model, scenario, dep_order, processed)
                        self.logger.info(f"Process '{process_name}' can be covered by any scenario as it is not "
                                         f"required to cover")
                        local_model_pool.add(new)
                        added += 1
                        break
                    elif self._check_coverage_impact(process_name, local_coverage[process_name], scenario):
                        # Check savepoints
                        p_with_sp = [n for n, s in model.environment.items() if s and s.savepoint]
                        p_with_sp = None if not p_with_sp else p_with_sp.pop()
                        reassign = None
                        if scenario and isinstance(scenario, Scenario) and p_with_sp and \
                                ((p_with_sp in dep_order and process_name in dep_order and
                                  dep_order.index(p_with_sp) < dep_order.index(process_name)) or scenario.savepoint):
                            self.logger.info(f"Save model '{model.attributed_name}' before reassigning savepoint")
                            short = model.clone(model.name)
                            self.delete_with_deps(short, process_name, dep_order, processed)
                            local_model_pool.add(short)
                            reassign = p_with_sp
                            added += 1

                        new = self._clone_model_with_scenario(process_name, model, scenario, dep_order, processed,
                                                              reassign)
                        self.logger.info(f"Add a new model '{new.attributed_name}'")
                        local_model_pool.add(new)
                        added += 1
                    else:
                        self.logger.info(f"Skip scenario '{scenario.name}' of '{process_name}' "
                                         f"as it has no coverage impact")

                # This is a corner case when no coverage impact exists for a model. If a model still has a coverage
                # bonus for any other process add it.
                if not added and any(p for p in local_coverage if p in model.environment and p not in order):
                    self.logger.warning(f'Cannot find any suitable scenarios of process {process_name} that give extra'
                                        f' coverage for model {model.attributed_name}, deleting it but keep a model')
                    new = model.clone(model.name)
                    self.delete_with_deps(model, process_name, dep_order, processed)
                    local_model_pool.add(new)

                next_model_pool.update(local_model_pool)

            filtered_models = set({m.attributed_name: m for m in next_model_pool}.values())
            model_pool = filtered_models

        if not model_pool:
            self.logger.info('No models have been selected, use the base one')
            model_pool = {first_model}

        # Remove infeasible models
        model_pool = self._get_feasible_models(model_pool)

        # Detect models that can be superseded
        model_pool = self._supersede_models(model_pool)

        for model, related_process in model_pool:
            self.logger.info(f"Finally return a batch for model '{model.attributed_name}'")
            yield model, related_process

    def _get_feasible_models(self, models):
        new_model_pool = []
        for model in sorted(models, key=lambda x: x.attributed_name):
            related_process = None
            for process_name in (p for p, s in model.environment.items() if s and s.savepoint):
                related_process = process_name
                break

            if not related_process and not self.model.entry:
                self.logger.warning(f"Skip model {model.attributed_name} as it has no savepoints and the entry process")
                continue

            new_model_pool.append((model, related_process))
        return new_model_pool

    def _supersede_models(self, models_list):
        model_attributes = {m.attributed_name: {p: s for p, s in m.attributes.items() if s != 'Removed'}
                            for m, _ in models_list}
        sorted_names = sorted(model_attributes.keys(),
                              key=lambda x: len(model_attributes[x].keys()), reverse=True)

        selected = set()
        for name in sorted_names:
            my_attrs = model_attributes[name]
            for accepted in selected:
                selected_attrs = model_attributes[accepted]

                for key, scenario in my_attrs.items():
                    if key not in selected_attrs or selected_attrs[key] != scenario:
                        break
                else:
                    self.logger.info(f"Model '{name}' is superseded by model '{accepted}'")
                    break
            else:
                selected.add(name)

        return [m for m in models_list if m[0].attributed_name in selected]

    def _add_peers_as_requirements(self, model):
        model.establish_peers()
        for process in model.environment.values():
            receives = set(map(str, process.actions.filter(include={Receive})))

            for peer, dispatches in process.peers.items():
                if peer in model.environment and dispatches.issubset(receives):
                    for dispatch in dispatches:
                        self.logger.debug(f"Add requirement '{peer}': '{dispatch}' to process '{str(process)}'")
                        process.actions[dispatch].add_required_process(peer, {dispatch})

    def _check_controversial_requirements(self, deleted_processes, must_contain, coverage):
        # todo: We may need to implement more checks for complicated cases
        for deleted in deleted_processes:
            if deleted in must_contain or deleted in coverage:
                raise ValueError(f"Forced to delete '{deleted}' process according to 'must not contain' property but it"
                                 f" is mentioned in 'cover scenarios' or 'must contain' properties. Such specification"
                                 f" is controversial.")

    def _sanity_check_must_contain(self, must_contain):
        for process_name in must_contain:
            assert process_name in self.model.environment, f"There is no process '{process_name}' in the model"

            if 'actions' in must_contain[process_name]:
                assert isinstance(must_contain[process_name]['actions'], list), \
                    "Provide a list of lists to the 'must contain' parameter"

                for item in must_contain[process_name].get('actions', []):
                    assert isinstance(item, list), "Provide a list of lists to the 'must contain' parameter"

                    for action_name in item:
                        assert isinstance(action_name, str) and \
                               action_name in self.model.environment[process_name].actions, \
                               f"There is no action '{action_name}' in '{process_name}'"

            if 'savepoints' in must_contain[process_name]:
                assert isinstance(must_contain[process_name]['savepoints'], list), \
                    "Provide a list of savepoints to the 'must contain' parameter"

                for item in must_contain[process_name]['savepoints']:
                    assert isinstance(item, str), \
                           "Provide a list of savepoints' names to the 'must contain' parameter"

                    assert isinstance(item, str) and item in map(str, self.model.environment[process_name].savepoints),\
                           f"There is no savepoint '{item}' in '{process_name}'"

    def _sanity_check_must_not_contain(self, must_not_contain):
        for process_name in must_not_contain:
            assert process_name in self.model.environment, f"There is no process '{process_name}' in the model"

            for item in must_not_contain[process_name].get('actions', []):
                assert isinstance(item, list), "Provide a list of lists to the 'must not contain' parameter"

                for action_name in item:
                    assert isinstance(action_name, str) and \
                           action_name in action_name in self.model.environment[process_name].actions, \
                           f"There is no action '{action_name}' in '{process_name}'"

            if 'savepoints' in must_not_contain[process_name]:
                assert isinstance(must_not_contain[process_name]['savepoints'], list), \
                    "Provide a list of savepoints to the 'must not contain' parameter"

                for item in must_not_contain[process_name]['savepoints']:
                    assert isinstance(item, str), \
                        "Provide a list of savepoints' names to the 'must not contain' parameter"

                    assert isinstance(item, str) and item in map(str, self.model.environment[process_name].savepoints),\
                        f"There is no savepoint '{item}' in '{process_name}'"

    def _calculate_process_order(self, must_contain, must_not_contain, coverage):
        # Detect order using transitive dependencies
        todo = set(self.model.environment.keys())

        # Check controversial configurations
        for process_name in sorted(todo):
            if process_name in must_not_contain and len(must_not_contain[process_name].keys()) == 0 and \
                    process_name in must_contain:
                raise ValueError(f"Cannot cover '{process_name}' as it is given in 'must not contain' configuration "
                                 f"and required by other configurations")

        dep_order = []
        deps = all_transitive_dependencies(set(self.model.environment.values()))
        while todo and deps:
            free = []
            for entry in sorted(todo):
                if not is_required(deps, self.model.environment[entry]):
                    free.append(entry)
            for selected in free:
                dep_order.append(selected)
                todo.remove(selected)
                del deps[selected]

        # These processes will be deleted from models at all
        deleted_processes = set()
        for process_name in (p for p in sorted(must_not_contain.keys()) if len(must_not_contain[p].keys()) == 0):
            deleted_processes.add(process_name)
            if process_name in todo:
                todo.remove(process_name)

            if process_name in dep_order:
                for process_covered in (p for p in dep_order[:dep_order.index(process_name)+1] if p in coverage):
                    # Check savepoints
                    if len(coverage[process_covered].keys()) == 1:
                        raise ValueError(f"Cannot cover '{process_covered}' as '{process_name}' should be deleted")
        else:
            self.logger.info(f"Delete processes: " + ", ".join(sorted(deleted_processes)))

        # Check cover first, then dependencies
        order = [p for p in dep_order if p in coverage] + \
                [p for p in dep_order if p not in coverage]

        # Add from rest list
        order.extend([p for p in sorted(todo) if p in coverage])
        todo = [p for p in sorted(todo) if p not in order]

        # Sort rest by coverage
        order = order + [p for p in sorted(todo) if p in coverage] + [p for p in sorted(todo) if p not in coverage]

        return deleted_processes, order, dep_order

    def _prepare_coverage(self, cover_conf):
        coverage = dict()
        for process_name in cover_conf:
            # Subprocesses may not be covered in scenarios, so avoid adding the origin process to cover them
            assert process_name in self.model.environment, f"There is no process '{process_name}' in the model"
            actions = set(str(a) for a in self.model.environment[process_name].actions.filter(exclude={Subprocess}))
            savepoints = {str(sp) for ac in self.model.environment[process_name].actions.values()
                          for sp in ac.savepoints}

            if 'actions' in cover_conf[process_name]:
                assert(isinstance(cover_conf[process_name]['actions'], list))
                for item in cover_conf[process_name]['actions']:
                    assert isinstance(item, str) and item in self.model.environment[process_name].actions, \
                        f"There is no action '{item}' in '{process_name}'"
                actions_to_cover = set(cover_conf[process_name]['actions'])
            else:
                actions_to_cover = actions

            if cover_conf[process_name].get('actions except'):
                assert (isinstance(cover_conf[process_name]['actions except'], list))
                for item in cover_conf[process_name]['actions except']:
                    assert isinstance(item, str) and item in self.model.environment[process_name].actions, \
                        f"There is no action '{item}' in '{process_name}'"
                actions_to_cover.difference_update(set(cover_conf[process_name]['actions except']))

            if 'savepoints' in cover_conf[process_name]:
                assert (isinstance(cover_conf[process_name]['savepoints'], list))
                for item in cover_conf[process_name]['savepoints']:
                    assert isinstance(item, str) and item in map(str, self.model.environment[process_name].savepoints),\
                        f"There is no savepoint '{item}' in {process_name}"
                sp_to_cover = set(cover_conf[process_name]['savepoints'])
            else:
                sp_to_cover = savepoints

            if cover_conf[process_name].get('savepoints except'):
                assert (isinstance(cover_conf[process_name]['savepoints except'], list))
                for item in cover_conf[process_name]['savepoints except']:
                    assert isinstance(item, str) and item in map(str, self.model.environment[process_name].savepoints),\
                        f"There is no savepoint '{item}' in '{process_name}'"
                sp_to_cover.difference_update(set(cover_conf[process_name]['savepoints except']))

            self.logger.info(f"Cover the following actions from the process '{process_name}': " +
                             ", ".join(sorted(actions_to_cover)))
            self.logger.info(f"Cover the following savepoints from the process '{process_name}': " +
                             ", ".join(sorted(sp_to_cover)))

            # Now split coverage according to required savepoints
            coverage[process_name] = {process_name: set(actions_to_cover)}
            for sp in sp_to_cover:
                coverage[process_name][sp] = set(actions_to_cover)

            if cover_conf[process_name].get("savepoints only"):
                coverage[process_name][process_name] = set()
                if len(coverage[process_name].keys()) == 1:
                    raise ValueError(f"Process '{process_name}' cannot be covered with the provided configuration")

        return coverage

    def _filter_must_contain_base_process(self, process_name, scenarios_items, must_contain):
        if process_name not in must_contain or must_contain[process_name].get('scenarios only', True):
            self.logger.debug(f"Remove base process '{process_name}' as only scenarios can be selected")
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
            self.logger.debug(f"{process_name.capitalize()} has the following scenarios with required actions: " +
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

            self.logger.debug(f"{process_name.capitalize()} has the following scenarios with required savepoints: " +
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

            self.logger.debug(f"{process_name.capitalize()} has the following scenarios without forbidden actions: " +
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

            self.logger.debug(f"{process_name.capitalize()} has the following scenarios without forbidden "
                              f"savepoints: " + ', '.join(list(map(str, new_scenarios_items))))
            return new_scenarios_items
        else:
            return scenarios_items

    def _filter_by_model(self, model, process_name, scenarios_items, dep_order, must_contain, processed,  in_coverage):
        # Check that there is a savepoint in the model and required by must contain
        exists_savepoint = False
        for scenario in model.environment.values():
            if isinstance(scenario, Scenario) and scenario.savepoint:
                exists_savepoint = True
                self.logger.debug(f"Model '{model.attributed_name}' has a savepoint already")
                break

        # Edit deps order
        deps = transitive_restricted_deps(self.model, model, self.model.environment[process_name], dep_order, processed)

        # Check must contain dependencies
        if in_coverage:
            mc_required = [p for p in dep_order if p in processed and p in must_contain]
            if mc_required:
                self.logger.debug(f"Consider dependencies up to '{mc_required[0]}'")
                removing_deps = dep_order[:dep_order.index(mc_required[0])]
                for pname in (p for p in removing_deps if p in deps):
                    del deps[pname]
            else:
                self.logger.debug(f"Do not consider dependencies to increase the coverage")
                deps = dict()

        if exists_savepoint and not in_coverage:
            new_scenarios_items = {s for s in scenarios_items if isinstance(s, Process) or not s.savepoint}
        else:
            new_scenarios_items = set(scenarios_items)

        selected_items = set()
        for scenario in new_scenarios_items:
            if satisfy_deps(deps, self.model.environment[process_name], scenario):
                self.logger.debug(f"Scenario '{scenario.name}' meets model '{model.attributed_name}'")

                # Now check that model is compatible with the scenario
                model.environment[process_name] = scenario
                deps2 = transitive_deps(self.model, model, dep_order[dep_order.index(process_name):])
                model.environment[process_name] = None
                for required in (r for r in deps2.get(process_name, dict()) if r in self.model.environment and
                                 r in process_dependencies(self.model.environment[process_name])):
                    if required in model.environment and model.environment[required]:
                        possible_actions = set(model.environment[required].actions.keys())
                    elif required in model.environment:
                        possible_actions = set(self.model.environment[required].actions.keys())
                    else:
                        possible_actions = set()

                    if not deps2[process_name][required].issubset(possible_actions):
                        acts = ', '.join(deps2[process_name][required])
                        self.logger.debug(f"Model '{model.attributed_name}' do not have actions "
                                          f"({acts}) of '{required}' required by '{process_name}'")
                        break
                    else:
                        selected_items.add(scenario)
                else:
                    selected_items.add(scenario)
            else:
                self.logger.debug(f"Scenario '{scenario.name}' don't meet model '{model.attributed_name}'")
        new_scenarios_items = selected_items
        return new_scenarios_items

    def detect_broken_dependencies(self, model, process_name, scenario, dep_order, processed):
        # Check that there is a savepoint in the model and required by must contain
        savepoint = None
        for name, s in model.environment.items():
            if isinstance(s, Scenario) and s.savepoint and name in dep_order:
                savepoint = name
                break

        if process_name in dep_order:
            if savepoint:
                if savepoint not in dep_order:
                    broken = {savepoint}
                elif dep_order.index(savepoint) > dep_order.index(savepoint):
                    # Just collect dependencies and forget about the SP
                    broken = set()
                elif isinstance(scenario, Scenario) and scenario.savepoint:
                    # We remove the savepoint and add the scenario, just need to be sure about all broken things
                    broken = {savepoint}
                    deps = transitive_restricted_deps(self.model, model, self.model.environment[process_name],
                                                      dep_order, processed)
                    if deps:
                        for asker, required in ((a, r) for a, r in deps.items() if a != savepoint):
                            if savepoint in required and \
                                    process_name not in process_dependencies(self.model.environment[asker]):
                                broken.add(asker)
                            elif process_name in required and \
                                    not required[process_name].issubset(set(scenario.actions.keys())):
                                broken.add(asker)
                        return broken
                    else:
                        return set()
                else:
                    broken = set()
            else:
                broken = set()

            processed = set(processed)
            if process_name in processed:
                processed.remove(process_name)
            deps = transitive_restricted_deps(self.model, model, self.model.environment[process_name], dep_order,
                                              processed)
            if deps:
                for asker, required_actions in ((a, d[process_name]) for a, d in deps.items() if process_name in d):
                    if not required_actions.issubset(set(scenario.actions.keys())):
                        broken.add(asker)
                return broken
            else:
                return set()
        elif savepoint and savepoint in dep_order:
            # Savepoint will be deleted, so it may broke dependencies.
            deps = transitive_restricted_deps(self.model, model, self.model.environment[savepoint], dep_order,
                                              processed)
            if deps:
                broken = {savepoint}
                for child in (p for p in dep_order[:dep_order.index(savepoint)]
                              if p in deps and savepoint in deps[p]):
                    broken.add(child)
            else:
                return set()
        elif savepoint:
            # Only savepoint is broken
            return {savepoint}
        else:
            # Nothing is broken
            return set()

    def _obtain_ordered_scenarios(self, scenarios_set, coverage=None, greedy=False):
        new_scenario_list = [s for s in scenarios_set if isinstance(s, Scenario)]
        if coverage:
            # Split into two parts that contain forbidden actions and not
            good = [s for s in new_scenario_list if not set(s.actions.keys()).difference(coverage)]
            bad = [s for s in new_scenario_list if s not in good]
            new_scenario_list = sorted(good,
                                       key=lambda x: (not bool(isinstance(x, Scenario) and x.savepoint),
                                                      len(set(x.actions.keys()).intersection(coverage)),
                                                      x.name),
                                       reverse=greedy)
            new_scenario_list.extend(sorted(bad,
                                            key=lambda x: (not bool(isinstance(x, Scenario) and x.savepoint),
                                                           len(set(x.actions.keys()).difference(coverage)),
                                                           x.name)))
        else:
            new_scenario_list = sorted(new_scenario_list,
                                       key=lambda x: (not bool(isinstance(x, Scenario) and x.savepoint),
                                                      len(x.actions.keys()),
                                                      x.name),
                                       reverse=greedy)
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
            self.logger.debug(f"Coverage impact of scenario '{scenario.name}' of '{process_name}' includes: " +
                              ', '.join(impact))
            uncovered_actions.difference_update(impact)

            if isinstance(scenario, Scenario) and scenario.savepoint and str(scenario.savepoint) in coverage and \
                    not uncovered_actions:
                self.logger.debug(f"Covered '{str(scenario.savepoint)}' of '{process_name}'")
                del coverage[str(scenario.savepoint)]

            return True
        else:
            return False

    def _clone_model_with_scenario(self, process_name, model, scenario, dep_order, processed, reassign=None):
        self.logger.info(f"Add scenario '{scenario.name}' of '{process_name}' to model '{model.attributed_name}'"
                         f" as it has coverage impact")
        new = model.clone(model.name)

        # Check dependencies
        broken = self.detect_broken_dependencies(new, process_name, scenario, dep_order, processed)
        if reassign:
            broken.add(reassign)
        if broken:
            for entry in broken:
                new.remove_process(entry)

        # This should change the name of the model
        self._assign_scenario(new, scenario if isinstance(scenario, Scenario) else None, process_name)
        return new

    def delete_with_deps(self, model, process_name, dep_order, processed):
        # Check that there is a savepoint in the model and required by must contain
        savepoint = None
        for name, s in model.environment.items():
            if isinstance(s, Scenario) and s.savepoint and name in dep_order:
                savepoint = name
                break

        # Edit deps order
        deps = transitive_restricted_deps(self.model, model, self.model.environment[process_name], dep_order, processed)
        if not deps:
            selected_items = {process_name}
        else:
            selected_items = {name for name in deps.items() if process_name in deps}
            if savepoint:
                saved_order = dep_order[:dep_order.index(savepoint)+1]
                for p in saved_order:
                    if p in selected_items:
                        selected_items.remove(p)
            selected_items.add(process_name)

        # Now delete processes
        for p in selected_items:
            model.remove_process(p)


class SelectiveFactory(ModelFactory):

    strategy = SelectiveSelector
