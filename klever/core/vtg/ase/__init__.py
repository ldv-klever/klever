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

import fileinput
import os
from clade import Clade

import klever.core.utils
import klever.core.vtg.plugins
import klever.core.vtg.utils


class ASE(klever.core.vtg.plugins.Plugin):
    def extract_argument_signatures(self):
        if 'request aspects' not in self.conf:
            raise KeyError('There is not mandatory option "request aspects"')

        if not self.conf['request aspects']:
            raise KeyError(
                'Value of option "request aspects" is not mandatory JSON object with request aspects as keys')

        self.request_arg_signs()

        if 'template context' not in self.abstract_task_desc:
            self.abstract_task_desc['template context'] = {}

        for request_aspect in self.conf['request aspects']:
            arg_signs_file = os.path.splitext(os.path.splitext(os.path.basename(request_aspect))[0])[0]

            arg_signs = None

            if os.path.isfile(arg_signs_file):
                self.logger.info(f'Process obtained argument signatures from file "{arg_signs_file}"')
                # We could obtain the same argument signatures, so remove duplicates.
                with open(arg_signs_file, encoding='utf-8') as fp:
                    arg_signs = set(fp.read().splitlines())
                self.logger.debug(f'Obtain following argument signatures "{arg_signs}"')

            # Convert each argument signature (that is represented as C identifier) into:
            # * the same identifier but with leading "_" for concatenation with other identifiers ("_" allows to
            #   separate these identifiers visually more better in rendered templates, while in original templates they
            #   are already separated quite well by template syntax, besides, we can generate models and aspects without
            #   argument signatures at all on the basis of the same templates)
            # * more nice text representation for notes to be shown to users.
            self.abstract_task_desc['template context'][arg_signs_file] = {
                arg_signs_file + '_arg_signs':
                    [
                        {'id': '_{0}'.format(arg_sign), 'text': ' "{0}"'.format(arg_sign)}
                        for arg_sign in sorted(arg_signs)
                    ] if arg_signs else [{'id': '', 'text': ''}],
                arg_signs_file + '_arg_sign_patterns':
                    ['_$arg_sign{0}'.format(i) if arg_signs else '' for i in range(10)]
            }

    def request_arg_signs(self):
        self.logger.info('Request argument signatures')
        clade_conf = {"log_level": "ERROR"}
        clade = Clade(work_dir=self.conf['build base'], conf=clade_conf)
        if not clade.work_dir_ok():
            raise RuntimeError('Build base is not OK')
        meta = clade.get_meta()

        for request_aspect in self.conf['request aspects']:
            request_aspect = klever.core.vtg.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                                                    request_aspect)
            self.logger.debug(f'Request aspect is "{request_aspect}"')

            for grp in self.abstract_task_desc['grps']:
                self.logger.info('Request argument signatures for C files of group "%s"', grp['id'])

                for extra_cc in grp['Extra CCs']:
                    infile = extra_cc['in file']
                    self.logger.info(f'Request argument signatures for C file "{infile}"')

                    cc = clade.get_cmd(*extra_cc['CC'], with_opts=True)

                    env = dict(os.environ)
                    env['LDV_ARG_SIGNS_FILE'] = os.path.realpath(
                        os.path.splitext(os.path.splitext(os.path.basename(request_aspect))[0])[0])
                    self.logger.debug('Argument signature file is "%s"',
                                      os.path.relpath(env['LDV_ARG_SIGNS_FILE']))

                    # Add plugin aspects produced thus far (by EMG) since they can include additional headers for which
                    # additional argument signatures should be extracted. Like in Weaver.
                    if 'plugin aspects' in extra_cc:
                        self.logger.info('Concatenate all aspects of all plugins together')

                        # Resulting request aspect.
                        aspect = '{0}.aspect'.format(
                            klever.core.utils.unique_file_name(os.path.splitext(os.path.basename(infile))[0],
                                                               '.aspect'))

                        # Get all aspects. Place original request aspect at beginning since it can instrument entities
                        # added by aspects of other plugins while corresponding function declarations still need be at
                        # beginning of file.
                        aspects = [os.path.relpath(request_aspect, self.conf['main working directory'])]
                        for plugin_aspects in extra_cc['plugin aspects']:
                            aspects.extend(plugin_aspects['aspects'])

                        # Concatenate aspects.
                        with open(aspect, 'w', encoding='utf-8') as fout, fileinput.input(
                                [os.path.join(self.conf['main working directory'], aspect) for aspect in aspects],
                                openhook=fileinput.hook_encoded('utf-8')) as fin:
                            for line in fin:
                                fout.write(line)
                    else:
                        aspect = request_aspect

                    storage_path = clade.get_storage_path(infile)
                    if meta['conf'].get('Compiler.preprocess_cmds', False) and \
                            'klever-core-work-dir' not in storage_path:
                        storage_path = storage_path.split('.c')[0] + '.i'

                    opts = cc['opts']
                    # Like in Weaver.
                    opts.append(klever.core.vtg.utils.define_arch_dependent_macro(self.conf))

                    klever.core.utils.execute(
                        self.logger,
                        tuple(
                            [
                                klever.core.vtg.utils.get_cif_or_aspectator_exec(self.conf, 'cif'),
                                '--in', storage_path,
                                '--aspect', os.path.realpath(aspect),
                                '--stage', 'instrumentation',
                                '--out', os.path.realpath('{0}.c'.format(klever.core.utils.unique_file_name(
                                    os.path.splitext(os.path.basename(infile))[0], '.c.aux'))),
                                '--debug', 'DEBUG'
                            ] +
                            (['--keep'] if self.conf['keep intermediate files'] else []) +
                            ['--'] +
                            klever.core.vtg.utils.prepare_cif_opts(opts, clade) +
                            # Like in Weaver.
                            ['-I' + os.path.join(os.path.dirname(self.conf['specifications base']), 'include')]
                        ),
                        env,
                        cwd=clade.get_storage_path(cc['cwd']),
                        timeout=0.01,
                        filter_func=klever.core.vtg.utils.CIFErrorFilter())

    main = extract_argument_signatures
