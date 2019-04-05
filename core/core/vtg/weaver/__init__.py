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

import fileinput
import json
import os
import re
from clade import Clade

import core.utils
import core.vtg.utils
import core.vtg.plugins


class Weaver(core.vtg.plugins.Plugin):

    def __init__(self, conf, logger, parent_id, callbacks, mqs, vals, id=None, work_dir=None, attrs=None,
                 separate_from_parent=False, include_child_resources=False):
        super(Weaver, self).__init__(conf, logger, parent_id, callbacks, mqs, vals, id, work_dir, attrs,
                                     separate_from_parent, include_child_resources)

    def weave(self):
        self.abstract_task_desc['extra C files'] = []

        clade = Clade(self.conf['build base'])

        # This is required to get compiler (Aspectator) specific stdarg.h since kernel C files are compiled
        # with "-nostdinc" option and system stdarg.h couldn't be used.
        aspectator_search_dir = '-isystem' + core.utils.execute(self.logger,
                                                                ('aspectator', '-print-file-name=include'),
                                                                collect_all_stdout=True)[0]

        env = dict(os.environ)
        # Print stubs instead of inline Assembler since verifiers do not interpret it and even can fail.
        env['LDV_INLINE_ASM_STUB'] = ''

        for grp in self.abstract_task_desc['grps']:
            self.logger.info('Weave in C files of group "{0}"'.format(grp['id']))

            for extra_cc in grp['Extra CCs']:
                if 'CC' in extra_cc:
                    if extra_cc['CC'].isdigit():
                        cc = clade.get_cmd(extra_cc['CC'], with_opts=True)
                    else:
                        with open(os.path.join(self.conf['main working directory'], extra_cc['CC']),
                                  encoding='utf8') as fp:
                            cc = json.load(fp)

                        # extra_cc is a cc command that is not from Clade
                        # Thus paths in it need to be converted to be absolute
                        # like in other Clade commands
                        if "cwd" in cc and "in" in cc:
                            cc["in"] = [os.path.join(cc["cwd"], cc_in) for cc_in in cc["in"]]

                        if "cwd" in cc and "out" in cc:
                            cc["out"] = [os.path.join(cc["cwd"], cc_out) for cc_out in cc["out"]]

                    self.logger.info('Weave in C file "{0}"'.format(cc['in'][0]))

                    cc['out'][0] = '{0}.c'.format(core.utils.unique_file_name(os.path.splitext(
                        os.path.basename(cc['out'][0]))[0], '.abs-paths.i'))

                    # Produce aspect to be weaved in.
                    if 'plugin aspects' in extra_cc:
                        self.logger.info('Concatenate all aspects of all plugins together')

                        # Resulting aspect.
                        aspect = 'aspect'

                        # Get all aspects. Place RSG aspects at beginning since they can instrument entities added by
                        # aspects of other plugins while corresponding function declarations still need be at beginning
                        # of file.
                        aspects = []
                        for plugin_aspects in extra_cc['plugin aspects']:
                            if plugin_aspects['plugin'] == 'RSG':
                                aspects[0:0] = plugin_aspects['aspects']
                            else:
                                aspects.extend(plugin_aspects['aspects'])

                        # Concatenate aspects.
                        with open(aspect, 'w', encoding='utf8') as fout, fileinput.input(
                                [os.path.join(self.conf['main working directory'], aspect) for aspect in aspects],
                                openhook=fileinput.hook_encoded('utf8')) as fin:
                            for line in fin:
                                fout.write(line)
                    else:
                        # Simulate resulting aspect.
                        aspect = '/dev/null'
                    self.logger.debug('Aspect to be weaved in is "{0}"'.format(aspect))
                    storage_path = clade.get_storage_path(cc['in'][0])
                    if self.conf.get('use preprocessed files') and 'klever-core-work-dir' not in storage_path:
                        storage_path = storage_path.split('.c')[0] + '.i'
                    core.utils.execute(
                        self.logger,
                        tuple([
                                  'cif',
                                  '--in', storage_path,
                                  '--aspect', os.path.realpath(aspect),
                                  # Besides header files specific for requirements specifications will be searched for.
                                  '--general-opts',
                                  '-I' + os.path.realpath(os.path.dirname(self.conf['requirements DB'])),
                                  '--aspect-preprocessing-opts', ' '.join(self.conf['aspect preprocessing options'])
                                                                 if 'aspect preprocessing options' in self.conf else '',
                                  '--out', os.path.realpath(cc['out'][0]),
                                  '--back-end', 'src',
                                  '--debug', 'DEBUG'
                              ] +
                              (['--keep'] if self.conf['keep intermediate files'] else []) +
                              ['--'] +
                              core.vtg.utils.prepare_cif_opts(self.conf, cc['opts'], clade.storage_dir,
                                                              preprocessed_files=self.conf.get('use preprocessed files')) +
                              [aspectator_search_dir]
                              ),
                        env=env,
                        cwd=clade.get_storage_path(cc['cwd']),
                        timeout=0.01,
                        filter_func=core.vtg.utils.CIFErrorFilter())
                    self.logger.debug('C file "{0}" was weaved in'.format(cc['in'][0]))

                    # In addition preprocess output files since CIF outputs a bit unpreprocessed files.
                    preprocessed_c_file = '{}.i'.format(os.path.splitext(cc['out'][0])[0])
                    core.utils.execute(self.logger,
                                       (
                                           'aspectator',
                                           '-E',
                                           '-x', 'c', cc['out'][0],
                                           '-o', preprocessed_c_file
                                       ),
                                       timeout=0.01)
                    if not self.conf['keep intermediate files']:
                        os.remove(cc['out'][0])
                    self.logger.debug('Preprocessed weaved C file was put to "{0}"'.format(preprocessed_c_file))

                    abs_paths_c_file = '{0}.abs-paths.i'.format(os.path.splitext(cc['out'][0])[0])
                    with open(preprocessed_c_file, encoding='utf8') as fp_in, open(abs_paths_c_file, 'w',
                                                                                   encoding='utf8') as fp_out:
                        # Print preprocessor header as is.
                        first_line = fp_in.readline()
                        fp_out.write(first_line)
                        for line in fp_in:
                            fp_out.write(line)
                            if line == first_line:
                                break

                        # Replace relative file paths with absolute ones for line directives in other lines.
                        for line in fp_in:
                            match = re.match(r'(# \d+ ")(.+)("\n)', line)
                            if match:
                                file = match.group(2)
                                if not os.path.isabs(file):
                                    # All relative file paths are relative to CC working directory.
                                    file = os.path.abspath(os.path.join(os.path.realpath(clade.storage_dir) + cc['cwd'], file))
                                fp_out.write(match.group(1) + file + match.group(3))
                            else:
                                fp_out.write(line)
                    if not self.conf['keep intermediate files']:
                        os.remove(preprocessed_c_file)
                    self.logger.debug(
                        'Preprocessed weaved C file with absolute paths was put to "{0}"'.format(abs_paths_c_file))

                    extra_c_file = {'C file': os.path.relpath(abs_paths_c_file, self.conf['main working directory'])}
                else:
                    extra_c_file = {}

                if 'requirement id' in extra_cc:
                    extra_c_file['requirement id'] = extra_cc['requirement id']

                if 'bug kinds' in extra_cc:
                    extra_c_file['bug kinds'] = extra_cc['bug kinds']

                self.abstract_task_desc['extra C files'].append(extra_c_file)

        # These sections won't be reffered any more.
        del (self.abstract_task_desc['grps'])
        del (self.abstract_task_desc['deps'])

    main = weave
