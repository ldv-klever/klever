#!/usr/bin/python3

import json
import os
import string

import core.components
import core.utils


class RSG(core.components.Component):
    def generate_rule_specification(self):
        self.abstract_task_desc = self.mqs['abstract task description'].get()

        aspects = []
        models = {}

        if 'files' in self.abstract_task_desc:
            self.logger.info('Get additional aspects and models specified in abstract task description')

            for file in self.abstract_task_desc['files']:
                ext = os.path.splitext(file)[1]
                if ext == '.c':
                    models[file] = {}
                    self.logger.debug('Get additional model with C file "{0}'.format(file))
                elif ext == '.aspect':
                    aspects.append(file)
                    self.logger.debug('Get additional aspect "{0}'.format(file))
                else:
                    raise ValueError('Files with extension "{0}" are not supported'.format(ext))

        self.add_aspects(aspects)
        self.add_models(models)

        if 'files' in self.abstract_task_desc:
            self.abstract_task_desc.pop('files')

        self.mqs['abstract task description'].put(self.abstract_task_desc)

    main = generate_rule_specification

    def add_aspects(self, aspects):
        self.logger.info('Add aspects to abstract task description')

        # Get common and rule specific aspects.
        for aspect in (self.conf.get('common aspects') or []) + (self.conf.get('aspects') or []):
            aspect = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'], aspect)
            self.logger.debug('Get aspect "{0}"'.format(aspect))
            aspects.append(os.path.relpath(aspect, os.path.realpath(self.conf['source tree root'])))

        if not aspects:
            self.logger.warning('No aspects ase specified')
            return

        for grp in self.abstract_task_desc['grps']:
            self.logger.info('Add aspects to C files of group "{0}"'.format(grp['id']))
            for cc_extra_full_desc_file in grp['cc extra full desc files']:
                if 'plugin aspects' not in cc_extra_full_desc_file:
                    cc_extra_full_desc_file['plugin aspects'] = []
                cc_extra_full_desc_file['plugin aspects'].append({"plugin": self.name, "aspects": aspects}
                                                                 )

    def add_models(self, models):
        self.logger.info('Add models to abstract task description')

        # Get common and rule specific models.
        if 'common models' in self.conf and 'models' in self.conf:
            for common_model_c_file in self.conf['common models'].keys():
                if common_model_c_file in self.conf['models'].keys():
                    raise KeyError('C file "{0}" is specified in both common and rule specific models')
        if 'models' in self.conf:
            for model_c_file in self.conf['models'].keys():
                # Specify additional settings for generated models that have not any settings.
                if model_c_file.startswith('$'):
                    for generated_model_c_file in models.keys():
                        if generated_model_c_file.endswith(model_c_file[1:]):
                            models[generated_model_c_file] = self.conf['models'][model_c_file]
                        else:
                            raise KeyError('Model C file "{0}" was not generated'.format(model_c_file[1:]))
            # Like common models processed below.
            for model_c_file in self.conf['models'].keys():
                if not model_c_file.startswith('$'):
                    model_c_file_realpath = core.utils.find_file_or_dir(self.logger,
                                                                        self.conf['main working directory'],
                                                                        model_c_file)
                    self.logger.debug('Get model with C file "{0}"'.format(model_c_file_realpath))
                    models[os.path.relpath(model_c_file_realpath,
                                           os.path.realpath(self.conf['source tree root']))] = \
                        self.conf['models'][model_c_file]
        if 'common models' in self.conf:
            for common_model_c_file in self.conf['common models'].keys():
                common_model_c_file_realpath = core.utils.find_file_or_dir(self.logger,
                                                                           self.conf['main working directory'],
                                                                           common_model_c_file)
                self.logger.debug('Get common model with C file "{0}"'.format(common_model_c_file_realpath))
                models[os.path.relpath(common_model_c_file_realpath,
                                       os.path.realpath(self.conf['source tree root']))] = \
                    self.conf['common models'][common_model_c_file]

        if not models:
            self.logger.warning('No models are specified')
            return

        # CC extra full description files will be put to this directory as well as corresponding output files.
        os.makedirs('models')

        # TODO: at the moment it is assumed that there is the only group in each verification object. Actually we need
        # to create a separate group and make all other to depend on it.
        # Generate CC extra full description file per each model and add it to abstract task description.
        for grp in self.abstract_task_desc['grps']:
            self.logger.info('Add models to group "{0}"'.format(grp['id']))
            for model_c_file in models.keys():
                out_file = os.path.join('models', '{}.c'.format(os.path.splitext(os.path.basename(model_c_file))[0]))
                full_desc_file = '{0}.json'.format(out_file)
                if os.path.isfile(full_desc_file):
                    raise FileExistsError('CC extra full description file "{0}" already exists'.format(full_desc_file))
                self.logger.debug('Dump CC extra full description to file "{0}"'.format(full_desc_file))
                with open(full_desc_file, 'w', encoding='ascii') as fp:
                    json.dump({
                        # Input file path should be relative to source tree root since compilation options are relative
                        # to this directory and we will change directory to that one before invoking preprocessor.
                        "in files": [model_c_file],
                        # Otput file should be located somewhere inside RSG working directory to avoid races.
                        "out file": os.path.relpath(out_file, os.path.realpath(self.conf['source tree root'])),
                        "opts":
                            [string.Template(opt).substitute(hdr_arch=self.conf['sys']['hdr arch']) for opt in
                             self.conf['model CC options']] +
                            ['-DLDV_SETS_MODEL_' + (models[model_c_file]['sets model']
                                                    if 'sets model' in models[model_c_file]
                                                    else self.conf['common sets model']).upper()]
                    }, fp, sort_keys=True, indent=4)

                grp['cc extra full desc files'].append({
                    'cc full desc file': os.path.relpath(full_desc_file,
                                                         os.path.realpath(self.conf['source tree root'])),
                    'rule spec id': self.conf['rule spec id'],
                    'bug kinds': self.conf['bug kinds']
                })
