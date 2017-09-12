import os
import json

import core.utils


class LCOV:
    def __init__(self, logger, coverage_file, shadow_src_dir, main_work_dir, type):
        self.logger = logger
        self.coverage_file = coverage_file
        self.shadow_src_dir = shadow_src_dir
        self.main_work_dir = main_work_dir
        self.type = type
        self.len_files = {}
        if self.type not in ('full', 'partial', 'lightweight'):
            raise NotImplementedError("Coverage type '{0}' is not supported".format(self.type))

        self.lines_coverage = {}

        self.functions_coverage = {}

        self.functions_statistics = {}

        self.arcnames = {}

        self.parse()

    def parse(self):
        NEW_FILE_PREFIX = "TN:"
        EOR_PREFIX = "end_of_record"
        FILENAME_PREFIX = "SF:"
        LINE_PREFIX = "DA:"
        FUNCTION_PREFIX = "FNDA:"
        FUNCTION_NAME_PREFIX = "FN:"

        PARIALLY_ALLOWED_EXT = ('.c', '.i', '.c.aux')

        DIR_MAP = (('source files', self.shadow_src_dir),
                   ('specifications', os.path.join(self.main_work_dir, 'job', 'root')),
                   ('generated models', self.main_work_dir))

        ignore_file = False

        coverage_info = {}

        excluded_dirs = set()
        if self.type in ('partial', 'lightweight'):
            with open(self.coverage_file, encoding='utf-8') as fp:
                all_files = {}
                for line in fp:
                    line = line.rstrip('\n')
                    if line.startswith(FILENAME_PREFIX):
                        file_name = line[len(FILENAME_PREFIX):]
                        if os.path.isfile(file_name):
                            dir, file = os.path.split(file_name)
                            all_files.setdefault(dir, [])
                            all_files[dir].append(file)
                for dir, files in all_files.items():
                    if self.type == 'lightweight' \
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
            for line in fp:
                line = line.rstrip('\n')

                if ignore_file and not line.startswith(FILENAME_PREFIX):
                    continue

                if line.startswith(NEW_FILE_PREFIX):
                    # Clean
                    file_name = None
                    covered_lines = {}
                    function_to_line = {}
                    covered_functions = {}
                    count_covered_functions = 0
                    len_file = 0
                elif line.startswith(FILENAME_PREFIX):
                    # Get file name, determine his directory and determine, should we ignore this
                    file_name = line[len(FILENAME_PREFIX):]
                    if os.path.isfile(file_name) \
                        and not any(map(lambda prefix: file_name.startswith(prefix), excluded_dirs)):
                        len_file = self.get_file_len(file_name)
                        for dest, src in DIR_MAP:
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
                elif line.startswith(LINE_PREFIX):
                    splts = line[len(LINE_PREFIX):].split(',')
                    if splts[1] == "0":
                        continue
                    covered_lines[int(splts[0])] = int(splts[1])
                    #covered_lines.setdefault(int(splts[0]), [])
                    #covered_lines[int(splts[0])].append(int(splts[1]))
                elif line.startswith(FUNCTION_NAME_PREFIX):
                    splts = line[len(FUNCTION_NAME_PREFIX):].split(',')
                    function_to_line.setdefault(splts[1], [])
                    function_to_line[splts[1]] = int(splts[0])
                elif line.startswith(FUNCTION_PREFIX):
                    splts = line[len(FUNCTION_PREFIX):].split(',')
                    if splts[0] == "0":
                        continue
                    covered_functions[function_to_line[splts[1]]] = int(splts[0])
                    #covered_functions.setdefault(int(splts[0]), [])
                    #covered_functions[int(splts[0])].append(function_to_line[splts[1]])
                    count_covered_functions += 1
                elif line.startswith(EOR_PREFIX):
                    coverage_info.setdefault(file_name, [])
                    coverage_info[file_name].append({
                        'file name': old_file_name,
                        'arcname': file_name,
                        'len file': len_file,
                        'total functions': len(function_to_line),
                        'covered lines': covered_lines,
                        'covered functions': covered_functions,
                    })

                    """
                    self.len_files.setdefault(len_file, [])
                    self.len_files[len_file].append(file_name)
                    self.functions_statistics[file_name] = [count_covered_functions, len(function_to_line)]
                    for count, values in covered_lines.items():
                        ranges = self.build_ranges(values)
                        self.lines_coverage.setdefault(count, {})
                        self.lines_coverage[count][file_name] = ranges
                    for count, values in covered_functions.items():
                        self.functions_coverage.setdefault(count, {})
                        self.functions_coverage[count][file_name] = list(values)
                    """

        return coverage_info

    @staticmethod
    def get_coverage(coverage_info):
        merged_coverage_info = {}
        for file_name, coverages in coverage_info.items():
            merged_coverage_info[file_name] = {
                'len file': coverages[0]['len file'],
                'total functions': coverages[0]['total functions'],
                'covered lines': {},
                'covered functions': {}
            }
            for coverage in coverages:
                for type in ('covered lines', 'covered functions'):
                    for line, value in coverage[type].items():
                        merged_coverage_info[file_name][type].setdefault(line, 0)
                        merged_coverage_info[file_name][type][line] += value

        line_coverage = {}
        function_coverage = {}
        function_statistics = {}
        for file_name, coverage in merged_coverage_info.items():
            for line, value in coverage['covered lines'].items():
                line_coverage.setdefault(value, {})
                line_coverage[value].setdefault(file_name, [])
                line_coverage[value][file_name].append(line)
            for line, value in coverage['covered functions'].items():
                function_coverage.setdefault(value, {})
                function_coverage[value].setdefault(file_name, [])
                function_coverage[value][file_name].append(line)
            function_statistics[file_name] = [len(coverage['covered functions']), coverage['total functions']]
        for key, value in line_coverage.items():
            for file_name, lines in value.items():
                line_coverage[key][file_name] = LCOV.build_ranges(lines)
        return {
            'line coverage':
                [[key, value] for key, value in line_coverage.items()]
            ,
            'function coverage': {
                'statistics': function_statistics,
                'coverage': [[key, value] for key, value in function_coverage.items()]
            }
        }

    def get_arcnames(self):
        return self.arcnames

    def get_file_len(self, file_name):
        with open(file_name, encoding='utf-8') as fp:
            res = sum(1 for _ in fp)
        return res

    @staticmethod
    def build_ranges(lines):
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
