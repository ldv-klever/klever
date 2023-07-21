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

import ujson
import zipfile


from klever.core.pfg.abstractions.strategies import Abstract
import klever.core.utils


class Coverage(Abstract):
    """
    This strategy gets information about coverage of fragments and searches for suitable fragments to add to cover
    functions exported by target ones.
    """

    def __init__(self, logger, conf, tactic, program):
        super().__init__(logger, conf, tactic, program)
        self.archive = conf.get('coverage archive')
        self._black_list = set(self.tactic.get('ignore fragments', set()))
        self._white_list = set(self.tactic.get('prefer fragments', set()))

        # Get archive
        if not self.archive:
            raise ValueError("Provide 'coverage archive' configuration property with the coverage archive file name")
        archive = klever.core.utils.find_file_or_dir(self.logger, self.conf['main working directory'], self.archive)

        # Extract/fetch file
        with zipfile.ZipFile(archive) as z:
            with z.open('coverage.json') as zf:
                coverage = ujson.load(zf) # pylint: disable=c-extension-no-member

        # Extract information on functions
        self._func_coverage = coverage.get('functions statistics')
        if not self._func_coverage or not self._func_coverage.get('statistics'):
            raise ValueError("There is no statistics about functions in the given coverage archive")
        self._func_coverage = {p.replace('source files/', ''): v
                               for p, v in self._func_coverage.get('statistics').items()}
        self._func_coverage.pop('overall')

    def _generate_groups_for_target(self, fragment):
        """
        For each target fragment search for fragments that call functions from files of this target fragment. But find
        a minimal set and only that fragments that have these calls in the covered  code.

        :param fragment: Fragment object.
        """
        cg = self.program.clade.callgraph
        self.logger.info("Find fragments that call functions from the target fragment {!r}".format(fragment.name))
        # Search for export functions
        ranking = {}
        function_map = {}
        for path in fragment.files:
            for func in path.export_functions:
                # Find fragments that call this function
                relevant = self._find_fragments(fragment, path, func, cg)
                for rel in relevant:
                    ranking.setdefault(rel.name, 0)
                    ranking[rel.name] += 1
                    function_map.setdefault(func, set())
                    function_map[func].update(relevant)

        # Use a greedy algorythm. Go from functions that most rarely used and add fragments that most oftenly used
        # Turn into account white and black lists
        added = set()
        for func in (f for f in sorted(function_map.keys(), key=lambda x: len(function_map[x]))
                     if len(function_map[f])):
            if function_map[func].intersection(added):
                # Already added
                continue

            possible = {f.name for f in function_map[func]}.intersection(self._white_list)
            if not possible:
                # Get rest
                possible = {f.name for f in function_map[func]}.difference(self._black_list)
            if possible:
                added.add(sorted((f for f in function_map[func] if f.name in possible),
                                 key=lambda x: ranking[x.name], reverse=True)[0])

        # Now generate pairs
        return [("{}:{}".format(fragment.name, frag.name), fragment, {fragment, frag}) for frag in added] + \
               [(fragment.name, fragment, {fragment})]

    def _find_fragments(self, fragment, path, func, cg):
        """
        Find all fragments that contain calls of the given function.

        :param fragment: Fragment object with the function definition.
        :param path: file with the function definition.
        :param func: function name.
        :param cg: Callgraph dict.
        :return: A set of Fragment objects.
        """
        result = set()
        # Get functions from the callgraph
        desc = cg.get(path.name, {}).get(func)
        if desc:
            for scope, called_funcs in ((s, d) for s, d in desc.get('called_in', {}).items()
                                        if s != path.name and s in self._func_coverage):
                if any(True for f in called_funcs if f in self._func_coverage[scope]):
                    # Found function call in covered functions retrieve Fragment and add to result
                    frags = self.program.get_fragments_with_files([scope])
                    for new in frags:
                        if new in self.program.get_fragment_predecessors(fragment):
                            result.add(new)
        self.logger.debug("Found the following caller of function {!r} from {!r}: {!r}".
                          format(func, path, ', '.join((f.name for f in result))))
        return result
