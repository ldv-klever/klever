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


class Separate(Abstract):
    """This strategy just returns as aggregations separate fragments marked as target ones."""

    def _aggregate(self):
        """
        Just return target fragments as aggregations consisting of a single fragment.

        :return: Generator that retursn Aggregation objects.
        """
        for fragment in self.divider.target_fragments:
            new = Aggregation(fragment)
            new.name = fragment.name
            yield new
