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
import re

from core.pfg.fragmentation import FragmentationAlgorythm


class Busybox(FragmentationAlgorythm):

    CLADE_PRESET = 'busybox_linux'

    def __init__(self, logger, conf, desc, clade):
        super().__init__(logger, conf, desc, clade)
        self._incorporate_libbb = self.desc.get("include dependencies from libbb to applets fragments")

    def _determine_units(self, deps):
        main_func = re.compile("\\w+main")

        libbb = set()
        applets = dict()
        for file in deps.files:
            if os.path.commonpath(['libbb', file.name]):
                libbb.add(file)
            else:
                for func in file.export_functions:
                    if main_func.match(func):
                        path, name = os.path.split(file.name)
                        name = os.path.splitext(name)[0]
                        applets[name] = {file}
                        if self._incorporate_libbb:
                            dfiles = deps.collect_dependencies({file})
                        else:
                            dfiles = deps.collect_dependencies(
                                {file}, filter_func=lambda x: not os.path.commonpath(['libbb', x.name]))
                        applets[name].update(dfiles)

        # Create fragments for found applets and libbb
        for name, files in applets.items():
            deps.create_fragment(name, files, add=True)
        deps.create_fragment('libbb', libbb, add=True)

        self.logger.info('Found {} applets: {}'.format(len(applets), ', '.join(applets)))

