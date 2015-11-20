#!/usr/bin/python3

import os

import psi.components
import psi.utils


class RSG(psi.components.Component):
    def generate_rule_specification(self):
        self.abstract_task_desc = self.mqs['abstract task description'].get()

        self.add_aspects()

        self.mqs['abstract task description'].put(self.abstract_task_desc)

    main = generate_rule_specification

    def add_aspects(self):
        self.logger.info("Add aspects to abstract task description")

        # Get common and rule specific aspects.
        aspects = []

        for aspect in self.conf['common aspects'] + self.conf['aspects']:
            # All aspects are relative to aspects directory.
            aspect = psi.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                                os.path.join(self.conf['aspects directory'], aspect))
            self.logger.debug('Get aspect "{0}"'.format(aspect))
            aspects.append(aspect)

        for grp in self.abstract_task_desc['grps']:
            for cc_extra_full_desc_file in grp['cc extra full desc files']:
                if 'plugin aspect files' not in cc_extra_full_desc_file:
                    cc_extra_full_desc_file['plugin aspect files'] = []
                    cc_extra_full_desc_file['plugin aspect files'].append(
                        {"plugin": self.name, "aspect files": aspects})
