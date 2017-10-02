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
import os
import core.utils


class LCOV:
    NEW_FILE_PREFIX = "TN:"
    EOR_PREFIX = "end_of_record"
    FILENAME_PREFIX = "SF:"
    LINE_PREFIX = "DA:"
    FUNCTION_PREFIX = "FNDA:"
    FUNCTION_NAME_PREFIX = "FN:"
    PARIALLY_ALLOWED_EXT = ('.c', '.i', '.c.aux')

    @property
    def coverage(self):
        return {
            'line coverage':
                [[key, value] for key, value in self._lines_coverage.items()]
            ,
            'function coverage': {
                'statistics': self._functions_statistics,
                'coverage': [[key, value] for key, value in self._functions_coverage.items()]
            }
        }

    def __init__(self, logger, coverage_file, shadow_src_dir, main_work_dir, completeness):
        # Public
        self.shadow_src_dir = shadow_src_dir
        self.coverage_file = coverage_file
        self.main_work_dir = main_work_dir
        self.completeness = completeness
        self.logger = logger
        self.arcnames = {}
        self.success = False

        # Private
        self._functions_statistics = {}
        self._functions_coverage = {}
        self._lines_coverage = {}

        # Sanity checks
        if self.completeness not in ('full', 'partial', 'lightweight', 'none', None):
            raise NotImplementedError("Coverage type {!r} is not supported".format(self.completeness))

        # Import coverage
        try:
            if self.completeness in ('full', 'partial', 'lightweight'):
                self.__parse()
                self.success = True
        except Exception as e:
            self._lines_coverage.clear()
            self._functions_statistics.clear()
            self._functions_coverage.clear()
            self.logger.debug(e)

    def __parse(self):
        dir_map = (('source files', self.shadow_src_dir),
                   ('specifications', os.path.join(self.main_work_dir, 'job', 'root')),
                   ('generated models', self.main_work_dir))

        ignore_file = False

        excluded_dirs = set()

        if not os.path.isfile(self.coverage_file):
            raise Exception('There is no coverage file')

        if self.completeness in ('partial', 'lightweight'):
            with open(self.coverage_file, encoding='utf-8') as fp:
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
                    if self.completeness == 'lightweight' \
                            and not dir.startswith(self.shadow_src_dir):
                        self.logger.debug('Excluded {0}'.format(dir))
                        excluded_dirs.add(dir)
                        continue
                    for file in files:
                        if file.endswith('.c') or file.endswith('.c.aux'):
                            break
                    else:
                        excluded_dirs.add(dir)

        self.logger.debug(str(excluded_dirs))

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
                    if os.path.isfile(file_name) \
                        and not any(map(lambda prefix: file_name.startswith(prefix), excluded_dirs)):
                        for dest, src in dir_map:
                            if file_name.startswith(src):
                                if dest == 'generated models':
                                    new_file_name = os.path.join(dest, os.path.basename(file_name))
                                else:
                                    new_file_name = os.path.join(dest, os.path.relpath(file_name, src))
                                ignore_file = False
                                break
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
                    splts = line[len(self.LINE_PREFIX):].split(',')
                    covered_lines.setdefault(int(splts[1]), [])
                    covered_lines[int(splts[1])].append(int(splts[0]))
                elif line.startswith(self.FUNCTION_NAME_PREFIX):
                    splts = line[len(self.FUNCTION_NAME_PREFIX):].split(',')
                    function_to_line.setdefault(splts[1], [])
                    function_to_line[splts[1]] = int(splts[0])
                elif line.startswith(self.FUNCTION_PREFIX):
                    splts = line[len(self.FUNCTION_PREFIX):].split(',')
                    if splts[0] == "0":
                        continue
                    covered_functions.setdefault(int(splts[0]), [])
                    covered_functions[int(splts[0])].append(function_to_line[splts[1]])
                    count_covered_functions += 1
                elif line.startswith(self.EOR_PREFIX):
                    self._functions_statistics[file_name] = [count_covered_functions, len(function_to_line)]
                    for count, values in covered_lines.items():
                        ranges = self.__build_ranges(values)
                        self._lines_coverage.setdefault(count, {})
                        self._lines_coverage[count][file_name] = ranges
                    for count, values in covered_functions.items():
                        self._functions_coverage.setdefault(count, {})
                        self._functions_coverage[count][file_name] = list(values)

    @staticmethod
    def __build_ranges(lines):
        if not lines:
            return []
        res = []
        prev = 0
        lines = sorted(lines)
        for i in range(1, len(lines)):
            if lines[i] != lines[i-1] + 1:
                if i - 1 != prev:
                    if i - 2 == prev:
                        res.append(lines[prev])
                        res.append(lines[i - 1])
                    else:
                        res.append([lines[prev], lines[i-1]])
                else:
                    res.append(lines[prev])
                prev = i

        if prev != len(lines) - 1:
            if prev == len(lines) - 2:
                res.append(lines[prev])
                res.append(lines[-1])
            else:
                res.append([lines[prev], lines[-1]])
        else:
            res.append(lines[prev])
        return res
