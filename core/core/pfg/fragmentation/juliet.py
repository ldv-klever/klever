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


class Juliet(FragmentationAlgorythm):

    CLADE_PRESET = 'base'

    def __init__(self, logger, conf, desc, pf_dir):
        super().__init__(logger, conf, desc, pf_dir)

    def _determine_units(self, program):
        """
        Determine them by .out linking commands.

        :param program: Program object.
        """
        for desc in program.clade.get_all_cmds_by_type("CC"):
            identifier = desc['id']
            # This shouldn't happen ever, but let's fail otherwise.
            if len(desc['out']) != 1:
                self.logger.warning("LD commands with several out files are not supported, skip commands: {!r}".
                                    format(identifier))
                continue

            out = desc['out'][0]
            if out.endswith('.out'):
                files = set()
                for in_file in desc['in']:
                    if not in_file.endswith('.c'):
                        continue
                    file = program.get_file(in_file)
                    files.add(file)

                ccs = self.clade.get_root_cmds_by_type(identifier, "CC")
                for i in ccs:
                    d = self.clade.get_cmd(i)
                    for in_file in d['in']:
                        if not in_file.endswith('.c'):
                            self.logger.warning(
                                "You should implement more strict filters to reject CC commands with such "
                                "input files as {!r}".format(in_file))
                            continue
                        file = program.get_file(in_file)
                        files.add(file)

                if len(files) == 0:
                    self.logger.warning('Cannot find C files for LD command {!r}'.format(out))

                program.create_fragment(make_relative_path(self.source_paths, out), files, add=True)
        self.logger.debug('Found {} programs'.format(len(program.fragments)))
