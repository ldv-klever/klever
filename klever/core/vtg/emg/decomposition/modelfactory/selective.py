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
from klever.core.vtg.emg.decomposition.modelfactory import Selector, ModelFactory


class SelectiveSelector(Selector):

    def __call__(self, *args, **kwargs):
        must_contain = self.conf.get("must contain", dict())
        must_not_contain = self.conf.get("must not contain", dict())
        cover_conf = self.conf.get("cover scenarios", dict())

        # Make a map with requirements
        dependencies_map = dict()
        dependant_map = dict()
        for process in self.model.environment:
            action_names = [str(a) for a in process.actions if process.actions[a].requirements]
            if action_names:
                dependencies_map[str(process)] = action_names

                for action in action_names:
                    for dependant in process.actions[action].requirement.keys():
                        dependant_map.setdefault(dependant, set())
                        dependant_map[dependant].add(str(process))

        # Determine the order to iterate over the processes
        todo = set(self.model.environment.keys())
        to_cover = todo.intersection(cover_conf.keys())
        todo.difference_update(to_cover)
        order = []
        for process_name in to_cover:
            if process_name in must_not_contain and len(must_not_contain[process_name].keys()) == 0:
                if process_name in must_contain or process_name in dependant_map:
                    raise ValueError(f'Cannot cover {process_name} as it is given in "must not contain" configuration')
                else:
                    continue
            else:
                order.append(process_name)
        order.extend(list(todo))
        order = sorted(order)

        # Prepare coverage
        coverage = dict()
        for process in cover_conf:
            actions = set(self.model.environment[process].actions.keys())
            savepoints = {str(sp) for ac in self.model.environment[process].actions.values() for sp in ac.savepoints}

            if cover_conf[process].get('actions'):
                actions_to_cover = set(cover_conf[process]['actions'])
            else:
                actions_to_cover = actions

            if cover_conf[process].get('actions except'):
                actions_to_cover.difference_update(cover_conf[process]['actions except'])

            if cover_conf[process].get('savepoints'):
                sp_to_cover = set(cover_conf[process]['savepoints'])
            else:
                sp_to_cover = savepoints

            if cover_conf[process].get('savepoints except'):
                sp_to_cover.difference_update(cover_conf[process]['savepoints except'])
            coverage[process] = [actions_to_cover, sp_to_cover]

        # Iterate over
        first_model = self._make_base_model()
        model_pool = [first_model]

        while order:
            process_name = order.pop()

            # Get all scenarios
            scenarios_items = set(list(self.processes_to_scenarios[process_name]) +
                                  [self.model.environment[process_name]])

            # Filter "must contain"
            new_scenarios_items = set()
            if process_name in must_contain:
                # Check actions
                if must_contain[process_name].get('actions'):
                    for suitable in scenarios_items:
                        for action_set in must_contain[process_name]['actions']:
                            if set(action_set).issubset(set(suitable.actions.keys())):
                                new_scenarios_items.add(suitable)
                scenarios_items = new_scenarios_items
                new_scenarios_items = set()

                # Check savepoints
                if must_contain[process_name].get('savepoints'):
                    for suitable in (s for s in scenarios_items
                                     if isinstance(s, Scenario) and
                                        str(s.savepoint) in must_contain[process_name]['savepoints']):
                        new_scenarios_items.add(suitable)

                scenarios_items = new_scenarios_items
                new_scenarios_items = set()

            # Proceed to must not contain
            if process_name in must_not_contain:
                # Check actions
                if must_not_contain[process_name].get('actions'):
                    for suitable in scenarios_items:
                        for action_set in must_not_contain[process_name]['actions']:
                            if not set(action_set).issubset(set(suitable.actions.keys())):
                                new_scenarios_items.add(suitable)
                scenarios_items = new_scenarios_items
                new_scenarios_items = set()

                # Check savepoints
                if must_not_contain[process_name].get('savepoints'):
                    for suitable in scenarios_items:
                        if isinstance(suitable, Scenario) and \
                                str(suitable.savepoint) in must_not_contain[process_name]['savepoints']:
                            continue
                        else:
                            new_scenarios_items.add(suitable)
                scenarios_items = new_scenarios_items
                new_scenarios_items = set()

            new_scenarios_items = set()
            next_model_pool = list()
            for model in model_pool:
                # Filter requirements
                if process_name in dependant_map:
                    for suitable in scenarios_items:
                        accept_flag = True
                        for proc_with_reqs in dependant_map[process_name]:
                            if proc_with_reqs in order:   # We already traversed it
                                continue

                            actions = model.environment[proc_with_reqs] if model.environment[proc_with_reqs] else \
                                self.model.environment[proc_with_reqs]

                            if accept_flag:
                                for action in (a for a in dependencies_map[proc_with_reqs] if a in actions):
                                    if actions[action].requirements.get(process_name):
                                        accept_flag = False
                                        if set(actions[action].requirements[process_name]["includes"]).\
                                                issubset(set(suitable.actions.keys())):
                                            accept_flag = True

                                        if not accept_flag:
                                            break

                        if accept_flag:
                            if process_name in dependencies_map:
                                for action in (a for a in dependencies_map[process_name] if a in suitable.actions):
                                    for asked_process in (a for a in suitable.actions[action].requirements
                                                          if a not in order):
                                        considered = model.environment[asked_process]
                                        if not considered:
                                            considered = self.model.environment[asked_process]

                                        if not set(suitable.actions[action].requirements[asked_process]["includes"]). \
                                                issubset(set(considered.actions.keys())):
                                            accept_flag = False

                        if accept_flag:
                            new_scenarios_items.add(suitable)

                # Iteratively copy models to fill the coverage
                if not new_scenarios_items:
                    raise ValueError(f'Cannot find any suitable scenarios for process {process_name}')

                while process_name in coverage and new_scenarios_items:
                    cover = False
                    scenario = new_scenarios_items.pop()
                    actions_to_cover, sp_to_cover = coverage[process_name]

                    if actions_to_cover and actions_to_cover.intersection(set(scenario.actions.keys())):
                        cover = True
                        actions_to_cover.difference_update(set(scenario.actions.keys()))

                    if sp_to_cover and scenario.savepoint and str(scenario.savepoint) in sp_to_cover and \
                            all([not i or not i.savepoint for i in model.environment.values()]):
                        cover = True
                        sp_to_cover.remove(str(scenario.savepoint))

                    if cover:
                        if isinstance(scenario, Scenario):
                            name = (str(model.name) + f'_{scenario.name}') \
                                    if scenario.name != 'base' or model.name != 'base' else scenario.name
                        else:
                            name = str(model.name)

                        new = model.clone(name)
                        new[process_name] = scenario if isinstance(scenario, Scenario) else None
                        next_model_pool.append(new)

            model_pool = next_model_pool

        for model in model_pool:
            related_process = None
            for process_name in (p for p, s in model.environment.items() if s and s.savepoint):
                related_process = process_name
            yield model, related_process


class SelectiveFactory(ModelFactory):

    strategy = SelectiveSelector
