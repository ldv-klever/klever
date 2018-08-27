#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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

import core.utils
from core.vog.fragmentation.abstract import AbstractDivider


class Single(AbstractDivider):

    def _divide(self):
        fragments = set()
        target_fragments = set()
        self.logger.info("Each c file will be considered as a separate fragment")
        cmdg = self.clade.CommandGraph()

        for identifier, desc in ((i, d) for i, d in cmdg.CCs if d.get('out')):
            rel_object_path = core.utils.make_relative_path(self.source.source_paths, desc['out'])
            name = rel_object_path
            fragment = self._create_fragment_from_cc(identifier, name)
            if self.source.check_target(rel_object_path):
                fragment.target = True
                target_fragments.add(fragment)
            fragments.add(fragment)

        self._fragments = fragments
        self._target_fragments = target_fragments
