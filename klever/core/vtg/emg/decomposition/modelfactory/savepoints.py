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

from klever.core.vtg.emg.decomposition.modelfactory import Selector, ModelFactory


class SavepointsSelector(Selector):

    def __call__(self, *args, **kwargs):
        self.logger.info("Iterate over all generated scenarios with both SP and not")

        selection = self.conf.get("savepoints", dict())
        self._check_configuration(selection)

        for process in (p for n, p in self.model.environment.items()
                        if not selection or n in selection):
            scenarios = self.processes_to_scenarios[str(process)]

            for scenario in (s for s in scenarios
                             if s.savepoint and (not selection or str(s.savepoint) in selection[str(process)])):
                model = self._make_base_model()
                self._assign_scenario(model, scenario, str(scenario))

                # Then go over other required processes and add them
                for name, scenarios in ((n, s) for n, s in self.processes_to_scenarios.items() if n != str(scenario)):
                    # Find that on relevant scenario
                    suitable = [s for s in scenarios if not s.savepoint and s.relevant_savepoint and
                                s.relevant_savepoint == str(scenario.savepoint)]
                    if suitable:
                        one = suitable[-1]
                        self._assign_scenario(model, one, str(one))
                    else:
                        self.logger.debug(f"Skip the process '{name}' for model '{model.attributed_name}'")

                # Delete missing
                for name in scenario.savepoint.requirements.forbidden_processes:
                    model.remove_process(name)

                yield model, str(scenario)

    def _check_configuration(self, selection):
        for process_name in selection:
            if process_name not in self.model.environment:
                raise ValueError(f"There is no environment process '{process_name}' to check its savepoints")

            possible_savepoints = set(map(str, self.model.environment[process_name].actions.savepoints))
            if isinstance(selection.get(process_name), list):
                left = set(selection[process_name]).difference(possible_savepoints)
                if left:
                    left = ', '.join(left)
                    raise ValueError(f"Process '{process_name}' does not have the following savepoints: {left}")
            elif isinstance(selection.get(process_name), bool):
                selection[process_name] = possible_savepoints
            else:
                raise ValueError(f"The savepoints configuration has an invalid value provided for '{process_name}'")


class SavepointsFactory(ModelFactory):

    strategy = SavepointsSelector
