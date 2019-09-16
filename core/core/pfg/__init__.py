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

import os
import json
import importlib

import core.components
import core.utils


class PFG(core.components.Component):

    PF_FILE = 'program_fragments.json'
    PF_DIR = 'program fragments'

    def generate_program_fragments(self):
        """
        This is the main function of the Program Fragment Generator. It gets the build base of the program, analyses
        it and generates program fragments descriptions that VTG uses to generate verification tasks. Each program
        fragment contains several sets of C files to be analyzed together independently from other files.
        """
        # Collect and merge configuration
        self.logger.info("Start program fragmentation stage")
        fragdb = self.conf['program fragmentation DB']
        with open(fragdb, encoding='utf8') as fp:
            fragdb = json.load(fp)

        # Make basic sanity checks and merge configurations
        desc = self._merge_configurations(fragdb, self.conf['program'], self.conf.get('version'),
                                          self.conf['fragmentation set'])

        # Import project strategy
        program = desc.get('program')
        if not program:
            raise KeyError('There is no available supported program fragmentation template {!r}, the following are '
                           'available: {}'.format(program, ', '.join(fragdb['templates'].keys())))
        strategy = self._get_fragmentation_strategy(program)

        # Fragmentation
        strategy = strategy(self.logger, self.conf, desc, self.PF_DIR)
        attr_data, fragments_files = strategy.fragmentation()

        # Prepare attributes
        self.source_paths = strategy.source_paths
        self.common_prj_attrs = strategy.common_attributes
        attr_data[0].extend(strategy.common_attributes)
        self.submit_project_attrs(*attr_data)

        self.prepare_descriptions_file(fragments_files)
        self.excluded_clean = [self.PF_DIR, self.PF_FILE]
        self.excluded_clean.extend(attr_data[1])
        self.logger.debug("Excluded {0}".format(self.excluded_clean))
        self.clean_dir = True

    main = generate_program_fragments

    def submit_project_attrs(self, attrs, dfiles):
        """
        !Has a callback!
        Submit project attribute to Bridge.

        :param attrs: Prepared list of attributes.
        :param dfiles: Fiels to attach as data attribute values.
        """
        core.utils.report(self.logger,
                          'patch',
                          {
                              'identifier': self.id,
                              'attrs': attrs
                          },
                          self.mqs['report files'],
                          self.vals['report id'],
                          self.conf['main working directory'],
                          data_files=dfiles)

    def prepare_descriptions_file(self, files):
        """
        Get the list of file with program fragments descriptions and save it to the file to provide it to VTG.

        :param files: The list of program fragment description files.
        """
        self.logger.info("Save file with program fragments descriptions {!r}".format(self.PF_FILE))
        with open(self.PF_FILE, 'w') as fp:
            fp.writelines((os.path.relpath(f, self.conf['main working directory']) + '\n' for f in files))

    def _merge_configurations(self, db, program, version, dset):
        """
        Program fragmentation depends on a template and fragmentation set prepared for a particular program version.
        This function reads the file with templates and fragmentation sets and merges required configuration properties
        into the single dictionary.

        :param db: Content of fragmentation sets file.
        :param program: Program name.
        :param version: Program version.
        :param dset: Fragmentation set name.
        :return: Merged dictionary.
        """
        self.logger.info("Search for fragmentation description and configuration for {!r}".format(program))

        # Basic sanity checks
        if not db.get('fragmentation sets') or not db.get('templates'):
            raise KeyError("Provide both 'templates' and 'fragmentation sets' sections to 'program configuration'.json")

        if program not in db['fragmentation sets'] or dset not in db['fragmentation sets'][program]:
            raise KeyError('There is no prepared fragmentation set {!r} for program {!r}'.format(dset, program))
        if version not in db['fragmentation sets'][program][dset]:
            self.logger.warning("There is no fragmentation set description for provided version {!r}".format(version))
        desc = db['fragmentation sets'].get(program, dict()).get(dset, dict()).get(version, dict())

        # Merge templates
        template = db['templates'][dset]
        do = [template]
        while do:
            tmplt = do.pop()
            if tmplt.get('template'):
                if db['templates'].get(tmplt.get('template')):
                    do.append(db['templates'].get(tmplt.get('template')))
                    del tmplt['template']
                else:
                    raise KeyError("There is no template {!r} in program fragmentation file".
                                   format(tmplt.get('template')))

            tmplt.update(template)
            template = tmplt

        # Merge template and fragmentation set
        template.update(desc)

        # Check if job contains options for fragmentation
        for option in ('fragments', 'add to all fragments', 'exclude from all fragments'):
            if option in self.conf:
                template[option] = self.conf[option]

        if "fragmentation configuration options" in self.conf:
            template.update(self.conf["fragmentation configuration options"])

        return template

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
        project_package = importlib.import_module(module_path, 'core')
        cls = getattr(project_package, strategy_name.capitalize().replace(' ', ''))
        return cls
