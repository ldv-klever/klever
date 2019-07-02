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

import re
import json
from urllib.parse import unquote
from wsgiref.util import FileWrapper

from django.utils.translation import ugettext_lazy as _

from bridge.vars import ETV_FORMAT, COVERAGE_FILE
from bridge.utils import ArchiveFileContent, BridgeException, construct_url

from reports.models import CoverageArchive, ReportComponent, ReportSafe, ReportUnsafe, ReportUnknown

TABLE_STAT_COLOR = ['#f18fa6', '#f1c0b2', '#f9e19b', '#e4f495', '#acf1a8']

ROOT_DIRS_ORDER = ['source files', 'specifications', 'generated models']


def coverage_url_and_total(report, many=False):
    url_name = 'reports:coverage'
    if isinstance(report, (ReportSafe, ReportUnsafe)):
        cov_qs = CoverageArchive.objects.filter(report_id=report.parent_id).only('total')
        if len(cov_qs):
            return construct_url(url_name, report.parent_id), cov_qs[0].total
    elif isinstance(report, ReportUnknown):
        cov_qs = CoverageArchive.objects.filter(report_id=report.parent_id, report__verification=True).only('total')
        if len(cov_qs):
            return construct_url(url_name, report.parent_id), cov_qs[0].total
    elif isinstance(report, ReportComponent):
        if report.verification:
            cov_qs = CoverageArchive.objects.filter(report_id=report.id).only('total')
            if len(cov_qs):
                return construct_url(url_name, report.id), cov_qs[0].total
        elif many:
            cov_qs = CoverageArchive.objects\
                .filter(report_id=report.id).exclude(identifier='').only('id', 'identifier')
            return list({
                'name': cov.identifier,'url': construct_url(url_name, report.id, coverage_id=cov.id), 'total': cov.total
            } for cov in cov_qs)
    return None, None


def json_to_html(data):
    tab_len = 2

    def span(text, obj_class):
        return '<span class="{0}">{1}</span>'.format(obj_class, text)

    data = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)

    data_html = []
    for line in data.split('\n'):
        line = line.replace('\t', ' ' * tab_len).replace('&', '&amp;') \
            .replace('<', '&lt;').replace('>', '&gt;')

        m = re.match(r'^(\s*)(\".*?\"):\s(.*)$', line)
        if m is not None:
            if m.group(3) in {'{', '['}:
                data_html.append('{0}{1}: {2}'.format(
                    m.group(1), span(m.group(2), 'COVJsonKey'), m.group(3)
                ))
                continue
            m2 = re.match(r'^(\d.*?)(,?)$', m.group(3))
            if m2 is not None:
                data_html.append('{0}{1}: {2}{3}'.format(
                    m.group(1), span(m.group(2), 'COVJsonKey'),
                    span(m2.group(1), 'COVJsonNum'), m2.group(2)
                ))
                continue
            m2 = re.match(r'^(\".*?\")(,?)$', m.group(3))
            if m2 is not None:
                data_html.append('{0}{1}: {2}{3}'.format(
                    m.group(1), span(m.group(2), 'COVJsonKey'),
                    span(m2.group(1), 'COVJsonText'), m2.group(2)
                ))
                continue
            m2 = re.match(r'^(null|true|false)(,?)$', m.group(3))
            if m2 is not None:
                data_html.append('{0}{1}: {2}{3}'.format(
                    m.group(1), span(m.group(2), 'COVJsonKey'),
                    span(m2.group(1), 'COVJsonWord'), m2.group(2)
                ))
                continue
        m = re.match(r'^(\s*)(\".*\")(,?)$', line)
        if m is not None:
            data_html.append('{0}{1}{2}'.format(m.group(1), span(m.group(2), 'COVJsonText'), m.group(3)))
            continue
        m = re.match(r'^(\s*)(\d.*?)(,?)$', line)
        if m is not None:
            data_html.append('{0}{1}{2}'.format(m.group(1), span(m.group(2), 'COVJsonNum'), m.group(3)))
            continue
        m = re.match(r'^(\s*)(null|true|false)(,?)$', line)
        if m is not None:
            data_html.append('{0}{1}{2}'.format(m.group(1), span(m.group(2), 'COVJsonWord'), m.group(3)))
            continue
        data_html.append(line)
    return '<br>'.join(list(span(s, 'COVJsonLine') for s in data_html))


class CoverageStatistics:
    file_sep = '/'

    def __init__(self, report, coverage_id=None):
        self.coverage = self.__get_coverage_object(report, coverage_id)
        self.data, self.data_statistic = self.__collect_statistics()

    def __get_coverage_object(self, report, coverage_id):
        parents_ids = set(report.get_ancestors(include_self=True).values_list('id', flat=True))
        qs_filters = {'report_id__in': parents_ids}
        if coverage_id:
            qs_filters['id'] = coverage_id
        return CoverageArchive.objects.filter(**qs_filters).order_by('-report_id').first()

    def __get_statistics(self):
        try:
            res = ArchiveFileContent(self.coverage, 'archive', COVERAGE_FILE)
        except Exception as e:
            raise BridgeException(_("Error while extracting source: %(error)s") % {'error': str(e)})
        data = json.loads(res.content.decode('utf8'))
        if data.get('format') != ETV_FORMAT:
            raise BridgeException(_('Sources coverage format is not supported'))
        if not data.get('coverage statistics'):
            raise BridgeException(_('Common coverage file does not contain statistics'))
        return data['coverage statistics'], data['data statistics']

    def __get_data_statistics(self, data):
        statistics = []
        active = True
        for name in data:
            statistics.append({
                'tab': name, 'active': active, 'content': json_to_html(data[name])
            })
            active = False
        return statistics

    def __collect_statistics(self):
        if not self.coverage:
            return None, None

        statistics, data_statistics = self.__get_statistics()

        hide_all = False
        if len(statistics) > 30:
            hide_all = True

        cnt = 0
        parents = {}
        for fname in statistics:
            path = fname.split(self.file_sep)
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

        for fname in statistics:
            display = False
            if not hide_all and any(fname.endswith(x) for x in ['.i', '.c', '.c.aux']):
                display = True
            cov_lines, tot_lines, cov_funcs, tot_func = statistics[fname]
            parent = fname
            while parent is not None:
                parents[parent]['lines']['covered'] += cov_lines
                parents[parent]['lines']['total'] += tot_lines
                parents[parent]['funcs']['covered'] += cov_funcs
                parents[parent]['funcs']['total'] += tot_func
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
                break
        return ordered_data, self.__get_data_statistics(data_statistics)


class GetCoverageData:
    coverage_postfix = '.cov.json'

    def __init__(self, coverage, line, filename):
        self._coverage = coverage
        self._line = str(line)
        self._file_name = self.__parse_file_name(filename)
        self.data = self.__get_coverage_data()

    def __parse_file_name(self, file_name):
        name = unquote(file_name)
        if name.startswith('/'):
            name = name[1:]
        return name + self.coverage_postfix

    def __get_coverage_data(self):
        try:
            res = ArchiveFileContent(self._coverage, 'archive', self._file_name, not_exists_ok=True)
        except Exception as e:
            raise BridgeException(_("Error while extracting source: %(error)s") % {'error': str(e)})
        if res.content is None:
            return None
        data = json.loads(res.content.decode('utf8'))
        if data.get('format') != ETV_FORMAT:
            raise BridgeException(_('Sources coverage format is not supported'))
        if not data.get('data'):
            return None
        if not data['data'].get(self._line):
            return None
        return list({
            'name': data['name'], 'value': json_to_html(data['value'])
        } for data in data['data'][self._line])


class CoverageGenerator(FileWrapper):
    def __init__(self, cov_arch):
        assert isinstance(cov_arch, CoverageArchive), 'Unknown error'
        self.name = "coverage-{}.zip".format(cov_arch.identifier or 'verification')
        self.size = len(cov_arch.archive)
        super().__init__(cov_arch.archive, 8192)
