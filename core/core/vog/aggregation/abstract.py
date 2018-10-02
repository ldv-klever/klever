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

import re
import os
import ujson
import graphviz

from core.vog.common import Fragment


class Abstract:

    DESC_FILE = 'agregations description.json'

    def __init__(self, logger, conf, divider):
        self.logger = logger
        self.conf = conf
        self.divider = divider
        self.clade = self.divider.clade
        self._aggregations = set()

        self._max_size = self.conf['Aggregation strategy'].get('maximum verification object size')
        self._add_to_all = self.conf['Aggregation strategy'].get('add to all', set())
        self._remove_from_all = self.conf['Aggregation strategy'].get('remove from all', set())
        self._add_to_fragments = self.conf['Aggregation strategy'].get('add to aggregations', set())
        self._rm_from_fragments = self.conf['Aggregation strategy'].get('remove from aggregations', set())
        self._func_by_frags = self.conf['Aggregation strategy'].get('search fragments for functions', True)

        self.dynamic_excluded_clean = list()

    @property
    def aggregations(self):
        if not self._aggregations:
            self._aggregations = set(self._aggregate())
            if self._add_to_all or self._remove_from_all or self._add_to_fragments or self._rm_from_fragments:
                c_to_deps, f_to_deps, f_to_files, c_to_frag = self.divider.establish_dependencies()

                for agg in self._aggregations:
                    self._add_or_remove_elements(agg, self._add_to_all, c_to_deps, f_to_deps, f_to_files, c_to_frag,
                                                 add=True)
                    self._add_or_remove_elements(agg, self._remove_from_all, c_to_deps, f_to_deps, f_to_files,
                                                 c_to_frag, add=False)
                    if agg.name in self._add_to_fragments:
                        self._add_or_remove_elements(agg, self._add_to_fragments[agg.name], c_to_deps, f_to_deps,
                                                     f_to_files, c_to_frag, add=True)
                    if agg.name in self._rm_from_fragments:
                        self._add_or_remove_elements(agg, self._rm_from_fragments[agg.name], c_to_deps, f_to_deps,
                                                     f_to_files, c_to_frag, add=False)
        return self._aggregations

    @property
    def attributes(self):
        data = dict()
        for a in self.aggregations:
            data[a.name] = {f.name: list(f.in_files) for f in a.fragments}

        with open(self.DESC_FILE, 'w', encoding='utf8') as fp:
            ujson.dump(data, fp, sort_keys=True, indent=4, ensure_ascii=False,
                       escape_forward_slashes=False)

        return [{
            'name': 'Aggregation strategy',
            'value': [{'name': 'name', 'value': self.conf['Aggregation strategy']['name'], 'data': self.DESC_FILE}]
        }], [self.DESC_FILE]

    def generate_verification_objects(self):
        for aggregation in self.aggregations:
            if not self._max_size or aggregation.size <= self._max_size:
                if self.conf['Aggregation strategy'].get('draw aggregations'):
                    self.draw_aggregation(aggregation)
                yield self.__describe_verification_object(aggregation)
            else:
                self.logger.debug('verification object {!r} is rejected since it exceeds maximum size {}'.
                                  format(aggregation.name, aggregation.size()))

    def _aggregate(self):
        raise NotImplementedError

    def _belong(self, fragment, target):
        if re.search(r'\.o$', target):
            # This is an object file
            return fragment.name == target
        elif re.search(r'\.c$', target):
            # This is a C file
            return target in fragment.in_files
        else:
            # This is a dir
            return os.path.dirname(target) == os.path.dirname(fragment.name)

    def _check_filters(self, fragment):
        return True

    def _add_dependencies(self, aggregation, depth=None, maxfrags=None):
        layer = {aggregation.root}
        while layer and (depth is None or depth > 0) and (maxfrags is None or maxfrags > 0):
            new_layer = set()
            for fragment in layer:
                aggregation.fragments.add(fragment)
                if maxfrags:
                    maxfrags -= 1
                if maxfrags is not None and maxfrags == 0:
                    break

                for dep in fragment.successors:
                    if dep not in aggregation.fragments and dep not in new_layer and dep not in layer and \
                            self._check_filters(dep):
                        new_layer.add(dep)

            layer = new_layer
            if depth is not None:
                depth -= 1

    def __describe_verification_object(self, aggregation):
        self.logger.info('Generate verification object description for aggregation {!r}'.format(aggregation.name))
        vo_desc = dict()
        vo_desc['id'] = aggregation.name
        vo_desc['grps'] = list()
        vo_desc['deps'] = dict()
        for frag in aggregation.fragments:
            vo_desc['grps'].append({'id': frag.name, 'CCs': frag.ccs})
            vo_desc['deps'][frag.name] = [succ.name for succ in frag.successors if succ in aggregation.fragments]
        self.logger.debug('verification object dependencies are {}'.format(vo_desc['deps']))

        vo_desc_file = vo_desc['id'] + '.json'
        if os.path.isfile(vo_desc_file):
            raise FileExistsError('verification object description file {!r} already exists'.format(vo_desc_file))
        self.logger.debug('Dump verification object description {!r} to file {!r}'.format(vo_desc['id'], vo_desc_file))
        dir_path = os.path.dirname(vo_desc_file).encode('utf8')
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        # Add dir to exlcuded from cleaning by lkvog
        root_dir_id = vo_desc_file.split('/')[0]
        if root_dir_id not in self.dynamic_excluded_clean:
            self.logger.debug("Do not clean dir {!r} on component termination".format(root_dir_id))
            self.dynamic_excluded_clean.append(root_dir_id)

        with open(vo_desc_file, 'w', encoding='utf8') as fp:
            ujson.dump(vo_desc, fp, sort_keys=True, indent=4, ensure_ascii=False, escape_forward_slashes=False)
        return vo_desc_file

    def draw_aggregation(self, aggregation):
        g = graphviz.Digraph(graph_attr={'rankdir': 'LR'}, node_attr={'shape': 'rectangle'})
        for fragment in aggregation.fragments:
            g.node(fragment.name, "{}".format(fragment.name) + (' (target)' if fragment.target else ''))

        for fragment in aggregation.fragments:
            for suc in fragment.successors:
                if suc in aggregation.fragments:
                    g.edge(fragment.name, suc.name)
        if not os.path.exists('aggregations'):
            os.makedirs('aggregations')
        g.render(os.path.join('aggregations', aggregation.name))

    def _add_or_remove_file(self, aggregation, cfrag, file, add=True):
        if add and cfrag[file] not in aggregation.fragments:
            # Create an artificial fragment and add it
            cc = [cc for cc in cfrag[file].ccs if self.clade.get_cc(cc)['in'][0] == file][0]
            new_frag = Fragment(file)
            new_frag.ccs.add(cc)
            new_frag.in_files.add(file)
            aggregation.fragments.add(new_frag)
        elif file in self._remove_from_all:
            # Remove file directly from the fragment
            cc = [cc for cc in cfrag[file].ccs if self.clade.get_cc(cc)['in'][0] == file][0]
            cfrag[file].ccs.remove(cc)
            cfrag[file].in_files.remove(file)
        elif not add and cfrag[file] in aggregation.fragments:
            # We need to remove file from particular aggregation, so clone fragment and remove the file
            aggregation.fragments.remove(cfrag[file])
            cc = [cc for cc in cfrag[file].ccs if self.clade.get_cc(cc)['in'][0] == file][0]
            new_frag = Fragment(cfrag[file].name)
            new_frag.ccs = set(cfrag[file].ccs)
            new_frag.in_files = set(cfrag[file].in_files)
            new_frag.ccs.remove(cc)
            new_frag.in_files.remove(file)
            aggregation.fragments.add(new_frag)

    def _add_or_remove_frag(self, aggregation, frag, add=True):
        if add:
            aggregation.fragments.add(frag)
        else:
            fs = [f for f in aggregation.fragments if frag.name == f.name]
            if len(fs) > 0:
                for f in fs:
                    aggregation.fragments.remove(f)

    def _collect_fragments_for_functions(self, aggregation, functions, cmap, fmap, add=True):
        done = True
        while done and len(functions) > 0:
            done = False

            func = functions.pop()
            # As we are not sure about the scope lets try to find a fragment which is required by any of mentioned
            # otherwise it is not clear why we should add any if no calls detected.
            candidates = fmap[func]
            possible_cfiles = set()

            for frag in aggregation.fragments:
                for cf in frag.in_files:
                    possible_cfiles.add(cf)
                    possible_cfiles.update(cmap.get(cf, set()))

            for candidate in candidates:
                # Do this to avoid adding fragments which have nothing to do with chosen
                if possible_cfiles.intersection(candidate.in_files):
                    # Here we deal with files
                    self._add_or_remove_frag(aggregation, candidate, add)

                    # If we will not any fragments then maybe we need to add more fragments for other functions first
                    done = True

        if not done and len(functions) > 0:
            raise ValueError("Cannot find suitable fragments for functions: {}".format(', '.join(functions)))

    def _add_or_remove_elements(self, aggregation, nset, cmap, fmap, ffiles, cfrag, add=True):
        """
        Get an aggregation and a set of names of funcitons, files or fragments. Then remove or add them from/to the
        given aggregation.

        :param aggregation: Aggregation object.
        :param nset: Set of names to check.
        :param cmap: {c_file_name -> [c_file_names]} The right part contains files which provide implementations of
                     functions for the first one.
        :param fmap: {func_name -> [fragments]} Fragments that implement function func.
        :param ffiles: {func_name -> [files]} Files that implement the function.
        :param cfrag: {c_file_name -> fragment]} Fragment that contains this C file.
        :param add: Add or remove files, fragments or functions from the aggregation.
        :return: Aggregation object.
        """
        functions = []
        for frag_or_func in nset:
            # Check that it is a fragment
            frag = self.divider.find_fragment_by_name(frag_or_func)
            # It is a fragment
            if frag:
                self._add_or_remove_frag(aggregation, frag, add)
                continue

            # It is a file
            if frag_or_func in cfrag and cfrag[frag_or_func] and frag_or_func in cfrag[frag_or_func].in_files:
                self._add_or_remove_file(aggregation, cfrag, frag_or_func, add)
                continue

            # It is a function
            if frag_or_func in fmap:
                functions.append(frag_or_func)
                continue

        if self._func_by_frags:
            self._collect_fragments_for_functions(aggregation, functions, cmap, fmap, add=add)
        else:
            files = set()
            for func in functions:
                files.update(ffiles[func])
            for file in files:
                self._add_or_remove_file(aggregation, cfrag, file, add)

        return aggregation
