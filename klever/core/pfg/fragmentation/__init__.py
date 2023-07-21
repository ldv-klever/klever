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

import os
import ujson

from graphviz import Digraph
from clade import Clade

from klever.core.utils import make_relative_path
from klever.core.pfg.abstractions import Program
from klever.core.pfg.abstractions.strategies import Abstract


class FragmentationAlgorythm:
    """
    This is a generic class to implement fragmentation strategies for particular programs. This is not a fully abstract
    class and sometimes can be directly used for verification without adaptation to program specifics.
    """
    CLADE_PRESET = 'base'

    def __init__(self, logger, conf, tactic, pf_dir):
        """
        The strategy needs a logger and configuration as the rest Klever components but also it requires Clade interface
        object (uninitialized yet) and the description of the fragmentation set.

        :param logger: logging Logger object.
        :param conf: Dictionary.
        :param tactic: Dictionary with options.
        :param pf_dir: program fragments descriptions storage dir.
        """
        # Simple attributes
        self.logger = logger
        self.conf = conf
        self.tactic = tactic
        self.pf_dir = pf_dir
        self.files_to_keep = []
        self.project_attrs = []

        self.source_paths = self.conf['working source trees']

        # Import clade
        clade_conf = {"log_level": "ERROR"}
        self.clade = Clade(work_dir=self.conf['build base'], preset=self.CLADE_PRESET, conf=clade_conf)
        if not self.clade.work_dir_ok():
            raise RuntimeError('Build base is not OK')

        self.__get_project_attrs()

    def fragmentation(self, fragmentation_set, tactic_name, fset_name):
        """
        It is the main function for a fragmentation strategy. The workflow is the following: it determines logical
        components of the program called units, then chooses files and units that should be verified according to the
        configuration provided by the user, gets the fragmentation set and reconstruct fragments if necessary according
        to this manually provided description, then add dependencies if necessary to each fragment that should be
        verified and generate the description of each program fragment. The description contains in addition to the
        files names compilation commands to get their options and dependencies between files.

        :parameter fragmentation_set: Fragmentation set description dict.
        :parameter tactic_name: Fragmentation tactic name.
        :parameter fset_name: Fragmentation set name.
        """
        # Extract dependencies
        self.logger.info("Start program fragmentation")
        if self.tactic.get('ignore dependencies'):
            self.logger.info("Use memory efficient mode with limited dependencies extraction")
            memory_efficient_mode = True
        else:
            self.logger.info("Extract full dependencies between files and functions")
            memory_efficient_mode = False
        deps = Program(self.logger, self.clade, self.source_paths, memory_efficient_mode,
                       self.tactic.get("ignore missing files"))

        # Decompose using units
        self.logger.info("Determine units in the target program")
        self._determine_units(deps)

        # Prepare semifinal fragments according to strategy chosen manually
        self.logger.info("Apply corrections of program fragments provided by a user")
        defined_groups = self._do_manual_correction(deps, fragmentation_set)

        # Mark dirs, units, files, functions
        self.logger.info("Select program fragments for verification")
        self._determine_targets(deps)

        # Prepare final optional addiction of fragments if necessary
        self.logger.info("Collect dependencies if necessary for each fragment intended for verification")
        grps = self._add_dependencies(deps)

        # Remove useless duplicates
        for manual, group in defined_groups.items():
            fragment = deps.get_fragment(manual)
            if fragment:
                allfiles = set()
                for item in group:
                    allfiles.update(item.files)
                fragment.files.difference_update(allfiles)

        # Before describing files add manually defined files
        for group, item in grps.items():
            update = True
            while update:
                update = False
                old = set(item[1])
                for fragment in list(item[1]):
                    if not fragment.files:
                        item[1].remove(fragment)
                    item[1].update(defined_groups.get(str(fragment), set()))
                if old.symmetric_difference(item[1]):
                    update = True

        # Prepare program fragments
        self.logger.info("Generate program fragments")
        pairs = self.__generate_program_fragments_descriptions(deps, grps)

        # Prepare data attributes
        self.logger.info("Prepare data attributes for generated fragments")
        attr_data = self.__prepare_data_files(grps, tactic_name, fset_name)

        # Print fragments
        if self.tactic.get('print fragments'):
            self.__print_fragments(deps)
            for fragment in deps.fragments:
                self.__draw_fragment(fragment)

        return attr_data, pairs

    def _determine_units(self, program):
        """
        Implement this function to extract logical components of the particular program. For programs for which nobody
        created a specific strategy, there is no units at all.

        :param program: Program object.
        """

    def _determine_targets(self, program):
        """
        Determine that program fragments that should be verified. We refer to these fragments as target fragments.

        :param program:
        :return:
        """
        add = set(self.conf.get('targets'))
        if not add:
            raise RuntimeError("Set configuration property 'targets' to specify which functions, files or fragments"
                               " you want to verify")
        exclude = set(self.conf.get('exclude targets', set()))

        # Search for files that are already added to several units and mark them as not unique
        self.logger.info('Mark unique files that belong to no more than one fragment')
        summary = set()
        for fragment in program.fragments:
            for file in fragment.files:
                if file not in summary:
                    summary.add(file)
                else:
                    file.unique = False

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

    def _do_manual_correction(self, program, fragments_desc):
        """
        According to the fragmentation set configuration we need to change the content of logically extracted units or
        create new ones.

        :param program: Program object.
        :param fragments_desc: Fragmentation set dictionary.
        """
        self.logger.info("Adjust fragments according to the manually provided fragmentation set")
        fragments = fragments_desc.get('fragments', {})
        remove = set(fragments_desc.get('exclude from all fragments', set()))
        add = set(fragments_desc.get('add to all fragments', set()))
        defined_groups = {}

        # Collect files
        new = {}
        for identifier, frags_exprs in ((i, set(e)) for i, e in fragments.items()):
            # First detect fragments and use them at description of manually defined groups
            frags, matched = program.get_fragments(frags_exprs)
            self.logger.debug("Matched as fragments the following expressions for {!r}: {}".
                              format(identifier, ', '.join(matched)))
            self_fragment = program.get_fragment(identifier)
            if self_fragment and self_fragment in frags and len(frags) == 1:
                pass
            elif self_fragment and self_fragment in frags:
                frags.remove(self_fragment)
                matched.remove(identifier)
                frags_exprs.difference_update(matched)
                defined_groups[identifier] = frags
            else:
                defined_groups[identifier] = frags

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
        frags, matched = program.get_fragments(add)
        add.difference_update(matched)
        if frags:
            all_frgs = set(program.fragments).difference(frags)
            for fragment in all_frgs:
                defined_groups.setdefault(str(fragment), set())
                defined_groups[str(fragment)].update(frags)
        addiction, _ = program.get_files_for_expressions(add)

        # Remove all
        # First detect fragments and use them at description of manually defined groups
        frags, matched = program.get_fragments(remove)
        remove.difference_update(matched)
        if matched:
            for group in defined_groups.values():
                group.difference_update(frags)
            for frag in (str(f) for f in frags if str(f) in defined_groups):
                del defined_groups[frag]
        for fragment in frags:
            program.remove_fragment(fragment)

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

        return defined_groups

    def _add_dependencies(self, program):
        """
        After we determined target fragments we may want to add dependent fragments. This should be implemented mostly
        by strategies variants for particular programs.

        :param program: Program object.
        :return: Dictionary with sets of fragments.
        """
        aggregator = Abstract(self.logger, self.conf, self.tactic, program)
        return aggregator.get_groups()

    def __prepare_data_files(self, grps, tactic, fragmentation_set):
        """
        Prepare data files that describe program fragments content.

        :param grps: Dictionary with program fragments with dependencies.
        :param tactic: Name of the tactic.
        :param grps: Name of the fragmentation set.
        :return: Attributes and dict a list of data files.
        """
        data = {}
        for name, main_and_frgs in grps.items():
            _, frags = main_and_frgs
            data[name] = {
                "files": [make_relative_path(self.source_paths, l.name) for f in frags for l in f.files],
                "size": str(sum(int(f.size) for f in frags))
            }

        with open('aggregations description.json', 'w', encoding='utf-8') as fp:
            ujson.dump(data, fp, sort_keys=True, indent=4, ensure_ascii=False,
                       escape_forward_slashes=False)

        return [{
            'name': 'Program fragmentation',
            'value': [
                {
                    'name': 'tactic',
                    'value': tactic
                },
                {
                    'name': 'set',
                    'value': fragmentation_set
                }
            ]
        }], 'aggregations description.json'

    def __get_project_attrs(self):
        """
        Extract attributes that describe the program from the build base storage.
        """
        clade_meta = self.clade.get_meta()

        if 'project attrs' in clade_meta:
            self.project_attrs = clade_meta['project attrs']
        else:
            self.logger.warning("There is no project attributes in build base")

    def __generate_program_fragments_descriptions(self, program, grps):
        """
        Generate json files with descriptions of each program fragment that should be verified.

        :param program: Program object.
        :param grps: Dictionary with program fragments with dependencies.
        :return: A list of pairs of fragment and related file names.
        """
        pairs = []
        for name, grp in grps.items():
            pairs.append((name, self.__describe_program_fragment(program, name, grp)))
        return pairs

    def __describe_program_fragment(self, program, name, grp):
        """
        Create the JSON file for the given program fragment with dependencies.

        :param program: Program object.
        :param name: Name of the fragment.
        :param grp: Set of fragments with dependencies.
        :return: The name of the created file.
        """
        # Determine fragment name
        main_fragment, fragments = grp
        self.logger.info('Generate fragment description {!r}'.format(name))

        pf_desc = {
            'id': name,
            'fragment': name,
            'targets': sorted([str(f) for f in main_fragment.target_files]),
            'grps': [],
            'deps': {},
            'size': str(sum((int(f.size) for f in fragments)))
        }

        for frag in fragments:
            fragment_description = {
                'id': frag.name,
                'Extra CCs': [
                    {"CC": [file.cmd_id, file.cmd_type], "in file": str(file)} for file in frag.files
                ],
                'files': sorted(make_relative_path(self.source_paths, str(f)) for f in frag.files),
                'abs files': sorted(str(f) for f in frag.files)
            }
            pf_desc['grps'].append(fragment_description)
            pf_desc['deps'][frag.name] = [succ.name for succ in program.get_fragment_successors(frag)
                                          if succ in fragments]
        self.logger.debug('Program fragment dependencies are {}'.format(pf_desc['deps']))

        pf_desc_file = os.path.join(self.pf_dir, pf_desc['fragment'] + '.json')
        if os.path.isfile(pf_desc_file):
            raise FileExistsError('Program fragment description file {!r} already exists'.format(pf_desc_file))
        self.logger.debug('Dump program fragment description {!r} to file {!r}'.format(pf_desc['fragment'], pf_desc_file))
        dir_path = os.path.dirname(pf_desc_file).encode('utf-8')
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        with open(pf_desc_file, 'w', encoding='utf-8') as fp:
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
