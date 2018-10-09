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
import ujson

from graphviz import Digraph

from core.vog.abstractions import Dependencies
from core.vog.abstractions.strategies import Abstract


class FragmentationAlgorythm:

    def __init__(self, logger, conf, desc, clade):
        # Simple attributes
        self.logger = logger
        self.conf = conf
        self.desc = desc
        self.clade = clade
        self.dynamic_excluded_clean = list()

        # Complex attributes
        self.source_paths = self.__retrieve_source_paths()
        self.attributes = self.__attributes()

    def fragmentation(self):
        cg = self.clade.CallGraph().graph
        fs = self.clade.FunctionsScopes().scope_to_funcs

        # Extract dependencies
        deps = Dependencies(cg, fs)

        # Decompose using units
        self._determine_units(deps)

        # Mark dirs, units, files, functions
        self._determine_targets(deps)

        # Prepare semifinal fragments according to strategy chosen manually
        self._do_manual_correction(deps)

        # Prepare final optional addiction of fragments if necessary
        grps = self._do_postcomposition(deps)

        # Prepare verification objects
        fragments_files = self.__generate_verification_objects(grps)

        # Prepare data attributes
        attr_data = self.__prepare_data_files(grps)

        # Print fragments
        if self.desc.get('Print fragments'):
            self.__print_fragments(deps)
            for fragment in deps.fragments:
                self.__draw_fragment(fragment)

        return attr_data, fragments_files

    def _determine_units(self, deps):
        pass

    def _determine_targets(self, deps):
        add = set(self.conf.get('add', set()))
        exclude = set(self.conf.get('exclude', set()))

        files = set()
        new_files, matched = deps.find_files_for_expressions(add)
        files.update(new_files)
        add.difference_update(matched)
        if len(add) > 0:
                raise ValueError('Cannot find fragments, files or functions for the following expressions: {}'.
                                 format(', '.join(add)))
        new_files, matched = deps.find_files_for_expressions(exclude)
        files.difference_update(new_files)

        for file in files:
            self.logger.info('Mark file {!r} as a target'.format(file.name))
            file.target = True

    def _do_manual_correction(self, deps):
        self.logger.info("Adjust fragments according to the manually provided fragmentation set")
        self.__fragments = self.desc.get('fragments', list())
        self._remove = set(self.desc.get('remove from all', set()))
        self._add = set(self.desc.get('add to all', set()))
        description = self.__fragments
        new = list()

        # Collect files
        for frags_exprs in description:
            files = set()

            new_files, matched = deps.find_files_for_expressions(frags_exprs)
            files.update(new_files)

            frags_exprs.difference_update(matched)
            if len(frags_exprs) > 0:
                raise ValueError('Cannot find fragments, files or functions for the following expressions: {}'.
                                 format(', '.join(frags_exprs)))

            new.append(files)

        # Find relevant fragments
        all_files = set()
        for files in new:
            all_files.update(files)
        fragments = deps.find_fragments_with_files(all_files)

        # Remove them
        for fragment in fragments:
            deps.remove_fragment(fragment)

        # Create new fragments
        for files in new:
            deps.create_fragment(None, files)

        # Add all
        addiction, _ = deps.find_files_for_expressions(self._add)

        # Remove all
        removal, _ = deps.find_files_for_expressions(self._remove)

        # Do modification
        empty = set()
        for fragment in deps.fragments:
            fragment.files.update(addiction)
            fragment.files.difference_update(addiction)
            if not fragment.files:
                empty.add(fragment)

        # Remove empty
        for fragment in empty:
            deps.remove_fragment(fragment)

    def _do_postcomposition(self, deps):
        aggregator = Abstract(self.logger, self.conf, self.desc, deps)
        return aggregator.get_groups()

    def __prepare_data_files(self, grps):
        data = dict()
        for name, frags in grps.items():
            data[name] = {f.name: sorted(map(str, f.files)) for f in frags}

        with open('agregations description.json', 'w', encoding='utf8') as fp:
            ujson.dump(data, fp, sort_keys=True, indent=4, ensure_ascii=False,
                       escape_forward_slashes=False)

        return [{
            'name': 'Decomposition strategy',
            'value': [{'name': 'name', 'value': self.conf['program'], 'data': 'agregations description.json'}]
        }], ['agregations description.json']

    def __retrieve_source_paths(self):
        path = self.clade.FileStorage().convert_path('source paths.json')
        with open(path, 'r', encoding='utf8') as fp:
            paths = ujson.load(fp)
        return paths

    def __attributes(self):
        attrs = [
            {'name': 'kind', 'value': self.desc['program']},
            {'name': 'decomposition set', 'value': self.conf['fragmentation set']},
            {'name': 'version', 'value': self.conf['version']},
        ]

        path = self.clade.FileStorage().convert_path('source attrs.json')
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf8') as fp:
                build_attrs = ujson.load(fp)
            for attr in ('arch', 'configuration'):
                if build_attrs.get(attr):
                    attrs.append({"name": attr, "value": build_attrs[attr]})
        else:
            self.logger.warning("There is no source attributes description in build base")

        return [{
            'name': 'fragmentation',
            'value': attrs
        }]

    def __generate_verification_objects(self, grps):
        files = list()
        for name, grp in grps.items():
            files.append(self.__describe_verification_object(name, grp))
        return files

    def __describe_verification_object(self, name, grp):
        # Determine fragment name
        self.logger.info('Generate fragment description {!r}'.format(name))
        vo_desc = dict()
        vo_desc['id'] = name
        vo_desc['grps'] = list()
        vo_desc['deps'] = dict()
        for frag in grp:
            vo_desc['grps'].append({'id': frag.name, 'CCs': frag.ccs})
            vo_desc['deps'][frag.name] = [succ.name for succ in frag.successors if succ in grp]
        self.logger.debug('verification object dependencies are {}'.format(vo_desc['deps']))

        vo_desc_file = vo_desc['id'] + '.json'
        if os.path.isfile(vo_desc_file):
            raise FileExistsError('verification object description file {!r} already exists'.format(vo_desc_file))
        self.logger.debug('Dump verification object description {!r} to file {!r}'.format(vo_desc['id'], vo_desc_file))
        dir_path = os.path.dirname(vo_desc_file).encode('utf8')
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        with open(vo_desc_file, 'w', encoding='utf8') as fp:
            ujson.dump(vo_desc, fp, sort_keys=True, indent=4, ensure_ascii=False, escape_forward_slashes=False)
        return vo_desc_file

    def __print_fragments(self, deps):
        self.logger.info('Print fragments to working directory {!r}'.format(str(os.path.abspath(os.path.curdir))))
        g = Digraph(graph_attr={'rankdir': 'LR'}, node_attr={'shape': 'rectangle'})
        for fragment in deps.fragments:
            g.node(fragment.name, "{}".format(fragment.name) + (' (target)' if fragment.target else ''))

        for fragment in deps.fragments:
            for suc in fragment.successors:
                g.edge(fragment.name, suc.name)
        g.render('program fragments')

    def __draw_fragment(self, fragment):
        g = Digraph(graph_attr={'rankdir': 'LR'}, node_attr={'shape': 'rectangle'})
        for file in fragment.files:
            g.node(file.name, "{}".format(file.name) + (' (target)' if fragment.target else ''))

        for file in fragment.files:
            for suc in file.successors:
                if suc in fragment.files:
                    g.edge(fragment.name, suc.name)
        if not os.path.exists('fragments'):
            os.makedirs('fragments')
        g.render(os.path.join('fragments', fragment.name))

