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

from core.utils import make_relative_path
from core.vog.fragmentation import FragmentationAlgorythm
from core.vog.abstractions.strategies.callgraph import Callgraph
from core.vog.abstractions.strategies.coverage import Coverage


class Linux(FragmentationAlgorythm):

    def __init__(self, logger, conf, desc, clade):
        super().__init__(logger, conf, desc, clade)
        self._max_size = self.desc.get("maximum fragment size")
        self._separate_nested = self.desc.get("separate nested subsystems", True)
        self.kernel = self.desc.get("kernel", False)

    def _determine_units(self, deps):
        for identifier, desc in deps.cmdg.LDs:
            # This shouldn't happen ever, but let's fail otherwise.
            if len(desc['out']) != 1:
                raise NotImplementedError

            out = desc['out'][0]
            if out.endswith('.ko') or out.endswith('built-in.o'):
                rel_object_path = make_relative_path(self.source_paths, out)
                name = rel_object_path
                fragment = deps.create_fragment_from_ld(identifier, desc, name, deps.cmdg,
                                                        out.endswith('built-in.o') and self._separate_nested)
                if not self._max_size or fragment.size <= self._max_size:
                    deps.add_fragment(fragment)
                else:
                    self.logger.debug('Fragment {!r} is rejected since it exceeds maximum size {!r}'.
                                      format(fragment.name, fragment.size))

    def _determine_targets(self, deps):
        super()._determine_targets(deps)
        for fragment in deps.target_fragments:
            if fragment.name.endswith('built-in.o') and not self.kernel:
                fragment.target = False
            elif fragment.name.endswith('.ko') and self.kernel:
                fragment.target = False

    def _do_postcomposition(self, deps):
        if self.desc.get('add modules by coverage'):
            aggregator = Coverage(self.logger, self.conf, self.desc, deps)
            return aggregator.get_groups()
        elif self.desc.get('add modules by callgraph'):
            aggregator = Callgraph(self.logger, self.conf, self.desc, deps)
            return aggregator.get_groups()
        else:
            return super()._do_postcomposition(deps)
