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

from django.core.exceptions import ObjectDoesNotExist
from django.template import loader
from django.utils.translation import ugettext_lazy as _

from bridge.utils import BridgeException

from reports.models import ReportComponent, ReportUnsafe, ReportSafe, ReportUnknown

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
        self._weight = weight

        self.type = None
        self.report = self.__get_report(report_id)
        self.job = self.report.root.job
        self.parent = ReportComponent.objects.get(id=self.report.parent_id)
        self.parents = get_parents(self.report)

        self._files = []
        self._curr_i = 0
        self._sum = 0
        self.coverage = None

    def __get_report(self, report_id):
        try:
            self.type = 'safe'
            return ReportSafe.objects.get(id=report_id)
        except ObjectDoesNotExist:
            try:
                self.type = 'unsafe'
                return ReportUnsafe.objects.get(id=report_id)
            except ObjectDoesNotExist:
                try:
                    self.type = 'unknown'
                    return ReportUnknown.objects.get(id=report_id)
                except ObjectDoesNotExist:
                    raise BridgeException(_('The report was not found'))

    def __get_files(self):
        if not self.parent.verification:
            raise ValueError("The parent is not verification report")
        with self.parent.archive as fp:
            if os.path.splitext(fp.name)[-1] != '.zip':
                raise ValueError('Archive type is not supported')
            with zipfile.ZipFile(fp, 'r') as zfp:
                for filename in zfp.namelist():
                    if filename.endswith('/'):
                        continue
                    if filename not in {self.parent.coverage, self.parent.log}:
                        self._files.append(os.path.normpath(filename))

    def __wrap_item(self, title, item, header):
        self.__is_not_used()
        style = ''
        if header:
            style = ' style="color:%s;"' % COLOR['grey']
        return '<div class="item" data-value="%s"%s>%s</div>' % (title, style, item)

    def __wrap_items(self, title, items):
        self.__is_not_used()
        return '<i class="dropdown icon"></i><span class="text">%s</span><div class="menu">%s</div>' % (
            title, ''.join(items)
        )

    def __get_children_list(self, path):
        children = []
        headers_dir = True
        for f in self._files[self._curr_i:]:
            if f.startswith(path):
                relpath = os.path.relpath(f, path)
                childpath = relpath.split(os.path.sep)
                if len(childpath) == 1:
                    self._sum += 1
                    is_header = False
                    if childpath[0].endswith('.h'):
                        is_header = True
                    else:
                        headers_dir = False
                    children.append(self.__wrap_item(f, childpath[0], is_header))
                    self._curr_i += 1
                elif len(childpath) > 1:
                    children_html, children_are_headers = self.__get_children_list(os.path.join(path, childpath[0]))
                    if len(children_html) > 0:
                        if not children_are_headers:
                            headers_dir = False
                        children.append(self.__wrap_item('', children_html, children_are_headers))
            else:
                break
        if len(children) > 0:
            return self.__wrap_items(os.path.basename(path), children), headers_dir
        return '', headers_dir

    def files_tree(self):
        self.__get_files()
        self._files = list(sorted(self._files))

        root_dirs = []
        indexes = {}
        cnt = 0
        for rdir in sorted(ROOT_DIRS_ORDER):
            children_html, children_are_headers = self.__get_children_list(rdir)
            if len(children_html) > 0:
                for i in range(len(ROOT_DIRS_ORDER)):
                    if ROOT_DIRS_ORDER[i] == rdir:
                        indexes[i] = cnt
                        break
                root_dirs.append(self.__wrap_item(rdir, children_html, children_are_headers))
                cnt += 1

        root_dirs_sorted = []
        for j in sorted(indexes):
            root_dirs_sorted.append(root_dirs[indexes[j]])
        if self._sum != len(self._files):
            raise ValueError('Something is wrong')

        return self.__wrap_items('Select file', root_dirs_sorted)

    def get_file_content(self, filename):
        with self.parent.archive as fp:
            if os.path.splitext(fp.name)[-1] != '.zip':
                raise ValueError('Archive type is not supported')
            with zipfile.ZipFile(fp, 'r') as zfp:
                filename = os.path.normpath(filename).replace('\\', '/')
                return GetCoverageSrcHTML(
                    filename,
                    zfp.read(filename).decode('utf8'),
                    json.loads(zfp.read(self.parent.coverage).decode('utf8')),
                    self._weight
                )

    def __is_not_used(self):
        pass


class GetCoverageSrcHTML:
    def __init__(self, filename, content, coverage, weight):
        self._filename = filename
        self._weight = weight

        self._coverage = coverage
        self._max_cov_line, self._line_coverage = self.__get_coverage(coverage['line coverage'])
        del self._coverage['line coverage']
        self._max_cov_func, self._func_coverage = self.__get_coverage(coverage['function coverage']['coverage'])
        del self._coverage['function coverage']

        self._is_comment = False
        self._is_text = False
        self._text_quote = None
        self._total_lines = 1
        self._data_map = {}
        self.data_html = ''
        if self._weight == '0':
            self.data_html = self.__get_data()
        self.src_html = self.__get_source_html(content)

    def __get_coverage(self, coverage):
        data = {}
        max_cov = 0
        for cov in coverage:
            if self._filename in cov[1]:
                max_cov = max(max_cov, cov[0])
                for line_num in cov[1][self._filename]:
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
                if self._filename in data_val[1]:
                    cnt += 1
                    data_id = ("%s_%s" % (data_name, cnt)).replace(' ', '_')
                    data_names.add(data_name)
                    data_values[data_id] = json_to_html(data_val[0])
                    for line_num in data_val[1][self._filename]:
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

    def __get_report(self, report_id):
        self.__is_not_used()
        try:
            return ReportUnsafe.objects.get(pk=report_id)
        except ObjectDoesNotExist:
            raise BridgeException(_("Could not find the corresponding unsafe"))

    def __get_source_html(self, source_content):
        data = []
        cnt = 1
        lines = source_content.split('\n')
        self._total_lines = len(str(len(lines)))
        for line in lines:
            line = line.replace('\t', ' ' * TAB_LENGTH).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            data.append(self.__get_line_data(cnt, self.__parse_line(line)))
            cnt += 1
        return loader.get_template('reports/coverage/coverageFile.html').render({'linedata': data})

    def __get_line_data(self, line, code):
        line_num = {
            'class': 'COVLine', 'static': True, 'data': [],
            'content': '<a class="COVLineLink">%s</a>' % (' ' * (self._total_lines - len(str(line))) + str(line))
        }
        code = {'class': 'COVCode', 'content': code}
        if line in self._line_coverage and self._line_coverage[line] > 0:
            line_num['data'].append(('number', self._line_coverage[line]))
            code['color'] = coverage_color(self._line_coverage[line], self._max_cov_line)

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
        if self._weight == '0':
            linedata.append({
                'class': 'COVHasD', 'static': True,
                'content': '&nbsp;',
                'color': COLOR['purple'] if line in self._data_map else COLOR['lightgrey']
            })
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
    def __init__(self, report_id):
        self.type = None
        self.report = self.__get_report(report_id)
        self.parent = ReportComponent.objects.get(id=self.report.parent_id)
        self._files = []
        self._total_lines = {}
        self._covered_lines = {}
        self._covered_funcs = {}
        self.__get_files_and_data()
        self.shown_ids = set()
        self._table_data = self.__get_table_data()
        self.table_html = self.__html_table()

    def __get_report(self, report_id):
        try:
            self.type = 'safe'
            return ReportSafe.objects.get(id=report_id)
        except ObjectDoesNotExist:
            try:
                self.type = 'unsafe'
                return ReportUnsafe.objects.get(id=report_id)

            except ObjectDoesNotExist:
                try:
                    self.type = 'unknown'
                    return ReportUnknown.objects.get(id=report_id)
                except ObjectDoesNotExist:
                    raise BridgeException(_('The report was not found'))

    @exec_time
    def __get_files_and_data(self):
        if not self.parent.verification:
            raise ValueError("The parent is not verification report")
        with self.parent.archive as fp:
            if os.path.splitext(fp.name)[-1] != '.zip':
                raise ValueError('Archive type is not supported')
            with zipfile.ZipFile(fp, 'r') as zfp:
                for filename in zfp.namelist():
                    if filename.endswith('/'):
                        continue
                    if filename == self.parent.coverage:
                        coverage = json.loads(zfp.read(self.parent.coverage).decode('utf8'))
                        self.__get_covered(coverage['line coverage'])
                        self._covered_funcs = self.__get_covered_funcs(coverage['function coverage']['statistics'])
                    elif filename != self.parent.log:
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
                parents[fname]['lines']['percent'] = '%s%%' % int(
                    100 * parents[fname]['lines']['covered'] / parents[fname]['lines']['total']
                )
            if parents[fname]['funcs']['total'] > 0:
                parents[fname]['funcs']['percent'] = '%s%%' % int(
                    100 * parents[fname]['funcs']['covered'] / parents[fname]['funcs']['total']
                )

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
        return ordered_data

    def __html_table(self):
        return loader.get_template('reports/coverage/coverageStatisticsTable.html')\
            .render({'TableData': self._table_data})

    def __is_not_used(self):
        pass


class DataStatistic:
    def __init__(self, report_id):
        self.type = None
        self.report = self.__get_report(report_id)
        self.parent = ReportComponent.objects.get(id=self.report.parent_id)
        self.table_html = loader.get_template('reports/coverage/coverageDataStatistics.html')\
            .render({'DataStatistics': self.__get_data_stat()})

    def __get_report(self, report_id):
        try:
            self.type = 'safe'
            return ReportSafe.objects.get(id=report_id)
        except ObjectDoesNotExist:
            try:
                self.type = 'unsafe'
                return ReportUnsafe.objects.get(id=report_id)

            except ObjectDoesNotExist:
                try:
                    self.type = 'unknown'
                    return ReportUnknown.objects.get(id=report_id)
                except ObjectDoesNotExist:
                    raise BridgeException(_('The report was not found'))

    def __get_data_stat(self):
        if not self.parent.verification:
            raise ValueError("The parent is not verification report")
        data = []
        with self.parent.archive as fp:
            if os.path.splitext(fp.name)[-1] != '.zip':
                raise ValueError('Archive type is not supported')
            with zipfile.ZipFile(fp, 'r') as zfp:
                coverage = json.loads(zfp.read(self.parent.coverage).decode('utf8'))
                for val in sorted(coverage):
                    if val not in {'line coverage', 'function coverage'} and 'statistics' in coverage[val]:
                        data.append({
                            'tab': val, 'active': False, 'content': json_to_html(coverage[val]['statistics'])
                        })
        if len(data) > 0:
            data[0]['active'] = True
        return data
