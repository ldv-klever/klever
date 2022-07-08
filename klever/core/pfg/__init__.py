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

import glob
import os
import json
import importlib

import klever.core.components
import klever.core.utils


class PFG(klever.core.components.Component):

    PF_FILE = 'program fragments.txt'
    PF_DIR = 'program fragments'

    def generate_program_fragments(self):
        """
        This is the main function of the Program Fragment Generator. It gets the build base of the program, analyses
        it and generates program fragments descriptions that VTG uses to generate verification tasks. Each program
        fragment contains several sets of C files to be analyzed together independently from other files.
        """
        # Collect and merge configuration
        self.logger.info("Start program fragmentation stage")
        fragdb = self.conf['program fragments base']

        # Make basic sanity checks and merge configurations
        tactic, fset, tactic_name, fset_name = self._merge_configurations(fragdb, self.conf['project'])

        # Import project strategy
        strategy = self._get_fragmentation_strategy(self.conf['project'])

        # Fragmentation
        strategy = strategy(self.logger, self.conf, tactic, self.PF_DIR)
        attr_data, pairs = strategy.fragmentation(fset, tactic_name, fset_name)

        # Prepare attributes
        self.source_paths = strategy.source_paths
        self.common_attrs = strategy.project_attrs
        self.common_attrs.extend(attr_data[0])
        self.submit_common_attrs(self.common_attrs)

        with open(attr_data[1]) as fp:
            data = json.load(fp)
        data.update({'type': 'PFG'})
        klever.core.utils.report(
            self.logger,
            'patch',
            {
              'identifier': self.id,
              'data': data
            },
            self.mqs['report files'],
            self.vals['report id'],
            self.conf['main working directory'])

        self.prepare_descriptions_file(pairs)
        self.excluded_clean = [self.PF_DIR, self.PF_FILE]
        self.excluded_clean.append(attr_data[1])
        self.logger.debug("Excluded {}".format(', '.join(self.excluded_clean)))
        self.clean_dir = True

    main = generate_program_fragments

    def submit_common_attrs(self, attrs):
        """
        !Has a callback!
        Submit common attributes to Bridge.

        :param attrs: Prepared list of attributes.
        :param dfiles: Files to attach as data attribute values.
        """
        klever.core.utils.report(self.logger,
                                 'patch',
                                 {
                                   'identifier': self.id,
                                   'attrs': attrs
                                 },
                                 self.mqs['report files'],
                                 self.vals['report id'],
                                 self.conf['main working directory'])

    def prepare_descriptions_file(self, pairs):
        """
        Get the list of file with program fragments descriptions and save it to the file to provide it to VTG.

        :param pairs: The list of name and program fragment description files pairs.
        """
        self.logger.info("Save file with program fragments descriptions {!r}".format(self.PF_FILE))
        with open(self.PF_FILE, 'w') as fp:
            fp.writelines((name + ':=' + os.path.relpath(file, self.conf['main working directory']) + '\n'
                          for name, file in pairs))

    def _merge_configurations(self, db, program):
        """
        Program fragmentation depends on a template and fragmentation set prepared for a particular program version.
        This function reads the file with templates and fragmentation sets and merges required configuration properties
        into the single dictionary.

        :param db: Directory where to search for fragmentation sets description files.
        :param program: Program name.
        :return: {options}, {fragmentation set}, tactic_name, fset_name.
        """
        fset_name = self.conf.get('fragmentation set')
        tactic_name = self.conf.get('fragmentation tactic')

        if program:
            self.logger.info("Search for fragmentation description and configuration for {!r}".format(program))
            conf_files = glob.glob(os.path.join(db, '*.json'))
            specification = {}
            for conf_file in conf_files:
                if os.path.basename(conf_file) == '%s.json' % program:
                    with open(conf_file, 'r', encoding='utf-8') as fp:
                        specification = json.load(fp)

            if not specification:
                self.logger.warning('There is no fragmentation sets description file for program {!r}'.format(program))
        else:
            raise ValueError("Require 'project' attribute to be set in job.json to proceed")

        # Read tactics
        if not isinstance(tactic_name, dict):
            tactics = specification.get('tactics', {})
            tactic = {}
            if tactic_name and tactic_name in tactics:
                self.logger.info('Found options for {!r} tactic'.format(tactic))
                tactic.update(tactics[tactic_name])
            elif tactic_name:
                raise KeyError('There is no {!r} tactic in fragmentation sets description file'.format(tactic_name))
            else:
                for item, desc in tactics.items():
                    if desc.get('reference'):
                        self.logger.info('Use default options from {!r} tactic'.format(item))
                        tactic.update(desc)
                        tactic_name = item
                        break
                else:
                    self.logger.info('There is no either default or provided tactic')
        else:
            tactic = tactic_name
            tactic_name = 'custom'

        # Read fragmentation set
        if not isinstance(fset_name, dict):
            fsets = specification.get('fragmentation sets', {})
            fset = {}
            if fset_name and fset_name in fsets:
                self.logger.info('Fragmentation set {!r}'.format(fset_name))
                fset.update(fsets[fset_name])
            elif fset_name:
                raise KeyError('There is no {!r} fragmentation set in fragmentation sets description file'.format(tactic_name))
            else:
                fset_name = None
                if fsets:
                    for item, desc in fsets.items():
                        if desc.get('reference'):
                            self.logger.info('Use default {!r} fragmentation set'.format(item))
                            fset.update(desc)
                            if not fset_name:
                                fset_name = item
                            else:
                                # There are several sets were merged
                                fset_name = 'default'
                else:
                    self.logger.info('There is no either default or provided fragmentation set')
                    fset_name = 'custom'
        else:
            fset = fset_name
            fset_name = 'custom'

        return tactic, fset, tactic_name, fset_name

    def _get_fragmentation_strategy(self, strategy_name):
        """
        The function dynamically searches for fragmentation strategy depending on the program and return its class
        reference.

        :param strategy_name:
        :return: Fragmentation strategy class.
        """
        self.logger.info('Import fragmentation strategy {!r}'.format(strategy_name))
        # Remove spaces that are nice for users but can not be used in Python module names.
        module_path = '.pfg.fragmentation.{}'.format(strategy_name.lower().replace(' ', ''))
        try:
            project_package = importlib.import_module(module_path, 'klever.core')
            cls = getattr(project_package, strategy_name.capitalize().replace(' ', ''))
        except ModuleNotFoundError:
            # Use default fragmentation strategy if there is no specific one.
            project_package = importlib.import_module('.pfg.fragmentation.default', 'klever.core')
            cls = getattr(project_package, 'Default')

        return cls
