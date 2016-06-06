#!/usr/bin/python3

import json
import multiprocessing
import os
import string
import re

import core.components
import core.utils


def before_launch_sub_job_components(context):
    context.mqs['src tree root'] = multiprocessing.Queue()


def after_set_src_tree_root(context):
    context.mqs['src tree root'].put(context.src_tree_root)


class RSG(core.components.Component):
    def generate_rule_specification(self):
        self.abstract_task_desc = self.mqs['abstract task description'].get()

        aspects = []
        models = []

        if 'files' in self.abstract_task_desc:
            self.logger.info('Get additional aspects and models specified in abstract task description')

            for file in self.abstract_task_desc['files']:
                ext = os.path.splitext(file)[1]
                if ext == '.c':
                    models.append(os.path.relpath(os.path.join(self.conf['main working directory'], file)))
                    self.logger.debug('Get additional model "{0}'.format(file))
                elif ext == '.aspect':
                    aspects.append(file)
                    self.logger.debug('Get additional aspect "{0}'.format(file))
                elif ext == '.spc':
                    pass
                    # TODO: add support for automata
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
        if 'common aspect' in self.conf:
            common_aspect = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                                        self.conf['common aspect'])
            self.logger.debug('Get common aspect "{0}"'.format(common_aspect))
            aspects.append(os.path.relpath(common_aspect, self.conf['main working directory']))
        for aspect in (self.conf.get('common aspects') or []) + (self.conf.get('aspects') or []):
            aspect = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'], aspect)
            self.logger.debug('Get aspect "{0}"'.format(aspect))
            aspects.append(os.path.relpath(aspect, self.conf['main working directory']))

        if not aspects:
            self.logger.warning('No aspects ase specified')
            return

        for grp in self.abstract_task_desc['grps']:
            self.logger.info('Add aspects to C files of group "{0}"'.format(grp['id']))
            for cc_extra_full_desc_file in grp['cc extra full desc files']:
                if 'plugin aspects' not in cc_extra_full_desc_file:
                    cc_extra_full_desc_file['plugin aspects'] = []
                cc_extra_full_desc_file['plugin aspects'].append({"plugin": self.name, "aspects": aspects})

    def add_models(self, models):
        self.logger.info('Add models to abstract task description')

        # Get common and rule specific models.
        for model in (self.conf.get('common models')):
                try:
                    _model = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'], model)
                    self.logger.debug('Get model "{0}"'.format(_model))
                    models.append(_model)
                except FileNotFoundError:
                    continue

        for model in (self.conf.get('models')):
                try:
                    _model = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'], model)
                    self.logger.debug('Get model "{0}"'.format(_model))
                    models.append(_model)
                except FileNotFoundError:
                    continue

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
            for model in models:

                bug_kinds = set()
                lines = []
                with open(model,encoding='ascii') as fp:
                    for line in fp:
                        # Bug kinds are specified in form of strings like in rule specifications DB as first actual
                        # parameters of ldv_assert().
                        match = re.search(r'ldv_assert\("([^"]+)"', line)
                        if match:
                            bug_kind, = match.groups()
                            bug_kinds.add(bug_kind)
                            # Include bug kinds in names of ldv_assert().
                            lines.append(re.sub(r'ldv_assert\("([^"]+)", ?',
                                                r'ldv_assert_{0}('.format(re.sub(r'\W', '_', bug_kind)), line))
                        else:
                            lines.append(line)

                with open(model, 'w', encoding='ascii') as fp:
                    # Create ldv_assert*() function declarations to avoid compilation warnings. These functions will be
                    # defined later somehow by VTG.
                    for bug_kind in bug_kinds:
                        fp.write('extern void ldv_assert_{0}(int);\n'.format(re.sub(r'\W', '_', bug_kind)))
                    for line in lines:
                        fp.write(line)
                suffix = ''
                full_desc_file = os.path.join('models', '{0}.json'.format(os.path.basename(model)))
                if os.path.isfile(full_desc_file):
                    suffix = 2
                    while True:
                        full_desc_file = os.path.join('models', '{0}{1}.json'.format(os.path.basename(model), suffix))
                        if os.path.isfile(full_desc_file):
                            suffix = str(int(suffix) + 1)
                        else:
                            break
                # Otput file should be located somewhere inside RSG working directory to avoid races.
                out_file = os.path.join('models',
                                        '{0}{1}.c'.format(os.path.splitext(os.path.basename(model))[0], suffix))
                self.logger.debug('Dump CC extra full description to file "{0}"'.format(full_desc_file))
                with open(full_desc_file, 'w', encoding='ascii') as fp:
                    json.dump({
                        'cwd': self.conf['shadow source tree'],
                        # Input and output file paths should be relative to source tree root since compilation options
                        # are relative to this directory and we will change directory to that one before invoking
                        # preprocessor.
                        'in files': [os.path.relpath(model, os.path.join(self.conf['main working directory'],
                                                                         self.conf['shadow source tree']))],
                        'out file': os.path.relpath(out_file, os.path.join(self.conf['main working directory'],
                                                                           self.conf['shadow source tree'])),
                        'opts':
                            [string.Template(opt).substitute(hdr_arch=self.conf['header architecture']) for opt in
                             self.conf['model CC options']] +
                            ['-DLDV_SETS_MODEL_' + (model['sets model'] if 'sets model' in model
                                                    else self.conf['common sets model']).upper()]
                    }, fp, sort_keys=True, indent=4)
                is_add = False
                for model_file, attrs in self.conf['models'].items():
                    # TODO: absolutely different formats...
                    if os.path.commonprefix([model_file[::-1], model[::-1]]).__len__() > 5:
                        if "bug kinds" in attrs:
                            grp['cc extra full desc files'].append({
                                'cc full desc file': os.path.relpath(full_desc_file, self.conf['main working directory']),
                                'rule spec id': self.conf['rule spec id'],
                                'bug kinds': attrs['bug kinds']
                            })
                            is_add = True
                if not is_add:
                    grp['cc extra full desc files'].append({
                        'cc full desc file': os.path.relpath(full_desc_file, self.conf['main working directory']),
                        'rule spec id': self.conf['rule spec id']
                    })
