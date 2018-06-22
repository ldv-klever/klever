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

import os
import json
import zipfile
import xml.etree.ElementTree as ETree
from xml.dom import minidom

from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.core.files import File
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Count, Case, When
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _, string_concat

from bridge.vars import UNSAFE_VERDICTS, SAFE_VERDICTS, ASSOCIATION_TYPE
from bridge.tableHead import Header
from bridge.utils import logger, extract_archive, BridgeException
from bridge.ZipGenerator import ZipStream

from reports.models import ReportComponent, AttrFile, Attr, AttrName, ReportAttr, ReportUnsafe, ReportSafe,\
    ReportUnknown, ReportRoot
from marks.models import UnknownProblem, UnsafeReportTag, SafeReportTag, MarkUnknownReport, SafeTag, UnsafeTag

from users.utils import DEF_NUMBER_OF_ELEMENTS
from jobs.utils import get_resource_data, get_user_time, get_user_memory
from marks.utils import SAFE_COLOR, UNSAFE_COLOR


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
    'verifiers': _('Verifiers'),
    'verifiers:cpu': _('CPU time'),
    'verifiers:wall': _('Wall time'),
    'verifiers:memory': _('RAM'),
    'problems': _('Problems')
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


def get_column_title(column):
    col_parts = column.split(':')
    column_starts = []
    for i in range(0, len(col_parts)):
        column_starts.append(':'.join(col_parts[:(i + 1)]))
    titles = []
    for col_st in column_starts:
        titles.append(REP_MARK_TITLES.get(col_st, col_st))
    concated_title = titles[0]
    for i in range(1, len(titles)):
        concated_title = string_concat(concated_title, '/', titles[i])
    return concated_title


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
            'href': reverse('reports:component', args=[parent.id]),
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
        for ra in self.report.attrs.order_by('id').select_related('attr', 'attr__name'):
            columns.append(ra.attr.name.name)
            values.append((ra.attr.value, ra.id if ra.data is not None else None))
        return columns, values


class SafesListGetData:
    def __init__(self, data):
        self.title = _('Safes')
        self.args = {'page': data.get('page', 1)}
        self.__get_filters_data(data)

    def __get_filters_data(self, data):
        if 'confirmed' in data:
            self.args['confirmed'] = True
            self.title = string_concat(_("Safes"), ': ', _('confirmed'))
        if 'verdict' in data:
            for v in SAFE_VERDICTS:
                if v[0] == data['verdict']:
                    self.args['verdict'] = data['verdict']
                    if 'confirmed' in data:
                        self.title = string_concat(_("Safes"), ': ', _('confirmed'), ' ', v[1])
                    else:
                        self.title = string_concat(_("Safes"), ': ', v[1])
                    break
        elif 'tag' in data:
            try:
                tag = SafeTag.objects.get(pk=data['tag']).tag
            except ObjectDoesNotExist:
                raise BridgeException(_("The tag was not found"))
            self.title = string_concat(_("Safes"), ': ', tag)
            self.args['tag'] = tag
        elif 'attr' in data:
            try:
                attr = Attr.objects.get(id=data['attr'])
            except ObjectDoesNotExist:
                raise BridgeException(_("The attribute was not found"))
            self.title = _('Safes where %(a_name)s is %(a_val)s') % {'a_name': attr.name.name, 'a_val': attr.value}
            self.args['attr'] = attr


class UnsafesListGetData:
    def __init__(self, data):
        self.title = _('Unsafes')
        self.args = {'page': data.get('page', 1)}
        self.__get_filters_data(data)

    def __get_filters_data(self, data):
        if 'confirmed' in data:
            self.args['confirmed'] = True
            self.title = string_concat(_("Unsafes"), ': ', _('confirmed'))
        if 'verdict' in data:
            for v in UNSAFE_VERDICTS:
                if v[0] == data['verdict']:
                    self.args['verdict'] = data['verdict']
                    if 'confirmed' in data:
                        self.title = string_concat(_("Unsafes"), ': ', _('confirmed'), ' ', v[1])
                    else:
                        self.title = string_concat(_("Unsafes"), ': ', v[1])
                    break
        elif 'tag' in data:
            try:
                tag = UnsafeTag.objects.get(pk=data['tag']).tag
            except ObjectDoesNotExist:
                raise BridgeException(_("The tag was not found"))
            self.title = string_concat(_("Unsafes"), ': ', tag)
            self.args['tag'] = tag
        elif 'attr' in data:
            try:
                attr = Attr.objects.get(id=data['attr'])
            except ObjectDoesNotExist:
                raise BridgeException(_("The attribute was not found"))
            self.title = _('Unsafes where %(a_name)s is %(a_val)s') % {'a_name': attr.name.name, 'a_val': attr.value}
            self.args['attr'] = attr


class UnknownsListGetData:
    def __init__(self, data):
        self.title = _('Unknowns')
        self.args = {'page': data.get('page', 1)}
        self.__get_filters_data(data)

    def __get_filters_data(self, data):
        if 'component' in data:
            self.args['component'] = data['component']
        if 'problem' in data:
            problem_id = int(data['problem'])
            if problem_id == 0:
                self.title = string_concat(_("Unknowns without marks"))
                self.args['problem'] = 0
            else:
                try:
                    problem = UnknownProblem.objects.get(pk=problem_id)
                except ObjectDoesNotExist:
                    raise BridgeException(_("The problem was not found"))
                self.title = string_concat(_("Unknowns"), ': ', problem.name)
                self.args['problem'] = problem
        elif 'attr' in data:
            try:
                attr = Attr.objects.values('name__name', 'value').get(id=data['attr'])
            except ObjectDoesNotExist:
                raise BridgeException(_("The attribute was not found"))
            self.title = _('Unknowns where %(a_name)s is %(a_val)s') % {
                'a_name': attr['name__name'], 'a_val': attr['value']
            }
            self.args['attr'] = attr


class SafesTable:
    def __init__(self, user, report, view, **kwargs):
        self.user = user
        self.report = report
        self.view = view
        self.tag = kwargs.get('tag')

        self.selected_columns = self.__selected()
        self.available_columns = self.__available()

        self.verdicts = SAFE_VERDICTS
        self._filters = self.__safes_filters(**kwargs)
        columns, values = self.__safes_data()
        self.paginator = None
        self.table_data = {
            'header': Header(columns, REP_MARK_TITLES).struct,
            'values': self.__get_page(kwargs.get('page', 1), values)
        }

    def __selected(self):
        columns = []
        for col in self.view['columns']:
            if col not in {
                'marks_number', 'report_verdict', 'tags', 'verifiers:cpu', 'verifiers:wall', 'verifiers:memory'
            }:
                return []
            if ':' in col:
                col_title = get_column_title(col)
            else:
                col_title = REP_MARK_TITLES.get(col, col)
            columns.append({'value': col, 'title': col_title})
        return columns

    def __available(self):
        self.__is_not_used()
        columns = []
        for col in ['marks_number', 'report_verdict', 'tags', 'verifiers:cpu', 'verifiers:wall', 'verifiers:memory']:
            if ':' in col:
                col_title = get_column_title(col)
            else:
                col_title = REP_MARK_TITLES.get(col, col)
            columns.append({'value': col, 'title': col_title})
        return columns

    def __safes_data(self):
        columns = ['number']
        columns.extend(self.view['columns'])

        leaves_set = self.report.leaves.filter(**self._filters).exclude(safe=None).annotate(
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

        data = {}
        for r_id, a_name, a_val in ReportAttr.objects.filter(report_id__in=reports).order_by('id') \
                .values_list('report_id', 'attr__name__name', 'attr__value'):
            if a_name not in data:
                columns.append(a_name)
                data[a_name] = {}
            data[a_name][r_id] = a_val

        reports_ordered = []
        # We want reports without ordering parameter to be at the end (with any order direction)
        end_reports = []
        if 'order' in self.view and self.view['order'][1] == 'attr' and self.view['order'][2] in data:
            for rep_id in reports:
                if self.__has_tag(reports[rep_id]['tags']):
                    if rep_id in data[self.view['order'][2]]:
                        reports_ordered.append((data[self.view['order'][2]][rep_id], rep_id))
                    else:
                        end_reports.append(rep_id)
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
            for rep_id in reports:
                if self.__has_tag(reports[rep_id]['tags']):
                    reports_ordered.append(rep_id)
            reports_ordered = sorted(reports_ordered)
        reports_ordered += list(sorted(end_reports))

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
                elif col == 'verifiers:cpu':
                    val = get_user_time(self.user, reports[rep_id]['parent_cpu'])
                elif col == 'verifiers:wall':
                    val = get_user_time(self.user, reports[rep_id]['parent_wall'])
                elif col == 'verifiers:memory':
                    val = get_user_memory(self.user, reports[rep_id]['parent_memory'])
                values_row.append({'value': val, 'color': color, 'href': href})
            else:
                cnt += 1
                values_data.append(values_row)
        return columns, values_data

    def __safes_filters(self, **kwargs):
        safes_filters = {}
        if kwargs.get('confirmed', False):
            safes_filters['safe__has_confirmed'] = True
        if kwargs.get('verdict') is not None:
            safes_filters['safe__verdict'] = kwargs['verdict']
        else:
            if 'verdict' in self.view:
                safes_filters['safe__verdict__in'] = self.view['verdict']
            if kwargs.get('attr') is not None:
                safes_filters['safe__attrs__attr'] = kwargs['attr']

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
        return safes_filters

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
    def __init__(self, user, report, view, **kwargs):
        self.user = user
        self.report = report
        self.view = view
        self.tag = kwargs.get('tag')

        self.selected_columns = self.__selected()
        self.available_columns = self.__available()

        self.verdicts = UNSAFE_VERDICTS
        self._filters = self.__unsafes_filters(**kwargs)
        columns, values = self.__unsafes_data()
        self.paginator = None
        self.table_data = {
            'header': Header(columns, REP_MARK_TITLES).struct,
            'values': self.__get_page(kwargs.get('page', 1), values)
        }

    def __selected(self):
        columns = []
        for col in self.view['columns']:
            if col not in {
                'marks_number', 'report_verdict', 'tags', 'verifiers:cpu', 'verifiers:wall', 'verifiers:memory'
            }:
                return []
            if ':' in col:
                col_title = get_column_title(col)
            else:
                col_title = REP_MARK_TITLES.get(col, col)
            columns.append({'value': col, 'title': col_title})
        return columns

    def __available(self):
        self.__is_not_used()
        columns = []
        for col in ['marks_number', 'report_verdict', 'tags', 'verifiers:cpu', 'verifiers:wall', 'verifiers:memory']:
            if ':' in col:
                col_title = get_column_title(col)
            else:
                col_title = REP_MARK_TITLES.get(col, col)
            columns.append({'value': col, 'title': col_title})
        return columns

    def __unsafes_data(self):
        data = {}
        columns = ['number']
        columns.extend(self.view['columns'])

        leaves_set = self.report.leaves.filter(**self._filters).exclude(unsafe=None).annotate(
            marks_number=Count('unsafe__markreport_set'),
            confirmed=Count(Case(When(unsafe__markreport_set__type='1', then=1)))
        ).values('unsafe_id', 'unsafe__trace_id', 'confirmed', 'marks_number', 'unsafe__verdict',
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
                'trace_id': leaf['unsafe__trace_id'],
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
        # We want reports without ordering parameter to be at the end (with any order direction)
        end_reports = []
        if 'order' in self.view and self.view['order'][1] == 'attr' and self.view['order'][2] in data:
            for rep_id in reports:
                if self.__has_tag(reports[rep_id]['tags']):
                    if rep_id in data[self.view['order'][2]]:
                        reports_ordered.append((data[self.view['order'][2]][rep_id], rep_id))
                    else:
                        end_reports.append(rep_id)
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
            for rep_id in reports:
                if self.__has_tag(reports[rep_id]['tags']):
                    reports_ordered.append(rep_id)
            reports_ordered = sorted(reports_ordered)
        reports_ordered += list(sorted(end_reports))

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
                    href = reverse('reports:unsafe', args=[reports[rep_id]['trace_id']])
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
                elif col == 'verifiers:cpu':
                    val = get_user_time(self.user, reports[rep_id]['parent_cpu'])
                elif col == 'verifiers:wall':
                    val = get_user_time(self.user, reports[rep_id]['parent_wall'])
                elif col == 'verifiers:memory':
                    val = get_user_memory(self.user, reports[rep_id]['parent_memory'])
                values_row.append({'value': val, 'color': color, 'href': href})
            else:
                cnt += 1
                values_data.append(values_row)
        return columns, values_data

    def __unsafes_filters(self, **kwargs):
        unsafes_filters = {}
        if kwargs.get('confirmed', False):
            unsafes_filters['unsafe__has_confirmed'] = True
        if kwargs.get('verdict') is not None:
            unsafes_filters['unsafe__verdict'] = kwargs['verdict']
        else:
            if 'verdict' in self.view:
                unsafes_filters['unsafe__verdict__in'] = self.view['verdict']
            if kwargs.get('attr') is not None:
                unsafes_filters['unsafe__attrs__attr'] = kwargs['attr']

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
        return unsafes_filters

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
    columns_list = ['component', 'marks_number', 'problems', 'verifiers:cpu', 'verifiers:wall', 'verifiers:memory']
    columns_set = set(columns_list)

    def __init__(self, user, report, view, **kwargs):
        self.user = user
        self.report = report
        self.view = view

        self.selected_columns = self.__selected()
        self.available_columns = self.__available()

        self._filters = self.__unknowns_filters(**kwargs)
        columns, values = self.__unknowns_data()
        self.paginator = None
        self.table_data = {
            'header': Header(columns, REP_MARK_TITLES).struct,
            'values': self.__get_page(kwargs.get('page', 1), values)
        }

    def __selected(self):
        columns = []
        for col in self.view['columns']:
            if col not in self.columns_set:
                return []
            if ':' in col:
                col_title = get_column_title(col)
            else:
                col_title = REP_MARK_TITLES.get(col, col)
            columns.append({'value': col, 'title': col_title})
        return columns

    def __available(self):
        self.__is_not_used()
        columns = []
        for col in self.columns_list:
            if ':' in col:
                col_title = get_column_title(col)
            else:
                col_title = REP_MARK_TITLES.get(col, col)
            columns.append({'value': col, 'title': col_title})
        return columns

    def __unknowns_data(self):
        columns = ['number']
        columns.extend(self.view['columns'])

        data = {}
        reports = {}

        annotations = {
            'marks_number': Count('unknown__markreport_set'),
            'confirmed': Count(Case(When(unknown__markreport_set__type='1', then=1)))
        }

        leaves_set = self.report.leaves.annotate(**annotations).filter(~Q(unknown=None) & Q(**self._filters)).values(
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

        if 'problems' in self.view['columns']:
            for r_id, problem, link in MarkUnknownReport.objects.filter(report_id__in=reports)\
                    .exclude(type=ASSOCIATION_TYPE[2][0]).values_list('report_id', 'problem__name', 'mark__link'):
                if 'problems' not in reports[r_id]:
                    reports[r_id]['problems'] = set()
                reports[r_id]['problems'].add((problem, link))
            for r_id in list(reports):
                if 'problems' in reports[r_id]:
                    problems = []
                    has_problem = False
                    for p, l in sorted(reports[r_id]['problems']):
                        if 'problem' in self.view and self.view['problem'][0] == p:
                            has_problem = True
                        problems.append('<a href="{0}">{1}</a>'.format(l, p) if l else p)
                    if 'problem' in self.view and not has_problem:
                        del reports[r_id]
                    else:
                        reports[r_id]['problems'] = '; '.join(problems)
                elif 'problem' in self.view:
                    del reports[r_id]

        for u_id, aname, aval in ReportAttr.objects.filter(report_id__in=reports).order_by('id') \
                .values_list('report_id', 'attr__name__name', 'attr__value'):
            if aname not in data:
                columns.append(aname)
                data[aname] = {}
            data[aname][u_id] = aval

        ids_order_data = []
        # We want reports without ordering parameter to be at the end (with any order direction)
        end_reports = []
        if 'order' in self.view and self.view['order'][1] == 'attr' and self.view['order'][2] in data:
            for rep_id in reports:
                if rep_id in data[self.view['order'][2]]:
                    ids_order_data.append((data[self.view['order'][2]][rep_id], rep_id))
                else:
                    end_reports.append(rep_id)
        elif 'order' in self.view and self.view['order'][1] in {'parent_cpu', 'parent_wall', 'parent_memory'}:
            for rep_id in reports:
                if reports[rep_id][self.view['order'][1]] is None:
                    end_reports.append(rep_id)
                else:
                    ids_order_data.append((reports[rep_id][self.view['order'][1]], rep_id))
        else:
            for u_id in reports:
                ids_order_data.append((reports[u_id]['component'], u_id))
        report_ids = list(x[1] for x in sorted(ids_order_data))
        if 'order' in self.view and self.view['order'][0] == 'up':
            report_ids = list(reversed(report_ids))
        report_ids += list(sorted(end_reports))

        cnt = 1
        values_data = []
        for rep_id in report_ids:
            values_row = []
            for col in columns:
                val = '-'
                href = None
                is_html = False
                if col in data and rep_id in data[col]:
                    val = data[col][rep_id]
                    if not self.__filter_attr(col, val):
                        break
                elif col == 'number':
                    val = cnt
                    href = reverse('reports:unknown', args=[rep_id])
                elif col == 'component':
                    val = reports[rep_id]['component']
                elif col == 'marks_number':
                    val = reports[rep_id]['marks_number']
                elif col == 'problems':
                    if 'problems' in reports[rep_id]:
                        val = reports[rep_id]['problems']
                        is_html = True
                elif col == 'verifiers:cpu':
                    if reports[rep_id]['parent_cpu'] is not None:
                        val = get_user_time(self.user, reports[rep_id]['parent_cpu'])
                elif col == 'verifiers:wall':
                    if reports[rep_id]['parent_wall'] is not None:
                        val = get_user_time(self.user, reports[rep_id]['parent_wall'])
                elif col == 'verifiers:memory':
                    if reports[rep_id]['parent_memory'] is not None:
                        val = get_user_memory(self.user, reports[rep_id]['parent_memory'])
                values_row.append({'value': val, 'href': href, 'html': is_html})
            else:
                cnt += 1
                values_data.append(values_row)
        return columns, values_data

    def __unknowns_filters(self, **kwargs):
        unknowns_filters = {}

        if kwargs.get('component') is not None:
            unknowns_filters['unknown__component_id'] = int(kwargs['component'])
        elif 'component' in self.view and self.view['component'][0] in {'iexact', 'istartswith', 'icontains'}:
            unknowns_filters['unknown__component__name__%s' % self.view['component'][0]] = self.view['component'][1]

        if kwargs.get('attr') is not None:
            unknowns_filters['unknown__attrs__attr'] = kwargs['attr']

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

        problem = kwargs.get('problem')

        if 'marks_number' in self.view and problem != 0:
            if self.view['marks_number'][0] == 'confirmed':
                unknowns_filters['confirmed__%s' % self.view['marks_number'][1]] = int(self.view['marks_number'][2])
            else:
                unknowns_filters['marks_number__%s' % self.view['marks_number'][1]] = int(self.view['marks_number'][2])

        if isinstance(problem, UnknownProblem):
            unknowns_filters['unknown__markreport_set__problem'] = problem
        elif problem == 0:
            unknowns_filters['marks_number'] = 0
        return unknowns_filters

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
    def __init__(self, user, report, view, page=1):
        self.user = user
        self.report = report
        self.view = view

        self.columns = []
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
    def __init__(self, root_id, archive):
        self._root_id = root_id
        self._data = []
        self._name = {}
        self._attrs = {}
        self._files = {}
        if archive is not None:
            self.__get_files(archive)

    def __get_files(self, archive):
        archive.seek(0)
        try:
            files_dir = extract_archive(archive)
        except Exception as e:
            logger.exception("Archive extraction failed: %s" % e, stack_info=True)
            raise ValueError('Archive "%s" with attributes data is corrupted' % archive.name)
        for dir_path, dir_names, file_names in os.walk(files_dir.name):
            for file_name in file_names:
                full_path = os.path.join(dir_path, file_name)
                rel_path = os.path.relpath(full_path, files_dir.name).replace('\\', '/')
                newfile = AttrFile(root_id=self._root_id)
                with open(full_path, mode='rb') as fp:
                    newfile.file.save(os.path.basename(rel_path), File(fp), True)
                self._files[rel_path] = newfile.id

    def add(self, report_id, name, value, compare, associate, data):
        self._data.append((report_id, name, value, compare, associate, self._files.get(data)))
        if name not in self._name:
            self._name[name] = None
        if (name, value) not in self._attrs:
            self._attrs[(name, value)] = None

    def upload(self):
        self.__upload_names()
        self.__upload_attrs()
        ReportAttr.objects.bulk_create(list(ReportAttr(
            report_id=d[0], attr_id=self._attrs[(d[1], d[2])], compare=d[3], associate=d[4], data_id=d[5]
        ) for d in self._data))
        self.__init__(self._root_id, None)

    def __upload_names(self):
        names_to_create = set(self._name) - set(n.name for n in AttrName.objects.filter(name__in=self._name))
        AttrName.objects.bulk_create(list(AttrName(name=name) for name in names_to_create))
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


def get_report_data_type(component, data):
    if component == 'Core' and isinstance(data, dict) and all(isinstance(res, dict) for res in data.values()):
        if all(x in res for x in ['ideal verdict', 'verdict'] for res in data.values()):
            return 'Core:testing'
        elif all(x in res for x in ['before fix', 'after fix'] for res in data.values()) \
                and all('verdict' in data[mod]['before fix'] and 'verdict' in data[mod]['after fix'] for mod in data):
            return 'Core:validation'
    elif component == 'LKVOG' and isinstance(data, dict):
        return 'LKVOG:lines'
    return 'Unknown'


class ReportStatus:
    def __init__(self, report):
        self._report = report
        self.name = _('In progress')
        self.color = '#a4e9eb'
        self.href = None
        self.duration = None
        self.__get_status()

    def __get_status(self):
        if self._report.finish_date is not None:
            self.duration = self._report.finish_date - self._report.start_date
            self.name = _('Finished')
            self.color = '#4ce215'
        try:
            self.href = reverse('reports:unknown', args=[
                ReportUnknown.objects.get(parent=self._report, component=self._report.component).id
            ])
            self.name = _('Failed')
            self.color = None
        except ObjectDoesNotExist:
            pass
        except MultipleObjectsReturned:
            self.name = None


class ReportData:
    def __init__(self, report):
        self._report = report
        self.data = self.__get_data()
        self.type = self.__get_type()

    def __get_type(self):
        component = self._report.component.name
        if component == 'Core' and isinstance(self.data, dict) \
                and all(isinstance(res, dict) for res in self.data.values()):
            if all(x in res for x in ['ideal verdict', 'verdict'] for res in self.data.values()):
                return 'Core:testing'
            elif all(any(x in res for x in ['before fix', 'after fix']) for res in self.data.values()) \
                    and all(('verdict' in self.data[bug]['before fix'] if 'before fix' in self.data[bug] else True)
                            or ('verdict' in self.data[bug]['after fix'] if 'after fix' in self.data[bug] else True)
                            for bug in self.data):
                return 'Core:validation'
        elif component == 'LKVOG' and isinstance(self.data, dict):
            return 'LKVOG:lines'
        return 'Unknown'

    def __get_data(self):
        if self._report.data:
            with self._report.data.file as fp:
                return json.loads(fp.read().decode('utf8'))
        return None
