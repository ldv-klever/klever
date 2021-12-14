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

import json
import os
import shutil
import re
import multiprocessing

import klever.core.components
import klever.core.utils

coverage_format_version = 1
most_covered_lines_num = 100


def add_to_coverage(merged_coverage_info, coverage_info):
    for file_name, file_coverage_info in coverage_info.items():
        merged_coverage_info.setdefault(file_name, {
            'total functions': coverage_info[file_name]['total functions'],
            'covered lines': dict(),
            'covered functions': dict(),
            'covered function names': list(),
            'notes': dict()
        })

        for kind in ('covered lines', 'covered functions'):
            for line, cov_num in file_coverage_info[kind].items():
                merged_coverage_info[file_name][kind].setdefault(line, 0)
                merged_coverage_info[file_name][kind][line] += cov_num

        for cov_func_name in file_coverage_info['covered function names']:
            if cov_func_name not in merged_coverage_info[file_name]['covered function names']:
                merged_coverage_info[file_name]['covered function names'].append(cov_func_name)

        # TODO: What about multiple notes?
        for line, note in file_coverage_info['notes'].items():
            merged_coverage_info[file_name]['notes'][line] = note


def convert_coverage(merged_coverage_info, coverage_dir, pretty, src_files_info=None, total=False):
    # Convert combined coverage to the required format.
    os.mkdir(coverage_dir)

    # Collect coverage statistics for all individual files during their processing. This statistics will be printed
    # later.
    coverage_stats = {
        'format': coverage_format_version,
        'coverage statistics': dict(),
        'data statistics': dict()
    }

    for file_name, file_coverage_info in merged_coverage_info.items():
        file_coverage = {
            'format': coverage_format_version,
            'line coverage': file_coverage_info['covered lines'],
            'function coverage': file_coverage_info['covered functions'],
            'notes': file_coverage_info['notes']
        }

        os.makedirs(os.path.join(coverage_dir, os.path.dirname(file_name)), exist_ok=True)
        with open(os.path.join(coverage_dir, file_name + '.cov.json'), 'w') as fp:
            klever.core.utils.json_dump(file_coverage, fp, pretty)

        coverage_stats['coverage statistics'][file_name] = [
            # Total number of covered lines of code.
            len([line_number for line_number, line_coverage in file_coverage_info['covered lines'].items()
                 if line_coverage]),
            # Total number of considered lines of code.
            len(file_coverage_info['covered lines']),
            # Total number of covered functions.
            len([func_line_number for func_line_number, func_coverage in file_coverage_info['covered functions'].items()
                 if func_coverage]),
            # Total number of considered functions.
            len(file_coverage_info['covered functions'])
        ]

    # Obtain most covered lines for code coverage of verification tasks.
    if not total:
        file_most_covered_lines = {}
        for file_name, file_coverage_info in merged_coverage_info.items():
            sorted_covered_lines = sorted(file_coverage_info['covered lines'].items(), key=lambda kv: kv[1], reverse=True)

            # It is enough to remember not more than the total number of most covered lines per each file.
            for i in range(most_covered_lines_num):
                if i == len(sorted_covered_lines):
                    break

                file_most_covered_lines["{0}:{1}".format(file_name, sorted_covered_lines[i][0])] = sorted_covered_lines[i][1]

        sorted_file_most_covered_lines = sorted(file_most_covered_lines.items(), key=lambda kv: kv[1], reverse=True)

        if sorted_file_most_covered_lines:
            coverage_stats['most covered lines'] = []
            for i in range(most_covered_lines_num):
                if i == len(sorted_file_most_covered_lines):
                    break
                coverage_stats['most covered lines'].append(sorted_file_most_covered_lines[i][0])

    if src_files_info:
        # Remove data for covered source files. It is out of interest, but we did not know these files earlier.
        for file_name in coverage_stats['coverage statistics']:
            if file_name in src_files_info:
                del src_files_info[file_name]

        for file_name, info in src_files_info.items():
            # TODO: it would be better to make this depending on code coverage completeness. But for this here we will need to know completeness and source directories in addition.
            if not file_name.endswith('.c'):
                continue

            # Add the total number of lines and functions for uncovered source files.
            coverage_stats['coverage statistics'][file_name] = [
                info[0],
                len(info[1])
            ]

            # Add places where uncovered functions are defined.
            file_coverage = {
                'format': coverage_format_version,
                'function coverage': {str(line): 0 for line in info[1]}
            }

            os.makedirs(os.path.join(coverage_dir, os.path.dirname(file_name)), exist_ok=True)
            with open(os.path.join(coverage_dir, file_name + '.cov.json'), 'w') as fp:
                klever.core.utils.json_dump(file_coverage, fp, pretty)

    with open(os.path.join(coverage_dir, 'coverage.json'), 'w') as fp:
        klever.core.utils.json_dump(coverage_stats, fp, pretty)


class JCR(klever.core.components.Component):

    COVERAGE_FILE_NAME = "cached coverage.json"

    def __init__(self, conf, logger, parent_id, callbacks, mqs, vals, id=None, work_dir=None, attrs=None,
                 separate_from_parent=True, include_child_resources=False, queues_to_terminate=None):
        super(JCR, self).__init__(conf, logger, parent_id, callbacks, mqs, vals, id, work_dir,
                                  attrs, separate_from_parent, include_child_resources)

        # This function adds callbacks and it should work until we call it in the new process
        self.mqs['req spec ids and coverage info files'] = multiprocessing.Queue()
        queues_to_terminate.append('req spec ids and coverage info files')
        self.coverage = dict()

    def collect_total_coverage(self):
        self.logger.debug("Begin collecting coverage")

        total_coverage_infos = dict()
        arcfiles = {}
        os.mkdir('total coverages')
        counters = dict()
        try:
            while True:
                coverage_info = self.mqs['req spec ids and coverage info files'].get()

                if coverage_info is None:
                    self.logger.debug(
                        'Requirement specification identifiers and coverage info files message queue was terminated')
                    self.mqs['req spec ids and coverage info files'].close()
                    break

                sub_job_id = coverage_info['sub-job identifier']
                self.logger.debug('Get coverage for sub-job {!r}'.format(sub_job_id))

                if 'coverage info file' in coverage_info:
                    if sub_job_id not in total_coverage_infos:
                        total_coverage_infos[sub_job_id] = dict()
                        arcfiles[sub_job_id] = dict()
                    req_spec_id = coverage_info['req spec id']
                    total_coverage_infos[sub_job_id].setdefault(req_spec_id, {})
                    arcfiles[sub_job_id].setdefault(req_spec_id, {})

                    if os.path.isfile(coverage_info['coverage info file']):
                        with open(coverage_info['coverage info file'], encoding='utf-8') as fp:
                            loaded_coverage_info = json.load(fp)

                        # Clean if needed
                        if not self.conf['keep intermediate files']:
                            os.remove(os.path.join(self.conf['main working directory'],
                                                   coverage_info['coverage info file']))

                        add_to_coverage(total_coverage_infos[sub_job_id][req_spec_id], loaded_coverage_info)
                        for file, file_coverage_info in loaded_coverage_info.items():
                            arcfiles[sub_job_id][req_spec_id][file_coverage_info['original source file name']] = file
                        del loaded_coverage_info

                        counters.setdefault(sub_job_id, dict())
                        counters[sub_job_id].setdefault(req_spec_id, 0)
                        counters[sub_job_id][req_spec_id] += 1
                        if counters[sub_job_id][req_spec_id] >= 10:
                            self.__read_data(total_coverage_infos, sub_job_id, req_spec_id)
                            self.__save_data(total_coverage_infos, sub_job_id, req_spec_id)
                            self.__clean_data(total_coverage_infos, sub_job_id, req_spec_id)
                            counters[sub_job_id][req_spec_id] = 0
                    else:
                        self.logger.warning("There is no coverage file {!r}".
                                            format(coverage_info['coverage info file']))
                elif sub_job_id in total_coverage_infos:
                    self.logger.debug('Calculate total coverage for job {!r}'.format(sub_job_id))

                    total_coverages = dict()
                    total_coverage_dirs = []

                    # This is ugly. But this should disappear after implementing TODO at klever.core.job.start_jobs.
                    sub_job_dir = sub_job_id.lower()

                    for req_spec_id in counters[sub_job_id]:
                        self.__read_data(total_coverage_infos, sub_job_id, req_spec_id)
                        coverage_info = total_coverage_infos[sub_job_id][req_spec_id]
                        total_coverage_dir = os.path.join(self.__get_total_cov_dir(sub_job_id, req_spec_id), 'report')

                        with open(os.path.join(sub_job_dir, 'original sources basic information.json')) as fp:
                            src_files_info = json.load(fp)

                        convert_coverage(coverage_info, total_coverage_dir, self.conf['keep intermediate files'],
                                         src_files_info, total=True)
                        total_coverage_dirs.append(total_coverage_dir)

                        total_coverages[req_spec_id] = klever.core.utils.ArchiveFiles([total_coverage_dir])
                        self.__save_data(total_coverage_infos, sub_job_id, req_spec_id)
                        self.__clean_data(total_coverage_infos, sub_job_id, req_spec_id)

                    # This isn't great to build component identifier in such the artificial way.
                    # But otherwise we need to pass it everywhere like "sub-job identifier".
                    report_id = os.path.join(os.path.sep, sub_job_id)

                    if self.conf['code coverage details'] != 'Original C source files':
                        klever.core.utils.report(
                            self.logger,
                            'patch',
                            {
                                'identifier': report_id,
                                'additional_sources': klever.core.utils.ArchiveFiles(
                                    [os.path.join(sub_job_dir, 'additional sources')]),
                            },
                            self.mqs['report files'],
                            self.vals['report id'],
                            self.conf['main working directory'],
                            os.path.join('total coverages', sub_job_id)
                        )

                    klever.core.utils.report(
                        self.logger,
                        'coverage',
                        {
                            'identifier': report_id,
                            'coverage': total_coverages,
                        },
                        self.mqs['report files'],
                        self.vals['report id'],
                        self.conf['main working directory'],
                        os.path.join('total coverages', sub_job_id)
                    )

                    del total_coverage_infos[sub_job_id]

                    if not self.conf['keep intermediate files']:
                        for total_coverage_dir in total_coverage_dirs:
                            shutil.rmtree(total_coverage_dir, ignore_errors=True)

                    self.vals['coverage_finished'][sub_job_id] = True
        finally:
            self.logger.debug("Allow finish all jobs")
            for sub_job_id in self.vals['coverage_finished'].keys():
                self.vals['coverage_finished'][sub_job_id] = True

        self.logger.info("Finish coverage reporting")

        # Clean
        if not self.conf['keep intermediate files']:
            shutil.rmtree('total coverages')

    main = collect_total_coverage

    def __get_total_cov_dir(self, sub_job_id, requirement):
        total_coverage_dir = os.path.join('total coverages', sub_job_id, re.sub(r'/', '-', requirement))

        if not os.path.exists(total_coverage_dir):
            os.makedirs(total_coverage_dir)

        return total_coverage_dir

    def __read_data(self, cache, sub_job_id, requirement):
        file_name = os.path.join(self.__get_total_cov_dir(sub_job_id, requirement), self.COVERAGE_FILE_NAME)

        if os.path.isfile(file_name):
            with open(file_name, 'r', encoding='utf-8') as fp:
                large_cache = json.load(fp)
        else:
            large_cache = dict()

        cache.setdefault(sub_job_id, dict())
        cache[sub_job_id].setdefault(requirement, dict())

        for file_name in large_cache:
            # todo: This code is close to function add_to_coverage
            cache[sub_job_id][requirement].setdefault(file_name, {
                'total functions': large_cache[file_name]['total functions'],
                'covered lines': {},
                'covered functions': {},
                'covered function names': list(),
                'notes': {}
            })

            for path in ('covered lines', 'covered functions'):
                for line, value in large_cache[file_name][path].items():
                    cache[sub_job_id][requirement][file_name][path].setdefault(line, 0)
                    cache[sub_job_id][requirement][file_name][path][line] += value
            if large_cache[file_name].get('covered function names'):
                for name in large_cache[file_name]['covered function names']:
                    if name not in cache[sub_job_id][requirement][file_name]['covered function names']:
                        cache[sub_job_id][requirement][file_name]['covered function names'].append(name)

    def __save_data(self, cache, sub_job_id, requirement):
        file_name = os.path.join(self.__get_total_cov_dir(sub_job_id, requirement), self.COVERAGE_FILE_NAME)
        cache.setdefault(sub_job_id, dict())
        cache[sub_job_id].setdefault(requirement, dict())
        with open(file_name, 'w', encoding='utf-8') as fp:
            json.dump(cache[sub_job_id][requirement], fp)

    def __clean_data(self, cache, job_id, requirement):
        cache[job_id].pop(requirement, None)


class LCOV:
    FILENAME_PREFIX = "SF:"
    FUNCTION_NAME_PREFIX = "FN:"
    FUNCTION_NAME_END_PREFIX = "#FN:"
    FUNCTION_PREFIX = "FNDA:"
    LINE_PREFIX = "DA:"
    ADD_PREFIX = "ADD:"
    TIMERS_PREFIX = "TIMERS:"
    EOR_PREFIX = "end_of_record"

    def __init__(self, conf, logger, coverage_file, clade, source_dirs, search_dirs, main_work_dir, coverage_details,
                 coverage_id, coverage_info_dir, verification_task_files):
        # Public
        self.conf = conf
        self.logger = logger
        self.coverage_file = coverage_file
        self.clade = clade
        self.source_dirs = [os.path.normpath(p) for p in source_dirs]
        self.search_dirs = [os.path.normpath(p) for p in search_dirs]
        self.main_work_dir = main_work_dir
        self.coverage_details = coverage_details
        self.coverage_info_dir = coverage_info_dir
        self.verification_task_files = verification_task_files
        self.arcnames = {}

        # Sanity checks
        if self.coverage_details not in ('All source files', 'C source files including models',
                                         'Original C source files'):
            raise NotImplementedError("Code coverage details {!r} are not supported".format(self.coverage_details))

        # Import coverage
        try:
            self.coverage_info = self.parse()

            with open(coverage_id, 'w', encoding='utf-8') as fp:
                klever.core.utils.json_dump(self.coverage_info, fp, self.conf['keep intermediate files'])

            coverage = {}
            add_to_coverage(coverage, self.coverage_info)
            convert_coverage(coverage, 'coverage', self.conf['keep intermediate files'])
        except Exception:
            shutil.rmtree('coverage', ignore_errors=True)
            raise

    def parse(self):
        if not os.path.isfile(self.coverage_file):
            raise Exception('There is no coverage file {0}'.format(self.coverage_file))

        # Parse coverage file.
        coverage_info = {}
        line_map = {}
        func_map = {}
        func_reverse_map = {}

        def init_file_coverage_info(file):
            if file not in coverage_info:
                coverage_info[file] = {
                    'covered lines': {},
                    'covered functions': {},
                    'covered function names': [],
                    'total functions': len(func_reverse_map[file]) if file in func_reverse_map else 0,
                    'notes': {}
                }

        with open(self.coverage_file, encoding='utf-8') as fp:
            # TODO: verification tasks consisting of several source files are not supported.
            # Get actual CIL source file name.
            cil_src_file_name = None
            for line in fp:
                line = line.rstrip('\n')
                if line.startswith(self.FILENAME_PREFIX):
                    cil_src_file_name = line[len(self.FILENAME_PREFIX):]
                    cil_src_file_name = os.path.basename(os.path.normpath(cil_src_file_name))
                    cil_src_file_name = self.verification_task_files[cil_src_file_name]
                    break

            # Build C source files line map.
            with open(cil_src_file_name) as cil_fp:
                line_num = 1
                orig_file = None
                orig_file_line_num = 0
                line_preprocessor_directive = re.compile(r'\s*#line\s+(\d+)\s*(.*)')
                for line in cil_fp:
                    m = line_preprocessor_directive.match(line)
                    if m:
                        orig_file_line_num = int(m.group(1))
                        if m.group(2):
                            orig_file = m.group(2)[1:-1]
                    else:
                        line_map[line_num] = (orig_file, orig_file_line_num)
                        orig_file_line_num += 1
                    line_num += 1

            add = None
            timers = None
            for line in fp:
                line = line.rstrip('\n')
                # Build C functions map.
                if line.startswith(self.FUNCTION_NAME_PREFIX):
                    splts = line[len(self.FUNCTION_NAME_PREFIX):].split(',')
                    cil_src_line = int(splts[0])
                    func_name = splts[1]

                    orig_file, orig_line = line_map[cil_src_line]
                    func_map[func_name] = orig_file, orig_line
                    if orig_file not in func_reverse_map:
                        func_reverse_map[orig_file] = {}
                    func_reverse_map[orig_file][orig_line] = func_name
                elif line.startswith(self.FUNCTION_NAME_END_PREFIX):
                    pass
                # Get function coverage.
                elif line.startswith(self.FUNCTION_PREFIX):
                    splts = line[len(self.FUNCTION_PREFIX):].split(',')
                    cov_num = int(splts[0])
                    func_name = splts[1]

                    orig_file, orig_line = func_map[func_name]
                    init_file_coverage_info(orig_file)
                    coverage_info[orig_file]['covered functions'][orig_line] = cov_num
                    coverage_info[orig_file]['covered function names'].append(func_name)
                # Get line coverage.
                elif line.startswith(self.LINE_PREFIX):
                    splts = line[len(self.LINE_PREFIX):].split(',')
                    cil_src_line = int(splts[0])
                    cov_num = int(splts[1])

                    # TODO: Coverage can contain invalid references. Let's deal with this one day!
                    if cil_src_line not in line_map:
                        continue

                    orig_file, orig_line = line_map[cil_src_line]
                    init_file_coverage_info(orig_file)
                    coverage_info[orig_file]['covered lines'][orig_line] = cov_num

                    if add and timers:
                        coverage_info[orig_file]['notes'][orig_line] = {'kind': 'Multiple notes',
                                                                        'text': timers + '. ' + add}
                        add = None
                        timers = None
                    elif add:
                        coverage_info[orig_file]['notes'][orig_line] = {'kind': 'Verifier assumption', 'text': add}
                        add = None
                    elif timers:
                        coverage_info[orig_file]['notes'][orig_line] = {'kind': 'Verifier operation statistics', 'text': timers}
                        timers = None
                # Remember data to be associated with the next line.
                elif line.startswith(self.ADD_PREFIX):
                    add = line[len(self.ADD_PREFIX):]
                elif line.startswith(self.TIMERS_PREFIX):
                    timers = line[len(self.TIMERS_PREFIX):]
                # Finalize raw code coverage processing.
                elif line.startswith(self.EOR_PREFIX):
                    break
                else:
                    # We should not pass here but who knows.
                    raise NotImplementedError(line)

            # Add not covered functions.
            for orig_file, orig_line in func_map.values():
                init_file_coverage_info(orig_file)
                if orig_line not in coverage_info[orig_file]['covered functions']:
                    coverage_info[orig_file]['covered functions'][orig_line] = 0

            # Shrink source file names.
            new_coverage_info = {}
            for orig_file, file_coverage_info in coverage_info.items():
                # Like in klever.core.vrp.RP#__trim_file_names.
                storage_file = klever.core.utils.make_relative_path([self.clade.storage_dir],
                                                                    os.path.normpath(orig_file))
                shrank_src_file_name = storage_file
                tmp = klever.core.utils.make_relative_path(self.source_dirs, storage_file, absolutize=True)

                if tmp != os.path.join(os.path.sep, storage_file):
                    shrank_src_file_name = os.path.join('source files', tmp)
                else:
                    tmp = klever.core.utils.make_relative_path(self.search_dirs, storage_file, absolutize=True)
                    if tmp != os.path.join(os.path.sep, storage_file):
                        if tmp.startswith('specifications'):
                            shrank_src_file_name = tmp
                        else:
                            shrank_src_file_name = os.path.join('generated models', tmp)

                file_coverage_info.update({'original source file name': orig_file})
                new_coverage_info[shrank_src_file_name] = file_coverage_info

            # Filter out unnecessary source files.
            src_files_to_remove = []
            if self.coverage_details in ('C source files including models', 'Original C source files'):
                for file_name, file_coverage_info in new_coverage_info.items():
                    if not file_name.endswith('.c') or \
                            (self.coverage_details == 'Original C source files' and
                             not file_name.startswith('source files')):
                        src_files_to_remove.append(file_name)

            for src_file_to_remove in src_files_to_remove:
                del new_coverage_info[src_file_to_remove]

        if not new_coverage_info:
            self.logger.warning(
                "Resulting code coverage is empty, perhaps, produced code coverage or its parsing is wrong")

        return new_coverage_info
