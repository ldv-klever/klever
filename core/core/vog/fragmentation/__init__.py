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

from core.utils import make_relative_path
from core.vog.abstractions import Dependencies
from core.vog.abstractions.strategies import Abstract


class FragmentationAlgorythm:

    VO_DIR = 'verification objects'
    CLADE_PRESET = 'base'

    def __init__(self, logger, conf, desc, clade):
        # Simple attributes
        self.logger = logger
        self.conf = conf
        self.desc = desc
        self.clade = clade
        self.dynamic_excluded_clean = list()

        # Import clade
        self.clade.setup(self.conf['build base'], preset_configuration=self.CLADE_PRESET)

        # Complex attributes
        self.source_paths = self.__retrieve_source_paths()
        self.attributes = self.__attributes()

    def fragmentation(self):
        # Extract dependencies
        self.logger.info("Start program fragmentation")
        if self.desc.get('ignore dependencies'):
            self.logger.info("Use memory efficient mode with limitied dependencies extraction")
            memory_efficient_mode = True
        else:
            self.logger.info("Extract full dependencies between files and functions")
            memory_efficient_mode = False
        deps = Dependencies(self.logger, self.clade, self.source_paths, memory_efficient_mode=memory_efficient_mode)

        # Decompose using units
        self.logger.info("Determine units in the target program")
        self._determine_units(deps)

        # Mark dirs, units, files, functions
        self.logger.info("Select program fragments for verification")
        self._determine_targets(deps)

        # Prepare semifinal fragments according to strategy chosen manually
        self.logger.info("Apply corrections of program fragments provided by a user")
        self._do_manual_correction(deps)

        # Prepare final optional addiction of fragments if necessary
        self.logger.info("Collect dependencies if necessary for each fragment intended for verification")
        grps = self._do_postcomposition(deps)

        # Prepare verification objects
        self.logger.info("Generate verification objects")
        fragments_files = self.__generate_verification_objects(deps, grps)

        # Prepare data attributes
        self.logger.info("Prepare data attributes for generated fragments")
        attr_data = self.__prepare_data_files(grps)

        # Print fragments
        if self.desc.get('print fragments'):
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
        self.logger.info("Find files matched by given by the user expressions ('add' configuration properties)")
        new_files, matched = deps.find_files_for_expressions(add)
        files.update(new_files)
        add.difference_update(matched)
        if len(add) > 0:
            raise ValueError('Cannot find fragments, files or functions for the following expressions: {}'.
                             format(', '.join(add)))
        self.logger.info("Find files matched by given by the user expressions ('exclude' configuration properties)")
        new_files, matched = deps.find_files_for_expressions(exclude)
        files.difference_update(new_files)

        for file in files:
            self.logger.info('Mark file {!r} as a target'.format(file.name))
            file.target = True

    def _do_manual_correction(self, deps):
        self.logger.info("Adjust fragments according to the manually provided fragmentation set")
        fragments = self.desc.get('fragments', dict())
        remove = set(self.desc.get('exclude from all fragments', set()))
        add = set(self.desc.get('add to all fragments', set()))

        # Collect files
        new = dict()
        for identifier, frags_exprs in ((i, set(e)) for i, e in fragments.items()):
            files, matched = deps.find_files_for_expressions(frags_exprs)
            frags_exprs.difference_update(matched)
            if len(frags_exprs) > 0:
                raise ValueError('Cannot find fragments, files or functions for the following expressions: {}'.
                                 format(', '.join(frags_exprs)))

            new[identifier] = files

        # Find relevant fragments
        all_files = set()
        for files in new.values():
            all_files.update(files)
        relevant_fragments = deps.find_fragments_with_files(all_files)

        # Add all
        addiction, _ = deps.find_files_for_expressions(add)

        # Remove all
        removal, _ = deps.find_files_for_expressions(remove)

        # Remove them
        for fragment in relevant_fragments:
            deps.remove_fragment(fragment)

        # Create new fragments
        for name, files in new.items():
            deps.create_fragment(name, files, add=True)

        # Do modification
        empty = set()
        for fragment in deps.fragments:
            fragment.files.update(addiction)
            fragment.files.difference_update(removal)
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
            data[name] = {f.name: sorted(make_relative_path(self.source_paths, l.name) for l in f.files) for f in frags}

        with open('agregations description.json', 'w', encoding='utf8') as fp:
            ujson.dump(data, fp, sort_keys=True, indent=4, ensure_ascii=False,
                       escape_forward_slashes=False)

        return [
           {
                'name': 'Fragmentation set',
                'value': [
                    {'name': 'program', 'value': self.conf['program'], 'data': 'agregations description.json'},
                    {'name': 'version', 'value': self.conf['version']},
                    {'name': 'template', 'value': self.conf['fragmentation set']}
                ]
           }], ['agregations description.json']

    def __retrieve_source_paths(self):
        path = self.clade.FileStorage().convert_path('working source trees.json')
        with open(path, 'r', encoding='utf8') as fp:
            paths = ujson.load(fp)
        return paths

    def __attributes(self):
        attrs = []
        path = self.clade.FileStorage().convert_path('project attrs.json')
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf8') as fp:
                build_attrs = ujson.load(fp)
            if build_attrs:
                self.common_attributes = build_attrs
            attrs.extend(build_attrs)
        else:
            self.logger.warning("There is no source attributes description in build base")

        return attrs

    def __generate_verification_objects(self, deps, grps):
        files = list()
        for name, grp in grps.items():
            files.append(self.__describe_verification_object(deps, name, grp))
        return files

    def __describe_verification_object(self, deps, name, grp):
        # Determine fragment name
        self.logger.info('Generate fragment description {!r}'.format(name))
        vo_desc = dict()
        vo_desc['id'] = name
        vo_desc['grps'] = list()
        vo_desc['deps'] = dict()
        for frag in grp:
            vo_desc['grps'].append({
                'id': frag.name,
                'CCs': frag.ccs,
                'files': sorted(make_relative_path(self.source_paths, f.name) for f in frag.files)
            })
            vo_desc['deps'][frag.name] = [succ.name for succ in deps.fragment_successors(frag) if succ in grp]
        self.logger.debug('verification object dependencies are {}'.format(vo_desc['deps']))

        vo_desc_file = os.path.join(self.VO_DIR, vo_desc['id'] + '.json')
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
            for suc in deps.fragment_successors(fragment):
                g.edge(fragment.name, suc.name)
        g.render('program fragments')

    def __draw_fragment(self, fragment):
        g = Digraph(graph_attr={'rankdir': 'LR'}, node_attr={'shape': 'rectangle'})
        for file in fragment.files:
            g.node(file.name,
                   make_relative_path(self.source_paths, file.name) + (' (target)' if fragment.target else ''))

        for file in fragment.files:
            for suc in file.successors:
                if suc in fragment.files:
                    g.edge(fragment.name, suc.name)
        if not os.path.exists('fragments'):
            os.makedirs('fragments')
        g.render(os.path.join('fragments', fragment.name))

