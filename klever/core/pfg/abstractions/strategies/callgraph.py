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

from klever.core.pfg.abstractions.strategies import Abstract


class Callgraph(Abstract):
    """This strategy gets a target fragment and adds recursively fragments which are used by this one fragment."""

    def __init__(self, logger, conf, tactic, program):
        """
        Simple strategy to add dependencies to each target fragment.

        :param logger: Logger object.
        :param conf: Configuration dictionary.
        :param tactic: Fragmentation set dictionary.
        :param program: Program object.
        """
        super().__init__(logger, conf, tactic, program)
        self._max_deep = self.tactic.get('dependencies recursive depth', 3)
        self._max_size = self.tactic.get('maximum files')

    def _generate_groups_for_target(self, fragment):
        """
        Just return target fragments as aggregations consisting of fragments that are required by a target one
        collecting required fragments for given depth.

        :param fragment: Fragment object.
        """
        name = fragment.name
        files = self.program.collect_dependencies(fragment.files, depth=self._max_deep, max=self._max_size)
        fragments = self.program.get_fragments_with_files(files)
        fragments.add(fragment)
        return [(name, fragment, fragments)]
