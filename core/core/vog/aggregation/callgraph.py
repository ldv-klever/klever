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

from core.vog.common import Aggregation
from core.vog.aggregation.abstract import Abstract


class Callgraph(Abstract):
    """This strategy gets a target fragment and adds recursievely fragments which are used by this one fragment."""

    def _aggregate(self):
        """
        Just return target fragments as aggregations consisting of fragments that are required by a target one
        collecting required fragments for given depth.

        :return: Generator that retursn Aggregation objects.
        """
        # First we need fragments that are completely fullfilled
        self.divider.establish_dependencies()
        max_deep = self.conf['Aggregation strategy'].get('dependencies recursive depth', 3)
        for fragment in self.divider.target_fragments:
            new = Aggregation(fragment)
            new.name = fragment.name
            self._add_dependencies(new, max_deep)
            yield new

    def _add_dependencies(self, aggregation, max_depth):
        cnt = max_depth
        layer = {aggregation.root}
        while layer and cnt:
            new_layer = set()
            for fragment in layer:
                aggregation.fragments.add(fragment)
                for dep in fragment.successors:
                    if dep not in aggregation.fragments and dep not in new_layer and dep not in layer:
                        new_layer.add(dep)
            layer = new_layer
            cnt -= 1
