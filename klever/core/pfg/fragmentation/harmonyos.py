#
# Copyright (c) 2020 ISP RAS (http://www.ispras.ru)
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

from klever.core.utils import make_relative_path
from klever.core.pfg.fragmentation import FragmentationAlgorythm


class Harmonyos(FragmentationAlgorythm):

    CLADE_PRESET = 'base_print'

    def _determine_units(self, program):
        """
        Create verification units using build commands or file names. Currently there is a single unit can be crated.

        :param program: Program object.
        """
        # Get all C files
        decompostion_map = program.cmnds_recursive_tree_traversing('CC', ('Objcopy',))
        for program_identifier, files in decompostion_map.items():
            name = make_relative_path(self.source_paths, program_identifier)
            program.create_fragment(name, files, add=True)
            self.logger.info(f'Created harmonyos fragment {name}')

    def __init__(self, logger, conf, tactic, pf_dir):
        super().__init__(logger, conf, tactic, pf_dir)