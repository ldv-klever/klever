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

from klever.core.utils import make_relative_path
from klever.core.pfg.fragmentation import FragmentationAlgorythm
from klever.core.pfg.abstractions.strategies.callgraph import Callgraph
from klever.core.pfg.abstractions.strategies.coverage import Coverage


class Linux(FragmentationAlgorythm):

    CLADE_PRESET = 'linux_kernel'

    def __init__(self, logger, conf, tactic):
        super().__init__(logger, conf, tactic)
        self._max_size = tactic.get("maximum fragment size")
        self._separate_nested = tactic.get("separate nested subsystems", True)
        self.kernel = tactic.get("kernel", False)

    def _determine_units(self, program):
        """
        Create a module from all files compiled in .ko loadable module and files from directories compiled in modules
        build-in files also separate in units.

        :param program: Program object.
        """
        for desc in program.clade.get_all_cmds_by_type("LD"):
            identifier = desc['id']
            # This shouldn't happen ever, but let's fail otherwise.
            if len(desc['out']) != 1:
                self.logger.warning("LD commands with several out files are not supported, skip commands: {!r}".
                                    format(identifier))
                continue

            out = desc['out'][0]
            if out.endswith('.ko') or out.endswith('built-in.o'):
                rel_object_path = make_relative_path(self.source_paths, out)
                name = rel_object_path
                fragment = program.create_fragment_from_linker_cmds(identifier, desc, name,
                                                                    out.endswith('built-in.o') and self._separate_nested)
                if (not self._max_size or fragment.size <= self._max_size) and len(fragment.files) != 0:
                    program.add_fragment(fragment)
                else:
                    self.logger.debug('Fragment {!r} is rejected since it exceeds maximum size or does not contain '
                                      'files {!r}'.format(fragment.name, fragment.size))

    def _determine_targets(self, program):
        """
        There are two options: verification of modules, so all units with .ko names can be target, and verification of
        kernel, so only build-in can be targets.

        :param program: Program object.
        """
        super()._determine_targets(program)
        for fragment in program.target_fragments:
            if fragment.name.endswith('built-in.o') and not self.kernel:
                fragment.target = False
            elif fragment.name.endswith('.ko') and self.kernel:
                fragment.target = False

    def _add_dependencies(self, program):
        """
        Apply one of three options to add dependencies: add nothing (most often used), add dependencies on the base of
        the function callgraph (rarely used) and add dependencies on the base of coverage (used at kernel verification).

        :param program: Program object.
        :return: Dictionary with sets of fragments.
        """
        if self.tactic.get('add modules by coverage'):
            aggregator = Coverage(self.logger, self.conf, self.tactic, program)
            return aggregator.get_groups()
        if self.tactic.get('add modules by callgraph'):
            aggregator = Callgraph(self.logger, self.conf, self.tactic, program)
            return aggregator.get_groups()

        return super()._add_dependencies(program)
