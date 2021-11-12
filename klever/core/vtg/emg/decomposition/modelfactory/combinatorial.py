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

from klever.core.vtg.emg.common.process.actions import Subprocess
from klever.core.vtg.emg.decomposition.modelfactory import ModelFactory
from klever.core.vtg.emg.decomposition.modelfactory.selective import SelectiveSelector


class CombinatorialSelector(SelectiveSelector):

    def _prepare_coverage(self, cover_conf):
        coverage = dict()
        for process_name in self.model.environment:
            actions = set(str(a) for a in self.model.environment[process_name].actions.filter(exclude={Subprocess}))
            savepoints = {str(sp) for ac in self.model.environment[process_name].actions.values()
                          for sp in ac.savepoints}

            actions_to_cover = actions
            sp_to_cover = savepoints

            self.logger.info(f"Cover the following actions from the process '{process_name}': " +
                             ", ".join(sorted(actions_to_cover)))
            self.logger.info(f"Cover the following savepoints from the process '{process_name}': " +
                             ", ".join(sorted(sp_to_cover)))

            # Now split coverage according to required savepoints
            coverage[process_name] = {process_name: set(actions_to_cover)}
            for sp in sp_to_cover:
                coverage[process_name][sp] = set(actions_to_cover)

            if self.conf.get("skip origin model"):
                coverage[process_name][process_name] = set()
                if len(coverage[process_name].keys()) == 1:
                    raise ValueError(f"Process '{process_name}' cannot be covered with the provided configuration")

        return coverage

    def _check_controversial_requirements(self, deleted_processes, must_contain, coverage):
        for deleted in deleted_processes:
            if deleted in must_contain:
                raise ValueError(f"Forced to delete '{deleted}' process according to 'must not contain' property but it"
                                 f" is mentioned in 'must contain' properties. Such specification is controversial.")

    def _check_coverage_impact(self, process_name, coverage, scenario):
        return True


class CombinatorialFactory(ModelFactory):

    strategy = CombinatorialSelector
