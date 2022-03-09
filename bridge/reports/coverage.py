#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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

from django.http import Http404
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from bridge.vars import ETV_FORMAT, COVERAGE_FILE
from bridge.utils import ArchiveFileContent, BridgeException, construct_url

from reports.models import CoverageArchive, CoverageStatistics, CoverageDataStatistics

ROOT_DIRS_ORDER = ['source files', 'specifications', 'generated models']


def coverage_data_statistic(coverage):
    statistics = []
    active = True
    for data_stat in CoverageDataStatistics.objects.filter(coverage=coverage).order_by('name'):
        statistics.append({
            'name': data_stat.name, 'active': active,
            'content': json_to_html(data_stat.data)
        })
        active = False
    return statistics


def most_covered_lines(coverage: CoverageArchive):
    try:
        res = ArchiveFileContent(coverage, 'archive', COVERAGE_FILE)
    except Exception as e:
        raise BridgeException(_("Error while extracting source file: %(error)s") % {'error': str(e)})
    data = json.loads(res.content.decode('utf8'))
    return data.get('most covered lines')


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


class GetCoverageStatistics:
    def __init__(self, report, coverage_id=None):
        # Earlier only first found file with extension in ['.i', '.c', '.c.aux'] was opened
        self.coverage = self.__get_coverage_object(report, coverage_id)
        if not self.coverage:
            raise Http404('Coverage archive was not found')
        self.data = CoverageStatistics.objects.filter(coverage=self.coverage).order_by('id')
        self.data_statistic = coverage_data_statistic(self.coverage)
        self.most_covered = most_covered_lines(self.coverage)
        self.with_extra = self.coverage.has_extra

    def __get_coverage_object(self, report, coverage_id):
        parents_ids = set(report.get_ancestors(include_self=True).values_list('id', flat=True))
        qs_filters = {'report_id__in': parents_ids}
        if coverage_id:
            qs_filters['id'] = coverage_id
        return CoverageArchive.objects.filter(**qs_filters).order_by('-report_id').first()


class LeafCoverageStatistics:
    def __init__(self, coverage):
        self.coverage = coverage
        self.data = CoverageStatistics.objects.filter(coverage=self.coverage).order_by('id')
        self.data_statistic = coverage_data_statistic(coverage)
        self.most_covered = most_covered_lines(self.coverage)
        self.with_extra = False


class CoverageStatisticsBase:
    def __init__(self, coverage_id=None):
        self._coverage_id = coverage_id
        self.with_report_link = False
        self.has_extra = False

    def coverage_queryset(self):
        raise NotImplementedError('Coverage queryset is not implemented')

    def coverage_api(self, coverage_id):
        raise NotImplementedError('Coverage api url constructor is not implemented')

    @cached_property
    def coverages(self):
        cov_qs = self.coverage_queryset()
        coverages_list = []
        for cov in cov_qs:
            cov_data = {
                'name': cov.identifier, 'total': cov.total, 'url': self.coverage_api(cov.id),
                'details_url': construct_url('reports:coverage', cov.report_id, coverage_id=cov.id)
            }
            if self.with_report_link:
                cov_data['report'] = (cov.name, construct_url(
                    'reports:component', cov.report.decision.identifier, cov.report.identifier
                ))
            coverages_list.append(cov_data)
        return coverages_list

    @cached_property
    def statistics(self):
        cov_qs = self.coverage_queryset()
        if self._coverage_id:
            cov_obj = cov_qs.filter(id=self._coverage_id).first()
        else:
            cov_obj = cov_qs.first()
        if not cov_obj:
            return None
        self.has_extra = cov_obj.has_extra
        return CoverageStatistics.objects.filter(coverage=cov_obj).order_by('id')


class DecisionCoverageStatistics(CoverageStatisticsBase):
    def __init__(self, decision, coverage_id=None):
        self._decision = decision
        super(DecisionCoverageStatistics, self).__init__(coverage_id=coverage_id)
        if not self._decision.is_lightweight:
            self.with_report_link = True

    def coverage_queryset(self):
        qs = CoverageArchive.objects.filter(report__decision_id=self._decision.id).exclude(identifier='')
        if self.with_report_link:
            return qs.select_related('report', 'report__decision')
        return qs

    def coverage_api(self, coverage_id):
        return construct_url('jobs:api-get-coverage', self._decision.id, coverage_id=coverage_id)


class ReportCoverageStatistics(CoverageStatisticsBase):
    def __init__(self, report, coverage_id=None):
        self._report = report
        super(ReportCoverageStatistics, self).__init__(coverage_id=coverage_id)

    def coverage_queryset(self):
        return CoverageArchive.objects.filter(report=self._report).exclude(identifier='')

    def coverage_api(self, coverage_id):
        return construct_url('reports:api-coverage-table', self._report.id, coverage_id=coverage_id)


class VerificationCoverageStatistics(CoverageStatisticsBase):
    def __init__(self, report):
        self._report = report
        super(VerificationCoverageStatistics, self).__init__()

    def coverage_queryset(self):
        return CoverageArchive.objects.filter(report=self._report)

    def coverage_api(self, coverage_id):
        return construct_url('reports:api-coverage-table', self._report.id)


class FillCoverageStatistics:
    file_sep = '/'

    def __init__(self, coverage_obj):
        self.has_extra = False
        self.coverage_obj = coverage_obj
        self._statistics, self._data_stat = self.__get_statistics()
        self.__save_statistics()
        self.__save_data_statistics()

    def __get_statistics(self):
        try:
            res = ArchiveFileContent(self.coverage_obj, 'archive', COVERAGE_FILE)
        except Exception as e:
            raise BridgeException(_("Error while extracting source file: %(error)s") % {'error': str(e)})
        data = json.loads(res.content.decode('utf8'))
        if data.get('format') != ETV_FORMAT:
            raise BridgeException(_('Code coverage format is not supported'))
        if 'coverage statistics' not in data:
            raise BridgeException(_('Common code coverage file does not contain statistics'))
        return data['coverage statistics'], data['data statistics']

    def __save_statistics(self):
        CoverageStatistics.objects.filter(coverage=self.coverage_obj).delete()

        cnt = 0
        new_objects = {}
        for fname in self._statistics:
            cov_data = self._statistics[fname]
            if len(cov_data) == 4:
                cov_lines, tot_lines, cov_funcs, tot_func = cov_data
            else:
                cov_lines = cov_funcs = None
                tot_lines, tot_func = cov_data

            path_l = tuple(fname.split(self.file_sep))
            for i in range(len(path_l)):
                curr_path = path_l[:(i + 1)]
                if curr_path not in new_objects:
                    cnt += 1
                    parent_id = new_objects[path_l[:i]].identifier if i > 0 else None
                    new_objects[curr_path] = CoverageStatistics(
                        coverage_id=self.coverage_obj.id, identifier=cnt, parent=parent_id,
                        is_leaf=bool(i + 1 == len(path_l)),
                        name=path_l[i],
                        path='/'.join(curr_path),
                        depth=len(curr_path)
                    )
                if cov_lines is not None and cov_funcs is not None:
                    new_objects[curr_path].lines_covered += cov_lines
                    new_objects[curr_path].lines_total += tot_lines
                    new_objects[curr_path].funcs_covered += cov_funcs
                    new_objects[curr_path].funcs_total += tot_func
                    new_objects[curr_path].lines_covered_extra += cov_lines
                    new_objects[curr_path].funcs_covered_extra += cov_funcs
                else:
                    self.has_extra = True
                new_objects[curr_path].lines_total_extra += tot_lines
                new_objects[curr_path].funcs_total_extra += tot_func

        ordered_objects_list = list(sorted(new_objects.values(), key=lambda x: (x.is_leaf, x.name)))

        def __get_all_children(covstat_obj):
            children = []
            if covstat_obj.is_leaf:
                return children
            for obj in ordered_objects_list:
                if obj.parent == covstat_obj.identifier:
                    children.append(obj)
                    children.extend(__get_all_children(obj))
            return children

        ordered_objects = []
        for root_name in ROOT_DIRS_ORDER:
            root_path = (root_name,)
            if root_path not in new_objects:
                continue
            ordered_objects.append(new_objects[root_path])
            ordered_objects.extend(__get_all_children(new_objects[root_path]))

        CoverageStatistics.objects.bulk_create(ordered_objects)

    def __save_data_statistics(self):
        CoverageDataStatistics.objects.filter(coverage=self.coverage_obj).delete()
        new_objects = []
        for name in sorted(self._data_stat):
            new_objects.append(CoverageDataStatistics(
                coverage_id=self.coverage_obj.id, name=name, data=self._data_stat[name]
            ))
        CoverageDataStatistics.objects.bulk_create(new_objects)

    @property
    def total_coverage(self):
        total_statistics = [0, 0, 0, 0]
        for cov_obj in CoverageStatistics.objects.filter(coverage=self.coverage_obj, depth=1):
            assert isinstance(cov_obj, CoverageStatistics)
            total_statistics[0] += cov_obj.lines_covered
            total_statistics[1] += cov_obj.lines_total
            total_statistics[2] += cov_obj.funcs_covered
            total_statistics[3] += cov_obj.funcs_total
        lines_stat = 0
        if total_statistics[1] > 0:
            lines_stat = round(total_statistics[0] / total_statistics[1] * 100)
        funcs_stat = 0
        if total_statistics[3] > 0:
            funcs_stat = round(total_statistics[2] / total_statistics[3] * 100)
        return {'lines': '{}%'.format(lines_stat), 'funcs': '{}%'.format(funcs_stat)}


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
            raise BridgeException(_("Error while extracting source file: %(error)s") % {'error': str(e)})
        if res.content is None:
            return None
        data = json.loads(res.content.decode('utf8'))
        if data.get('format') != ETV_FORMAT:
            raise BridgeException(_('Code coverage format is not supported'))
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


class MostCoveredLines:
    coverage_postfix = '.cov.json'

    def __init__(self, coverage: CoverageArchive):
        self.coverage = coverage
        self._statistics = {}
        self._max_covered = 0

    def collect(self):
        try:
            res = ArchiveFileContent(self.coverage, 'archive', COVERAGE_FILE)
        except Exception as e:
            raise BridgeException(_("Error while extracting source file: %(error)s") % {'error': str(e)})
        data = json.loads(res.content.decode('utf8'))

        for filename in data['coverage statistics']:
            if data['coverage statistics'][filename][0] > 0:
                self.__parse_file(filename)
        print("Max covered:", self._max_covered)
        statistics = {}
        for filename in self._statistics:
            for line_num, cov_num in self._statistics[filename]:
                statistics['{}:{}'.format(filename, line_num)] = cov_num
        return list(sorted(statistics, key=lambda x: (-statistics[x], x)))[:30]

    def __parse_file(self, filename):
        try:
            res = ArchiveFileContent(self.coverage, 'archive', filename + self.coverage_postfix)
        except Exception as e:
            raise BridgeException(_("Error while extracting source file: %(error)s") % {'error': str(e)})
        data = json.loads(res.content.decode('utf8'))
        if 'line coverage' not in data:
            return

        lines_statistics = []
        for line_num, cov_num in data['line coverage'].items():
            self._max_covered = max(self._max_covered, cov_num)
            if cov_num == 0:
                continue
            if len(lines_statistics) == 0:
                lines_statistics.append((line_num, cov_num))
                continue
            for i in range(len(lines_statistics)):
                if lines_statistics[i][1] >= cov_num:
                    lines_statistics.insert(i, (line_num, cov_num))
                    break
            else:
                lines_statistics.append((line_num, cov_num))
            if len(lines_statistics) > 31:
                lines_statistics = lines_statistics[-30:]
        self._statistics[filename] = lines_statistics[-30:]

