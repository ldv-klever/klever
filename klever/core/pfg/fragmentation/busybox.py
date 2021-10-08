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

import os
import re

from klever.core.utils import make_relative_path
from klever.core.pfg.fragmentation import FragmentationAlgorythm


class Busybox(FragmentationAlgorythm):

    CLADE_PRESET = 'busybox_linux'

    def __init__(self, logger, conf, tactic, pf_dir):
        super().__init__(logger, conf, tactic, pf_dir)
        self._incorporate_libbb = tactic.get("include dependencies from libbb to applets fragments")
        self._match_files = dict()

    def _determine_units(self, program):
        """
        Find all files that has \w+_main function and add dependencies files except that ones that stored in libbb dir.
        All files from the libbb directory add to the specific unit with the libbb name.

        :param program: Program object.
        """
        main_func = re.compile("\\w+main")

        libbb = set()
        applets = dict()
        for file in program.files:
            rel_path = make_relative_path(self.source_paths, str(file))
            if os.path.commonpath(['libbb', rel_path]):
                libbb.add(file)
            else:
                for func in file.export_functions:
                    if main_func.match(func):
                        path, name = os.path.split(rel_path)
                        name = os.path.splitext(name)[0]
                        applets[name] = {file}
                        if self._incorporate_libbb:
                            dfiles = program.collect_dependencies({file})
                        else:
                            dfiles = program.collect_dependencies(
                                {file}, filter_func=lambda x:
                                    not os.path.commonpath(['libbb', make_relative_path(self.source_paths, x.name)]))
                        applets[name].update(dfiles)

        # Create fragments for found applets and libbb
        for name, files in applets.items():
            program.create_fragment(name, files, add=True)

            for file in files:
                if file.name not in self._match_files:
                    self._match_files[file.name] = 0
                else:
                    self._match_files[file.name] += 1

        program.create_fragment('libbb', libbb, add=True)

        self.logger.info('Found {} applets: {}'.format(len(applets), ', '.join(applets)))

    def _determine_targets(self, program):
        """
        Determine that program fragments that should be verified. We refer to these fragments as target fragments.

        :param program:
        :return:
        """
        super()._determine_targets(program)
        # Do not consider libbb files as targets
        for file in (program._files[f] for f in self._match_files if self._match_files[f] > 0):
            file.target = False
