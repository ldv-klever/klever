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

import re
import os

from klever.core.utils import make_relative_path
from klever.core.pfg.fragmentation import FragmentationAlgorythm
from klever.core.pfg.abstractions.strategies.callgraph import Callgraph
from klever.core.pfg.abstractions.strategies.coverage import Coverage


class Linux(FragmentationAlgorythm):

    CLADE_PRESET = 'linux_kernel'

    def __init__(self, logger, conf, tactic, pf_dir):
        super().__init__(logger, conf, tactic, pf_dir)
        self._max_size = tactic.get("maximum fragment size")
        self._separate_nested = tactic.get("separate nested subsystems", True)
        self.kernel = tactic.get("kernel", False)
        self._statically_linked = tactic.get("search by options")

    def _determine_units(self, program):
        """
        Create a module from all files compiled in .ko loadable module and files from directories compiled in modules
        build-in files also separate in units.

        :param program: Program object.
        """
        if self._statically_linked:
            self.logger.info("Search for modules that are linked to the kernel")
            self.search_for_statically_linked_modules(program)
        else:
            self._search_for_modules(program)
        if self.kernel:
            self.logger.info('Inspect AR comands in addition')
            self._search_for_modules(program, 'AR', 'built-in.a')

    def _search_for_modules(self, program, linking_command='LD', suffix='built-in.o'):
        for desc in program.clade.get_all_cmds_by_type(linking_command):
            identifier = desc['id']
            # This shouldn't happen ever, but let's fail otherwise.
            if len(desc['out']) != 1:
                self.logger.warning("{} commands with several out files are not supported, skip commands: {!r}".
                                    format(linking_command, identifier))
                continue

            out = desc['out'][0]
            if out.endswith('.ko') or out.endswith(suffix):
                rel_object_path = make_relative_path(self.source_paths, out)
                name = rel_object_path
                fragment = program.create_fragment_from_linker_cmds(identifier, desc, name,
                                                                    out.endswith(suffix) and self._separate_nested)
                if (not self._max_size or fragment.size <= self._max_size) and len(fragment.files) != 0:
                    program.add_fragment(fragment)
                else:
                    self.logger.debug('Fragment {!r} is rejected since it exceeds maximum size or does not contain '
                                      'files {!r}'.format(fragment.name, fragment.size))

    def search_for_statically_linked_modules(self, program):
        """Search for CC commands that are linked to a single kernel object usually but linked to the kernel now."""
        modules = dict()
        kbuiltstr_re = re.compile(r'KBUILD_STR\((\w+)\)')
        value_re = re.compile(r'\"(\w+)\"')
        valid_re = re.compile('\w+')
        for desc in program.clade.get_all_cmds_by_type('CC'):
            identifier = desc['id']
            if not desc['out']:
                self.logger.warning(f'Ignore command {identifier} without out file')
                continue

            opts = program.clade.get_cmd_opts(identifier)
            for option in opts:
                name = None
                if option.startswith('KBUILD_MODNAME='):
                    name = option.replace('KBUILD_MODNAME=', '')
                elif option.startswith('-DKBUILD_MODNAME'):
                    name = option.replace('-DKBUILD_MODNAME=', '')

                if name:
                    match1 = value_re.match(name)
                    match2 = kbuiltstr_re.match(name)
                    if match1:
                        name = match1.group(1)
                    elif match2:
                        name = match2.group(1)

                    if valid_re.match(name):
                        name += '.ko'
                        break

                    raise ValueError(f"Cannot parse the option: '{option}'")
            else:
                # We do not expect a command to be a module part
                self.logger.debug(f'No match for {identifier}')
                continue

            # Get C files
            files = program.collect_files_from_commands('CC', [desc])

            # Save before creating a fragment
            out = desc['out'][0]
            rel_object_path = make_relative_path(self.source_paths, out)
            name = os.path.join(os.path.dirname(rel_object_path), name)
            modules.setdefault(name, set())
            modules[name].update(files)

        # Finally create modules
        for name, files in modules.items():
            if not files:
                self.logger.warning(f'Cannot find C files for linker command {name}')

            fragment = program.create_fragment(name, files)
            if (not self._max_size or fragment.size <= self._max_size) and len(fragment.files) != 0:
                program.add_fragment(fragment)
            else:
                self.logger.debug('Fragment {!r} is rejected since it exceeds maximum size or does not contain '
                                  'files {!r}'.format(fragment.name, fragment.size))

    def _determine_targets(self, program):
        """
        There are two options: verification of modules, so all unts with .ko names can be target, and verification of
        kernel, so only build-in can be targets.

        :param program: Program object.
        """
        if self.kernel:
            self.logger.info('Searching for kernel parts instead of kernel objects')
        else:
            self.logger.info('Searching for kernel objects instead of statically linked parts')

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
        elif self.tactic.get('add modules by callgraph'):
            aggregator = Callgraph(self.logger, self.conf, self.tactic, program)
            return aggregator.get_groups()
        else:
            return super()._add_dependencies(program)
