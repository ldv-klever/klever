#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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

from core.pfg.abstractions.strategies import Abstract


class Callgraph(Abstract):
    """This strategy gets a target fragment and adds recursievely fragments which are used by this one fragment."""

    def _make_groups(self):
        """
        Just return target fragments as aggregations consisting of fragments that are required by a target one
        collecting required fragments for given depth.

        :return: {GroupName: Set of Fragments}.
        """
        # First we need fragments that are completely fullfilled
        max_deep = self.desc.get('dependencies recursive depth', 3)
        max_size = self.desc.get('maximum files')
        for fragment in self.deps.target_fragments:
            name = fragment.name
            files = self.deps.collect_dependencies(fragment.files, depth=max_deep, maxfrags=max_size)
            fragments = self.deps.find_fragments_with_files(files)
            fragments.add(fragment)
            self.add_group(name, fragments)
