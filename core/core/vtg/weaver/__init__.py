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

import glob
import fileinput
import json
import os
import re
import shutil

from clade import Clade

import core.utils
import core.vtg.utils
import core.vtg.plugins
from core.cross_refs import CrossRefs


class Weaver(core.vtg.plugins.Plugin):

    def __init__(self, conf, logger, parent_id, callbacks, mqs, vals, id=None, work_dir=None, attrs=None,
                 separate_from_parent=False, include_child_resources=False):
        super(Weaver, self).__init__(conf, logger, parent_id, callbacks, mqs, vals, id, work_dir, attrs,
                                     separate_from_parent, include_child_resources)

    def weave(self):
        self.abstract_task_desc.setdefault('extra C files', dict())

        clade = Clade(self.conf['build base'])
        meta = clade.get_meta()

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
                    # Each CC is either pair (compiler command identifier, compiler command type) or JSON file name
                    # with compiler command description.
                    if isinstance(extra_cc['CC'], list):
                        cc = clade.get_cmd(*extra_cc['CC'], with_opts=True)
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

                    if "in file" in extra_cc:
                        # This is for CC commands with several input files
                        infile = extra_cc["in file"]
                    else:
                        infile = cc["in"][0]
                    outfile = '{0}.c'.format(core.utils.unique_file_name(os.path.splitext(os.path.basename(
                        infile))[0], '.abs-paths.i'))
                    self.logger.info('Weave in C file "{0}"'.format(infile))

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
                    storage_path = clade.get_storage_path(infile)
                    if meta['conf'].get('Compiler.preprocess_cmds', False) and \
                            'klever-core-work-dir' not in storage_path:
                        storage_path = storage_path.split('.c')[0] + '.i'
                    core.utils.execute(
                        self.logger,
                        tuple([
                                  'cif',
                                  '--in', storage_path,
                                  '--aspect', os.path.realpath(aspect),
                                  # Besides header files specific for requirements specifications will be searched for.
                                  '--general-opts',
                                  '-I' + os.path.realpath(os.path.dirname(self.conf['specifications base'])),
                                  '--aspect-preprocessing-opts', ' '.join(self.conf['aspect preprocessing options'])
                                                                 if 'aspect preprocessing options' in self.conf else '',
                                  '--out', os.path.realpath(outfile),
                                  '--back-end', 'src',
                                  '--debug', 'DEBUG'
                              ] +
                              (['--keep'] if self.conf['keep intermediate files'] else []) +
                              ['--'] +
                              core.vtg.utils.prepare_cif_opts(cc['opts'], clade, grp['id'] == 'models') +
                              [aspectator_search_dir] +
                              ['-I' + clade.get_storage_path(p) for p in self.conf['working source trees']]
                              ),
                        env=env,
                        cwd=clade.get_storage_path(cc['cwd']),
                        timeout=0.01,
                        filter_func=core.vtg.utils.CIFErrorFilter())
                    self.logger.debug('C file "{0}" was weaved in'.format(infile))

                    # In addition preprocess output files since CIF outputs a bit unpreprocessed files.
                    preprocessed_c_file = '{}.i'.format(os.path.splitext(outfile)[0])
                    core.utils.execute(self.logger,
                                       (
                                           'aspectator',
                                           '-E',
                                           '-x', 'c', outfile,
                                           '-o', preprocessed_c_file
                                       ),
                                       timeout=0.01)
                    if not self.conf['keep intermediate files']:
                        os.remove(outfile)
                    self.logger.debug('Preprocessed weaved C file was put to "{0}"'.format(preprocessed_c_file))

                    abs_paths_c_file = '{0}.abs-paths.i'.format(os.path.splitext(outfile)[0])
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

                                # Omit artificial and sometimes invalid reference to built-in stuff.
                                if file == '<built-in>':
                                    continue

                                if not os.path.isabs(file):
                                    # All relative file paths are relative to CC working directory.
                                    file = os.path.abspath(os.path.join(os.path.realpath(clade.storage_dir) + cc['cwd'],
                                                                        file))
                                elif not os.path.isfile(file):
                                    # Sometimes, e.g. for source files on Windows, their paths are absolute but just on
                                    # Windows. To make them absolute on Linux we need to prepend them with Clade storage
                                    # directory.
                                    file = clade.get_storage_path(file)
                                    if not os.path.isfile(file):
                                        raise FileNotFoundError('Can not find file "{0}" eventually'.format(file))

                                fp_out.write(match.group(1) + file + match.group(3))
                            else:
                                fp_out.write(line)
                    if not self.conf['keep intermediate files']:
                        os.remove(preprocessed_c_file)
                    self.logger.debug(
                        'Preprocessed weaved C file with absolute paths was put to "{0}"'.format(abs_paths_c_file))

                    extra_c_file = {'C file': os.path.relpath(abs_paths_c_file, self.conf['main working directory'])}

                    # TODO: this can be incorporated into instrumentation above but it will need some Clade changes.
                    # Emulate normal compilation (indeed just parsing thanks to "-fsyntax-only") to get additional
                    # dependencies (model source files) and information on them.
                    if grp['id'] == 'models':
                        core.utils.execute(
                            self.logger,
                            tuple([
                                    'clade',
                                    '-ia',
                                    '--cmds', os.path.realpath('cmds.txt'),
                                    'aspectator',
                                    '-I' + os.path.realpath(os.path.dirname(self.conf['specifications base']))
                                ] +
                                core.vtg.utils.prepare_cif_opts(cc['opts'], clade, grp['id'] == 'models') +
                                [
                                    aspectator_search_dir,
                                    '-fsyntax-only',
                                    clade.get_storage_path(cc['in'][0]),
                                    '-o', os.path.realpath('{0}.o'
                                                           .format(os.path.splitext(os.path.basename(cc['in'][0]))[0]))
                                ]
                            ),
                            env=env,
                            cwd=clade.get_storage_path(cc['cwd']),
                            timeout=0.01,
                        )
                else:
                    extra_c_file = {}

                self.abstract_task_desc['extra C files'].append(extra_c_file)

        # Get cross references and everything required for them when all required commands were executed.
        # Limit parallel workers in Clade by 1 since at this stage there may be several parallel task generators and we
        # prefer their parallelism over the Clade one.
        clade_extra = Clade(cmds_file='cmds.txt', conf={'cpu_count': 1})
        clade_extra.parse_list(["CrossRef"])

        # Like in core.job.Job#__upload_original_sources.
        search_dirs = core.utils.get_search_dirs(self.conf['main working directory'], abs_paths=True)
        os.makedirs('additional sources')
        for root, dirs, files in os.walk(clade_extra.storage_dir):
            for file in files:
                file = os.path.join(root, file)

                storage_file = core.utils.make_relative_path([clade_extra.storage_dir], file)

                # Do not treat those source files that were already processed and uploaded as original sources.
                if os.path.commonpath(
                        [os.path.join(os.path.sep, storage_file), clade.storage_dir]) == clade.storage_dir:
                    continue

                new_file = core.utils.make_relative_path(search_dirs, storage_file, absolutize=True)

                # These source files do not belong neither to original sources nor to models, e.g. there are compiler
                # headers.
                if os.path.isabs(new_file):
                    continue

                # We treat all remaining source files which paths do not start with "specifications" as generated
                # models. This is not correct for all cases, e.g. when users put some files within $KLEVER_DATA_DIR.
                if not new_file.startswith('specifications'):
                    new_file = os.path.join('generated models', new_file)

                new_file = os.path.join('additional sources', new_file)
                os.makedirs(os.path.dirname(new_file), exist_ok=True)
                shutil.copy(file, new_file)

                cross_refs = CrossRefs(self.conf, self.logger, clade_extra, os.path.join(os.path.sep, storage_file),
                                       new_file, search_dirs)
                cross_refs.get_cross_refs()

        # For auxiliary files there is no cross references since it is rather hard to get them from Aspectator. But
        # there still highlighting.
        for aux_file in glob.glob('*.aux'):
            new_file = os.path.join('additional sources', 'generated models',
                                    os.path.relpath(aux_file, self.conf['main working directory']))

            os.makedirs(os.path.dirname(new_file), exist_ok=True)
            shutil.copy(aux_file, new_file)

            cross_refs = CrossRefs(self.conf, self.logger, clade_extra, aux_file, new_file, search_dirs)
            cross_refs.get_cross_refs()

        self.abstract_task_desc['additional sources'] = os.path.relpath('additional sources',
                                                                        self.conf['main working directory'])

        # Copy additional sources for total code coverage.
        if self.conf['code coverage details'] == 'All source files':
            with core.utils.Cd('additional sources'):
                for root, dirs, files in os.walk(os.path.curdir):
                    for file in files:
                        file = os.path.join(root, file)
                        new_file = os.path.join(self.conf['additional sources directory'], file)

                        if os.path.isfile(new_file):
                            # TODO: this should never happen, otherwise there should be more explicit warning (note).
                            self.logger.warning('Additional source file "{0}" already exists'.format(file))
                            continue

                        os.makedirs(os.path.dirname(new_file), exist_ok=True)
                        shutil.copy(file, new_file)

        if not self.conf['keep intermediate files']:
            shutil.rmtree('clade')
            os.remove('cmds.txt')

        # These sections won't be refereed any more.
        del (self.abstract_task_desc['grps'])
        del (self.abstract_task_desc['deps'])

    main = weave
