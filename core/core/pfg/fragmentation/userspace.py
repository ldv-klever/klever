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


class Userspace(FragmentationAlgorythm):

    CLADE_PRESET = 'base'

    def __init__(self, logger, conf, desc, pf_dir):
        super().__init__(logger, conf, desc, pf_dir)

    def _determine_units(self, program):
        """
        Find all files that has \w+_main function and add dependecnies files except that ones that stored in libbb dir.
        All files from the libbb directory add to the specific unit with the libbb name.

        :param program: Program object.
        """
        main_func = re.compile("main")

        # Get programs by callgraph
        programs = dict()
        for file in program.files:
            if any(map(main_func.match, file.export_functions)):
                name = os.path.basename(file.name).split('.')[0]
                programs[name] = {file}
                dep_files = program.collect_dependencies(
                    {file},
                    filter_func=lambda x: True if not any(map(main_func.match, x.export_functions)) else False)
                programs[name].update(dep_files)

        # Create fragments for programs
        for name, files in programs.items():
            program.create_fragment(name, files, add=True)

        self.logger.debug('Found {} programs'.format(len(programs)))
