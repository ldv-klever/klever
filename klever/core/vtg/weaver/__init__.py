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

import glob
import json
import os
import shutil

from clade import Clade

import klever.core.utils
import klever.core.vtg.utils
import klever.core.vtg.plugins
from klever.core.cross_refs import CrossRefs


class Weaver(klever.core.vtg.plugins.Plugin):

    def __init__(self, conf, logger, parent_id, callbacks, mqs, vals, id=None, work_dir=None, attrs=None,
                 separate_from_parent=False, include_child_resources=False):
        super(Weaver, self).__init__(conf, logger, parent_id, callbacks, mqs, vals, id, work_dir, attrs,
                                     separate_from_parent, include_child_resources)
        self.search_dirs = klever.core.utils.get_search_dirs(self.conf['main working directory'], abs_paths=True)

    def weave(self):
        self.abstract_task_desc.setdefault('extra C files', dict())

        clade = Clade(self.conf['build base'])
        if not clade.work_dir_ok():
            raise RuntimeError('Build base is not OK')
        meta = clade.get_meta()

        # This is required to get compiler (Aspectator) specific stdarg.h since kernel C files are compiled
        # with "-nostdinc" option and system stdarg.h couldn't be used.
        aspectator_search_dir = '-isystem' + klever.core.utils.execute(
            self.logger, (klever.core.vtg.utils.get_cif_or_aspectator_exec(self.conf, 'aspectator'),
                          '-print-file-name=include'), collect_all_stdout=True)[0]

        env = dict(os.environ)
        # Print stubs instead of inline Assembler since verifiers do not interpret it and even can fail.
        env['LDV_INLINE_ASM_STUB'] = ''

        for grp in self.abstract_task_desc['grps']:
            self.logger.info('Weave in C files of group "{0}"'.format(grp['id']))

            for extra_cc in grp['Extra CCs']:
                # Each CC is either pair (compiler command identifier, compiler command type) or JSON file name
                # with compiler command description.
                if isinstance(extra_cc['CC'], list):
                    cc = clade.get_cmd(*extra_cc['CC'], with_opts=True)
                    if "in file" in extra_cc:
                        # This is for CC commands with several input files
                        infile = extra_cc["in file"]
                    else:
                        infile = cc["in"][0]

                    infile = clade.get_storage_path(infile)
                    if meta['conf'].get('Compiler.preprocess_cmds', False):
                        infile = infile('.c')[0] + '.i'
                else:
                    with open(os.path.join(self.conf['main working directory'], extra_cc['CC']),
                              encoding='utf8') as fp:
                        cc = json.load(fp)

                    infile = cc["in"][0]

                # Distinguish source files having the same names.
                outfile_unique = '{0}.i'.format(
                    klever.core.utils.unique_file_name(os.path.splitext(os.path.basename(infile))[0], '.i'))
                # This is used for storing/getting to/from cache where uniqueness is guaranteed by other means.
                outfile = '{0}.i'.format(os.path.splitext(os.path.basename(infile))[0])
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
                    with open(aspect, 'w', encoding='utf8') as fout:
                        for a in aspects:
                            with open(os.path.join(self.conf['main working directory'], a), encoding='utf8') as fin:
                                for line in fin:
                                    fout.write(line)
                                # Aspects may not terminate with the new line symbol that will cause horrible syntax
                                # errors when parsing the concatenated aspect, e.g. when the last line of some aspect is
                                # a one-line comment "//" that will truncate the first line of the next aspect.
                                if not line.endswith('\n'):
                                    fout.write('\n')
                else:
                    # Instrumentation is not required when there is no aspects. But we will still pass source files
                    # through C-backend to make resulting code to look similarly and thus to avoid different issues
                    # at merging source files and models together.
                    aspect = None

                if aspect:
                    self.logger.info('Aspect to be weaved in is "{0}"'.format(aspect))
                else:
                    self.logger.info('C file will be passed through C Back-end only')

                cwd = clade.get_storage_path(cc['cwd'])

                is_model = (grp['id'] == 'models')

                # Original sources should be woven in and we do not need to get cross references for them since this
                # was already done before.
                if not is_model:
                    self.__weave(infile, cc['opts'], aspect, outfile_unique, clade, env, cwd,
                                 aspectator_search_dir, is_model)
                # For generated models we need to weave them in (actually, just pass through C Back-end) and to get
                # cross references always since most likely they all are different.
                elif 'generated' in extra_cc:
                    self.__weave(infile, cc['opts'], aspect, outfile_unique, clade, env, cwd,
                                 aspectator_search_dir, is_model)
                    if self.conf['code coverage details'] != 'Original C source files':
                        self.__get_cross_refs(infile, cc['opts'], outfile_unique, clade, cwd,
                                              aspectator_search_dir)
                # For non-generated models use results cache in addition.
                else:
                    cache_dir = os.path.join(self.conf['cache directory'],
                                             klever.core.utils.get_file_name_checksum(infile))
                    with klever.core.utils.LockedOpen(cache_dir + '.tmp', 'w'):
                        if os.path.exists(cache_dir):
                            self.logger.info('Get woven in C file from cache')
                            self.abstract_task_desc['extra C files'].append(
                                {'C file': os.path.relpath(os.path.join(cache_dir, os.path.basename(outfile)),
                                                           self.conf['main working directory'])})
                            if self.conf['code coverage details'] != 'Original C source files':
                                self.logger.info('Get cross references from cache')
                                self.__merge_additional_srcs(os.path.join(cache_dir, 'additional sources'))
                        else:
                            os.makedirs(cache_dir)
                            self.__weave(infile, cc['opts'], aspect, outfile_unique, clade, env, cwd,
                                         aspectator_search_dir, is_model)
                            self.logger.info('Store woven in C file to cache')
                            shutil.copy(outfile_unique, os.path.join(cache_dir, outfile))

                            if self.conf['code coverage details'] != 'Original C source files':
                                self.__get_cross_refs(infile, cc['opts'], outfile_unique, clade, cwd,
                                                      aspectator_search_dir)
                                self.logger.info('Store cross references to cache')
                                shutil.copytree(outfile_unique + ' additional sources',
                                                os.path.join(cache_dir, 'additional sources'))

        # For auxiliary files there is no cross references since it is rather hard to get them from Aspectator. But
        # there still highlighting.
        if self.conf['code coverage details'] == 'All source files':
            for aux_file in glob.glob('*.aux'):
                new_file = os.path.join('additional sources', 'generated models',
                                        os.path.relpath(aux_file, self.conf['main working directory']))

                os.makedirs(os.path.dirname(new_file), exist_ok=True)
                shutil.copy(aux_file, new_file)

                cross_refs = CrossRefs(self.conf, self.logger, clade, aux_file, new_file, self.search_dirs)
                cross_refs.get_cross_refs()

        self.abstract_task_desc['additional sources'] = os.path.relpath('additional sources',
                                                                        self.conf['main working directory']) \
            if os.path.isdir('additional sources') else None

        # Copy additional sources for total code coverage.
        if self.conf['code coverage details'] != 'Original C source files':
            with klever.core.utils.Cd('additional sources'):
                for root, dirs, files in os.walk(os.path.curdir):
                    for file in files:
                        # These files are handled below in addition to corresponding source files.
                        if file.endswith('.json'):
                            continue

                        if self.conf['code coverage details'] == 'C source files including models' \
                                and not file.endswith('.c'):
                            continue

                        file = os.path.join(root, file)
                        new_file = os.path.join(self.conf['additional sources directory'], file)
                        os.makedirs(os.path.dirname(new_file), exist_ok=True)

                        with klever.core.utils.LockedOpen(new_file + '.tmp', 'w'):
                            if os.path.isfile(new_file):
                                os.remove(new_file + '.tmp')
                                continue

                            shutil.copy(file, new_file)
                            shutil.copy(file + '.idx.json', new_file + '.idx.json')

                            os.remove(new_file + '.tmp')

        # These sections won't be refereed any more.
        del (self.abstract_task_desc['grps'])
        del (self.abstract_task_desc['deps'])

    def __weave(self, infile, opts, aspect, outfile, clade, env, cwd, aspectator_search_dir, is_model):
        klever.core.utils.execute(
            self.logger,
            tuple(
                [
                    klever.core.vtg.utils.get_cif_or_aspectator_exec(self.conf, 'cif'),
                    '--in', infile,
                    # Besides header files specific for requirements specifications will be searched for.
                    '--general-opts',
                    '-I' + os.path.join(os.path.dirname(self.conf['specifications base']), 'include'),
                    '--aspect-preprocessing-opts', ' '.join(self.conf['aspect preprocessing options'])
                    if 'aspect preprocessing options' in self.conf else '',
                    '--out', os.path.realpath(outfile),
                    '--back-end', 'src',
                    '--debug', 'DEBUG'
                ] +
                (['--keep'] if self.conf['keep intermediate files'] else []) +
                (['--aspect', os.path.realpath(aspect)] if aspect else ['--stage', 'C-backend']) +
                ['--', '-include', 'ldv/common/inline_asm.h'] +
                klever.core.vtg.utils.prepare_cif_opts(opts, clade, is_model) +
                [aspectator_search_dir] +
                ['-I' + clade.get_storage_path(p) for p in self.conf['working source trees']]
            ),
            env=env,
            cwd=cwd,
            timeout=0.01,
            filter_func=klever.core.vtg.utils.CIFErrorFilter())

        self.abstract_task_desc['extra C files'].append(
            {'C file': os.path.relpath(outfile, self.conf['main working directory'])})

    def __get_cross_refs(self, infile, opts, outfile, clade, cwd, aspectator_search_dir):
        # Get cross references and everything required for them.
        # Limit parallel workers in Clade by 4 since at this stage there may be several parallel task generators and we
        # prefer their parallelism over the Clade default one.
        clade_extra = Clade(work_dir=os.path.realpath(outfile + ' clade'), preset=self.conf['Clade']['preset'],
                            conf={'cpu_count': 4})
        # TODO: this can be incorporated into instrumentation above but it will need some Clade changes.
        # Emulate normal compilation (indeed just parsing thanks to "-fsyntax-only") to get additional
        # dependencies (model source files) and information on them.
        clade_extra.intercept(
            [
                klever.core.vtg.utils.get_cif_or_aspectator_exec(self.conf, 'aspectator'),
                '-I' + os.path.join(os.path.dirname(self.conf['specifications base']), 'include')
            ] + klever.core.vtg.utils.prepare_cif_opts(opts, clade, True) +
            [
                aspectator_search_dir,
                '-fsyntax-only',
                infile
            ],
            cwd=cwd
        )
        clade_extra.parse_list(["CrossRef"])

        if not clade_extra.work_dir_ok():
            raise RuntimeError('Build base is not OK')

        # Like in klever.core.job.Job#__upload_original_sources.
        os.makedirs(outfile + ' additional sources')
        for root, dirs, files in os.walk(clade_extra.storage_dir):
            for file in files:
                file = os.path.join(root, file)

                storage_file = klever.core.utils.make_relative_path([clade_extra.storage_dir], file)

                # Do not treat those source files that were already processed and uploaded as original sources.
                if os.path.commonpath(
                        [os.path.join(os.path.sep, storage_file), clade.storage_dir]) == clade.storage_dir:
                    continue

                new_file = klever.core.utils.make_relative_path(self.search_dirs, storage_file, absolutize=True)

                # These source files do not belong neither to original sources nor to models, e.g. there are compiler
                # headers.
                if os.path.isabs(new_file):
                    continue

                # We treat all remaining source files which paths do not start with "specifications" as generated
                # models. This is not correct for all cases, e.g. when users put some files within $KLEVER_DATA_DIR.
                if not new_file.startswith('specifications'):
                    new_file = os.path.join('generated models', new_file)

                new_file = os.path.join(outfile + ' additional sources', new_file)
                os.makedirs(os.path.dirname(new_file), exist_ok=True)
                shutil.copy(file, new_file)

                cross_refs = CrossRefs(self.conf, self.logger, clade_extra, os.path.join(os.path.sep, storage_file),
                                       new_file, self.search_dirs)
                cross_refs.get_cross_refs()

        self.__merge_additional_srcs(outfile + ' additional sources')

        if not self.conf['keep intermediate files']:
            shutil.rmtree(outfile + ' clade')

    def __merge_additional_srcs(self, from_dir):
        to_dir = os.path.realpath('additional sources')
        with klever.core.utils.Cd(from_dir):
            for root, dirs, files in os.walk(os.path.curdir):
                for file in files:
                    file = os.path.join(root, file)
                    dest = os.path.join(to_dir, file)
                    if not os.path.exists(dest):
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        shutil.copy(file, dest)

    main = weave
