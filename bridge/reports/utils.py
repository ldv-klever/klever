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
import json
import zipfile
import xml.etree.ElementTree as ETree
from xml.dom import minidom

from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.urlresolvers import reverse
from django.db.models import Q, Count, Case, When
from django.utils.translation import ugettext_lazy as _

from bridge.vars import UNSAFE_VERDICTS, SAFE_VERDICTS, VIEW_TYPES
from bridge.tableHead import Header
from bridge.utils import logger
from bridge.ZipGenerator import ZipStream

from reports.models import ReportComponent, Attr, AttrName, ReportAttr, ReportUnsafe, ReportSafe, ReportUnknown,\
    ReportRoot
from marks.models import UnknownProblem, UnsafeReportTag, SafeReportTag

from users.utils import DEF_NUMBER_OF_ELEMENTS, ViewData
from jobs.utils import get_resource_data, get_user_time, get_user_memory
from marks.tables import SAFE_COLOR, UNSAFE_COLOR


REP_MARK_TITLES = {
    'mark_num': _('Mark'),
    'mark_verdict': _("Verdict"),
    'mark_result': _('Similarity'),
    'mark_status': _('Status'),
    'number': _('#'),
    'component': _('Component'),
    'marks_number': _("Number of associated marks"),
    'report_verdict': _("Total verdict"),
    'tags': _('Tags'),
    'parent_cpu': _('Verifiers cpu time'),
    'parent_wall': _('Verifiers wall time'),
    'parent_memory': _('Verifiers memory')
}

MARK_COLUMNS = ['mark_verdict', 'mark_result', 'mark_status']


def computer_description(computer):
    computer = json.loads(computer)
    data = []
    comp_name = _('Unknown')
    for comp_data in computer:
        if isinstance(comp_data, dict):
            data_name = str(next(iter(comp_data)))
            if data_name == 'node name':
                comp_name = str(comp_data[data_name])
            else:
                data.append([data_name, str(comp_data[data_name])])
    return {
        'name': comp_name,
        'data': data
    }


def get_parents(report):
    parents_data = []
    try:
        parent = ReportComponent.objects.get(id=report.parent_id)
    except ObjectDoesNotExist:
        parent = None
    while parent is not None:
        parent_attrs = []
        for rep_attr in parent.attrs.order_by('attr__name__name').values_list('attr__name__name', 'attr__value'):
            parent_attrs.append(rep_attr)
        parents_data.insert(0, {
            'title': parent.component.name,
            'href': reverse('reports:component', args=[report.root.job_id, parent.id]),
            'attrs': parent_attrs,
            'has_coverage': (parent.covnum > 0)
        })
        try:
            parent = ReportComponent.objects.get(id=parent.parent_id)
        except ObjectDoesNotExist:
            parent = None
    return parents_data


def get_leaf_resources(user, report):
    if all(x is not None for x in [report.wall_time, report.cpu_time, report.memory]):
        rd = get_resource_data(user.extended.data_format, user.extended.accuracy, report)
        return {'wall_time': rd[0], 'cpu_time': rd[1], 'memory': rd[2]}
    return None


def report_resources(report, user):
    if all(x is not None for x in [report.wall_time, report.cpu_time, report.memory]):
        rd = get_resource_data(user.extended.data_format, user.extended.accuracy, report)
        return {'wall_time': rd[0], 'cpu_time': rd[1], 'memory': rd[2]}
    return None


class ReportAttrsTable:
    def __init__(self, report):
        self.report = report
        columns, values = self.__self_data()
        self.table_data = {'header': Header(columns, REP_MARK_TITLES).struct, 'values': values}

    def __self_data(self):
        columns = []
        values = []
        for a_name, a_val in self.report.attrs.order_by('id').values_list('attr__name__name', 'attr__value'):
            columns.append(a_name)
            values.append(a_val)
        return columns, values


class SafesTable:
    def __init__(self, user, report, view=None, view_id=None, page=1,
                 verdict=None, confirmed=None, tag=None, attr=None):
        self.user = user
        self.report = report
        self.verdict = verdict
        self.confirmed = confirmed
        self.tag = tag
        self.attr = attr

        self.view = ViewData(self.user, VIEW_TYPES[5][0], view=view, view_id=view_id)

        self.selected_columns = self.__selected()
        self.available_columns = self.__available()

        self.verdicts = SAFE_VERDICTS
        columns, values = self.__safes_data()
        self.paginator = None
        self.table_data = {'header': Header(columns, REP_MARK_TITLES).struct, 'values': self.__get_page(page, values)}

    def __selected(self):
        columns = []
        for col in self.view['columns']:
            if col not in {'marks_number', 'report_verdict', 'tags', 'parent_cpu', 'parent_wall', 'parent_memory'}:
                return []
            col_title = col
            if col_title in REP_MARK_TITLES:
                col_title = REP_MARK_TITLES[col_title]
            columns.append({'value': col, 'title': col_title})
        return columns

    def __available(self):
        self.__is_not_used()
        columns = []
        for col in ['marks_number', 'report_verdict', 'tags', 'parent_cpu', 'parent_wall', 'parent_memory']:
            col_title = col
            if col_title in REP_MARK_TITLES:
                col_title = REP_MARK_TITLES[col_title]
            columns.append({'value': col, 'title': col_title})
        return columns

    def __safes_data(self):
        data = {}
        columns = ['number']
        columns.extend(self.view['columns'])

        safes_filters = {}
        if isinstance(self.confirmed, bool) and self.confirmed:
            safes_filters['safe__has_confirmed'] = True
        if self.verdict is not None:
            safes_filters['safe__verdict'] = self.verdict
        else:
            if 'verdict' in self.view:
                safes_filters['safe__verdict__in'] = self.view['verdict']
            if self.attr is not None:
                safes_filters['safe__attrs__attr'] = self.attr

        if 'parent_cpu' in self.view:
            parent_cpu_value = float(self.view['parent_cpu'][1].replace(',', '.'))
            if self.view['parent_cpu'][2] == 's':
                parent_cpu_value *= 1000
            elif self.view['parent_cpu'][2] == 'm':
                parent_cpu_value *= 60000
            safes_filters['safe__cpu_time__%s' % self.view['parent_cpu'][0]] = parent_cpu_value
        if 'parent_wall' in self.view:
            parent_wall_value = float(self.view['parent_wall'][1].replace(',', '.'))
            if self.view['parent_wall'][2] == 's':
                parent_wall_value *= 1000
            elif self.view['parent_wall'][2] == 'm':
                parent_wall_value *= 60000
            safes_filters['safe__wall_time__%s' % self.view['parent_wall'][0]] = parent_wall_value
        if 'parent_memory' in self.view:
            parent_memory_value = float(self.view['parent_memory'][1].replace(',', '.'))
            if self.view['parent_memory'][2] == 'KB':
                parent_memory_value *= 1024
            elif self.view['parent_memory'][2] == 'MB':
                parent_memory_value *= 1024 * 1024
            elif self.view['parent_memory'][2] == 'GB':
                parent_memory_value *= 1024 * 1024 * 1024
            safes_filters['safe__memory__%s' % self.view['parent_memory'][0]] = parent_memory_value

        leaves_set = self.report.leaves.filter(**safes_filters).exclude(safe=None).annotate(
            marks_number=Count('safe__markreport_set'),
            confirmed=Count(Case(When(safe__markreport_set__type='1', then=1)))
        ).values('safe_id', 'confirmed', 'marks_number', 'safe__verdict', 'safe__parent_id',
                 'safe__cpu_time', 'safe__wall_time', 'safe__memory')

        if 'marks_number' in self.view:
            if self.view['marks_number'][0] == 'confirmed':
                marknum_filter = 'confirmed__%s' % self.view['marks_number'][1]
            else:
                marknum_filter = 'marks_number__%s' % self.view['marks_number'][1]
            leaves_set = leaves_set.filter(**{marknum_filter: int(self.view['marks_number'][2])})

        include_confirmed = 'hidden' not in self.view or 'confirmed_marks' not in self.view['hidden']

        reports = {}
        for leaf in leaves_set:
            if include_confirmed:
                marks_num = "%s (%s)" % (leaf['confirmed'], leaf['marks_number'])
            else:
                marks_num = str(leaf['marks_number'])
            reports[leaf['safe_id']] = {
                'marks_number': marks_num,
                'verdict': leaf['safe__verdict'],
                'parent_id': leaf['safe__parent_id'],
                'parent_cpu': leaf['safe__cpu_time'],
                'parent_wall': leaf['safe__wall_time'],
                'parent_memory': leaf['safe__memory'],
                'tags': {}
            }
        for r_id, tag in SafeReportTag.objects.filter(report_id__in=reports).values_list('report_id', 'tag__tag'):
            reports[r_id]['tags'][tag] = reports[r_id]['tags'].get(tag, 0) + 1
        for r_id, a_name, a_val in ReportAttr.objects.filter(report_id__in=reports).order_by('id') \
                .values_list('report_id', 'attr__name__name', 'attr__value'):
            if a_name not in data:
                columns.append(a_name)
                data[a_name] = {}
            data[a_name][r_id] = a_val

        reports_ordered = []
        if 'order' in self.view and self.view['order'][1] == 'attr' and self.view['order'][2] in data:
            for rep_id in data[self.view['order'][2]]:
                if self.__has_tag(reports[rep_id]['tags']):
                    reports_ordered.append((data[self.view['order'][2]][rep_id], rep_id))
            reports_ordered = [x[1] for x in sorted(reports_ordered, key=lambda x: x[0])]
            if self.view['order'][0] == 'up':
                reports_ordered = list(reversed(reports_ordered))
        elif 'order' in self.view and self.view['order'][1] in {'parent_cpu', 'parent_wall', 'parent_memory'}:
            for attr in data:
                for rep_id in data[attr]:
                    order_id = (reports[rep_id][self.view['order'][1]], rep_id)
                    if order_id not in reports_ordered and self.__has_tag(reports[rep_id]['tags']):
                        reports_ordered.append(order_id)
            reports_ordered = [x[1] for x in sorted(reports_ordered, key=lambda x: x[0])]
            if self.view['order'][0] == 'up':
                reports_ordered = list(reversed(reports_ordered))
        else:
            for attr in data:
                for rep_id in data[attr]:
                    if rep_id not in reports_ordered and self.__has_tag(reports[rep_id]['tags']):
                        reports_ordered.append(rep_id)
            reports_ordered = sorted(reports_ordered)

        for r_id in reports:
            tags_str = []
            for t_name in sorted(reports[r_id]['tags']):
                if reports[r_id]['tags'][t_name] == 1:
                    tags_str.append(t_name)
                else:
                    tags_str.append("%s (%s)" % (t_name, reports[r_id]['tags'][t_name]))
            reports[r_id]['tags'] = '; '.join(tags_str)

        cnt = 1
        values_data = []
        for rep_id in reports_ordered:
            values_row = []
            for col in columns:
                val = '-'
                href = None
                color = None
                if col in data:
                    if rep_id in data[col]:
                        val = data[col][rep_id]
                        if not self.__filter_attr(col, val):
                            break
                elif col == 'number':
                    val = cnt
                    href = reverse('reports:safe', args=[rep_id])
                elif col == 'marks_number':
                    val = reports[rep_id]['marks_number']
                elif col == 'report_verdict':
                    for s in SAFE_VERDICTS:
                        if s[0] == reports[rep_id]['verdict']:
                            val = s[1]
                            break
                    color = SAFE_COLOR[reports[rep_id]['verdict']]
                elif col == 'tags':
                    if len(reports[rep_id]['tags']) > 0:
                        val = reports[rep_id]['tags']
                elif col == 'parent_cpu':
                    val = get_user_time(self.user, reports[rep_id]['parent_cpu'])
                elif col == 'parent_wall':
                    val = get_user_time(self.user, reports[rep_id]['parent_wall'])
                elif col == 'parent_memory':
                    val = get_user_memory(self.user, reports[rep_id]['parent_memory'])
                values_row.append({'value': val, 'color': color, 'href': href})
            else:
                cnt += 1
                values_data.append(values_row)
        return columns, values_data

    def __has_tag(self, tags):
        if self.tag is None and 'tags' not in self.view:
            return True
        elif self.tag is not None and self.tag in tags:
            return True
        elif 'tags' in self.view:
            view_tags = list(x.strip() for x in self.view['tags'][0].split(';'))
            return all(t in tags for t in view_tags)
        return False

    def __filter_attr(self, attribute, value):
        if 'attr' in self.view:
            attr_name = self.view['attr'][0]
            ftype = self.view['attr'][1]
            attr_val = self.view['attr'][2]
            if attr_name is not None and attr_name.lower() == attribute.lower():
                if ftype == 'iexact' and attr_val.lower() != value.lower():
                    return False
                elif ftype == 'istartswith' and not value.lower().startswith(attr_val.lower()):
                    return False
                elif ftype == 'iendswith' and not value.lower().endswith(attr_val.lower()):
                    return False
        return True

    def __get_page(self, page, values):
        num_per_page = DEF_NUMBER_OF_ELEMENTS
        if 'elements' in self.view:
            num_per_page = int(self.view['elements'][0])
        self.paginator = Paginator(values, num_per_page)
        try:
            values = self.paginator.page(page)
        except PageNotAnInteger:
            values = self.paginator.page(1)
        except EmptyPage:
            values = self.paginator.page(self.paginator.num_pages)
        return values

    def __is_not_used(self):
        pass


class UnsafesTable:
    def __init__(self, user, report, view=None, view_id=None, page=1,
                 verdict=None, confirmed=None, tag=None, attr=None):
        self.user = user
        self.report = report
        self.verdict = verdict
        self.confirmed = confirmed
        self.tag = tag
        self.attr = attr

        self.view = ViewData(self.user, VIEW_TYPES[4][0], view=view, view_id=view_id)

        self.selected_columns = self.__selected()
        self.available_columns = self.__available()

        self.verdicts = UNSAFE_VERDICTS
        columns, values = self.__unsafes_data()
        self.paginator = None
        self.table_data = {'header': Header(columns, REP_MARK_TITLES).struct, 'values': self.__get_page(page, values)}

    def __selected(self):
        columns = []
        for col in self.view['columns']:
            if col not in {'marks_number', 'report_verdict', 'tags', 'parent_cpu', 'parent_wall', 'parent_memory'}:
                return []
            col_title = col
            if col_title in REP_MARK_TITLES:
                col_title = REP_MARK_TITLES[col_title]
            columns.append({'value': col, 'title': col_title})
        return columns

    def __available(self):
        self.__is_not_used()
        columns = []
        for col in ['marks_number', 'report_verdict', 'tags', 'parent_cpu', 'parent_wall', 'parent_memory']:
            col_title = col
            if col_title in REP_MARK_TITLES:
                col_title = REP_MARK_TITLES[col_title]
            columns.append({'value': col, 'title': col_title})
        return columns

    def __unsafes_data(self):
        data = {}
        columns = ['number']
        columns.extend(self.view['columns'])

        unsafes_filters = {}
        if isinstance(self.confirmed, bool) and self.confirmed:
            unsafes_filters['unsafe__has_confirmed'] = True
        if self.verdict is not None:
            unsafes_filters['unsafe__verdict'] = self.verdict
        else:
            if 'verdict' in self.view:
                unsafes_filters['unsafe__verdict__in'] = self.view['verdict']
            if self.attr is not None:
                unsafes_filters['unsafe__attrs__attr'] = self.attr

        if 'parent_cpu' in self.view:
            parent_cpu_value = float(self.view['parent_cpu'][1].replace(',', '.'))
            if self.view['parent_cpu'][2] == 's':
                parent_cpu_value *= 1000
            elif self.view['parent_cpu'][2] == 'm':
                parent_cpu_value *= 60000
            unsafes_filters['unsafe__cpu_time__%s' % self.view['parent_cpu'][0]] = parent_cpu_value
        if 'parent_wall' in self.view:
            parent_wall_value = float(self.view['parent_wall'][1].replace(',', '.'))
            if self.view['parent_wall'][2] == 's':
                parent_wall_value *= 1000
            elif self.view['parent_wall'][2] == 'm':
                parent_wall_value *= 60000
            unsafes_filters['unsafe__wall_time__%s' % self.view['parent_wall'][0]] = parent_wall_value
        if 'parent_memory' in self.view:
            parent_memory_value = float(self.view['parent_memory'][1].replace(',', '.'))
            if self.view['parent_memory'][2] == 'KB':
                parent_memory_value *= 1024
            elif self.view['parent_memory'][2] == 'MB':
                parent_memory_value *= 1024 * 1024
            elif self.view['parent_memory'][2] == 'GB':
                parent_memory_value *= 1024 * 1024 * 1024
            unsafes_filters['unsafe__memory__%s' % self.view['parent_memory'][0]] = parent_memory_value

        leaves_set = self.report.leaves.filter(**unsafes_filters).exclude(unsafe=None).annotate(
            marks_number=Count('unsafe__markreport_set'),
            confirmed=Count(Case(When(unsafe__markreport_set__type='1', then=1)))
        ).values('unsafe_id', 'confirmed', 'marks_number', 'unsafe__verdict',
                 'unsafe__parent_id', 'unsafe__cpu_time', 'unsafe__wall_time', 'unsafe__memory')

        if 'marks_number' in self.view:
            if self.view['marks_number'][0] == 'confirmed':
                marknum_filter = 'confirmed__%s' % self.view['marks_number'][1]
            else:
                marknum_filter = 'marks_number__%s' % self.view['marks_number'][1]
            leaves_set = leaves_set.filter(**{marknum_filter: int(self.view['marks_number'][2])})

        include_confirmed = 'hidden' not in self.view or 'confirmed_marks' not in self.view['hidden']

        reports = {}
        for leaf in leaves_set:
            if include_confirmed:
                marks_num = "%s (%s)" % (leaf['confirmed'], leaf['marks_number'])
            else:
                marks_num = str(leaf['marks_number'])
            reports[leaf['unsafe_id']] = {
                'marks_number': marks_num,
                'verdict': leaf['unsafe__verdict'],
                'parent_id': leaf['unsafe__parent_id'],
                'parent_cpu': leaf['unsafe__cpu_time'],
                'parent_wall': leaf['unsafe__wall_time'],
                'parent_memory': leaf['unsafe__memory'],
                'tags': {}
            }
        for r_id, tag in UnsafeReportTag.objects.filter(report_id__in=reports).values_list('report_id', 'tag__tag'):
            reports[r_id]['tags'][tag] = reports[r_id]['tags'].get(tag, 0) + 1
        for r_id, a_name, a_val in ReportAttr.objects.filter(report_id__in=reports).order_by('id') \
                .values_list('report_id', 'attr__name__name', 'attr__value'):
            if a_name not in data:
                columns.append(a_name)
                data[a_name] = {}
            data[a_name][r_id] = a_val

        reports_ordered = []
        if 'order' in self.view and self.view['order'][1] == 'attr' and self.view['order'][2] in data:
            for rep_id in data[self.view['order'][2]]:
                if self.__has_tag(reports[rep_id]['tags']):
                    reports_ordered.append(
                        (data[self.view['order'][2]][rep_id], rep_id)
                    )
            reports_ordered = [x[1] for x in sorted(reports_ordered, key=lambda x: x[0])]
            if self.view['order'][0] == 'up':
                reports_ordered = list(reversed(reports_ordered))
        elif 'order' in self.view and self.view['order'][1] in {'parent_cpu', 'parent_wall', 'parent_memory'}:
            for attr in data:
                for rep_id in data[attr]:
                    order_id = (reports[rep_id][self.view['order'][1]], rep_id)
                    if order_id not in reports_ordered and self.__has_tag(reports[rep_id]['tags']):
                        reports_ordered.append(order_id)
            reports_ordered = [x[1] for x in sorted(reports_ordered, key=lambda x: x[0])]
            if self.view['order'][0] == 'up':
                reports_ordered = list(reversed(reports_ordered))
        else:
            for attr in data:
                for rep_id in data[attr]:
                    if rep_id not in reports_ordered and self.__has_tag(reports[rep_id]['tags']):
                        reports_ordered.append(rep_id)
            reports_ordered = sorted(reports_ordered)

        for r_id in reports:
            tags_str = []
            for t_name in sorted(reports[r_id]['tags']):
                if reports[r_id]['tags'][t_name] == 1:
                    tags_str.append(t_name)
                else:
                    tags_str.append("%s (%s)" % (t_name, reports[r_id]['tags'][t_name]))
            reports[r_id]['tags'] = '; '.join(tags_str)

        cnt = 1
        values_data = []
        for rep_id in reports_ordered:
            values_row = []
            for col in columns:
                val = '-'
                href = None
                color = None
                if col in data:
                    if rep_id in data[col]:
                        val = data[col][rep_id]
                        if not self.__filter_attr(col, val):
                            break
                elif col == 'number':
                    val = cnt
                    href = reverse('reports:unsafe', args=[rep_id])
                elif col == 'marks_number':
                    val = reports[rep_id]['marks_number']
                elif col == 'report_verdict':
                    for s in UNSAFE_VERDICTS:
                        if s[0] == reports[rep_id]['verdict']:
                            val = s[1]
                            break
                    color = UNSAFE_COLOR[reports[rep_id]['verdict']]
                elif col == 'tags':
                    if len(reports[rep_id]['tags']) > 0:
                        val = reports[rep_id]['tags']
                elif col == 'parent_cpu':
                    val = get_user_time(self.user, reports[rep_id]['parent_cpu'])
                elif col == 'parent_wall':
                    val = get_user_time(self.user, reports[rep_id]['parent_wall'])
                elif col == 'parent_memory':
                    val = get_user_memory(self.user, reports[rep_id]['parent_memory'])
                values_row.append({'value': val, 'color': color, 'href': href})
            else:
                cnt += 1
                values_data.append(values_row)
        return columns, values_data

    def __has_tag(self, tags):
        if self.tag is None and 'tags' not in self.view:
            return True
        elif self.tag is not None and self.tag in tags:
            return True
        elif 'tags' in self.view:
            view_tags = list(x.strip() for x in self.view['tags'][0].split(';'))
            return all(t in tags for t in view_tags)
        return False

    def __filter_attr(self, attribute, value):
        if 'attr' in self.view:
            attr_name = self.view['attr'][0]
            ftype = self.view['attr'][1]
            attr_val = self.view['attr'][2]
            if attr_name is not None and attr_name.lower() == attribute.lower():
                if ftype == 'iexact' and attr_val.lower() != value.lower():
                    return False
                elif ftype == 'istartswith' and not value.lower().startswith(attr_val.lower()):
                    return False
                elif ftype == 'iendswith' and not value.lower().endswith(attr_val.lower()):
                    return False
        return True

    def __get_page(self, page, values):
        num_per_page = DEF_NUMBER_OF_ELEMENTS
        if 'elements' in self.view:
            num_per_page = int(self.view['elements'][0])
        self.paginator = Paginator(values, num_per_page)
        try:
            values = self.paginator.page(page)
        except PageNotAnInteger:
            values = self.paginator.page(1)
        except EmptyPage:
            values = self.paginator.page(self.paginator.num_pages)
        return values

    def __is_not_used(self):
        pass


class UnknownsTable:
    def __init__(self, user, report, view=None, view_id=None, page=1, component=None, problem=None, attr=None):
        self.user = user
        self.report = report
        self.component_id = component
        self.problem = problem
        self.attr = attr

        self.view = ViewData(self.user, VIEW_TYPES[6][0], view=view, view_id=view_id)

        self.selected_columns = self.__selected()
        self.available_columns = self.__available()

        columns, values = self.__unknowns_data()
        self.paginator = None
        self.table_data = {'header': Header(columns, REP_MARK_TITLES).struct, 'values': self.__get_page(page, values)}

    def __selected(self):
        columns = []
        for col in self.view['columns']:
            if col not in {'marks_number', 'parent_cpu', 'parent_wall', 'parent_memory'}:
                return []
            col_title = col
            if col_title in REP_MARK_TITLES:
                col_title = REP_MARK_TITLES[col_title]
            columns.append({'value': col, 'title': col_title})
        return columns

    def __available(self):
        self.__is_not_used()
        columns = []
        for col in ['marks_number', 'parent_cpu', 'parent_wall', 'parent_memory']:
            col_title = col
            if col_title in REP_MARK_TITLES:
                col_title = REP_MARK_TITLES[col_title]
            columns.append({'value': col, 'title': col_title})
        return columns

    def __unknowns_data(self):
        columns = ['component']
        columns.extend(self.view['columns'])

        data = {}
        reports = {}

        unknowns_filters = {}
        annotations = {
            'marks_number': Count('unknown__markreport_set'),
            'confirmed': Count(Case(When(unknown__markreport_set__type='1', then=1)))
        }
        if self.component_id is not None:
            unknowns_filters['unknown__component_id'] = int(self.component_id)
        if 'component' in self.view and self.view['component'][0] in {'iexact', 'istartswith', 'icontains'}:
            unknowns_filters['unknown__component__name__%s' % self.view['component'][0]] = self.view['component'][1]

        if 'parent_cpu' in self.view:
            parent_cpu_value = float(self.view['parent_cpu'][1].replace(',', '.'))
            if self.view['parent_cpu'][2] == 's':
                parent_cpu_value *= 1000
            elif self.view['parent_cpu'][2] == 'm':
                parent_cpu_value *= 60000
            unknowns_filters['unknown__cpu_time__%s' % self.view['parent_cpu'][0]] = parent_cpu_value
        if 'parent_wall' in self.view:
            parent_wall_value = float(self.view['parent_wall'][1].replace(',', '.'))
            if self.view['parent_wall'][2] == 's':
                parent_wall_value *= 1000
            elif self.view['parent_wall'][2] == 'm':
                parent_wall_value *= 60000
            unknowns_filters['unknown__wall_time__%s' % self.view['parent_wall'][0]] = parent_wall_value
        if 'parent_memory' in self.view:
            parent_memory_value = float(self.view['parent_memory'][1].replace(',', '.'))
            if self.view['parent_memory'][2] == 'KB':
                parent_memory_value *= 1024
            elif self.view['parent_memory'][2] == 'MB':
                parent_memory_value *= 1024 * 1024
            elif self.view['parent_memory'][2] == 'GB':
                parent_memory_value *= 1024 * 1024 * 1024
            unknowns_filters['unknown__memory__%s' % self.view['parent_memory'][0]] = parent_memory_value

        if 'marks_number' in self.view:
            if self.view['marks_number'][0] == 'confirmed':
                unknowns_filters['confirmed__%s' % self.view['marks_number'][1]] = int(self.view['marks_number'][2])
            else:
                unknowns_filters['marks_number__%s' % self.view['marks_number'][1]] = int(self.view['marks_number'][2])

        if isinstance(self.problem, UnknownProblem):
            unknowns_filters['unknown__markreport_set__problem'] = self.problem
        elif self.attr is not None:
            unknowns_filters['unknown__attrs__attr'] = self.attr
        elif self.problem == 0:
            unknowns_filters['marks_number'] = 0
        leaves_set = self.report.leaves.annotate(**annotations).filter(~Q(unknown=None) & Q(**unknowns_filters)).values(
            'unknown_id', 'unknown__component__name', 'confirmed', 'marks_number',
            'unknown__cpu_time', 'unknown__wall_time', 'unknown__memory'
        )

        include_confirmed = 'hidden' not in self.view or 'confirmed_marks' not in self.view['hidden']

        for leaf in leaves_set:
            if include_confirmed:
                marks_num = "%s (%s)" % (leaf['confirmed'], leaf['marks_number'])
            else:
                marks_num = str(leaf['marks_number'])
            reports[leaf['unknown_id']] = {
                'component': leaf['unknown__component__name'],
                'marks_number': marks_num,
                'parent_cpu': leaf['unknown__cpu_time'],
                'parent_wall': leaf['unknown__wall_time'],
                'parent_memory': leaf['unknown__memory'],
            }

        for u_id, aname, aval in ReportAttr.objects.filter(report_id__in=reports).order_by('id') \
                .values_list('report_id', 'attr__name__name', 'attr__value'):
            if aname not in data:
                columns.append(aname)
                data[aname] = {}
            data[aname][u_id] = aval

        ids_order_data = []
        if 'order' in self.view and self.view['order'][1] == 'attr' and self.view['order'][2] in data:
            for rep_id in data[self.view['order'][2]]:
                ids_order_data.append((data[self.view['order'][2]][rep_id], rep_id))
        elif 'order' in self.view and self.view['order'][1] in {'parent_cpu', 'parent_wall', 'parent_memory'}:
            for rep_id in reports:
                if reports[rep_id][self.view['order'][1]] is not None:
                    ids_order_data.append((reports[rep_id][self.view['order'][1]], rep_id))
        else:
            for u_id in reports:
                ids_order_data.append((reports[u_id]['component'], u_id))
        report_ids = list(x[1] for x in sorted(ids_order_data))
        if 'order' in self.view and self.view['order'][0] == 'up':
            report_ids = list(reversed(report_ids))

        values_data = []
        for rep_id in report_ids:
            values_row = []
            for col in columns:
                val = '-'
                href = None
                if col in data and rep_id in data[col]:
                    val = data[col][rep_id]
                    if not self.__filter_attr(col, val):
                        break
                elif col == 'component':
                    val = reports[rep_id]['component']
                    href = reverse('reports:unknown', args=[rep_id])
                elif col == 'marks_number':
                    val = reports[rep_id]['marks_number']
                elif col == 'parent_cpu':
                    if reports[rep_id]['parent_cpu'] is not None:
                        val = get_user_time(self.user, reports[rep_id]['parent_cpu'])
                elif col == 'parent_wall':
                    if reports[rep_id]['parent_wall'] is not None:
                        val = get_user_time(self.user, reports[rep_id]['parent_wall'])
                elif col == 'parent_memory':
                    if reports[rep_id]['parent_memory'] is not None:
                        val = get_user_memory(self.user, reports[rep_id]['parent_memory'])
                values_row.append({'value': val, 'href': href})
            else:
                values_data.append(values_row)
        return columns, values_data

    def __filter_attr(self, attribute, value):
        if 'attr' in self.view:
            attr_name = self.view['attr'][0]
            ftype = self.view['attr'][1]
            attr_val = self.view['attr'][2]
            if attr_name is not None and attr_name.lower() == attribute.lower():
                if ftype == 'iexact' and attr_val.lower() != value.lower():
                    return False
                elif ftype == 'istartswith' and not value.lower().startswith(attr_val.lower()):
                    return False
                elif ftype == 'iendswith' and not value.lower().endswith(attr_val.lower()):
                    return False
        return True

    def __get_page(self, page, values):
        num_per_page = DEF_NUMBER_OF_ELEMENTS
        if 'elements' in self.view:
            num_per_page = int(self.view['elements'][0])
        self.paginator = Paginator(values, num_per_page)
        try:
            values = self.paginator.page(page)
        except PageNotAnInteger:
            values = self.paginator.page(1)
        except EmptyPage:
            values = self.paginator.page(self.paginator.num_pages)
        return values

    def __is_not_used(self):
        pass


class ReportChildrenTable:
    def __init__(self, user, report, view=None, view_id=None, page=1):
        self.user = user
        self.report = report
        self.columns = []

        self.view = ViewData(self.user, VIEW_TYPES[3][0], view=view, view_id=view_id)

        columns, values = self.__component_data()
        self.paginator = None
        self.table_data = {'header': Header(columns, REP_MARK_TITLES).struct, 'values': self.__get_page(page, values)}

    def __component_data(self):
        data = {}
        components = {}
        columns = []
        component_filters = {'parent': self.report}
        if 'component' in self.view:
            component_filters['component__name__' + self.view['component'][0]] = self.view['component'][1]

        finish_dates = {}
        report_ids = set()
        for report in ReportComponent.objects.filter(**component_filters).select_related('component'):
            report_ids.add(report.id)
            components[report.id] = report.component
            if 'order' in self.view and self.view['order'][1] == 'date' and report.finish_date is not None:
                finish_dates[report.id] = report.finish_date

        for ra in ReportAttr.objects.filter(report_id__in=report_ids).order_by('id') \
                .values_list('report_id', 'attr__name__name', 'attr__value'):
            if ra[1] not in data:
                columns.append(ra[1])
                data[ra[1]] = {}
            data[ra[1]][ra[0]] = ra[2]

        comp_data = []
        for pk in components:
            if self.view['order'][1] == 'component':
                comp_data.append((components[pk].name, {'pk': pk, 'component': components[pk]}))
            elif self.view['order'][1] == 'date':
                if pk in finish_dates:
                    comp_data.append((finish_dates[pk], {'pk': pk, 'component': components[pk]}))
            elif self.view['order'][1] == 'attr':
                attr_val = '-'
                if self.view['order'][2] in data and pk in data[self.view['order'][2]]:
                    attr_val = data[self.view['order'][2]][pk]
                comp_data.append((attr_val, {'pk': pk, 'component': components[pk]}))

        sorted_components = []
        for name, dt in sorted(comp_data, key=lambda x: x[0]):
            sorted_components.append(dt)
        if self.view['order'] is not None and self.view['order'][0] == 'up':
            sorted_components = list(reversed(sorted_components))

        values_data = []
        for comp_data in sorted_components:
            values_row = []
            for col in columns:
                cell_val = '-'
                if comp_data['pk'] in data[col]:
                    cell_val = data[col][comp_data['pk']]
                values_row.append(cell_val)
                if not self.__filter_attr(col, cell_val):
                    break
            else:
                values_data.append({
                    'pk': comp_data['pk'],
                    'component': comp_data['component'],
                    'attrs': values_row
                })
        columns.insert(0, 'component')
        return columns, values_data

    def __filter_attr(self, attribute, value):
        if 'attr' in self.view:
            attr_name = self.view['attr'][0]
            ftype = self.view['attr'][1]
            attr_val = self.view['attr'][2]
            if attr_name is not None and attr_name.lower() == attribute.lower():
                if ftype == 'iexact' and attr_val.lower() != value.lower():
                    return False
                elif ftype == 'istartswith' and not value.lower().startswith(attr_val.lower()):
                    return False
        return True

    def __get_page(self, page, values):
        num_per_page = DEF_NUMBER_OF_ELEMENTS
        if 'elements' in self.view:
            num_per_page = int(self.view['elements'][0])
        self.paginator = Paginator(values, num_per_page)
        try:
            values = self.paginator.page(page)
        except PageNotAnInteger:
            values = self.paginator.page(1)
        except EmptyPage:
            values = self.paginator.page(self.paginator.num_pages)
        return values


class AttrData:
    def __init__(self):
        self._data = []
        self._name = {}
        self._attrs = {}

    def add(self, report_id, name, value):
        self._data.append((report_id, name, value))
        if name not in self._name:
            self._name[name] = None
        if (name, value) not in self._attrs:
            self._attrs[(name, value)] = None

    def upload(self):
        self.__upload_names()
        self.__upload_attrs()
        ReportAttr.objects.bulk_create(
            list(ReportAttr(report_id=d[0], attr_id=self._attrs[(d[1], d[2])]) for d in self._data)
        )
        self.__init__()

    def __upload_names(self):
        existing_names = set(n.name for n in AttrName.objects.filter(name__in=self._name))
        names_to_create = []
        for name in self._name:
            if name not in existing_names:
                names_to_create.append(AttrName(name=name))
        AttrName.objects.bulk_create(names_to_create)
        for n in AttrName.objects.filter(name__in=self._name):
            self._name[n.name] = n.id

    def __upload_attrs(self):
        for a in Attr.objects.filter(value__in=list(attr[1] for attr in self._attrs)).select_related('name'):
            if (a.name.name, a.value) in self._attrs:
                self._attrs[(a.name.name, a.value)] = a.id
        attrs_to_create = []
        for attr in self._attrs:
            if self._attrs[attr] is None and attr[0] in self._name:
                attrs_to_create.append(Attr(name_id=self._name[attr[0]], value=attr[1]))
        Attr.objects.bulk_create(attrs_to_create)
        for a in Attr.objects.filter(value__in=list(attr[1] for attr in self._attrs)).select_related('name'):
            if (a.name.name, a.value) in self._attrs:
                self._attrs[(a.name.name, a.value)] = a.id


class FilesForCompetitionArchive:
    def __init__(self, job, filters):
        self.name = 'svcomp.zip'
        self.benchmark_fname = 'benchmark.xml'
        self.prp_fname = 'unreach-call.prp'
        self.obj_attr = 'Verification object'
        self.rule_attr = 'Rule specification'
        try:
            self.root = ReportRoot.objects.get(job=job)
        except ObjectDoesNotExist:
            raise ValueError('The job is not decided')
        self._archives = self.__get_archives()
        self.filters = filters
        self.xml_root = None
        self.prp_file_added = False
        self.stream = ZipStream()

    def __iter__(self):
        for f_t in self.filters:
            if isinstance(f_t, str) and f_t in {'u', 's'}:
                for data in self.__reports_data(f_t):
                    yield data
            elif isinstance(f_t, list):
                for data in self.__reports_data('f', f_t):
                    yield data
        if self.xml_root is None:
            for data in self.stream.compress_string('NOFILES', ''):
                yield data
        else:
            benchmark_content = minidom.parseString(ETree.tostring(self.xml_root, 'utf-8')).toprettyxml(indent="  ")
            for data in self.stream.compress_string(self.benchmark_fname, benchmark_content):
                yield data
        yield self.stream.close_stream()

    def __get_archives(self):
        archives = {}
        for c in ReportComponent.objects.filter(root=self.root, verification=True).exclude(verifier_input='')\
                .only('id', 'verifier_input'):
            if c.verifier_input:
                archives[c.id] = c.verifier_input
        return archives

    def __reports_data(self, f_type, problems=None):
        if f_type == 'u':
            table = ReportUnsafe
            cil_dir = 'Unsafes'
        elif f_type == 's':
            table = ReportSafe
            cil_dir = 'Safes'
        elif f_type == 'f':
            table = ReportUnknown
            cil_dir = 'Unknowns'
        else:
            raise ValueError('Wrong filter type')

        reports = {}
        if f_type == 'f' and problems is not None and len(problems) > 0:
            for problem in problems:
                comp_id, problem_id = problem.split('_')[0:2]
                if comp_id == problem_id == '0':
                    for r in ReportUnknown.objects.annotate(mr_len=Count('markreport_set'))\
                            .filter(root=self.root, mr_len=0).exclude(parent__parent=None).only('id', 'parent_id'):
                        if r.parent_id not in self._archives:
                            continue
                        reports[r.id] = r.parent_id
                else:
                    for r in ReportUnknown.objects\
                            .filter(root=self.root, markreport_set__problem_id=problem_id, component_id=comp_id)\
                            .exclude(parent__parent=None).only('id', 'parent_id'):
                        if r.parent_id not in self._archives:
                            continue
                        reports[r.id] = r.parent_id
        else:
            for r in table.objects.filter(root=self.root).exclude(parent__parent=None).only('id', 'parent_id'):
                if r.parent_id not in self._archives:
                    continue
                reports[r.id] = r.parent_id
        attrs_data = {}
        for ra in ReportAttr.objects\
                .filter(report_id__in=list(reports), attr__name__name__in=[self.obj_attr, self.rule_attr])\
                .select_related('attr', 'attr__name'):
            if ra.report_id not in attrs_data:
                attrs_data[ra.report_id] = {}
            attrs_data[ra.report_id][ra.attr.name.name] = ra.attr.value
        cnt = 1
        paths_in_use = []
        for r_id in reports:
            if r_id in attrs_data and self.obj_attr in attrs_data[r_id] and self.rule_attr in attrs_data[r_id]:
                ver_obj = attrs_data[r_id][self.obj_attr].replace('~', 'HOME').replace('/', '---')
                ver_rule = attrs_data[r_id][self.rule_attr].replace(':', '-')
                r_path = '%s/%s__%s__%s.cil.i' % (cil_dir, f_type, ver_rule, ver_obj)
                if r_path in paths_in_use:
                    ver_obj_path, ver_obj_name = r_path.split('/')
                    r_path = '/'.join([ver_obj_path, "%s__%s" % (cnt, ver_obj_name)])
                    cnt += 1
                try:
                    for data in self.__cil_data(reports[r_id], r_path):
                        yield data
                except Exception as e:
                    logger.exception(e)
                else:
                    new_elem = ETree.Element('include')
                    new_elem.text = r_path
                    self.xml_root.find('tasks').append(new_elem)
                    paths_in_use.append(r_path)

    def __cil_data(self, report_id, arcname):
        with self._archives[report_id] as fp:
            if os.path.splitext(fp.name)[-1] != '.zip':
                raise ValueError('Archive type is not supported')
            with zipfile.ZipFile(fp, 'r') as zfp:
                xml_root = ETree.fromstring(zfp.read(self.benchmark_fname))
                cil_content = zfp.read(xml_root.find('tasks').find('include').text)
                for data in self.stream.compress_string(arcname, cil_content):
                    yield data
                if not self.prp_file_added:
                    for data in self.stream.compress_string(self.prp_fname, zfp.read(self.prp_fname)):
                        yield data
                    self.prp_file_added = True
            if self.xml_root is None:
                self.xml_root = xml_root
                self.xml_root.find('tasks').clear()


def report_attibutes(report):
    return report.attrs.order_by('id').values_list('attr__name__name', 'attr__value')


def report_attributes_with_parents(report):
    attrs = []
    parent = report
    while parent is not None:
        attrs = list(parent.attrs.order_by('id').values_list('attr__name__name', 'attr__value')) + attrs
        parent = parent.parent
    return attrs


def remove_verification_files(job):
    for report in ReportComponent.objects.filter(root=job.reportroot, verification=True).exclude(verifier_input=''):
        report.verifier_input.delete()
