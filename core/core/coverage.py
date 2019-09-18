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
import shutil
import re
import multiprocessing

import core.components
import core.utils

coverage_format_version = 1


def add_to_coverage(merged_coverage_info, coverage_info):
    for file_name in coverage_info:
        merged_coverage_info.setdefault(file_name, {
            'total functions': coverage_info[file_name][0]['total functions'],
            'covered lines': dict(),
            'covered functions': dict(),
            'covered function names': list()
        })

        for coverage in coverage_info[file_name]:
            for path in ('covered lines', 'covered functions'):
                for line, value in coverage[path].items():
                    merged_coverage_info[file_name][path].setdefault(line, 0)
                    merged_coverage_info[file_name][path][line] += value
            if coverage.get('covered function names'):
                for name in coverage['covered function names']:
                    if name not in merged_coverage_info[file_name]['covered function names']:
                        merged_coverage_info[file_name]['covered function names'].append(name)


def convert_coverage(merged_coverage_info, coverage_dir='coverage'):
    # Convert combined coverage to the required format.
    os.mkdir(coverage_dir)

    # Collect coverage statistics for all individual files during their processing. This statistics will be printed
    # later.
    coverage_stats = {
        'format': coverage_format_version,
        'coverage statistics': dict(),
        'data statistics': dict()
    }
    for file_name in list(merged_coverage_info.keys()):
        raw_file_coverage = merged_coverage_info[file_name]

        file_coverage = {
            'format': coverage_format_version,
            'line coverage': raw_file_coverage['covered lines'],
            'function coverage': raw_file_coverage['covered functions']
        }

        os.makedirs(os.path.join(coverage_dir, os.path.dirname(file_name)), exist_ok=True)
        with open(os.path.join(coverage_dir, file_name + '.cov.json'), 'w') as fp:
            json.dump(file_coverage, fp, ensure_ascii=True, sort_keys=True, indent=4)

        coverage_stats['coverage statistics'][file_name] = [
            # Total number of covered lines of code.
            len([line_number for line_number, line_coverage in raw_file_coverage['covered lines'].items()
                 if line_coverage]),
            # Total number of considered lines of code.
            len(raw_file_coverage['covered lines']),
            # Total number of covered functions.
            len([func_line_number for func_line_number, func_coverage in raw_file_coverage['covered functions'].items()
                 if func_coverage]),
            # Total number of considered functions.
            len(raw_file_coverage['covered functions'])
        ]

    with open(os.path.join(coverage_dir, 'coverage.json'), 'w') as fp:
        json.dump(coverage_stats, fp, ensure_ascii=True, sort_keys=True, indent=4)


class JCR(core.components.Component):

    COVERAGE_FILE_NAME = "cached coverage.json"

    def __init__(self, conf, logger, parent_id, callbacks, mqs, vals, id=None, work_dir=None, attrs=None,
                 separate_from_parent=True, include_child_resources=False, queues_to_terminate=None):
        super(JCR, self).__init__(conf, logger, parent_id, callbacks, mqs, vals, id, work_dir,
                                  attrs, separate_from_parent, include_child_resources)

        # This function adds callbacks and it should work until we call it in the new process
        self.mqs['requirements and coverage info files'] = multiprocessing.Queue()
        queues_to_terminate.append('requirements and coverage info files')
        self.coverage = dict()

    def collect_total_coverage(self):
        self.logger.debug("Begin collecting coverage")

        total_coverage_infos = dict()
        arcfiles = {}
        os.mkdir('total coverages')
        counters = dict()
        try:
            while True:
                coverage_info = self.mqs['requirements and coverage info files'].get()

                if coverage_info is None:
                    self.logger.debug('Requirement coverage info files message queue was terminated')
                    self.mqs['requirements and coverage info files'].close()
                    break

                sub_job_id = coverage_info['sub-job identifier']
                self.logger.debug('Get coverage for sub-job {!r}'.format(sub_job_id))

                if 'coverage info file' in coverage_info:
                    if sub_job_id not in total_coverage_infos:
                        total_coverage_infos[sub_job_id] = dict()
                        arcfiles[sub_job_id] = dict()
                    requirement = coverage_info['requirement']
                    total_coverage_infos[sub_job_id].setdefault(requirement, {})
                    arcfiles[sub_job_id].setdefault(requirement, {})

                    if os.path.isfile(coverage_info['coverage info file']):
                        with open(coverage_info['coverage info file'], encoding='utf8') as fp:
                            loaded_coverage_info = json.load(fp)

                        # Clean if needed
                        if not self.conf['keep intermediate files']:
                            os.remove(os.path.join(self.conf['main working directory'],
                                                   coverage_info['coverage info file']))

                        add_to_coverage(total_coverage_infos[sub_job_id][requirement], loaded_coverage_info)
                        for file in loaded_coverage_info.values():
                            arcfiles[sub_job_id][requirement][file[0]['file name']] = file[0]['arcname']
                        del loaded_coverage_info

                        counters.setdefault(sub_job_id, dict())
                        counters[sub_job_id].setdefault(requirement, 0)
                        counters[sub_job_id][requirement] += 1
                        if counters[sub_job_id][requirement] >= 10:
                            self.__read_data(total_coverage_infos, sub_job_id, requirement)
                            self.__save_data(total_coverage_infos, sub_job_id, requirement)
                            self.__clean_data(total_coverage_infos, sub_job_id, requirement)
                            counters[sub_job_id][requirement] = 0
                    else:
                        self.logger.warning("There is no coverage file {!r}".
                                            format(coverage_info['coverage info file']))
                elif sub_job_id in total_coverage_infos:
                    self.logger.debug('Calculate total coverage for job {!r}'.format(sub_job_id))

                    total_coverages = dict()
                    total_coverage_dirs = []

                    for requirement in counters[sub_job_id]:
                        self.__read_data(total_coverage_infos, sub_job_id, requirement)
                        coverage_info = total_coverage_infos[sub_job_id][requirement]
                        total_coverage_dir = os.path.join(self.__get_total_cov_dir(sub_job_id, requirement), 'report')
                        convert_coverage(coverage_info, total_coverage_dir)
                        total_coverage_dirs.append(total_coverage_dir)
                        total_coverages[requirement] = core.utils.ArchiveFiles([total_coverage_dir])
                        self.__save_data(total_coverage_infos, sub_job_id, requirement)
                        self.__clean_data(total_coverage_infos, sub_job_id, requirement)

                    core.utils.report(self.logger,
                                      'coverage',
                                      {
                                          # This isn't great to build component identifier in such the artificial way.
                                          # But otherwise we need to pass it everywhere like "sub-job identifier".
                                          'identifier': os.path.join(os.path.sep, sub_job_id),
                                          'coverage': total_coverages
                                      },
                                      self.mqs['report files'],
                                      self.vals['report id'],
                                      self.conf['main working directory'],
                                      os.path.join('total coverages', sub_job_id))

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
            with open(file_name, 'r', encoding='utf8') as fp:
                large_cache = json.load(fp)
        else:
            large_cache = dict()

        cache.setdefault(sub_job_id, dict())
        cache[sub_job_id].setdefault(requirement, dict())

        for file_name in large_cache:
            # todo: Thic code is close to function add_to_coverage
            cache[sub_job_id][requirement].setdefault(file_name, {
                'total functions': large_cache[file_name]['total functions'],
                'covered lines': {},
                'covered functions': {},
                'covered function names': list()
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
        with open(file_name, 'w', encoding='utf8') as fp:
            json.dump(cache[sub_job_id][requirement], fp)

    def __clean_data(self, cache, job_id, requirement):
        cache[job_id].pop(requirement, None)


class LCOV:
    NEW_FILE_PREFIX = "TN:"
    EOR_PREFIX = "end_of_record"
    FILENAME_PREFIX = "SF:"
    LINE_PREFIX = "DA:"
    FUNCTION_PREFIX = "FNDA:"
    FUNCTION_NAME_PREFIX = "FN:"
    PARIALLY_ALLOWED_EXT = ('.c', '.i', '.c.aux')

    def __init__(self, logger, coverage_file, clade, source_dirs, search_dirs, main_work_dir, completeness,
                 coverage_id, coverage_info_dir, collect_functions, preprocessed_files=False):
        # Public
        self.logger = logger
        self.coverage_file = coverage_file
        self.clade = clade
        self.source_dirs = [os.path.normpath(p) for p in source_dirs]
        self.search_dirs = [os.path.normpath(p) for p in search_dirs]
        self.main_work_dir = main_work_dir
        self.completeness = completeness
        self.coverage_info_dir = coverage_info_dir
        self.arcnames = {}
        self.collect_functions = collect_functions

        # Sanity checks
        if self.completeness not in ('full', 'partial', 'lightweight', 'none', None):
            raise NotImplementedError("Coverage type {!r} is not supported".format(self.completeness))

        # Import coverage
        try:
            if self.completeness in ('full', 'partial', 'lightweight'):
                self.coverage_info = self.parse()

                with open(coverage_id, 'w', encoding='utf-8') as fp:
                    json.dump(self.coverage_info, fp, ensure_ascii=True, sort_keys=True, indent=4)

                coverage = {}
                add_to_coverage(coverage, self.coverage_info)
                convert_coverage(coverage)
        except Exception:
            shutil.rmtree('coverage', ignore_errors=True)
            raise

    def parse(self):
        dir_map = (
            ('source files', self.source_dirs),
            ('specifications', (
                os.path.normpath(os.path.join(self.main_work_dir, 'job', 'root', 'specifications')),
            )),
            ('generated models', (
                os.path.normpath(self.main_work_dir),
            ))
        )

        ignore_file = False

        if not os.path.isfile(self.coverage_file):
            raise Exception('There is no coverage file {0}'.format(self.coverage_file))

        # Gettings dirs, that should be excluded.
        excluded_dirs = set()
        if self.completeness in ('partial', 'lightweight'):
            with open(self.coverage_file, encoding='utf-8') as fp:
                # Build map, that contains dir as key and list of files in the dir as value
                all_files = {}
                for line in fp:
                    line = line.rstrip('\n')
                    if line.startswith(self.FILENAME_PREFIX):
                        file_name = line[len(self.FILENAME_PREFIX):]
                        file_name = os.path.normpath(file_name)
                        if os.path.isfile(file_name):
                            path, file = os.path.split(file_name)
                            # All paths should be absolute, otherwise we cannot match source dirs later.
                            path = os.path.join(os.path.sep, core.utils.make_relative_path([self.clade.storage_dir],
                                                                                           path))
                            all_files.setdefault(path, [])
                            all_files[path].append(file)

                for path, files in all_files.items():
                    # Lightweight coverage keeps only source code dirs.
                    if self.completeness == 'lightweight' and \
                            all(os.path.commonpath([s, path]) != s for s in self.source_dirs):
                        self.logger.debug('Excluded {0}'.format(path))
                        excluded_dirs.add(path)
                        continue
                    # Partial coverage keeps only dirs, that contains source files.
                    for file in files:
                        if file.endswith('.c') or file.endswith('.c.aux'):
                            break
                    else:
                        excluded_dirs.add(path)

        # Parsing coverage file
        coverage_info = {}
        with open(self.coverage_file, encoding='utf-8') as fp:
            count_covered_functions = None
            for line in fp:
                line = line.rstrip('\n')

                if ignore_file and not line.startswith(self.FILENAME_PREFIX):
                    continue

                if line.startswith(self.NEW_FILE_PREFIX):
                    # Clean
                    file_name = None
                    covered_lines = {}
                    function_to_line = {}
                    covered_functions = {}
                    count_covered_functions = 0
                elif line.startswith(self.FILENAME_PREFIX):
                    # Get file name, determine his directory and determine, should we ignore this
                    real_file_name = line[len(self.FILENAME_PREFIX):]
                    real_file_name = os.path.normpath(real_file_name)
                    file_name = os.path.join(os.path.sep,
                                             core.utils.make_relative_path([self.clade.storage_dir], real_file_name))
                    if os.path.isfile(real_file_name) and \
                            all(os.path.commonpath((p, file_name)) != p for p in excluded_dirs):
                        for dest, srcs in dir_map:
                            for src in (s for s in srcs if os.path.commonpath((s, file_name)) == s):
                                if dest == 'generated models':
                                    copy_file_name = os.path.join(self.coverage_info_dir,
                                                                  os.path.relpath(file_name, src))
                                    if not os.path.exists(os.path.dirname(copy_file_name)):
                                        os.makedirs(os.path.dirname(copy_file_name))
                                    shutil.copy(real_file_name, copy_file_name)
                                    file_name = copy_file_name
                                    real_file_name = copy_file_name
                                    new_file_name = os.path.join(dest, os.path.basename(file_name))
                                else:
                                    new_file_name = os.path.join(dest, os.path.relpath(file_name, src))
                                ignore_file = False
                                break
                            else:
                                continue
                            break
                        # This "else" corresponds "for"
                        else:
                            # Check other prefixes
                            new_file_name = core.utils.make_relative_path(self.search_dirs, file_name)
                            if new_file_name == file_name:
                                ignore_file = True
                                continue
                            else:
                                ignore_file = False
                            new_file_name = os.path.join('specifications', new_file_name)

                        self.arcnames[real_file_name] = new_file_name
                        old_file_name, file_name = real_file_name, new_file_name
                    else:
                        ignore_file = True
                elif line.startswith(self.LINE_PREFIX):
                    # Coverage of the specified line
                    splts = line[len(self.LINE_PREFIX):].split(',')
                    covered_lines[int(splts[0])] = int(splts[1])
                elif line.startswith(self.FUNCTION_NAME_PREFIX):
                    # Mapping of the function name to the line number
                    splts = line[len(self.FUNCTION_NAME_PREFIX):].split(',')
                    function_to_line.setdefault(splts[1], [])
                    function_to_line[splts[1]] = int(splts[0])
                elif line.startswith(self.FUNCTION_PREFIX):
                    # Coverage of the specified function
                    splts = line[len(self.FUNCTION_PREFIX):].split(',')
                    if splts[0] == "0":
                        continue
                    covered_functions[function_to_line[splts[1]]] = int(splts[0])
                    count_covered_functions += 1
                elif line.startswith(self.EOR_PREFIX):
                    # End coverage for the specific file

                    # Add not covered functions
                    covered_functions.update({line: 0 for line in set(function_to_line.values())
                                             .difference(set(covered_functions.keys()))})

                    coverage_info.setdefault(file_name, [])

                    new_cov = {
                        'file name': old_file_name,
                        'arcname': file_name,
                        'total functions': len(function_to_line),
                        'covered lines': covered_lines,
                        'covered functions': covered_functions
                    }
                    if self.collect_functions:
                        new_cov['covered function names'] = list((name for name, line in function_to_line.items()
                                                                  if covered_functions[line] != 0))
                    coverage_info[file_name].append(new_cov)

        return coverage_info
