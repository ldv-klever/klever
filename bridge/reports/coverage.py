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
import re
import json
import zipfile
import time

from django.template import loader

from reports.models import ReportComponent

from reports.utils import get_parents
from reports.etv import TAB_LENGTH, KEY1_WORDS, KEY2_WORDS


SOURCE_CLASSES = {
    'comment': "COVComment",
    'number': "COVNumber",
    'text': "COVText",
    'key1': "COVKey1",
    'key2': "COVKey2"
}

COLOR = {
    'grey': '#bcbcbc',
    'purple': '#a478e9',
    'lightgrey': '#f4f7ff'
}

TABLE_STAT_COLOR = ['#f18fa6', '#f1c0b2', '#f9e19b', '#e4f495', '#acf1a8']

ROOT_DIRS_ORDER = ['source files', 'specifications', 'generated models']


def exec_time(func):
    def inner(*args, **kwargs):
        t1 = time.time()
        res = func(*args, **kwargs)
        print("CALL {}(): {:5.5f}".format(func.__name__, time.time() - t1))
        return res
    return inner


def coverage_color(curr_cov, max_cov, delta=0):
    green = 140 + int(100 * (1 - curr_cov / max_cov))
    blue = 140 + int(100 * (1 - curr_cov / max_cov)) - delta
    return 'rgb(255, %s, %s)' % (green, blue)


def get_legend(max_cov, leg_type, number=5):
    if max_cov == 0:
        return []
    elif max_cov > 100:
        rounded_max = 100 * int(max_cov/100)
    else:
        rounded_max = max_cov

    delta = 0
    if leg_type == 'funcs':
        delta = 40

    colors = []
    divisions = number - 1
    for i in reversed(range(divisions)):
        curr_cov = int(i * rounded_max / divisions)
        if curr_cov == 0:
            curr_cov = 1
        colors.append((curr_cov, coverage_color(curr_cov, max_cov, delta)))
    colors.insert(0, (rounded_max, coverage_color(rounded_max, max_cov, delta)))
    new_colors = []
    for i in reversed(range(len(colors))):
        if colors[i] not in new_colors:
            new_colors.insert(0, colors[i])
    return new_colors


def json_to_html(data):
    data = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)

    def wrap_text(text):
        return '<span class="COVJsonText">{0}</span>'.format(text)

    def wrap_number(number):
        return '<span class="COVJsonNum">{0}</span>'.format(number)

    def wrap_string(string):
        return '<span class="COVJsonLine">{0}</span><br>'.format(string)

    data_html = ''
    for line in data.split('\n'):
        line = line.replace('\t', ' ' * TAB_LENGTH).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        m = re.match('^(\s*)(\".*?\"):\s(.*)$', line)
        if m is not None:
            if m.group(3) in {'{', '['}:
                new_line = '{0}{1}: {2}'.format(m.group(1), wrap_text(m.group(2)), m.group(3))
                data_html += wrap_string(new_line)
                continue
            m2 = re.match('^(\d.*?)(,?)$', m.group(3))
            if m2 is not None:
                new_line = '{0}{1}: {2}{3}'.format(
                    m.group(1), wrap_text(m.group(2)), wrap_number(m2.group(1)), m2.group(2)
                )
                data_html += wrap_string(new_line)
                continue
            m2 = re.match('^(\".*?\")(,?)$', m.group(3))
            if m2 is not None:
                new_line = '{0}{1}: {2}{3}'.format(
                    m.group(1), wrap_text(m.group(2)), wrap_text(m2.group(1)), m2.group(2)
                )
                data_html += wrap_string(new_line)
                continue
        m = re.match('^(\s*)(\".*\")(,?)$', line)
        if m is not None:
            new_line = '{0}{1}{2}'.format(m.group(1), wrap_text(m.group(2)), m.group(3))
            data_html += wrap_string(new_line)
            continue
        m = re.match('^(\s*)(\d.*?)(,?)$', line)
        if m is not None:
            new_line = '{0}{1}{2}'.format(m.group(1), wrap_number(m.group(2)), m.group(3))
            data_html += wrap_string(new_line)
            continue
        data_html += wrap_string(line)
    return data_html


class GetCoverage:
    def __init__(self, report_id, weight):
        self.report = ReportComponent.objects.get(id=report_id)
        self.job = self.report.root.job
        self.parents = get_parents(self.report)
        self._statistic = CoverageStatistics(self.report)
        self.statistic_table = self._statistic.table_data
        if self._statistic.first_file:
            self.first_file = GetCoverageSrcHTML(report_id, self._statistic.first_file, weight)
        if weight == '0':
            self.data_statistic = DataStatistic(report_id).table_html

    def __is_not_used(self):
        pass


class GetCoverageSrcHTML:
    def __init__(self, report_id, filename, weight):
        self._report = ReportComponent.objects.get(id=report_id)
        self.filename = os.path.normpath(filename).replace('\\', '/')
        self._weight = weight

        self._content, self._coverage = self.__get_arch_content()
        self._max_cov_line, self._line_coverage = self.__get_coverage(self._coverage['line coverage'])
        del self._coverage['line coverage']
        self._max_cov_func, self._func_coverage = self.__get_coverage(self._coverage['function coverage']['coverage'])
        del self._coverage['function coverage']

        self._is_comment = False
        self._is_text = False
        self._text_quote = None
        self._total_lines = 1
        self._data_map = {}
        self.data_html = ''
        if self._weight == '0':
            self.data_html = self.__get_data()
        self.src_html = self.__get_source_html()
        self.legend = loader.get_template('reports/coverage/cov_legend.html').render({'legend': {
            'lines': get_legend(self._max_cov_line, 'lines', 5),
            'funcs': get_legend(self._max_cov_func, 'funcs', 5)
        }})

    def __get_arch_content(self):
        with self._report.coverage_arch as fp:
            if os.path.splitext(fp.name)[-1] != '.zip':
                raise ValueError('Archive type is not supported')
            with zipfile.ZipFile(fp, 'r') as zfp:
                return zfp.read(self.filename).decode('utf8'), json.loads(zfp.read(self._report.coverage).decode('utf8'))

    def __get_coverage(self, coverage):
        data = {}
        max_cov = 0
        for cov in coverage:
            if self.filename in cov[1]:
                max_cov = max(max_cov, cov[0])
                for line_num in cov[1][self.filename]:
                    if isinstance(line_num, int):
                        data[line_num] = cov[0]
                    elif isinstance(line_num, list) and len(line_num) == 2:
                        for i in range(*line_num):
                            data[i] = cov[0]
                        data[line_num[1]] = cov[0]
        return max_cov, data

    def __get_data(self):
        data_values = {}
        data_names = set()
        for data_name in self._coverage:
            cnt = 0
            for data_val in self._coverage[data_name]['values']:
                if self.filename in data_val[1]:
                    cnt += 1
                    data_id = ("%s_%s" % (data_name, cnt)).replace(' ', '_')
                    data_names.add(data_name)
                    data_values[data_id] = json_to_html(data_val[0])
                    for line_num in data_val[1][self.filename]:
                        if isinstance(line_num, int):
                            if line_num not in self._data_map:
                                self._data_map[line_num] = {}
                            self._data_map[line_num][data_name] = data_id
                        elif isinstance(line_num, list) and len(line_num) == 2:
                            for i in range(*line_num):
                                if i not in self._data_map:
                                    self._data_map[i] = {}
                                self._data_map[i][data_name] = data_id
                            if line_num[1] not in self._data_map:
                                self._data_map[line_num[1]] = {}
                            self._data_map[line_num[1]][data_name] = data_id
        data = []
        data_names = list(sorted(data_names))
        for i in self._data_map:
            content = []
            for name in data_names:
                if name in self._data_map[i]:
                    content.append([name, self._data_map[i][name], False])
            content[0][2] = True
            data.append({'line': i, 'content': content})
        return loader.get_template('reports/coverage/coverageData.html').render({
            'data_map': data,
            'data_values': list([d_id, data_values[d_id]] for d_id in data_values)
        })

    def __get_source_html(self):
        data = []
        cnt = 1
        lines = self._content.split('\n')
        self._total_lines = len(str(len(lines)))
        for line in lines:
            line = line.replace('\t', ' ' * TAB_LENGTH).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            data.append(self.__get_line_data(cnt, self.__parse_line(line)))
            cnt += 1
        return loader.get_template('reports/coverage/coverageFile.html').render({'linedata': data})

    def __get_line_data(self, line, code):
        line_num = {
            'class': 'COVLine', 'static': True, 'data': [],
            'content': (' ' * (self._total_lines - len(str(line))) + str(line))
        }
        code = {'class': 'COVCode', 'content': code}
        if line in self._line_coverage and self._line_coverage[line] > 0:
            line_num['data'].append(('number', self._line_coverage[line]))
            code['color'] = coverage_color(self._line_coverage[line], self._max_cov_line)
            code['data'] = [('number', self._line_coverage[line])]

        if line in self._data_map:
            line_num['data'].append(('line', line))

        func_cov = {'class': 'COVIsFC', 'static': True, 'content': '<i class="ui mini icon"></i>'}
        if line in self._func_coverage:
            func_cov['data'] = [('number', self._func_coverage[line])]
            if self._func_coverage[line] == 0:
                func_cov['content'] = '<i class="ui mini red remove icon"></i>'
            else:
                func_cov['content'] = '<i class="ui mini blue checkmark icon"></i>'
                func_cov['color'] = coverage_color(self._func_coverage[line], self._max_cov_func, 40)

        linedata = [line_num]
        if self._weight == '0' and line in self._data_map:
            line_num['content'] = '<a class="COVLineLink">%s</a>' % line_num['content']
            line_num['class'] += ' COVWithData'
        linedata.append(func_cov)
        linedata.append(code)
        return linedata

    def __parse_line(self, line):
        if self._is_comment:
            m = re.match('(.*?)\*/(.*)', line)
            if m is None:
                return self.__wrap_line(line, 'comment')
            self._is_comment = False
            new_line = self.__wrap_line(m.group(1) + '*/', 'comment')
            return new_line + self.__parse_line(m.group(2))

        if self._is_text:
            before, after = self.__parse_text(line)
            if after is None:
                return self.__wrap_line(before, 'text')
            self._is_text = False
            return self.__wrap_line(before, 'text') + self.__parse_line(after)

        m = re.match('(.*?)/\*(.*)', line)
        if m is not None and m.group(1).find('"') == -1 and m.group(1).find("'") == -1:
            new_line = self.__parse_line(m.group(1))
            self._is_comment = True
            new_line += self.__parse_line('/*' + m.group(2))
            return new_line
        m = re.match('(.*?)//(.*)', line)
        if m is not None and m.group(1).find('"') == -1 and m.group(1).find("'") == -1:
            new_line = self.__parse_line(m.group(1))
            new_line += self.__wrap_line('//' + m.group(2), 'comment')
            return new_line

        m = re.match('(.*?)([\'\"])(.*)', line)
        if m is not None:
            new_line = self.__parse_line(m.group(1))
            self._text_quote = m.group(2)
            before, after = self.__parse_text(m.group(3))
            new_line += self.__wrap_line(self._text_quote + before, 'text')
            if after is None:
                self._is_text = True
                return new_line
            self._is_text = False
            return new_line + self.__parse_line(after)

        m = re.match("(.*\W)(\d+)(\W.*)", line)
        if m is not None:
            new_line = self.__parse_line(m.group(1))
            new_line += self.__wrap_line(m.group(2), 'number')
            new_line += self.__parse_line(m.group(3))
            return new_line
        words = re.split('([^a-zA-Z0-9-_#])', line)
        new_words = []
        for word in words:
            if word in KEY1_WORDS:
                new_words.append(self.__wrap_line(word, 'key1'))
            elif word in KEY2_WORDS:
                new_words.append(self.__wrap_line(word, 'key2'))
            else:
                new_words.append(word)
        return ''.join(new_words)

    def __parse_text(self, text):
        escaped = False
        before = ''
        after = ''
        end_found = False
        for c in text:
            if end_found:
                after += c
                continue
            if not escaped and c == self._text_quote:
                end_found = True
            elif escaped:
                escaped = False
            elif c == '\\':
                escaped = True
            before += c
        if end_found:
            return before, after
        return before, None

    def __wrap_line(self, line, text_type, line_id=None):
        self.__is_not_used()
        if text_type not in SOURCE_CLASSES:
            return line
        if line_id is not None:
            return '<span id="%s" class="%s">%s</span>' % (line_id, SOURCE_CLASSES[text_type], line)
        return '<span class="%s">%s</span>' % (SOURCE_CLASSES[text_type], line)

    def __is_not_used(self):
        pass


class CoverageStatistics:
    def __init__(self, report):
        self.report = report
        self._files = []
        self._total_lines = {}
        self._covered_lines = {}
        self._covered_funcs = {}
        self.__get_files_and_data()
        self.shown_ids = set()
        self.first_file = None
        self.table_data = self.__get_table_data()

    def __get_files_and_data(self):
        if not self.report.verification:
            raise ValueError("The parent is not verification report")
        with self.report.coverage_arch as fp:
            if os.path.splitext(fp.name)[-1] != '.zip':
                raise ValueError('Archive type is not supported')
            with zipfile.ZipFile(fp, 'r') as zfp:
                for filename in zfp.namelist():
                    if filename.endswith('/'):
                        continue
                    if filename == self.report.coverage:
                        coverage = json.loads(zfp.read(self.report.coverage).decode('utf8'))
                        self.__get_covered(coverage['line coverage'])
                        self._covered_funcs = self.__get_covered_funcs(coverage['function coverage']['statistics'])
                    elif filename != self.report.log:
                        self._files.append(os.path.normpath(filename))
                        with zfp.open(filename) as inzip_fp:
                            lines = 0
                            while inzip_fp.readline():
                                lines += 1
                            self._total_lines[os.path.normpath(filename)] = lines

    def __get_covered(self, line_coverage):
        covered_lines = {}
        for data in line_coverage:
            if data[0] > 0:
                for f in data[1]:
                    path = os.path.normpath(f)
                    if path not in covered_lines:
                        covered_lines[path] = set()
                    for linenum in data[1][f]:
                        if isinstance(linenum, int):
                            covered_lines[path].add(linenum)
                        elif isinstance(linenum, list):
                            for ln in range(*linenum):
                                covered_lines[path].add(ln)
                            covered_lines[path].add(linenum[1])
        for filename in covered_lines:
            self._covered_lines[filename] = len(covered_lines[filename])

    def __get_covered_funcs(self, coverage):
        self.__is_not_used()
        func_coverage = {}
        for fname in coverage:
            func_coverage[os.path.normpath(fname)] = coverage[fname]
        return func_coverage

    def __get_table_data(self):
        cnt = 0
        parents = {}
        for fname in self._files:
            path = fname.split(os.path.sep)
            for i in range(len(path)):
                cnt += 1
                curr_path = os.path.join(*path[:(i + 1)])
                if curr_path not in parents:
                    parent_id = parent = None
                    if i > 0:
                        parent = os.path.join(*path[:i])
                        parent_id = parents[parent]['id']
                    parents[curr_path] = {
                        'id': cnt,
                        'title': path[i],
                        'parent': parent,
                        'parent_id': parent_id,
                        'display': False,
                        'is_dir': (i != len(path) - 1),
                        'path': curr_path,
                        'lines': {'covered': 0, 'total': 0, 'percent': '-'},
                        'funcs': {'covered': 0, 'total': 0, 'percent': '-'}
                    }

        for fname in self._files:
            display = False
            if any(fname.endswith(x) for x in ['.i', '.c', '.c.aux']):
                display = True
            covered_lines = self._covered_lines.get(fname, 0)
            total_lines = self._total_lines.get(fname, 0)
            covered_funcs = total_funcs = 0
            if fname in self._covered_funcs:
                covered_funcs = self._covered_funcs[fname][0]
                total_funcs = self._covered_funcs[fname][1]
            parent = fname
            while parent is not None:
                parents[parent]['lines']['covered'] += covered_lines
                parents[parent]['lines']['total'] += total_lines
                parents[parent]['funcs']['covered'] += covered_funcs
                parents[parent]['funcs']['total'] += total_funcs
                if parents[parent]['is_dir'] and display or parents[parent]['parent'] is None:
                    parents[parent]['display'] = True
                parent = parents[parent]['parent']

        for fname in parents:
            if parents[fname]['lines']['total'] > 0:
                div = parents[fname]['lines']['covered'] / parents[fname]['lines']['total']
                parents[fname]['lines']['percent'] = '%s%%' % int(100 * div)
                color_id = int(div * len(TABLE_STAT_COLOR))
                if color_id == len(TABLE_STAT_COLOR):
                    color_id -= 1
                parents[fname]['lines']['color'] = TABLE_STAT_COLOR[color_id]
            if parents[fname]['funcs']['total'] > 0:
                div = parents[fname]['funcs']['covered'] / parents[fname]['funcs']['total']
                parents[fname]['funcs']['percent'] = '%s%%' % int(100 * div)
                color_id = int(div * len(TABLE_STAT_COLOR))
                if color_id == len(TABLE_STAT_COLOR):
                    color_id -= 1
                parents[fname]['funcs']['color'] = TABLE_STAT_COLOR[color_id]

        other_data = list(sorted(parents.values(), key=lambda x: (not x['is_dir'], x['title'])))

        def __get_all_children(file_info):
            children = []
            if not file_info['is_dir']:
                return children
            for fi in other_data:
                if fi['parent_id'] == file_info['id']:
                    children.append(fi)
                    children.extend(__get_all_children(fi))
            return children

        first_lvl = []
        for root_name in ROOT_DIRS_ORDER:
            if root_name in parents:
                first_lvl.append(parents[root_name])

        ordered_data = []
        for fd in first_lvl:
            ordered_data.append(fd)
            ordered_data.extend(__get_all_children(fd))
        for fd in ordered_data:
            if not fd['is_dir'] and parents[fd['parent']]['display']:
                self.first_file = fd['path']
                break
        return ordered_data

    def __is_not_used(self):
        pass


class DataStatistic:
    def __init__(self, report_id):
        self.report = ReportComponent.objects.get(id=report_id)
        self.table_html = loader.get_template('reports/coverage/coverageDataStatistics.html')\
            .render({'DataStatistics': self.__get_data_stat()})

    def __get_data_stat(self):
        if not self.report.verification:
            raise ValueError("The parent is not verification report")
        data = []
        with self.report.coverage_arch as fp:
            if os.path.splitext(fp.name)[-1] != '.zip':
                raise ValueError('Archive type is not supported')
            with zipfile.ZipFile(fp, 'r') as zfp:
                coverage = json.loads(zfp.read(self.report.coverage).decode('utf8'))
                for val in sorted(coverage):
                    if val not in {'line coverage', 'function coverage'} and 'statistics' in coverage[val]:
                        data.append({
                            'tab': val, 'active': False, 'content': json_to_html(coverage[val]['statistics'])
                        })
        if len(data) > 0:
            data[0]['active'] = True
        return data
