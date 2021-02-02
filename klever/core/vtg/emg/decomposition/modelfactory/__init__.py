#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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


class ModelFactory:

    def __init__(self, logger, conf, model):
        self.logger = logger
        self.conf = conf
        self.origin_model = model

    def generate_models(self, processes_to_scenarios):
        return []

    def _choose_scenarios_for_model(self, processes_to_scenarios):
        root_process = self.origin_model.entry
        pass

    def _find_process_peers(self):
        # todo: Implement a tactic to choose scenarios
        pass


    def _clone_process(self, process):
        # todo: Copy the process completely
        pass

    def _replace_actions(self, process, scenario):
        # todo: Replace actions by the actions from the scenario
        # todo: Find unused labels and delete them also
        pass

    def _prepare_savepoint_block(self, process, savepoint):
        # todo: Determine the initial action
        # todo: Remove it and add a new Block action instead of it
        pass

    def _replace_signal_peers(self, process, old_to_new):
        # todo: Replace old peers with the new ones
        pass
