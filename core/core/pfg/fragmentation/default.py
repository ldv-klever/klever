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
from core.pfg.fragmentation import FragmentationAlgorythm


class Default(FragmentationAlgorythm):

    def _determine_units(self, program):
        """
        Consider all program source files as independent program fragments.

        :param program: Program object.
        """
        for file in program.files:
            name = make_relative_path(self.source_paths, file.name)
            program.create_fragment(name, {file}, add=True)
