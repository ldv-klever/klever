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

        for process in self.model.environment.values():
            scenarios = self.processes_to_scenarios[str(process)]

            for scenario in (s for s in scenarios if s.savepoint):
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


class SavepointsFactory(ModelFactory):

    strategy = SavepointsSelector
