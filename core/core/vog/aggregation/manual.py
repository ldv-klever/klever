#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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

from core.vog.common import Aggregation
from core.vog.aggregation.abstract import Abstract


class Manual(Abstract):
    """
    This is a manual strategy to specify aggregations. A user should manually specify for each target fragment
    a list of lists of fragments or export functions to find and add. For missed descriptions the strategy just
    generates an aggregation with a single fragment.
    """

    def __init__(self, logger, conf, divider):
        super(Manual, self).__init__(logger, conf, divider)
        self.fragments_map = self.conf['Aggregation strategy'].get('aggregations')
        if not self.fragments_map:
            raise ValueError("Provide configuration property 'aggregations' to ")

    def _aggregate(self):
        """
        Collect fragments set by a user explicitly by name of export functions.

        :return: Generator that retursn Aggregation objects.
        """
        # First we need fragments that are completely fullfilled
        c_to_deps, f_to_deps, c_to_frag = self.divider.establish_dependencies()
        for fragment in self.divider.target_fragments:
            if fragment.name in self.fragments_map:
                # Expect specified set
                desc = self.fragments_map[fragment.name]
                if not isinstance(desc, list) or any(not isinstance(i, list) for i in desc):
                    raise ValueError('For {!r} fragment provide a list of lists of fragment or functions names')

                if len(self.fragments_map[fragment.name]) == 0:
                    self.logger.warning("Skip fragment {!r} as no fragments to include were given"
                                        .format(fragment.name))
                elif len(self.fragments_map[fragment.name]) == 1:
                    yield self._collect_frgments(fragment.name, desc[0], c_to_deps, f_to_deps, c_to_frag)
                else:
                    for i, nset in enumerate(desc):
                        name = "{}:{}".format(fragment.name, i)
                        yield self._collect_frgments(name, nset, c_to_deps, f_to_deps, c_to_frag)
            else:
                self.logger.warning("There is no manual specified description for fragment {!r}".format(fragment.name))
                new = Aggregation(fragment)
                new.name = fragment.name
                yield new

    def _collect_frgments(self, name, nset, cmap, fmap, cfrag):
        """
        Create an aggregation by given names of fragments, C files or function names.

        :param name: Name of the new aggragation.
        :param nset: Set of names to check.
        :param cmap: {c_file_name -> [c_file_names]} The right part contains files which provide implementations of
                     functions for the first one.
        :param fmap: {func_name -> [fragments]} Fragments that implement function func.
        :param cfrag: {c_file_name -> fragment]} Fragment that contains this C file.
        :return: Aggregation object.
        """
        new = Aggregation(name=name)
        functions = []
        for frag_or_func in nset:
            # Check that it is a fragment
            frag = self.divider.find_fragment_by_name(frag_or_func)
            if frag:
                new.fragments.add(frag)
                continue

            if frag_or_func in cfrag and cfrag[frag_or_func]:
                new.fragments.add(cfrag[frag_or_func])
                continue

            if frag_or_func in fmap:
                functions.append(frag_or_func)
                continue

            raise ValueError("Cannot find a fragment, a C file or a function with the name {!r}".format(frag_or_func))

        done = True
        while done and len(functions) > 0:
            done = False

            func = functions.pop()
            # As we are not sure about the scope lets try to find a fragment which is required by any of mentioned
            # otherwise it is not clear why we should add any if no calls detected.
            candidates = fmap[func]
            possible_cfiles = set()

            for frag in new.fragments:
                for cf in frag.in_files:
                    possible_cfiles.add(cf)
                    possible_cfiles.update(cmap.get(cf, set()))

            for candidate in candidates:
                # Do this to avoid adding fragments which have nothing to do with chosen
                if possible_cfiles.intersection(candidate.in_files):
                    new.fragments.add(candidate)
                    # If we will not any fragments then maybe we need to add more fragments for other functions first
                    done = True

        if not done and len(functions) > 0:
            raise ValueError("Cannot find suitable fragments for functions: {}".format(', '.join(to_process)))

        return new
