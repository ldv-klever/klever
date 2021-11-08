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


class CombinatorialSelector(Selector):

    def __call__(self, *args, **kwargs):
        self.logger.info("Iterate over all generated scenarios with both SP and not")
        for new, related_process in self._iterate_over_base_models(
                include_base_model=True, include_savepoints=not self.conf.get('skip savepoints')):
            iterate_over_processes = [
                p for p in self.processes_to_scenarios
                if related_process != p and [x for x in self.processes_to_scenarios[p] if not x.savepoint]]
            if iterate_over_processes:
                self.logger.info(f"Create copies of '{new.attributed_name}' for processes:"
                                 f" {', '.join(iterate_over_processes)}")
                pool = []
                for process_name in iterate_over_processes:
                    for new_model in (list(pool) if pool else [new]):
                        for scenario in (s for s in self.processes_to_scenarios[process_name] if not s.savepoint):
                            newest = new_model.clone(new_model.name)
                            newest.extend_model_name(process_name, scenario.name)
                            self.logger.info(f"Add a new model '{newest.attributed_name}' from model"
                                             f" '{new_model.attributed_name}' and scenario '{scenario.name}'")
                            self._assign_scenario(newest, scenario, process_name)
                            pool.append(newest)

                for new_model in pool:
                    self.logger.debug(f"Generate model '{new_model.name}'" +
                                      (f" for related_process '{related_process}'" if related_process else ''))
                    yield new_model, related_process
            else:
                self.logger.info(
                    f"No processes with scenarios without savepoints were selected for model '{new.attributed_name}'")
                yield new, related_process


class CombinatorialFactory(ModelFactory):

    strategy = CombinatorialSelector
