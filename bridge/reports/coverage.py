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
import time
import hashlib
import zipfile
from io import StringIO

from django.core.exceptions import ObjectDoesNotExist
from django.core.files import File as NewFile
from django.db import transaction
from django.template import loader

from bridge.vars import COVERAGE_FILE

from reports.models import ReportComponent, CoverageFile, CoverageData, CoverageDataValue, CoverageDataStatistics,\
    CoverageArchive

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
    if curr_cov == 0:
        return 'rgb(200, 190, 255)'
    green = 140 + int(100 * (1 - curr_cov / max_cov))
    blue = 140 + int(100 * (1 - curr_cov / max_cov)) - delta
    return 'rgb(255, %s, %s)' % (green, blue)


def get_legend(max_cov, leg_type, number=5, with_zero=False):
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
    if with_zero:
        colors.append((0, coverage_color(0, max_cov, delta)))
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
    def __init__(self, report_id, cov_arch_id, with_data):
        if cov_arch_id is None:
            self.report = ReportComponent.objects.get(id=report_id)
            self.cov_arch = self.report.coverages.order_by('identifier').first()
        else:
            self.cov_arch = CoverageArchive.objects.get(id=cov_arch_id)
            self.report = self.cov_arch.report
        self.coverage_archives = self.report.coverages.order_by('identifier').values_list('id', 'identifier')
        self.job = self.report.root.job

        self.parents = get_parents(self.report)
        self._statistic = CoverageStatistics(self.cov_arch)
        self.statistic_table = self._statistic.table_data
        if self._statistic.first_file:
            self.first_file = GetCoverageSrcHTML(self.cov_arch.id, self._statistic.first_file, with_data)
        if with_data:
            self.data_statistic = DataStatistic(self.cov_arch.id).table_html

    def __is_not_used(self):
        pass


class GetCoverageSrcHTML:
    def __init__(self, cov_arch_id, filename, with_data):
        self._cov_arch = CoverageArchive.objects.get(id=cov_arch_id)
        self.filename = os.path.normpath(filename).replace('\\', '/')
        try:
            self._covfile = CoverageFile.objects.get(archive=self._cov_arch, name=self.filename)
        except ObjectDoesNotExist:
            self._covfile = None
        self._with_data = with_data

        self._content = self.__get_arch_content()
        self._max_cov_line, self._max_cov_func, self._line_coverage, self._func_coverage = self.__get_coverage()

        self._is_comment = False
        self._is_text = False
        self._text_quote = None
        self._total_lines = 1
        self._lines_with_data = set()
        self.data_html = ''
        if self._with_data:
            self.data_html = self.__get_data()
        self.src_html = self.__get_source_html()
        self.legend = loader.get_template('reports/coverage/cov_legend.html').render({'legend': {
            'lines': get_legend(self._max_cov_line, 'lines', 5, True),
            'funcs': get_legend(self._max_cov_func, 'funcs', 5, False)
        }})

    def __get_arch_content(self):
        with self._cov_arch.archive as fp:
            if os.path.splitext(fp.name)[-1] != '.zip':
                raise ValueError('Archive type is not supported')
            with zipfile.ZipFile(fp, 'r') as zfp:
                return zfp.read(self.filename).decode('utf8')

    def __get_coverage(self):
        if self._covfile is None:
            return 0, 0, {}, {}
        max_line_cov = 0
        max_func_cov = 0
        line_data = {}
        func_data = {}
        with self._covfile.file.file as fp:
            coverage = json.loads(fp.read().decode('utf8'))
        for linecov in coverage[0]:
            max_line_cov = max(max_line_cov, linecov[0])
            for line in linecov[1]:
                if isinstance(line, int):
                    line_data[line] = linecov[0]
                elif isinstance(line, list) and len(line) == 2:
                    for i in range(*line):
                        line_data[i] = linecov[0]
                    line_data[line[1]] = linecov[0]
        for linecov in coverage[1]:
            max_func_cov = max(max_func_cov, linecov[0])
            for line in linecov[1]:
                if isinstance(line, int):
                    func_data[line] = linecov[0]
                elif isinstance(line, list) and len(line) == 2:
                    for i in range(*line):
                        func_data[i] = linecov[0]
                    func_data[line[1]] = linecov[0]
        return max_line_cov, max_func_cov, line_data, func_data

    def __get_data(self):
        data_map = []
        data_ids = set()
        last_i = -1
        if self._covfile is not None:
            for data_id, dataname, line in CoverageData.objects.filter(covfile=self._covfile)\
                    .values_list('data_id', 'data__name', 'line').order_by('line', 'data__name'):
                self._lines_with_data.add(line)
                if last_i >= 0 and data_map[last_i]['line'] == line:
                    data_map[last_i]['content'].append([dataname, data_id, False])
                else:
                    data_map.append({'line': line, 'content': [[dataname, data_id, True]]})
                    last_i += 1
                data_ids.add(data_id)

        return loader.get_template('reports/coverage/coverageData.html').render({
            'data_map': data_map,
            'data_values': CoverageDataValue.objects.filter(id__in=data_ids).values_list('id', 'value')
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
        if line in self._line_coverage:
            line_num['data'].append(('number', self._line_coverage[line]))
            code['color'] = coverage_color(self._line_coverage[line], self._max_cov_line)
            code['data'] = [('number', self._line_coverage[line])]

        if line in self._lines_with_data:
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
        if self._with_data and line in self._lines_with_data:
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
    def __init__(self, cov_arch):
        self.cov_arch = cov_arch
        self.first_file = None
        self.table_data = self.__get_table_data()

    def __get_table_data(self):
        coverage = {}
        for c in CoverageFile.objects.filter(archive=self.cov_arch):
            coverage[c.name] = c

        hide_all = False
        if len(coverage) > 30:
            hide_all = True

        cnt = 0
        parents = {}
        for fname in coverage:
            path = fname.split('/')
            for i in range(len(path)):
                cnt += 1
                curr_path = '/'.join(path[:(i + 1)])
                if curr_path not in parents:
                    parent_id = parent = None
                    if i > 0:
                        parent = '/'.join(path[:i])
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

        for fname in coverage:
            display = False
            if not hide_all and any(fname.endswith(x) for x in ['.i', '.c', '.c.aux']):
                display = True
            covered_lines = coverage[fname].covered_lines
            total_lines = coverage[fname].total_lines
            covered_funcs = coverage[fname].covered_funcs
            total_funcs = coverage[fname].total_funcs
            parent = fname
            while parent is not None:
                parents[parent]['lines']['covered'] += covered_lines
                parents[parent]['lines']['total'] += total_lines
                parents[parent]['funcs']['covered'] += covered_funcs
                parents[parent]['funcs']['total'] += total_funcs
                if parents[parent]['is_dir'] and display or parents[parent]['parent'] is None and not hide_all:
                    parents[parent]['display'] = True
                parent = parents[parent]['parent']

        for fname in parents:
            if parents[fname]['lines']['total'] > 0:
                div = parents[fname]['lines']['covered'] / parents[fname]['lines']['total']
                parents[fname]['lines']['percent'] = '%s%%' % int(100 * div)
                color_id = int(div * len(TABLE_STAT_COLOR))
                if color_id >= len(TABLE_STAT_COLOR):
                    color_id = len(TABLE_STAT_COLOR) - 1
                elif color_id < 0:
                    color_id = 0
                parents[fname]['lines']['color'] = TABLE_STAT_COLOR[color_id]
            if parents[fname]['funcs']['total'] > 0:
                div = parents[fname]['funcs']['covered'] / parents[fname]['funcs']['total']
                parents[fname]['funcs']['percent'] = '%s%%' % int(100 * div)
                color_id = int(div * len(TABLE_STAT_COLOR))
                if color_id >= len(TABLE_STAT_COLOR):
                    color_id = len(TABLE_STAT_COLOR) - 1
                elif color_id < 0:
                    color_id = 0
                parents[fname]['funcs']['color'] = TABLE_STAT_COLOR[color_id]

        other_data = list(sorted(parents.values(), key=lambda x: (not x['is_dir'], x['title'])))

        def __get_all_children(file_info, depth):
            children = []
            if not file_info['is_dir']:
                return children
            for fi in other_data:
                if fi['parent_id'] == file_info['id']:
                    fi['indent'] = '    ' * depth
                    children.append(fi)
                    children.extend(__get_all_children(fi, depth + 1))
            return children

        first_lvl = []
        for root_name in ROOT_DIRS_ORDER:
            if root_name in parents:
                first_lvl.append(parents[root_name])

        ordered_data = []
        for fd in first_lvl:
            fd['display'] = True
            ordered_data.append(fd)
            ordered_data.extend(__get_all_children(fd, 1))
        for fd in ordered_data:
            if hide_all:
                fd['display'] = True
            if not fd['is_dir'] and parents[fd['parent']]['display']:
                self.first_file = fd['path']
                break
        return ordered_data

    def __is_not_used(self):
        pass


class DataStatistic:
    def __init__(self, cov_arch_id):
        self.table_html = loader.get_template('reports/coverage/coverageDataStatistics.html')\
            .render({'DataStatistics': self.__get_data_stat(cov_arch_id)})

    def __get_data_stat(self, cov_arch_id):
        self.__is_not_used()
        data = []
        active = True
        for stat in CoverageDataStatistics.objects.filter(archive_id=cov_arch_id).order_by('name'):
            with stat.data.file as fp:
                data.append({'tab': stat.name, 'active': active, 'content': fp.read().decode('utf8')})
            active = False
        return data

    def __is_not_used(self):
        pass


class CreateCoverageFiles:
    def __init__(self, cov_arch, coverage):
        self._cov_arch = cov_arch
        self._coverage = coverage
        self._line_coverage = {}
        self._func_coverage = {}
        self._coverage_stat = {}
        self.__get_coverage_data()
        self.__create_files()
        self.files = self.__get_saved_files()

    def __get_coverage_data(self):
        for data in self._coverage['line coverage']:
            for fname in data[1]:
                if fname not in self._line_coverage:
                    self._line_coverage[fname] = []
                    self._coverage_stat[fname] = [0, 0, 0, 0]
                self._line_coverage[fname].append([data[0], data[1][fname]])
                if data[0] > 0:
                    self._coverage_stat[fname][0] += self.__num_of_lines(data[1][fname])
                self._coverage_stat[fname][1] += self.__num_of_lines(data[1][fname])
        for data in self._coverage['function coverage']['coverage']:
            for fname in data[1]:
                if fname not in self._func_coverage:
                    self._func_coverage[fname] = []
                if fname not in self._coverage_stat:
                    self._coverage_stat[fname] = [0, 0, 0, 0]
                self._func_coverage[fname].append([data[0], data[1][fname]])
                if data[0] > 0:
                    self._coverage_stat[fname][2] += self.__num_of_lines(data[1][fname])
                self._coverage_stat[fname][3] += self.__num_of_lines(data[1][fname])

    @transaction.atomic
    def __create_files(self):
        for fname in set(self._line_coverage) | set(self._func_coverage):
            file_coverage = StringIO(json.dumps(
                [self._line_coverage.get(fname, []), self._func_coverage.get(fname, [])]
            ))
            covfile = CoverageFile(
                archive=self._cov_arch, name=fname,
                covered_lines=self._coverage_stat[fname][0], total_lines=self._coverage_stat[fname][1],
                covered_funcs=self._coverage_stat[fname][2], total_funcs=self._coverage_stat[fname][3]
            )
            covfile.file.save('coverage.json', NewFile(file_coverage))

    def __num_of_lines(self, lines):
        self.__is_not_used()
        num = 0
        for l in lines:
            if isinstance(l, int):
                num += 1
            elif isinstance(l, list) and len(l) == 2 and isinstance(l[0], int) \
                    and isinstance(l[1], int) and l[0] <= l[1]:
                num += l[1] - l[0] + 1
        return num

    def __get_saved_files(self):
        files = {}
        for f_id, fname in CoverageFile.objects.filter(archive=self._cov_arch).values_list('id', 'name'):
            files[fname] = f_id
        return files

    def __is_not_used(self):
        pass


class FillCoverageCache:
    @exec_time
    def __init__(self, report):
        for cov_arch, data in self.__get_coverage_data(report):
            self._data = data
            self._cov_arch = cov_arch
            self._files = CreateCoverageFiles(self._cov_arch, self._data).files
            del self._data['line coverage'], self._data['function coverage']
            self.__fill_data()

    def __get_coverage_data(self, report):
        self.__is_not_used()
        for cov_arch in report.coverages.all():
            with cov_arch.archive as fp:
                with zipfile.ZipFile(fp, 'r') as zfp:
                    yield cov_arch, json.loads(zfp.read(COVERAGE_FILE).decode('utf8'))

    def __fill_data(self):
        covdata = []
        data_values = {}
        for vid, dataname, hashsum in CoverageDataValue.objects.values_list('id', 'name', 'hashsum'):
            data_values[(dataname, hashsum)] = vid

        for dataname in self._data:
            covdatastat = CoverageDataStatistics(archive=self._cov_arch, name=dataname)
            covdatastat.data.save('CoverageData.html', NewFile(StringIO(
                json_to_html(self._data[dataname]['statistics'])
            )))
            for data in self._data[dataname]['values']:
                dataval = json_to_html(data[0])
                hashsum = hashlib.md5(dataval.encode('utf8')).hexdigest()
                if (dataname, hashsum) not in data_values:
                    data_values[(dataname, hashsum)] = CoverageDataValue.objects\
                        .create(hashsum=hashsum, name=dataname, value=dataval).id
                data_id = data_values[(dataname, hashsum)]
                for fname in data[1]:
                    if fname not in self._files:
                        self._files[fname] = CoverageFile.objects.create(archive=self._cov_arch, name=fname).id
                    for line in data[1][fname]:
                        if isinstance(line, int):
                            covdata.append(CoverageData(covfile_id=self._files[fname], line=line, data_id=data_id))
                        elif isinstance(line, list) and len(line) == 2:
                            for i in range(*line):
                                covdata.append(CoverageData(covfile_id=self._files[fname], line=i, data_id=data_id))
                            covdata.append(CoverageData(covfile_id=self._files[fname], line=line[1], data_id=data_id))

        CoverageData.objects.bulk_create(covdata)

    def __is_not_used(self):
        pass
