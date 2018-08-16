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
from core.vog.dividers.abstract import AbstractDivider


class Linux(AbstractDivider):

    def __init__(self, logger, conf, source, clade_api):
        super(Linux, self).__init__(logger, conf, source, clade_api)
        self._kernel_verification = self.conf['VOG divider'].get('target kernel', False)
        self._max_size = self.conf['project'].get("maximum unit size")

    def _divide(self):
        units = set()
        target_units = set()
        self.logger.info("Start division of the Linux kernel into atomic units")
        cmdg = self.clade.CommandGraph()
        srcg = self.clade.SourceGraph()

        for identifier, desc in cmdg.LDs:
            if desc['out'].endswith('.ko') or (self._kernel_verification and desc['out'].endswith('built-in.o')):
                rel_object_path = make_relative_path(self.source.source_paths, desc['out'])
                name = rel_object_path
                unit = self._create_unit_from_ld(identifier, name, cmdg, srcg)
                if not self._max_size or unit.size <= self._max_size:
                    if self.source.check_target(rel_object_path):
                        unit.target = True
                        target_units.add(unit)
                    units.add(unit)
                else:
                    self.logger.debug('unit {!r} is rejected since it exceeds maximum size {!r}'.
                                      format(unit.name, unit.size))

        self._units = units
        self._target_units = target_units
