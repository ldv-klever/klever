#
# Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
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

import json
import os
import re
import string

import core.avtg.plugins
import core.utils


class RSG(core.avtg.plugins.Plugin):
    def generate_rule_specification(self):
        generated_models = {}

        if 'verifier specifications' in self.conf:
            self.logger.info('Verifier specifications are: '.join(self.conf['verifier specifications']))
            self.abstract_task_desc['verifier specifications'] = self.conf['verifier specifications']

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
                elif ext == '.spc':
                    generated_models[file] = {}
                    self.logger.debug('Get generated model with automaton file "{0}'.format(file))
                else:
                    raise ValueError('Files with extension "{0}" are not supported'.format(ext))

        self.add_models(generated_models)

        if 'files' in self.abstract_task_desc:
            self.abstract_task_desc.pop('files')

    main = generate_rule_specification

    def add_models(self, generated_models):
        self.logger.info('Add models to abstract verification task description')

        models = {}
        automata = {}
        # Get common and rule specific models.
        if 'common models' in self.conf and 'models' in self.conf:
            for common_model_c_file in self.conf['common models']:
                if common_model_c_file in self.conf['models']:
                    raise KeyError('C file "{0}" is specified in both common and rule specific models')

        if 'models' in self.conf:
            for model_c_file in self.conf['models']:
                # Specify additional settings for generated models that have not any settings.
                if model_c_file.startswith('$'):
                    is_generated_model_c_file_found = False
                    for generated_model_c_file in generated_models:
                        if generated_model_c_file.endswith(model_c_file[1:]):
                            models[generated_model_c_file] = self.conf['models'][model_c_file]
                            is_generated_model_c_file_found = True
                            # Get all property automata.
                            if self.conf['RSG strategy'] == 'property automaton':
                                if 'automaton' in self.conf['models'][model_c_file]:
                                    automaton = self.conf['models'][model_c_file]['automaton']
                                    for generated_model_automaton_file in generated_models:
                                        if generated_model_automaton_file.endswith(automaton[1:]):
                                            generated_model_automaton_file = \
                                                os.path.abspath(generated_model_automaton_file)
                                            automata[generated_model_c_file] = generated_model_automaton_file
                                            self.logger.debug('Get model with automaton file "{0}"'.
                                                              format(automaton))
                                else:
                                    raise ValueError('Automaton does not exist for "{0}" model'.
                                                     format(generated_model_c_file))
                    if not is_generated_model_c_file_found:
                        raise KeyError('Model C file "{0}" was not generated'.format(model_c_file[1:]))
            # Like common models processed below.
            for model_c_file in self.conf['models']:
                if not model_c_file.startswith('$'):
                    model_c_file_realpath = core.utils.find_file_or_dir(self.logger,
                                                                        self.conf['main working directory'],
                                                                        model_c_file)
                    self.logger.debug('Get model with C file "{0}"'.format(model_c_file_realpath))
                    models[model_c_file_realpath] = self.conf['models'][model_c_file]
                    # Get all property automata.
                    if self.conf['RSG strategy'] == 'property automaton':
                        for elem in self.conf['models'][model_c_file]:
                            if elem == 'automaton':
                                automaton = core.utils.find_file_or_dir(self.logger,
                                                                        self.conf['main working directory'],
                                                                        self.conf['models'][model_c_file][elem])
                                automaton = os.path.abspath(automaton)
                                if not os.path.isfile(automaton):
                                    raise ValueError('WTH is "{0}"'.format(automaton))

                                automata[model_c_file_realpath] = automaton
                                self.logger.debug('Get model with automaton file "{0}"'.
                                                  format(automaton))

        if 'common models' in self.conf:
            for common_model_c_file in self.conf['common models']:
                common_model_c_file_realpath = core.utils.find_file_or_dir(self.logger,
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
        os.makedirs('models')
        self.logger.info('Add aspects to abstract verification task description')
        aspects = []
        for model_c_file in models:
            model = models[model_c_file]

            aspect = '{}.aspect'.format(os.path.splitext(model_c_file)[0])
            if not os.path.isfile(aspect):
                model['prefix preprocessed C file'] = model_c_file
                continue
            self.logger.debug('Get aspect "{0}"'.format(aspect))

            if 'rule specification identifier' in model:
                rule_spec_prefix = 'ldv_' + re.sub(r'\W', '_', model['rule specification identifier']) + '_'
                self.logger.info(
                    'Replace prefix "ldv" with rule specification specific one "{0}" for model with C file "{1}"'
                    .format(rule_spec_prefix, model_c_file))

                if self.conf['RSG strategy'] == 'instrumentation':
                    model_c_file_short = os.path.splitext(os.path.basename(model_c_file))[0]
                    preprocessed_model_c_file = '{0}.{1}.c'.format(
                        model_c_file_short,
                        re.sub(r'\W', '_', model['rule specification identifier']))
                    with open(model_c_file, encoding='utf8') as fp_in, \
                            open(preprocessed_model_c_file, 'w', encoding='utf8') as fp_out:
                        # Specify original location to avoid references to generated C files in error traces. Absolute
                        # file path here and below is required to get absolute path references in error traces.
                        fp_out.write('# 1 "{0}"\n'.format(os.path.abspath(model_c_file)))
                        for line in fp_in:
                            fp_out.write(re.sub(r'LDV_(?!PTR)', rule_spec_prefix.upper(),
                                                re.sub(r'ldv_(?!assert|assume|undef|set|map|in_interrupt_context|'
                                                       r'is_err|exclusive|zalloc|malloc|pre)',
                                                       rule_spec_prefix, line)))
                    model['prefix preprocessed C file'] = preprocessed_model_c_file
                    self.logger.debug(
                        'Preprocessed C file with rule specification specific prefix was placed to "{0}"'.
                        format(preprocessed_model_c_file))

                aspect_short = os.path.splitext(os.path.basename(aspect))[0]
                preprocessed_aspect = '{0}.{1}.aspect'.format(
                    aspect_short,
                    re.sub(r'\W', '_', model['rule specification identifier']))
                with open(aspect, encoding='utf8') as fp_in, \
                        open(preprocessed_aspect, 'w', encoding='utf8') as fp_out:
                    # Specify original location to avoid references to generated aspects in error traces.
                    fp_out.write('# 1 "{0}"\n'.format(os.path.abspath(aspect)))
                    for line in fp_in:
                        fp_out.write(re.sub(r'LDV_', rule_spec_prefix.upper(),
                                            re.sub(r'ldv_(?!assert|assume|undef|set|map|in_interrupt_context|is_err|'
                                                   r'exclusive|zalloc|malloc|pre)',
                                                   rule_spec_prefix, line)))
                self.logger.debug(
                    'Preprocessed aspect with rule specification specific prefix {0} was placed to "{1}"'.
                    format('for model with C file "{0}"'.format(model_c_file), preprocessed_aspect))
                aspects.append(preprocessed_aspect)

                if model_c_file in automata:
                    automaton = automata[model_c_file]
                    automaton_short = os.path.splitext(os.path.basename(automaton))[0]
                    preprocessed_automaton = '{0}.{1}.spc'.format(
                        automaton_short,
                        re.sub(r'\W', '_', model['rule specification identifier']))
                    with open(automaton, encoding='utf8') as fp_in, \
                            open(preprocessed_automaton, 'w', encoding='utf8') as fp_out:
                        for line in fp_in:
                            fp_out.write(re.sub(r'LDV_', rule_spec_prefix.upper(),
                                                re.sub(r'ldv_(?!assert|assume|undef|set|map|in_interrupt_context|'
                                                       r'is_err|exclusive|zalloc|malloc|pre)',
                                                       rule_spec_prefix, line)))
                    automata[model_c_file] = os.path.abspath(preprocessed_automaton)
            else:
                if (self.conf['RSG strategy'] == 'instrumentation') or \
                        (model_c_file not in automata):
                    model['prefix preprocessed C file'] = model_c_file
                aspects.append(aspect)

        # Sort aspects to apply them in the deterministic order.
        aspects.sort()

        # Common aspect should be weaved first since it likely overwrites some parts of rule specific aspects. Common
        # aspect should be used just if several rule specifications are merged together to resolve possible conflicts.
        if 'constituent rule specifications' in self.conf:
            if 'common aspect' not in self.conf:
                raise KeyError(
                    'Common aspect is not specified although several rule specifications are merged together')
            common_aspect = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                                        self.conf['common aspect'])
            self.logger.debug('Get common aspect "{0}"'.format(common_aspect))
            aspects.insert(0, common_aspect)

        for grp in self.abstract_task_desc['grps']:
            self.logger.info('Add aspects to C files of group "{0}"'.format(grp['id']))
            for cc_extra_full_desc_file in grp['cc extra full desc files']:
                if 'plugin aspects' not in cc_extra_full_desc_file:
                    cc_extra_full_desc_file['plugin aspects'] = []
                cc_extra_full_desc_file['plugin aspects'].append({
                    'plugin': self.name,
                    'aspects': [os.path.relpath(aspect, self.conf['main working directory']) for aspect in aspects]
                })

        for model_c_file in models:
            model = models[model_c_file]

            if self.conf['RSG strategy'] == 'instrumentation':
                if 'bug kinds' in model:
                    self.logger.info('Preprocess bug kinds for model with C file "{0}"'.format(model_c_file))
                    # Collect all bug kinds specified in model to check that valid bug kinds are specified in rule
                    # specification model description.
                    bug_kinds = set()
                    lines = []
                    with open(model['prefix preprocessed C file'], encoding='utf8') as fp:
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
                    for bug_kind in model['bug kinds']:
                        if bug_kind not in bug_kinds:
                            raise KeyError(
                                'Invalid bug kind "{0}" is specified in rule specification model description'.format(
                                    bug_kind))
                    preprocessed_model_c_file = os.path.join('models', '{0}.bk.c'.format(
                        os.path.splitext(os.path.basename(model['prefix preprocessed C file']))[0]))
                    with open(preprocessed_model_c_file, 'w', encoding='utf8') as fp:
                        # Create ldv_assert*() function declarations to avoid compilation warnings. These functions will
                        # be defined later somehow by VTG.
                        for bug_kind in sorted(bug_kinds):
                            fp.write('extern void ldv_assert_{0}(int);\n'.format(re.sub(r'\W', '_', bug_kind)))
                        # Specify original location to avoid references to *.bk.c files in error traces.
                        fp.write('# 1 "{0}"\n'.format(os.path.abspath(model['prefix preprocessed C file'])))
                        for line in lines:
                            fp.write(line)
                    model['bug kinds preprocessed C file'] = preprocessed_model_c_file
                    self.logger.debug('Preprocessed bug kinds for model with C file "{0}" was placed to "{1}"'.
                                      format(model_c_file, preprocessed_model_c_file))
                else:
                    model['bug kinds preprocessed C file'] = model['prefix preprocessed C file']

        # Generate CC extra full description file per each model and add it to abstract task description.
        model_grp = {'id': 'models', 'cc extra full desc files': []}
        for model_c_file in sorted(models):
            model = models[model_c_file]
            cc_extra_full_desc_file = {}

            if 'bug kinds preprocessed C file' in model:
                suffix = ''
                full_desc_file = os.path.join('models', '{0}.json'.format(
                    os.path.basename(model['bug kinds preprocessed C file'])))
                if os.path.isfile(full_desc_file):
                    suffix = 2
                    while True:
                        full_desc_file = os.path.join('models', '{0}{1}.json'.format(
                            os.path.basename(model['bug kinds preprocessed C file']), suffix))
                        if os.path.isfile(full_desc_file):
                            suffix = str(int(suffix) + 1)
                        else:
                            break

                # Otput file should be located somewhere inside RSG working directory to avoid races.
                out_file = os.path.join('models', '{0}{1}.c'.format(
                    os.path.splitext(os.path.basename(model['bug kinds preprocessed C file']))[0], suffix))

                self.logger.debug('Dump CC extra full description to file "{0}"'.format(full_desc_file))
                with open(full_desc_file, 'w', encoding='utf8') as fp:
                    json.dump({
                        'cwd': self.conf['shadow source tree'],
                        # Input and output file paths should be relative to source tree root since compilation options
                        # are relative to this directory and we will change directory to that one before invoking
                        # preprocessor.
                        'in files': [os.path.relpath(model['bug kinds preprocessed C file'],
                                                     os.path.join(self.conf['main working directory'],
                                                                  self.conf['shadow source tree']))],
                        'out file': os.path.relpath(out_file, os.path.join(self.conf['main working directory'],
                                                                           self.conf['shadow source tree'])),
                        'opts':
                            [string.Template(opt).substitute(hdr_arch=self.conf['header architecture']) for opt in
                             self.conf['model CC options']] +
                            ['-DLDV_SETS_MODEL_' + (model['sets model'] if 'sets model' in model
                                                    else self.conf['common sets model']).upper()]
                    }, fp, ensure_ascii=False, sort_keys=True, indent=4)

                cc_extra_full_desc_file['cc full desc file'] = os.path.relpath(full_desc_file,
                                                                               self.conf['main working directory'])

            if model_c_file in automata:
                cc_extra_full_desc_file['automaton'] = automata[model_c_file]

            if 'bug kinds' in model:
                cc_extra_full_desc_file['bug kinds'] = model['bug kinds']

            if cc_extra_full_desc_file:
                model_grp['cc extra full desc files'].append(cc_extra_full_desc_file)

        self.abstract_task_desc['grps'].append(model_grp)
        for dep in self.abstract_task_desc['deps'].values():
            dep.append(model_grp['id'])
