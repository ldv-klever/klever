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

import os
from core.utils import make_relative_path
from core.vog.fragmentation.abstract import AbstractDivider


class Linux(AbstractDivider):

    def __init__(self, logger, conf, source, clade_api):
        super(Linux, self).__init__(logger, conf, source, clade_api)
        self._max_size = self.conf['Fragmentation strategy'].get("maximum fragment size")
        self._separate_nested = self.conf['Fragmentation strategy'].get("separate nested subsystems", True)

    def _divide(self):
        fragments = set()
        target_fragments = set()
        self.logger.info("Start division of the Linux kernel into atomic fragments")
        cmdg = self.clade.CommandGraph()
        srcg = self.clade.SourceGraph()

        for identifier, desc in cmdg.LDs:
            # This shouldn't happen ever, but let's fail otherwise.
            if len(desc['out']) != 1:
                raise NotImplementedError

            out = desc['out'][0]
            if out.endswith('.ko') or out.endswith('built-in.o'):
                rel_object_path = make_relative_path(self.source.source_paths, out)
                name = rel_object_path
                fragment = self._create_fragment_from_ld(identifier, desc, name, cmdg, srcg,
                                                         out.endswith('built-in.o') and self._separate_nested)
                if not self._max_size or fragment.size <= self._max_size:
                    if self.source.check_target(rel_object_path):
                        fragment.target = True
                        target_fragments.add(fragment)
                    fragments.add(fragment)
                else:
                    self.logger.debug('Fragment {!r} is rejected since it exceeds maximum size {!r}'.
                                      format(fragment.name, fragment.size))

        self._fragments = fragments
        self._target_fragments = target_fragments
