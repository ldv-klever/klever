#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
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
import shutil

import core.utils


class LCOV:
    NEW_FILE_PREFIX = "TN:"
    EOR_PREFIX = "end_of_record"
    FILENAME_PREFIX = "SF:"
    LINE_PREFIX = "DA:"
    FUNCTION_PREFIX = "FNDA:"
    FUNCTION_NAME_PREFIX = "FN:"
    PARIALLY_ALLOWED_EXT = ('.c', '.i', '.c.aux')

    def __init__(self, logger, coverage_file, shadow_src_dir, main_work_dir, completeness, coverage_id,
                 coverage_info_dir):
        # Public
        self.logger = logger
        self.coverage_file = coverage_file
        self.shadow_src_dir = shadow_src_dir
        self.main_work_dir = main_work_dir
        self.completeness = completeness
        self.coverage_info_dir = coverage_info_dir

        self.arcnames = {}

        # Sanity checks
        if self.completeness not in ('full', 'partial', 'lightweight', 'none', None):
            raise NotImplementedError("Coverage type {!r} is not supported".format(self.completeness))

        # Import coverage
        try:
            if self.completeness in ('full', 'partial', 'lightweight'):
                self.coverage_info = self.parse()

                with open(coverage_id, 'w', encoding='utf-8') as fp:
                    json.dump(self.coverage_info, fp, ensure_ascii=True, sort_keys=True, indent=4)

                with open('coverage.json', 'w', encoding='utf-8') as fp:
                    json.dump(LCOV.get_coverage(self.coverage_info), fp, ensure_ascii=True,
                              sort_keys=True, indent=4)
        except Exception as e:
            self.logger.exception('Could not parse coverage')

    def parse(self):
        dir_map = (('source files', self.shadow_src_dir),
                   ('specifications', os.path.join(self.main_work_dir, 'job', 'root')),
                   ('generated models', self.main_work_dir))

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
                        if os.path.isfile(file_name):
                            dir, file = os.path.split(file_name)
                            all_files.setdefault(dir, [])
                            all_files[dir].append(file)

                for dir, files in all_files.items():
                    # Lightweight coverage keeps only source code dirs.
                    if self.completeness == 'lightweight' \
                            and not dir.startswith(self.shadow_src_dir):
                        self.logger.debug('Excluded {0}'.format(dir))
                        excluded_dirs.add(dir)
                        continue
                    # Partial coverage keeps only dirs, that contains source files.
                    for file in files:
                        if file.endswith('.c') or file.endswith('.c.aux'):
                            break
                    else:
                        excluded_dirs.add(dir)

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
                    file_name = line[len(self.FILENAME_PREFIX):]
                    if os.path.isfile(file_name) and not \
                            any(map(lambda prefix: file_name.startswith(prefix), excluded_dirs)):
                        for dest, src in dir_map:
                            if file_name.startswith(src):
                                if dest == 'generated models':
                                    copy_file_name = os.path.join(self.coverage_info_dir, os.path.relpath(file_name, src))
                                    if not os.path.exists(os.path.dirname(copy_file_name)):
                                        os.makedirs(os.path.dirname(copy_file_name))
                                    shutil.copy(file_name, copy_file_name)
                                    file_name = copy_file_name
                                    new_file_name = os.path.join(dest, os.path.basename(file_name))
                                else:
                                    new_file_name = os.path.join(dest, os.path.relpath(file_name, src))
                                ignore_file = False
                                break
                        # This "else" corresponds "for"
                        else:
                            new_file_name = core.utils.make_relative_path(self.logger, self.main_work_dir, file_name)
                            if new_file_name == file_name:
                                ignore_file = True
                                continue
                            else:
                                ignore_file = False
                            new_file_name = os.path.join('specifications', new_file_name)

                        self.arcnames[file_name] = new_file_name
                        old_file_name, file_name = file_name, new_file_name
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
                    coverage_info[file_name].append({
                        'file name': old_file_name,
                        'arcname': file_name,
                        'total functions': len(function_to_line),
                        'covered lines': covered_lines,
                        'covered functions': covered_functions
                    })

        return coverage_info

    @staticmethod
    def get_coverage(coverage_info):

        # Combine line and function coverages of a file to a single one
        merged_coverage_info = {}
        for file_name, coverages in coverage_info.items():
            merged_coverage_info[file_name] = {
                'total functions': coverages[0]['total functions'],
                'covered lines': {},
                'covered functions': {}
            }

            for coverage in coverages:
                for type in ('covered lines', 'covered functions'):
                    for line, value in coverage[type].items():
                        merged_coverage_info[file_name][type].setdefault(line, 0)
                        merged_coverage_info[file_name][type][line] += value

        # Map combined coverage to the required format
        line_coverage = {}
        function_coverage = {}
        function_statistics = {}

        for file_name, coverage in merged_coverage_info.items():
            for line, value in coverage['covered lines'].items():
                line_coverage.setdefault(value, {})
                line_coverage[value].setdefault(file_name, [])
                line_coverage[value][file_name].append(int(line))

            for line, value in coverage['covered functions'].items():
                function_coverage.setdefault(value, {})
                function_coverage[value].setdefault(file_name, [])
                function_coverage[value][file_name].append(int(line))

            function_statistics[file_name] = [len(coverage['covered functions']), coverage['total functions']]

        # Merge contiguous covered lines into a range
        for key, value in line_coverage.items():
            for file_name, lines in value.items():
                line_coverage[key][file_name] = LCOV.__build_ranges(lines)

        return {
            'line coverage': [[key, value] for key, value in line_coverage.items()],
            'function coverage': {
                'statistics': function_statistics,
                'coverage': [[key, value] for key, value in function_coverage.items()]
                }
        }

    @staticmethod
    def __build_ranges(lines):
        if not lines:
            return []
        res = []
        prev = 0
        lines = sorted(lines)
        for i in range(1, len(lines)):
            if lines[i] != lines[i-1] + 1:
                # The sequence is broken.
                if i - 1 != prev:
                    # There is more than one line in the sequence. .
                    if i - 2 == prev:
                        # There is more than two lines in the sequence. Add the range.
                        res.append(lines[prev])
                        res.append(lines[i - 1])
                    else:
                        # Otherwise, add these lines separately.
                        res.append([lines[prev], lines[i-1]])
                else:
                    # Just add a single non-sequence line.
                    res.append(lines[prev])
                prev = i

        # This step is the same as in the loop body.
        if prev != len(lines) - 1:
            if prev == len(lines) - 2:
                res.append(lines[prev])
                res.append(lines[-1])
            else:
                res.append([lines[prev], lines[-1]])
        else:
            res.append(lines[prev])

        return res
