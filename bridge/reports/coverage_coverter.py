import os
import argparse
import json
import errno


class ConvertCoverage:
    def __init__(self, coverage_data, files_dir):
        self._data = coverage_data
        self._files_dir = files_dir
        self.common = {
            "format": 1,
            "coverage statistics": {},
            "data statistics": {}
        }
        self.file_coverage = {}
        self.__process_data()

    def __add_file(self, file_name):
        if file_name in self.file_coverage:
            return
        self.file_coverage[file_name] = {
            'format': 1,
            'line coverage': {},
            'function coverage': {},
            'notes': {}, 'data': {}
        }
        with open(os.path.join(self._files_dir, file_name), mode='r', encoding='utf-8') as src_fp:
            total_lines = len(src_fp.read().split('\n'))
        self.common['coverage statistics'][file_name] = [0, total_lines, 0, 0]

    def __collect_lines_coverage(self):
        for cov_val, cov_data in self._data['line coverage']:
            for file_name in cov_data:
                self.__add_file(file_name)
                lines = cov_data[file_name]
                for line in lines:
                    if isinstance(line, int):
                        self.common['coverage statistics'][file_name][0] += 1
                        self.file_coverage[file_name]['line coverage'][str(line)] = cov_val
                    elif isinstance(line, list):
                        for line_1 in range(*line):
                            self.common['coverage statistics'][file_name][0] += 1
                            self.file_coverage[file_name]['line coverage'][str(line_1)] = cov_val

    def __collect_funcs_coverage(self):
        for cov_val, cov_data in self._data['function coverage']['coverage']:
            for file_name in cov_data:
                self.__add_file(file_name)
                for line in cov_data[file_name]:
                    if isinstance(line, int):
                        self.file_coverage[file_name]['function coverage'][str(line)] = cov_val
                    elif isinstance(line, list):
                        for line_1 in range(*line):
                            self.file_coverage[file_name]['function coverage'][str(line_1)] = cov_val
        for file_name, stat_data in self._data['function coverage']['statistics'].items():
            self.__add_file(file_name)
            self.common['coverage statistics'][file_name][2] = stat_data[0]
            self.common['coverage statistics'][file_name][3] = stat_data[1]

    def __collect_data(self):
        for data_name in self._data:
            if data_name in {'line coverage', 'function coverage'}:
                continue
            for data_value, files_data in self._data[data_name]['values']:
                for file_name, lines in files_data.items():
                    self.__add_file(file_name)
                    for line in lines:
                        if isinstance(line, int):
                            self.file_coverage[file_name]['data'].setdefault(str(line), [])
                            self.file_coverage[file_name]['data'][str(line)].append({
                                'name': data_name, 'value': data_value
                            })
                        elif isinstance(line, list):
                            for line_1 in range(*line):
                                self.file_coverage[file_name]['data'].setdefault(str(line_1), [])
                                self.file_coverage[file_name]['data'][str(line_1)].append({
                                    'name': data_name, 'value': data_value
                                })
            self.common['data statistics'][data_name] = self._data[data_name]['statistics']

    def __process_data(self):
        self.__collect_lines_coverage()
        self.__collect_funcs_coverage()
        self.__collect_data()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('workdir', type=str, help='Working directory')
    parser.add_argument('--out', type=str, help='Directory where to save new format')
    args = parser.parse_args()
    workdir = os.path.abspath(args.workdir)
    out_dir = os.path.join(workdir, args.out or 'converted')

    with open(os.path.join(workdir, 'coverage.json'), mode='r', encoding='utf-8') as fp:
        converter = ConvertCoverage(json.load(fp), workdir)

    try:
        os.makedirs(out_dir)
    except OSError as exc:
        if exc.errno != errno.EEXIST:
            raise

    common_file = os.path.abspath(os.path.join(out_dir, 'coverage.json'))
    with open(common_file, mode='w', encoding='utf-8') as fp:
        json.dump(converter.common, fp, indent=2, sort_keys=True, ensure_ascii=False)
    for f_name in converter.file_coverage:
        cov_path = os.path.abspath(os.path.join(out_dir, '{}.cov.json'.format(f_name)))
        if not os.path.exists(os.path.dirname(cov_path)):
            try:
                os.makedirs(os.path.dirname(cov_path))
            except OSError as exc:
                if exc.errno != errno.EEXIST:
                    raise
        with open(cov_path, mode='w', encoding='utf-8') as fp:
            json.dump(converter.file_coverage[f_name], fp, indent=2, sort_keys=True, ensure_ascii=False)
