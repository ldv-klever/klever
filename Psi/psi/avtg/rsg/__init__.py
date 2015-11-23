#!/usr/bin/python3

import json
import os
import string

import psi.components
import psi.utils


class RSG(psi.components.Component):
    def generate_rule_specification(self):
        self.abstract_task_desc = self.mqs['abstract task description'].get()

        self.add_aspects()
        self.add_models()

        self.mqs['abstract task description'].put(self.abstract_task_desc)

    main = generate_rule_specification

    def add_aspects(self):
        self.logger.info('Add aspects to abstract task description')

        # Get common and rule specific aspects.
        aspects = []

        for aspect in self.conf['common aspects'] + self.conf['aspects']:
            # All aspects are relative to aspects directory.
            aspect = psi.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                                os.path.join(self.conf['aspects directory'], aspect))
            self.logger.debug('Get aspect "{0}"'.format(aspect))
            aspects.append(aspect)

        for grp in self.abstract_task_desc['grps']:
            self.logger.info('Add aspects to C files of group "{0}"'.format(grp['id']))
            for cc_extra_full_desc_file in grp['cc extra full desc files']:
                if 'plugin aspects' not in cc_extra_full_desc_file:
                    cc_extra_full_desc_file['plugin aspects'] = []
                    cc_extra_full_desc_file['plugin aspects'].append(
                        {"plugin": self.name,
                         "aspects": [os.path.relpath(aspect, os.path.realpath(self.conf['source tree root'])) for
                                     aspect in aspects]})

    def add_models(self):
        self.logger.info('Add models to abstract task description')

        # Get common and rule specific models.
        models = []

        for model in self.conf['common models'] + self.conf['models']:
            # All models are relative to models directory.
            model = psi.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                               os.path.join(self.conf['models directory'], model))
            self.logger.debug('Get model "{0}"'.format(model))
            models.append(model)

        # CC extra full description files will be put to this directory as well as corresponding output files.
        os.makedirs('models')

        # TODO: at the moment it is assumed that there is the only group in each verification object. Actually we need
        # to create a separate group and make all other to depend on it.
        # Generate CC extra full description file per each model and add it to abstract task description.
        for grp in self.abstract_task_desc['grps']:
            self.logger.info('Add models to group "{0}"'.format(grp['id']))
            for model in models:
                out_file = os.path.join('models', '{}.c'.format(os.path.splitext(os.path.basename(model))[0]))
                full_desc_file = '{0}.json'.format(out_file)
                with open(full_desc_file, 'w') as fp:
                    json.dump({
                        # Input file path should be relative to source tree root since compilation options are relative
                        # to this directory and we will change directory to that one before invoking preprocessor.
                        "in files": [os.path.relpath(model, os.path.realpath(self.conf['source tree root']))],
                        # Otput file should be located somewhere inside RSG working directory to avoid races.
                        "out file": os.path.relpath(out_file, os.path.realpath(self.conf['source tree root'])),
                        "opts":
                            [string.Template(opt).substitute(hdr_arch=self.conf['sys']['hdr arch']) for opt in
                             self.conf['model CC opts']] +
                            # Besides header files specific for rule specifications will be searched for.
                            ["-I{0}".format(os.path.relpath(
                                psi.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                                           self.conf['rule specifications directory']),
                                os.path.realpath(self.conf['source tree root'])))]
                    }, fp, sort_keys=True, indent=4)
                self.logger.debug('CC extra full description file is "{0}"'.format(full_desc_file))

                grp['cc extra full desc files'].append({
                    'cc full desc file': os.path.relpath(full_desc_file,
                                                         os.path.realpath(self.conf['source tree root'])),
                    'rule spec id': self.conf['rule spec id'],
                    'bug kinds': self.conf['bug kinds']
                })
