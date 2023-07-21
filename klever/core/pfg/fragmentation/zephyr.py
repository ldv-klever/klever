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

from klever.core.pfg.fragmentation import FragmentationAlgorythm


class Zephyr(FragmentationAlgorythm):

    CLADE_PRESET = 'base_print'

    def _determine_units(self, program):
        """
        Create a module from all files compiled in .ko loadable module and files from directories compiled in modules
        build-in files also separate in units.

        :param program: Program object.
        """
        zephyr = set()
        for file in program.files:
            # TODO: This should be fixed using the decomposition strategy and presets
            if file.name[-2:] == '.c' and 'configs.c' not in file.name:
                zephyr.add(file)

        program.create_fragment('zephyr', zephyr, add=True)

        self.logger.info('Created zephyr fragment')
