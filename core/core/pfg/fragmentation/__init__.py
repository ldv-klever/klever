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
from clade import Clade

from core.utils import make_relative_path
from core.pfg.abstractions import Program
from core.pfg.abstractions.strategies import Abstract


class FragmentationAlgorythm:
    """
    This is a generic class to implement fragmentation strategies for particular programs. This is not a fully abstract
    class and sometimes can be directly used for verification without adaptation to program specifics.
    """
    CLADE_PRESET = 'base'

    def __init__(self, logger, conf, desc, pf_dir):
        """
        The strategy needs a logger and configuration as the rest Klever components but also it requires Clade interface
        object (uninitialized yet) and the description of the fragmentation set.

        :param logger: logging Logger object.
        :param conf: Dictionary.
        :param desc: Dictionary.
        :param clade: Clade interface.
        :param pf_dir: program fragments descriptions storage dir.
        """
        # Simple attributes
        self.logger = logger
        self.conf = conf
        self.fragmentation_set_conf = desc
        self.pf_dir = pf_dir
        self.files_to_keep = list()
        self.common_attributes = list()

        # Import clade
        self.clade = Clade(work_dir=self.conf['build base'], preset=self.CLADE_PRESET)

        # Complex attributes
        self.source_paths = self.__retrieve_source_paths()
        self.attributes = self.__attributes()

    def fragmentation(self):
        """
        It is the main function for a fragmentation strategy. The workflow is the following: it determines logical
        components of the program called units, then chooses files and units that should be verified according to the
        configuration provided by the user, gets the fragmentation set and reconstruct fragments if necessary according
        to this manually provided description, then add dependencies if necessary to each fragment that should be
        verified and generate the description of each program fragment. The description contains in addition to the
        files names compilation commands to get their options and dependencies between files.
        """

        # Extract dependencies
        self.logger.info("Start program fragmentation")
        if self.fragmentation_set_conf.get('ignore dependencies'):
            self.logger.info("Use memory efficient mode with limitied dependencies extraction")
            memory_efficient_mode = True
        else:
            self.logger.info("Extract full dependencies between files and functions")
            memory_efficient_mode = False
        deps = Program(self.logger, self.clade, self.source_paths, memory_efficient_mode=memory_efficient_mode)

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
        grps = self._add_dependencies(deps)

        # Prepare program fragments
        self.logger.info("Generate program fragments")
        fragments_files = self.__generate_program_fragments_descriptions(deps, grps)

        # Prepare data attributes
        self.logger.info("Prepare data attributes for generated fragments")
        attr_data = self.__prepare_data_files(grps)

        # Print fragments
        if self.fragmentation_set_conf.get('print fragments'):
            self.__print_fragments(deps)
            for fragment in deps.fragments:
                self.__draw_fragment(fragment)

        return attr_data, fragments_files

    def _determine_units(self, program):
        """
        Implement this function to extract logical components of the particular program. For programs for which nobody
        created a specific strategy, there is no units at all.

        :param program: Program object.
        """
        pass

    def _determine_targets(self, program):
        """
        Determine that program fragments that should be verified. We refer to these fragments as target fragments.

        :param program:
        :return:
        """
        add = set(self.conf.get('add targets'))
        if not add:
            raise RuntimeError("Set configuration property 'add targets' to specify which functions, files or fragments"
                               " you want to verify")
        exclude = set(self.conf.get('exclude targets', set()))

        files = set()
        self.logger.info("Find files matched by given by the user expressions ('add' configuration properties)")
        new_files, matched = program.get_files_for_expressions(add)
        files.update(new_files)
        add.difference_update(matched)
        if len(add) > 0:
            raise ValueError('Cannot find fragments, files or functions for the following expressions: {}'.
                             format(', '.join(add)))
        self.logger.info("Find files matched by given by the user expressions ('exclude' configuration properties)")
        new_files, matched = program.get_files_for_expressions(exclude)
        files.difference_update(new_files)

        for file in files:
            self.logger.debug('Mark file {!r} as a target'.format(file.name))
            file.target = True

    def _do_manual_correction(self, program):
        """
        According to the fragmentation set configuration we need to change the content of logically extracted units or
        create new ones.

        :param program: Program object.
        """
        self.logger.info("Adjust fragments according to the manually provided fragmentation set")
        fragments = self.fragmentation_set_conf.get('fragments', dict())
        remove = set(self.fragmentation_set_conf.get('exclude from all fragments', set()))
        add = set(self.fragmentation_set_conf.get('add to all fragments', set()))

        # Collect files
        new = dict()
        for identifier, frags_exprs in ((i, set(e)) for i, e in fragments.items()):
            files, matched = program.get_files_for_expressions(frags_exprs)
            frags_exprs.difference_update(matched)
            if len(frags_exprs) > 0:
                self.logger.warning('Cannot find fragments, files or functions for the following expressions: {}'.
                                    format(', '.join(frags_exprs)))

            new[identifier] = files

        # Find relevant fragments
        all_files = set()
        for files in new.values():
            all_files.update(files)
        relevant_fragments = program.get_fragments_with_files(all_files)

        # Add all
        addiction, _ = program.get_files_for_expressions(add)

        # Remove all
        removal, _ = program.get_files_for_expressions(remove)

        # Remove them
        for fragment in relevant_fragments:
            program.remove_fragment(fragment)

        # Create new fragments
        for name, files in new.items():
            program.create_fragment(name, files, add=True)

        # Do modification
        empty = set()
        for fragment in program.fragments:
            fragment.files.update(addiction)
            fragment.files.difference_update(removal)
            if not fragment.files:
                empty.add(fragment)

        # Remove empty
        for fragment in empty:
            program.remove_fragment(fragment)

    def _add_dependencies(self, program):
        """
        After we determined target fragments we may want to add dependent fragments. This should be implemented mostly
        by strategies variants for particular programs.

        :param program: Program object.
        :return: Dictionary with sets of fragments.
        """
        aggregator = Abstract(self.logger, self.conf, self.fragmentation_set_conf, program)
        return aggregator.get_groups()

    def __prepare_data_files(self, grps):
        """
        Prepare data files that describe program fragments content.

        :param grps: Dictionary with program fragments with dependencies.
        :return: Attributes and dict a list of data files.
        """
        data = dict()
        for name, frags in grps.items():
            data[name] = {f.name: sorted(make_relative_path(self.source_paths, l.name) for l in f.files) for f in frags}

        with open('agregations description.json', 'w', encoding='utf8') as fp:
            ujson.dump(data, fp, sort_keys=True, indent=4, ensure_ascii=False,
                       escape_forward_slashes=False)

        main_desc = [
            {'name': 'program', 'value': self.conf['program'], 'data': 'agregations description.json'},
            {'name': 'template', 'value': self.conf['fragmentation set']}
        ]
        if self.conf.get('version'):
            main_desc.append({'name': 'version', 'value': self.conf['version']})
        return [{'name': 'Fragmentation set', 'value': main_desc}], ['agregations description.json']

    def __retrieve_source_paths(self):
        """
        Extract the file with paths to source directories from the build base storage.

        :return: A list of paths.
        """
        clade_meta = self.clade.get_meta()
        if 'working source trees' in clade_meta:
            return clade_meta['working source trees']
        else:
            return [clade_meta['build_dir']]

    def __attributes(self):
        """
        Extract attributes that describe the program from the build base storage.

        :return: Attributes list.
        """
        attrs = []
        clade_meta = self.clade.get_meta()

        if 'project attrs' in clade_meta:
            self.common_attributes = clade_meta['project attrs']
            attrs.extend(self.common_attributes)
        else:
            self.logger.warning("There is no project attributes in build base")

        return attrs

    def __generate_program_fragments_descriptions(self, program, grps):
        """
        Generate json files with descriptions of each program fragment that should be verified.

        :param program: Program object.
        :param grps: Dictionary with program fragments with dependecnies.
        :return: A list of file names.
        """
        files = list()
        for name, grp in grps.items():
            files.append(self.__describe_program_fragment(program, name, grp))
        return files

    def __describe_program_fragment(self, program, name, grp):
        """
        Create the JSON file for the given program fragment with dependencies.

        :param program: Program object.
        :param name: Name of the fragment.
        :param grp: Set of fragments with dependencies.
        :return: The name of the created file.
        """
        # Determine fragment name
        self.logger.info('Generate fragment description {!r}'.format(name))
        pf_desc = dict()
        pf_desc['id'] = name
        pf_desc['grps'] = list()
        pf_desc['deps'] = dict()
        for frag in grp:
            pf_desc['grps'].append({
                'id': frag.name,
                'CCs': frag.ccs,
                'files': sorted(make_relative_path(self.source_paths, f.name) for f in frag.files)
            })
            pf_desc['deps'][frag.name] = [succ.name for succ in program.get_fragment_successors(frag) if succ in grp]
        self.logger.debug('Program fragment dependencies are {}'.format(pf_desc['deps']))

        pf_desc_file = os.path.join(self.pf_dir, pf_desc['id'] + '.json')
        if os.path.isfile(pf_desc_file):
            raise FileExistsError('Program fragment description file {!r} already exists'.format(pf_desc_file))
        self.logger.debug('Dump program fragment description {!r} to file {!r}'.format(pf_desc['id'], pf_desc_file))
        dir_path = os.path.dirname(pf_desc_file).encode('utf8')
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        with open(pf_desc_file, 'w', encoding='utf8') as fp:
            ujson.dump(pf_desc, fp, sort_keys=True, indent=4, ensure_ascii=False, escape_forward_slashes=False)
        return pf_desc_file

    def __print_fragments(self, program):
        """
        Print a graph to illustrate dependencies between all program fragments. For large projects such graph can be
        huge. By default this should be disabled.

        :param program: Program object.
        """
        self.logger.info('Print fragments to working directory {!r}'.format(str(os.path.abspath(os.path.curdir))))
        g = Digraph(graph_attr={'rankdir': 'LR'}, node_attr={'shape': 'rectangle'})
        for fragment in program.fragments:
            g.node(fragment.name, "{}".format(fragment.name) + (' (target)' if fragment.target else ''))

        for fragment in program.fragments:
            for suc in program.get_fragment_successors(fragment):
                g.edge(fragment.name, suc.name)
        g.render('program fragments')

    def __draw_fragment(self, fragment):
        """
        Print a graph with files and dependencies between them for a fragment.

        :param fragment: Fragment object.
        """
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
