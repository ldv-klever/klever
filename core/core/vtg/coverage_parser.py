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
        if self.type not in ('full', 'partially'):
            raise NotImplementedError("Coverage type '{0}' is not supported".format(self.type))

        self.lines_coverage = {}

        self.functions_coverage = {}

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

        ignore_file = False

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
                    len_file = 0
                elif line.startswith(FILENAME_PREFIX):
                    # Get file name, determine his directory and determine, should we ignore this
                    file_name = line[len(FILENAME_PREFIX):]
                    if os.path.isfile(file_name) \
                            and (self.type == 'full'
                                         or any(file_name.endswith(suffix) for suffix in PARIALLY_ALLOWED_EXT)):
                        len_file = self.get_file_len(file_name)
                        if file_name.startswith(self.shadow_src_dir):
                            new_file_name = os.path.join('src', os.path.relpath(file_name, self.shadow_src_dir))
                            ignore_file = False
                        elif file_name.startswith(self.main_work_dir):
                            new_file_name = os.path.join('generated', os.path.relpath(file_name, self.main_work_dir))
                            ignore_file = False
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
                    covered_lines.setdefault(int(splts[1]), [])
                    covered_lines[int(splts[1])].append(int(splts[0]))
                elif line.startswith(FUNCTION_NAME_PREFIX):
                    splts = line[len(FUNCTION_NAME_PREFIX):].split(',')
                    function_to_line.setdefault(splts[1], [])
                    function_to_line[splts[1]] = int(splts[0])
                elif line.startswith(FUNCTION_PREFIX):
                    splts = line[len(FUNCTION_PREFIX):].split(',')
                    if splts[0] == "0":
                        continue
                    covered_functions.setdefault(int(splts[0]), [])
                    covered_functions[int(splts[0])].append(function_to_line[splts[1]])
                elif line.startswith(EOR_PREFIX):

                    for count, values in covered_lines.items():
                        ranges = self.build_ranges(values)
                        self.lines_coverage.setdefault(count, {})
                        self.lines_coverage[count][file_name] = ranges
                    for count, values in covered_functions.items():
                        self.functions_coverage.setdefault(count, {})
                        self.functions_coverage[count][file_name] = list(values)


    def get_files(self):
        return {
            'line coverage': {
                'coverage': [[key, value] for key, value in self.lines_coverage.items()]
            },
            'function coverage': {
                'coverage': [[key, value] for key, value in self.functions_coverage.items()]
            }
        }

    def get_arcnames(self):
        return self.arcnames

    def get_file_len(self, file_name):
        with open(file_name, encoding='utf-8') as fp:
            res = sum(1 for _ in fp)
        return res


    def build_ranges(self, lines):
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

if __name__ == '__main__':
    l = LCOV(None, '../coverage.info', '/home/alexey/klever/native-scheduler-work-dir/'
                                       'native-scheduler-work-dir/scheduler/jobs/35e0dfd4993067c50d8e4544fc9c157f/'
                                       'klever-core-work-dir/lkbce/', '.', None)
    with open('../coverage.json', 'w', encoding='utf-8') as fp:
        json.dump(l.get_files(), fp, indent=4)