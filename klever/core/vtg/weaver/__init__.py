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
import multiprocessing
import os
import shutil

from clade import Clade

import klever.core.components
import klever.core.utils
import klever.core.vtg.utils
import klever.core.vtg.plugins
from klever.core.cross_refs import CrossRefs


class Weaver(klever.core.vtg.plugins.Plugin):

    def weave(self):
        self.abstract_task_desc.setdefault('extra C files', {})

        search_dirs = klever.core.utils.get_search_dirs(self.conf['main working directory'], abs_paths=True)

        clade_conf = {"log_level": "ERROR"}
        clade = Clade(self.conf['build base'], conf=clade_conf)
        if not clade.work_dir_ok():
            raise RuntimeError('Build base is not OK')
        clade_meta = clade.get_meta()

        env = dict(os.environ)
        # Print stubs instead of inline Assembler since verifiers do not interpret it and even can fail.
        env['LDV_INLINE_ASM_STUB'] = ''
        # Get rid of all type qualifiers that are useless for verification most likely, but breaks generation or/and
        # solution of verification tasks from time to time.
        env['LDV_C_BACKEND_OMIT_TYPE_QUALS'] = "1"

        # It would be better to enable it in the development mode, but there is no any specific marker for it, so let's
        # use keeping intermediate files as an indicator.
        if self.conf['keep intermediate files']:
            env['LDV_PRINT_SIGNATURE_OF_MATCHED_BY_NAME'] = "1"

        # Put all extra CC descriptions into the queue prior to launching parallel workers.
        self.extra_ccs = []
        for grp in self.abstract_task_desc['grps']:
            self.logger.info('Weave in C files of group "%s"', grp['id'])

            for extra_cc in grp['Extra CCs']:
                self.extra_ccs.append((grp['id'], extra_cc))

        extra_cc_indexes_queue = multiprocessing.Queue()
        for i in range(len(self.extra_ccs)):
            extra_cc_indexes_queue.put(i)

        extra_cc_indexes_queue.put(None)

        self.logger.info('Start Weaver pull of workers')

        # Here workers will put their results, namely, paths to extra C files.
        vals = {'extra C files': multiprocessing.Manager().list()}

        # Lock to mutually exclude Weaver workers from each other.
        lock = multiprocessing.Manager().Lock()

        def constructor(extra_cc_index):
            weaver_worker = WeaverWorker(self.conf, self.logger, self.id, self.mqs,
                                         vals,
                                         str(extra_cc_index),
                                         search_dirs,
                                         clade, clade_meta,
                                         env,
                                         self.extra_ccs[extra_cc_index][0],
                                         self.extra_ccs[extra_cc_index][1],
                                         lock)

            return weaver_worker

        workers_num = klever.core.utils.get_parallel_threads_num(self.logger, self.conf, 'Weaving')
        if klever.core.components.launch_queue_workers(self.logger, extra_cc_indexes_queue, constructor, workers_num,
                                                       sleep_interval=0.05):
            raise klever.core.components.ComponentError('Weaver failed')

        self.abstract_task_desc['extra C files'] = list(vals['extra C files'])
        extra_cc_indexes_queue.close()

        # For auxiliary files there is no cross references since it is rather hard to get them from Aspectator. But
        # there still highlighting.
        if self.conf['code coverage details'] == 'All source files':
            for aux_file in glob.glob('*.aux'):
                new_file = os.path.join('additional sources', 'generated models',
                                        os.path.relpath(aux_file, self.conf['main working directory']))

                os.makedirs(os.path.dirname(new_file), exist_ok=True)
                shutil.copy(aux_file, new_file)

                cross_refs = CrossRefs(self.conf, self.logger, clade, aux_file, new_file, search_dirs)
                cross_refs.get_cross_refs()

        self.abstract_task_desc['additional sources'] = os.path.relpath('additional sources',
                                                                        self.conf['main working directory']) \
            if os.path.isdir('additional sources') else None

        # Copy additional sources for total code coverage.
        if self.conf['code coverage details'] != 'Original C source files':
            with klever.core.utils.Cd('additional sources'):
                for root, _, files in os.walk(os.path.curdir):
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
                                # It looks weird but sometimes that file may not exist. Silently ignore that case.
                                try:
                                    os.remove(new_file + '.tmp')
                                except OSError:
                                    pass

                                continue

                            shutil.copy(file, new_file)
                            shutil.copy(file + '.idx.json', new_file + '.idx.json')

                            os.remove(new_file + '.tmp')

        # These sections won't be refereed any more.
        del self.abstract_task_desc['grps']
        del self.abstract_task_desc['deps']

    main = weave


class WeaverWorker(klever.core.components.Component):
    def __init__(self, conf, logger, parent_id, mqs, vals, cur_id,
                 search_dirs, clade, clade_meta, env, grp_id, extra_cc, lock):
        super().__init__(conf, logger, parent_id, mqs, vals, cur_id, include_child_resources=True)

        self.name += cur_id

        self.search_dirs = search_dirs
        self.clade = clade
        self.clade_meta = clade_meta
        self.env = env
        self.grp_id = grp_id
        self.extra_cc = extra_cc
        self.lock = lock

    def process_extra_cc(self):
        # Each CC is either pair (compiler command identifier, compiler command type) or JSON file name
        # with compiler command description.
        if isinstance(self.extra_cc['CC'], list):
            cc = self.clade.get_cmd(*self.extra_cc['CC'], with_opts=True)
            if "in file" in self.extra_cc:
                # This is for CC commands with several input files
                infile = self.extra_cc["in file"]
            else:
                infile = cc["in"][0]

            infile = self.clade.get_storage_path(infile)
            if self.clade_meta['conf'].get('Compiler.preprocess_cmds', False):
                infile = infile('.c')[0] + '.i'
        else:
            with open(os.path.join(self.conf['main working directory'], self.extra_cc['CC']),
                      encoding='utf-8') as fp:
                cc = json.load(fp)

            infile = cc["in"][0]

        # Distinguish input source files having the same names. Here we would like to recreate again the appropriate
        # directory structure as this will result into too long path names. Locking is necessary to have really unique
        # names between different workers that can run in parallel.
        with self.lock:
            outfile_unique = '{0}.i'.format(
                klever.core.utils.unique_file_name(os.path.splitext(os.path.basename(infile))[0], '.i'))
            # Create empty unique output file while the lock is held in order unique_file_name() invoked in concurrent
            # processes will see it and do generate a new unique output file.
            with open(outfile_unique, 'w'):
                pass
        # This is used for storing/getting to/from cache where uniqueness is guaranteed by other means.
        outfile = '{0}.i'.format(os.path.splitext(os.path.basename(infile))[0])
        self.logger.info('Weave in C file "%s"', infile)

        # Produce aspect to be weaved in.
        if 'plugin aspects' in self.extra_cc:
            self.logger.info('Concatenate all aspects of all plugins together')

            # Resulting aspect.
            aspect = '{0}.aspect'.format(os.path.splitext(os.path.basename(outfile_unique))[0])

            # Get all aspects. Place RSG aspects at beginning since they can instrument entities added by
            # aspects of other plugins while corresponding function declarations still need be at beginning
            # of file.
            aspects = []
            for plugin_aspects in self.extra_cc['plugin aspects']:
                if plugin_aspects['plugin'] == 'RSG':
                    aspects[0:0] = plugin_aspects['aspects']
                else:
                    aspects.extend(plugin_aspects['aspects'])

            # Concatenate aspects.
            with open(aspect, 'w', encoding='utf-8') as fout:
                for a in aspects:
                    a = os.path.join(self.conf['main working directory'], a)

                    # Skip empty aspects since they have no sense. BTW, empty aspects for models are forbidden by RSG.
                    if not os.stat(a).st_size:
                        continue

                    with open(a, encoding='utf-8') as fin:
                        last_line = None
                        for line in fin:
                            fout.write(line)
                            last_line = line
                        # Aspects may not terminate with the new line symbol that will cause horrible syntax
                        # errors when parsing the concatenated aspect, e.g. when the last line of some aspect is
                        # a one-line comment "//" that will truncate the first line of the next aspect.
                        if last_line and not last_line.endswith('\n'):
                            fout.write('\n')
        else:
            # Instrumentation is not required when there is no aspects. But we will still pass source files
            # through C-backend to make resulting code to look similarly and thus to avoid different issues
            # at merging source files and models together.
            aspect = None

        if aspect:
            self.logger.info('Aspect to be weaved in is "%s"', aspect)
        else:
            self.logger.info('C file will be passed through C Back-end only')

        opts = cc['opts']
        # Some stuff, e.g. size_t definition, may be architecture dependent.
        opts.append(klever.core.vtg.utils.define_arch_dependent_macro(self.conf))

        # Add options for using models from RGS if so.
        opts.extend(self.extra_cc.get('opts', []))

        cwd = self.clade.get_storage_path(cc['cwd'])

        is_model = self.grp_id == 'models'

        # Original sources should be woven in and we do not need to get cross references for them since this
        # was already done before.
        if not is_model:
            self.__weave(infile, opts, aspect, outfile_unique, cwd, is_model)
        # For generated models we need to weave them in (actually, just pass through C Back-end) and to get
        # cross references always since most likely they all are different.
        elif 'generated' in self.extra_cc:
            self.__weave(infile, opts, aspect, outfile_unique, cwd, is_model)
            if self.conf['code coverage details'] != 'Original C source files':
                self.__get_cross_refs(infile, opts, outfile_unique, cwd)
        # For non-generated models use results cache in addition.
        else:
            cache_name = klever.core.utils.get_file_name_checksum(infile)[:32]

            # Different requirement specifications can bring different sets of aspects and they can affect models when
            # one requests for weaving in them with aspects. Let's distinguish cache directories for different aspects.
            if aspect:
                cache_name += klever.core.utils.get_file_checksum(aspect)[:32]

            cache_dir = os.path.join(self.conf['cache directory'], cache_name)
            with klever.core.utils.LockedOpen(cache_dir + '.tmp', 'w'):
                if os.path.exists(cache_dir):
                    self.logger.info('Get woven in C file from cache')
                    outfile = os.path.join(cache_dir, os.path.basename(outfile))
                    if not os.path.exists(outfile):
                        raise FileExistsError('Cache misses woven in C file (perhaps your models are broken)')
                    self.vals['extra C files'].append(
                        {'C file': os.path.relpath(outfile, self.conf['main working directory'])})
                    if self.conf['code coverage details'] != 'Original C source files':
                        self.logger.info('Get cross references from cache')
                        additional_srcs = os.path.join(cache_dir, 'additional sources')
                        if not os.path.exists(additional_srcs):
                            raise FileExistsError(
                                'Cache misses cross references (perhaps your models are broken)')
                        self.__merge_additional_srcs(os.path.join(cache_dir, 'additional sources'))
                else:
                    os.makedirs(cache_dir)
                    self.__weave(infile, opts, aspect, outfile_unique, cwd, is_model)
                    self.logger.info('Store woven in C file to cache')
                    shutil.copy(outfile_unique, os.path.join(cache_dir, outfile))

                    if self.conf['code coverage details'] != 'Original C source files':
                        self.__get_cross_refs(infile, opts, outfile_unique, cwd)
                        self.logger.info('Store cross references to cache')
                        shutil.copytree(outfile_unique + ' additional sources',
                                        os.path.join(cache_dir, 'additional sources'))

    main = process_extra_cc

    def __weave(self, infile, opts, aspect, outfile, cwd, is_model):
        common_headers = []
        for common_header in self.conf['common headers']:
            common_headers.extend(['-include', common_header])
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
                    '--debug', 'QUIET'
                ] +
                (['--keep'] if self.conf['keep intermediate files'] else []) +
                (['--aspect', os.path.realpath(aspect)] if aspect else ['--stage', 'C-backend']) +
                ['--'] + common_headers +
                klever.core.vtg.utils.prepare_cif_opts(opts, self.clade, is_model) +
                ['-I' + self.clade.get_storage_path(p) for p in self.conf['working source trees']]
            ),
            env=self.env,
            cwd=cwd,
            timeout=0.01,
            filter_func=klever.core.vtg.utils.CIFErrorFilter())

        self.vals['extra C files'].append(
            {'C file': os.path.relpath(outfile, self.conf['main working directory'])})

    def __get_cross_refs(self, infile, opts, outfile, cwd):
        # Get cross references and everything required for them.
        # Limit parallel workers in Clade by 4 since at this stage there may be several parallel task generators and we
        # prefer their parallelism over the Clade default one.
        clade_extra = Clade(work_dir=os.path.realpath(outfile + ' clade'), preset=self.conf['Clade']['preset'],
                            conf={
                                'cpu_count': 4,
                                "log_level": "ERROR",
                                'Info.cif': klever.core.vtg.utils.get_cif_or_aspectator_exec(self.conf, 'cif')
                            })
        # TODO: this can be incorporated into instrumentation above but it will need some Clade changes.
        # Emulate normal compilation (indeed just parsing thanks to "-fsyntax-only") to get additional
        # dependencies (model source files) and information on them.
        clade_extra.intercept(
            [
                klever.core.vtg.utils.get_cif_or_aspectator_exec(self.conf, 'aspectator'),
                '-I' + os.path.join(os.path.dirname(self.conf['specifications base']), 'include')
            ] +
            klever.core.vtg.utils.prepare_cif_opts(opts, self.clade, True) +
            ['-I' + self.clade.get_storage_path(p) for p in self.conf['working source trees']] +
            [
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
        for root, _, files in os.walk(clade_extra.storage_dir):
            for file in files:
                file = os.path.join(root, file)

                storage_file = klever.core.utils.make_relative_path([clade_extra.storage_dir], file)

                # Do not treat those source files that were already processed and uploaded as original sources.
                if os.path.commonpath(
                        [os.path.join(os.path.sep, storage_file), self.clade.storage_dir]) == self.clade.storage_dir:
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

    @staticmethod
    def __merge_additional_srcs(from_dir):
        to_dir = os.path.realpath('additional sources')
        with klever.core.utils.Cd(from_dir):
            for root, _, files in os.walk(os.path.curdir):
                for file in files:
                    file = os.path.join(root, file)
                    dest = os.path.join(to_dir, file)
                    if not os.path.exists(dest):
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        shutil.copy(file, dest)
