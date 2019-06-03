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

import json
import os
import re
from clade import Clade

import core.utils
import core.vtg.plugins
import core.vtg.utils


class RSG(core.vtg.plugins.Plugin):

    def __init__(self, conf, logger, parent_id, callbacks, mqs, vals, id=None, work_dir=None, attrs=None,
                 separate_from_parent=False, include_child_resources=False):
        super(RSG, self).__init__(conf, logger, parent_id, callbacks, mqs, vals, id, work_dir, attrs,
                                  separate_from_parent, include_child_resources)

    def generate_requirement(self):
        generated_models = {}

        if 'files' in self.abstract_task_desc:
            self.logger.info('Get generated aspects and models specified in abstract task description')

            for file in self.abstract_task_desc['files']:
                file = os.path.relpath(os.path.join(self.conf['main working directory'], file))
                ext = os.path.splitext(file)[1]
                if ext == '.c':
                    generated_models[file] = {}
                    self.logger.debug('Get generated model with C file "{0}'.format(file))
                elif ext == '.aspect':
                    self.logger.debug('Get generated aspect "{0}'.format(file))
                else:
                    raise ValueError('Files with extension "{0}" are not supported'.format(ext))

        self.add_models(generated_models)

        if 'files' in self.abstract_task_desc:
            self.abstract_task_desc.pop('files')

    main = generate_requirement

    def add_models(self, generated_models):
        self.logger.info('Add models to abstract verification task description')

        models = {}
        if 'environment model' in self.abstract_task_desc:
            rel_path = os.path.relpath(os.path.join(self.conf['main working directory'],
                                                    self.abstract_task_desc['environment model']), os.path.curdir)
            models[rel_path] = {}
        if self.abstract_task_desc.get('extra C files'):
            files = self.abstract_task_desc.get('extra C files')
            self.abstract_task_desc['extra C files'] = []
            for file in (f.get("C file") for f in files if "C file" in f):
                rel_path = os.path.relpath(os.path.join(self.conf['main working directory'], file), os.path.curdir)
                models[rel_path] = {}

        # Get common and requirement specific models.
        if 'common models' in self.conf and 'models' in self.conf:
            for common_model_c_file in self.conf['common models']:
                if common_model_c_file in self.conf['models']:
                    raise KeyError('C file "{0}" is specified in both common and requirement specific models')

        if 'models' in self.conf:
            for model_c_file in self.conf['models']:
                # Specify additional settings for generated models that have not any settings.
                if model_c_file.startswith('$'):
                    is_generated_model_c_file_found = False
                    for generated_model_c_file in generated_models:
                        if generated_model_c_file.endswith(model_c_file[1:]):
                            models[generated_model_c_file] = self.conf['models'][model_c_file]
                            is_generated_model_c_file_found = True
                    if not is_generated_model_c_file_found:
                        raise KeyError('Model C file "{0}" was not generated'.format(model_c_file[1:]))
            # Like common models processed below.
            for model_c_file in self.conf['models']:
                if not model_c_file.startswith('$'):
                    model_c_file_realpath = core.vtg.utils.find_file_or_dir(self.logger,
                                                                            self.conf['main working directory'],
                                                                            model_c_file)
                    self.logger.debug('Get model with C file "{0}"'.format(model_c_file_realpath))
                    models[model_c_file_realpath] = self.conf['models'][model_c_file]

        if 'common models' in self.conf:
            for common_model_c_file in self.conf['common models']:
                common_model_c_file_realpath = core.vtg.utils.find_file_or_dir(self.logger,
                                                                               self.conf['main working directory'],
                                                                               common_model_c_file)
                self.logger.debug('Get common model with C file "{0}"'.format(common_model_c_file_realpath))
                models[common_model_c_file_realpath] = self.conf['common models'][common_model_c_file]

        self.logger.debug('Resulting models are: {0}'.format(models))

        if not models:
            self.logger.warning('No models are specified')
            return

        # CC extra full description files will be put to this directory as well as corresponding intermediate and final
        # output files.
        os.makedirs('models'.encode('utf8'))

        self.logger.info('Add aspects to abstract verification task description')
        aspects = []
        for model_c_file in models:
            aspect = '{}.aspect'.format(os.path.splitext(model_c_file)[0])

            if not os.path.isfile(aspect):
                continue

            self.logger.debug('Get aspect "{0}"'.format(aspect))

            aspects.append(aspect)

        # Sort aspects to apply them in the deterministic order.
        aspects.sort()

        for grp in self.abstract_task_desc['grps']:
            self.logger.info('Add aspects to C files of group "{0}"'.format(grp['id']))
            for extra_cc in grp['Extra CCs']:
                if 'plugin aspects' not in extra_cc:
                    extra_cc['plugin aspects'] = []
                extra_cc['plugin aspects'].append({
                    'plugin': self.name,
                    'aspects': [os.path.relpath(aspect, self.conf['main working directory']) for aspect in aspects]
                })

        for model_c_file in models:
            model = models[model_c_file]

            if 'bug kinds' in model:
                self.logger.info('Preprocess bug kinds for model with C file "{0}"'.format(model_c_file))
                # Collect all bug kinds specified in model to check that valid bug kinds are specified in requirement
                # model description.
                bug_kinds = set()
                lines = []
                with open(model_c_file, encoding='utf8') as fp:
                    for line in fp:
                        # Bug kinds are specified in form of strings like in requirements DB as first actual
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
                for bug_kind in model['bug kinds']:
                    if bug_kind not in bug_kinds:
                        raise KeyError(
                            'Invalid bug kind "{0}" is specified in requirement model description'.format(
                                bug_kind))
                preprocessed_model_c_file = '{0}.bk.c'.format(
                    core.utils.unique_file_name(os.path.join('models',
                                                             os.path.splitext(os.path.basename(model_c_file))[0]),
                                                '.bk.c'))
                with open(preprocessed_model_c_file, 'w', encoding='utf8') as fp:
                    # Create ldv_assert*() function declarations to avoid compilation warnings. These functions will
                    # be defined later somehow by VTG.
                    for bug_kind in sorted(bug_kinds):
                        fp.write('extern void ldv_assert_{0}(int);\n'.format(re.sub(r'\W', '_', bug_kind)))
                    # Specify original location to avoid references to *.bk.c files in error traces.
                    fp.write('# 1 "{0}"\n'.format(os.path.abspath(model_c_file)))
                    for line in lines:
                        fp.write(line)
                model['bug kinds preprocessed C file'] = preprocessed_model_c_file
                self.logger.debug('Preprocessed bug kinds for model with C file "{0}" was placed to "{1}"'.
                                  format(model_c_file, preprocessed_model_c_file))
            else:
                model['bug kinds preprocessed C file'] = model_c_file

        # Generate CC full description file per each model and add it to abstract task description.
        # First of all obtain CC options to be used to compile models.
        clade = Clade(self.conf['build base'])
        meta = clade.get_meta()

        # Relative path to source file which CC options to be used is specified in configuration. Clade needs absolute
        # path. The former is relative to one of source paths.
        if not meta['conf'].get('Compiler.preprocess_cmds', False):
            for path in self.conf['source paths']:
                opts_file = os.path.join(path, self.conf['opts file'])
                try:
                    empty_cc = list(clade.get_compilation_cmds_by_file(opts_file))
                except KeyError:
                    pass

            if not empty_cc:
                raise RuntimeError("There is not of cc commands for {!r}".format(self.conf['opts file']))
            elif len(empty_cc) > 1:
                self.logger.warning("There are more than one cc command for {!r}".format(self.conf['opts file']))

            empty_cc = empty_cc.pop()
            empty_cc['opts'] = clade.get_cmd_opts(empty_cc['id'])
        else:
            empty_cc = {'opts': [], 'cwd': self.conf['source paths'][-1]}

        model_grp = {'id': 'models', 'Extra CCs': []}
        for model_c_file in sorted(models):
            model = models[model_c_file]
            extra_cc = {}

            if 'bug kinds preprocessed C file' in model:
                file, ext = os.path.splitext(os.path.join('models',
                                                          os.path.basename(model['bug kinds preprocessed C file'])))
                base_name = core.utils.unique_file_name(file, '{0}.json'.format(ext))
                full_desc_file = '{0}{1}.json'.format(base_name, ext)
                out_file = '{0}.c'.format(base_name)

                self.logger.debug('Dump CC full description to file "{0}"'.format(full_desc_file))
                with open(full_desc_file, 'w', encoding='utf8') as fp:
                    json.dump({
                        'cwd': empty_cc['cwd'],
                        'in': [os.path.relpath(model['bug kinds preprocessed C file'],
                                               os.path.realpath(clade.get_storage_path(empty_cc['cwd'])))],
                        'out': [os.path.realpath(out_file)],
                        'opts': empty_cc['opts'] +
                                ['-DLDV_SETS_MODEL_' + (model['sets model']
                                                        if 'sets model' in model
                                                        else self.conf['common sets model']).upper()]
                    }, fp, ensure_ascii=False, sort_keys=True, indent=4)

                extra_cc['CC'] = os.path.relpath(full_desc_file, self.conf['main working directory'])

            if 'bug kinds' in model:
                extra_cc['bug kinds'] = model['bug kinds']

            if extra_cc:
                model_grp['Extra CCs'].append(extra_cc)

        self.abstract_task_desc['grps'].append(model_grp)
        for dep in self.abstract_task_desc['deps'].values():
            dep.append(model_grp['id'])
