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
from io import BytesIO
from urllib.parse import unquote
from wsgiref.util import FileWrapper

from django.db.models import Max, Case, When, F, CharField, Value
from django.db.models.expressions import RawSQL
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _
from django.utils.functional import cached_property

from bridge.vars import UNSAFE_VERDICTS, SAFE_VERDICTS, JOB_WEIGHT, ERROR_TRACE_FILE, SAFE_COLOR, UNSAFE_COLOR
from bridge.tableHead import Header
from bridge.utils import BridgeException, ArchiveFileContent
from bridge.ZipGenerator import ZipStream

from reports.models import ReportComponent, ReportAttr, ReportUnsafe, ReportSafe, ReportUnknown, ReportRoot

from users.utils import HumanizedValue, paginate_queryset


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
        concated_title = '{0}/{1}'.format(concated_title, titles[i])
    return concated_title


def get_parents(report, include_self=False):
    parents_ids = list(r.pk for r in report.get_ancestors(include_self=include_self).only('id'))

    parents_data = []
    for report in ReportComponent.objects.filter(id__in=parents_ids).order_by('id').only('id', 'component'):
        parents_data.append({'id': report.id, 'component': report.component})

    # Get attributes for all parents
    attrs = {}
    for attr in ReportAttr.objects.filter(report_id__in=parents_ids)\
            .order_by('name').only('report_id', 'name', 'value'):
        attrs.setdefault(attr.report_id, [])
        attrs[attr.report_id].append({'name': attr.name, 'value': attr.value})
    for parent in parents_data:
        parent['attrs'] = attrs.get(parent['id'], [])
    return parents_data


def report_resources(user, report):
    if all(x is not None for x in [report.wall_time, report.cpu_time, report.memory]):
        return {
            'wall_time': HumanizedValue(report.wall_time, user=user).timedelta,
            'cpu_time': HumanizedValue(report.cpu_time, user=user).timedelta,
            'memory': HumanizedValue(report.memory, user=user).memory
        }
    return None


class ReportAttrsTable:
    def __init__(self, report):
        self._report = report
        self.header, self.values = self.__self_data()

    def __self_data(self):
        columns = []
        values = []
        for ra in self._report.attrs.order_by('id'):
            columns.append(ra.name)
            values.append((ra.value, ra.id if ra.data else None))
        return Header(columns, {}).struct, values


class SafesTable:
    cache_table = 'cache_safe'
    columns_list = ['marks_number', 'report_verdict', 'tags', 'verifiers:cpu', 'verifiers:wall', 'verifiers:memory']
    columns_set = set(columns_list)

    def __init__(self, user, report, view, query_params):
        self.user = user
        self.view = view
        self.paginator, self.page = self.__get_queryset(report, query_params)

        if not self.view['is_unsaved'] and self.paginator.count == 1:
            self.redirect = reverse('reports:safe', args=[self.paginator.object_list.first().pk])
            # Do not collect reports' values if page will be redirected
            return

        self.verdicts = SAFE_VERDICTS
        self.title = self.__get_title(query_params)
        self.parents = None
        if report.root.job.weight == JOB_WEIGHT[0][0]:
            self.parents = get_parents(report, include_self=True)

        self.header, self.values = self.__safes_data()

    def __redirect_link(self):
        if self.view['is_unsaved'] and self.paginator.count == 1:
            return reverse('reports:safe', args=[self.paginator.object_list.first().pk])
        return None

    def __get_ms(self, value, measure):
        if isinstance(value, str):
            value = float(value.replace(',', '.'))
        if measure == 's':
            return value * 1000
        elif measure == 'm':
            return value * 60000
        return value

    def __get_queryset(self, report, query_params):
        qs_filters = {'leaves__report': report}
        annotations = {}
        ordering = 'id'

        # Filter by verdict
        if 'verdict' in query_params:
            qs_filters['cache__verdict'] = query_params['verdict']
        elif 'verdict' in self.view and len(self.view['verdict']):
            qs_filters['cache__verdict__in'] = self.view['verdict']

        # Filter by cpu time
        if 'parent_cpu' in self.view:
            value = self.__get_ms(self.view['parent_cpu'][1], self.view['parent_cpu'][2])
            qs_filters['cpu_time__{}'.format(self.view['parent_cpu'][0])] = value

        # Order by cpu time
        if 'order' in self.view and self.view['order'][1] == 'parent_cpu':
            ordering = 'cpu_time'

        # Filter by wall time
        if 'parent_wall' in self.view:
            value = self.__get_ms(self.view['parent_wall'][1], self.view['parent_wall'][2])
            qs_filters['wall_time__{}'.format(self.view['parent_wall'][0])] = value

        # Order by wall time
        if 'order' in self.view and self.view['order'][1] == 'parent_wall':
            ordering = 'wall_time'

        # Filter by memory
        if 'parent_memory' in self.view:
            value = float(self.view['parent_memory'][1].replace(',', '.'))
            if self.view['parent_memory'][2] == 'KB':
                value *= 1024
            elif self.view['parent_memory'][2] == 'MB':
                value *= 1024 * 1024
            elif self.view['parent_memory'][2] == 'GB':
                value *= 1024 ** 3
            qs_filters['memory__{}'.format(self.view['parent_memory'][0])] = value

        # Order by memory
        if 'order' in self.view and self.view['order'][1] == 'parent_memory':
            ordering = 'memory'

        # Filter by marks number
        if 'confirmed' in query_params:
            qs_filters['cache__marks_confirmed__gt'] = 0
        elif 'marks_number' in self.view:
            if self.view['marks_number'][0] == 'confirmed':
                field = 'cache__marks_confirmed'
            else:
                field = 'cache__marks_total'
            qs_filters["{0}__{1}".format(field, self.view['marks_number'][1])] = int(self.view['marks_number'][2])

        # Filter by tags
        if 'tag' in query_params:
            qs_filters['cache__tags__has_key'] = unquote(query_params['tag'])
        elif 'tags' in self.view:
            view_tags = set(x.strip() for x in self.view['tags'][0].split(';'))
            if '' in view_tags:
                view_tags.remove('')
            if len(view_tags):
                qs_filters['cache__tags__has_any_keys'] = list(view_tags)

        # Filter by attribute(s)
        if 'attr_name' in query_params and 'attr_value' in query_params:
            attr_name = unquote(query_params['attr_name'])
            attr_value = unquote(query_params['attr_value'])
            annotations['attr_value'] = RawSQL(
                "\"{}\".\"attrs\"->>%s".format(self.cache_table),
                (attr_name,)
            )
            qs_filters['attr_value'] = attr_value
        elif 'attr' in self.view:
            annotations['attr_value'] = RawSQL(
                "\"{}\".\"attrs\"->>%s".format(self.cache_table),
                (self.view['attr'][0],)
            )
            qs_filters['attr_value__{}'.format(self.view['attr'][1])] = self.view['attr'][2]

        # Sorting by attribute value
        if 'order' in self.view and self.view['order'][1] == 'attr':
            annotations['ordering_attr'] = RawSQL(
                "\"{}\".\"attrs\"->>%s".format(self.cache_table),
                (self.view['order'][2],)
            )
            ordering = 'ordering_attr'

        # Order direction
        if 'order' in self.view and self.view['order'][0] == 'up':
            ordering = '-' + ordering

        queryset = ReportSafe.objects
        if annotations:
            queryset = queryset.annotate(**annotations)
        queryset = queryset.filter(**qs_filters).exclude(cache=None).order_by(ordering).select_related('cache')
        num_per_page = self.view['elements'][0] if self.view['elements'] else None
        return paginate_queryset(queryset, query_params.get('page', 1), num_per_page)

    def __get_title(self, query_params):
        title = _('Safes')
        if 'confirmed' in query_params:
            title = '{0}: {1}'.format(_("Safes"), _('confirmed'))

        # Either verdict, tag or attr is supported in kwargs
        if 'verdict' in query_params:
            verdict_title = dict(SAFE_VERDICTS)[query_params['verdict']]
            if 'confirmed' in query_params:
                title = '{0}: {1} {2}'.format(_("Safes"), _('confirmed'), verdict_title)
            else:
                title = '{0}: {1}'.format(_("Safes"), verdict_title)
        elif 'tag' in query_params:
            title = '{0}: {1}'.format(_("Safes"), unquote(query_params['tag']))
        elif 'attr_name' in query_params and 'attr_value' in query_params:
            title = _('Safes where %(a_name)s is %(a_val)s') % {
                'a_name': unquote(query_params['attr_name']), 'a_val': unquote(query_params['attr_value'])
            }
        return title

    @cached_property
    def selected_columns(self):
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

    @cached_property
    def available_columns(self):
        columns = []
        for col in self.columns_list:
            if ':' in col:
                col_title = get_column_title(col)
            else:
                col_title = REP_MARK_TITLES.get(col, col)
            columns.append({'value': col, 'title': col_title})
        return columns

    def __safes_data(self):
        safes_ids = list(report.pk for report in self.page)
        cnt = (self.page.number - 1) * self.paginator.per_page + 1

        columns = ['number']
        columns.extend(self.view['columns'])
        attributes = {}
        for r_id, a_name, a_value in ReportAttr.objects.filter(report_id__in=safes_ids).order_by('id')\
                .values_list('report_id', 'name', 'value'):
            if a_name not in attributes:
                columns.append(a_name)
                attributes[a_name] = {}
            attributes[a_name][r_id] = a_value

        verdicts_dict = dict(SAFE_VERDICTS)
        with_confirmed = 'hidden' not in self.view or 'confirmed_marks' not in self.view['hidden']

        values_data = []
        for report in self.page:
            values_row = []
            for col in columns:
                val = '-'
                href = None
                color = None
                if col in attributes:
                    val = attributes[col].get(report.pk, '-')
                elif col == 'number':
                    val = cnt
                    href = reverse('reports:safe', args=[report.pk])
                elif col == 'marks_number':
                    if with_confirmed:
                        val = '{0} ({1})'.format(report.cache.marks_confirmed, report.cache.marks_total)
                    else:
                        val = str(report.cache.marks_total)
                elif col == 'report_verdict':
                    val = verdicts_dict[report.cache.verdict]
                    color = SAFE_COLOR[report.cache.verdict]
                elif col == 'tags':
                    if len(report.cache.tags):
                        tags_values = []
                        for tag in sorted(report.cache.tags):
                            if report.cache.tags[tag] > 1:
                                tags_values.append('{0} ({1})'.format(tag, report.cache.tags[tag]))
                            else:
                                tags_values.append(tag)
                        val = ', '.join(tags_values)
                elif col == 'verifiers:cpu':
                    val = HumanizedValue(report.cpu_time, user=self.user).timedelta
                elif col == 'verifiers:wall':
                    val = HumanizedValue(report.wall_time, user=self.user).timedelta
                elif col == 'verifiers:memory':
                    val = HumanizedValue(report.memory, user=self.user).memory
                values_row.append({'value': val, 'color': color, 'href': href})
            values_data.append(values_row)
            cnt += 1

        return Header(columns, REP_MARK_TITLES).struct, values_data


class UnsafesTable:
    cache_table = 'cache_unsafe'
    columns_list = ['marks_number', 'report_verdict', 'tags', 'verifiers:cpu', 'verifiers:wall', 'verifiers:memory']
    columns_set = set(columns_list)

    def __init__(self, user, report, view, query_params):
        self.user = user
        self.view = view
        self.paginator, self.page = self.__get_queryset(report, query_params)

        if not self.view['is_unsaved'] and self.paginator.count == 1:
            self.redirect = reverse('reports:unsafe', args=[self.paginator.object_list.first().trace_id])
            # Do not collect reports' values if page will be redirected
            return

        self.verdicts = UNSAFE_VERDICTS

        self.title = self.__get_title(query_params)
        self.parents = None
        if report.root.job.weight == JOB_WEIGHT[0][0]:
            self.parents = get_parents(report, include_self=True)

        self.header, self.values = self.__unsafes_data()

    def __get_ms(self, value, measure):
        if isinstance(value, str):
            value = float(value.replace(',', '.'))
        if measure == 's':
            return value * 1000
        elif measure == 'm':
            return value * 60000
        return value

    def __get_queryset(self, report, query_params):
        qs_filters = {'leaves__report': report}
        annotations = {}
        ordering = 'id'

        # Filter by verdict
        if 'verdict' in query_params:
            qs_filters['cache__verdict'] = query_params['verdict']
        elif 'verdict' in self.view and len(self.view['verdict']):
            qs_filters['cache__verdict__in'] = self.view['verdict']

        # Filter by cpu time
        if 'parent_cpu' in self.view:
            value = self.__get_ms(self.view['parent_cpu'][1], self.view['parent_cpu'][2])
            qs_filters['cpu_time__{}'.format(self.view['parent_cpu'][0])] = value

        # Order by cpu time
        if 'order' in self.view and self.view['order'][1] == 'parent_cpu':
            ordering = 'cpu_time'

        # Filter by wall time
        if 'parent_wall' in self.view:
            value = self.__get_ms(self.view['parent_wall'][1], self.view['parent_wall'][2])
            qs_filters['wall_time__{}'.format(self.view['parent_wall'][0])] = value

        # Order by wall time
        if 'order' in self.view and self.view['order'][1] == 'parent_wall':
            ordering = 'wall_time'

        # Filter by memory
        if 'parent_memory' in self.view:
            value = float(self.view['parent_memory'][1].replace(',', '.'))
            if self.view['parent_memory'][2] == 'KB':
                value *= 1024
            elif self.view['parent_memory'][2] == 'MB':
                value *= 1024 * 1024
            elif self.view['parent_memory'][2] == 'GB':
                value *= 1024 ** 3
            qs_filters['memory__{}'.format(self.view['parent_memory'][0])] = value

        # Order by memory
        if 'order' in self.view and self.view['order'][1] == 'parent_memory':
            ordering = 'memory'

        # Filter by marks number
        if 'confirmed' in query_params:
            qs_filters['cache__marks_confirmed__gt'] = 0
        elif 'marks_number' in self.view:
            if self.view['marks_number'][0] == 'confirmed':
                field = 'cache__marks_confirmed'
            else:
                field = 'cache__marks_total'
            qs_filters["{0}__{1}".format(field, self.view['marks_number'][1])] = int(self.view['marks_number'][2])

        # Filter by tags
        if 'tag' in query_params:
            qs_filters['cache__tags__has_key'] = unquote(query_params['tag'])
        elif 'tags' in self.view:
            view_tags = set(x.strip() for x in self.view['tags'][0].split(';'))
            if '' in view_tags:
                view_tags.remove('')
            if len(view_tags):
                qs_filters['cache__tags__has_any_keys'] = list(view_tags)

        # Filter by attribute(s)
        if 'attr_name' in query_params and 'attr_value' in query_params:
            annotations['attr_value'] = RawSQL(
                "\"{}\".\"attrs\"->>%s".format(self.cache_table),
                (unquote(query_params['attr_name']),)
            )
            qs_filters['attr_value'] = unquote(query_params['attr_value'])
        elif 'attr' in self.view:
            annotations['attr_value'] = RawSQL(
                "\"{}\".\"attrs\"->>%s".format(self.cache_table),
                (self.view['attr'][0],)
            )
            qs_filters['attr_value__{}'.format(self.view['attr'][1])] = self.view['attr'][2]

        # Order by attribute value
        if 'order' in self.view and self.view['order'][1] == 'attr':
            annotations['ordering_attr'] = RawSQL(
                "\"{}\".\"attrs\"->>%s".format(self.cache_table),
                (self.view['order'][2],)
            )
            ordering = 'ordering_attr'

        # Order direction
        if 'order' in self.view and self.view['order'][0] == 'up':
            ordering = '-' + ordering

        queryset = ReportUnsafe.objects
        if annotations:
            queryset = queryset.annotate(**annotations)
        queryset = queryset.filter(**qs_filters).exclude(cache=None).order_by(ordering).select_related('cache')
        num_per_page = self.view['elements'][0] if self.view['elements'] else None
        return paginate_queryset(queryset, query_params.get('page', 1), num_per_page)

    def __get_title(self, query_params):
        title = _('Unsafes')
        if 'confirmed' in query_params:
            title = '{0}: {1}'.format(_("Unsafes"), _('confirmed'))

        # Either verdict, tag or attr is supported in kwargs
        if 'verdict' in query_params:
            verdict_title = dict(UNSAFE_VERDICTS)[query_params['verdict']]
            if 'confirmed' in query_params:
                title = '{0}: {1} {2}'.format(_("Unsafes"), _('confirmed'), verdict_title)
            else:
                title = '{0}: {1}'.format(_("Unsafes"), verdict_title)
        elif 'tag' in query_params:
            title = '{0}: {1}'.format(_("Unsafes"), unquote(query_params['tag']))
        elif 'attr_name' in query_params and 'attr_value' in query_params:
            title = _('Unsafes where %(a_name)s is %(a_val)s') % {
                'a_name': unquote(query_params['attr_name']), 'a_val': unquote(query_params['attr_value'])
            }
        return title

    @cached_property
    def selected_columns(self):
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

    @cached_property
    def available_columns(self):
        columns = []
        for col in self.columns_list:
            if ':' in col:
                col_title = get_column_title(col)
            else:
                col_title = REP_MARK_TITLES.get(col, col)
            columns.append({'value': col, 'title': col_title})
        return columns

    def __unsafes_data(self):
        unsafes_ids = list(report.pk for report in self.page)
        cnt = (self.page.number - 1) * self.paginator.per_page + 1

        columns = ['number']
        columns.extend(self.view['columns'])
        attributes = {}
        for r_id, a_name, a_value in ReportAttr.objects.filter(report_id__in=unsafes_ids).order_by('id')\
                .values_list('report_id', 'name', 'value'):
            if a_name not in attributes:
                columns.append(a_name)
                attributes[a_name] = {}
            attributes[a_name][r_id] = a_value

        verdicts_dict = dict(UNSAFE_VERDICTS)
        with_confirmed = 'hidden' not in self.view or 'confirmed_marks' not in self.view['hidden']

        values_data = []
        for report in self.page:
            values_row = []
            for col in columns:
                val = '-'
                href = None
                color = None
                if col in attributes:
                    val = attributes[col].get(report.pk, '-')
                elif col == 'number':
                    val = cnt
                    href = reverse('reports:unsafe', args=[report.trace_id])
                elif col == 'marks_number':
                    if with_confirmed:
                        val = '{0} ({1})'.format(report.cache.marks_confirmed, report.cache.marks_total)
                    else:
                        val = str(report.cache.marks_total)
                elif col == 'report_verdict':
                    val = verdicts_dict[report.cache.verdict]
                    color = UNSAFE_COLOR[report.cache.verdict]
                elif col == 'tags':
                    if len(report.cache.tags):
                        tags_values = []
                        for tag in sorted(report.cache.tags):
                            if report.cache.tags[tag] > 1:
                                tags_values.append('{0} ({1})'.format(tag, report.cache.tags[tag]))
                            else:
                                tags_values.append(tag)
                        val = ', '.join(tags_values)
                elif col == 'verifiers:cpu':
                    val = HumanizedValue(report.cpu_time, user=self.user).timedelta
                elif col == 'verifiers:wall':
                    val = HumanizedValue(report.wall_time, user=self.user).timedelta
                elif col == 'verifiers:memory':
                    val = HumanizedValue(report.memory, user=self.user).memory
                values_row.append({'value': val, 'color': color, 'href': href})
            values_data.append(values_row)
            cnt += 1

        return Header(columns, REP_MARK_TITLES).struct, values_data


class UnknownsTable:
    cache_table = 'cache_unknown'
    columns_list = ['component', 'marks_number', 'problems', 'verifiers:cpu', 'verifiers:wall', 'verifiers:memory']
    columns_set = set(columns_list)

    def __init__(self, user, report, view, query_params):
        self.user = user
        self.view = view
        self.paginator, self.page = self.__get_queryset(report, query_params)

        if not self.view['is_unsaved'] and self.paginator.count == 1:
            self.redirect = reverse('reports:unknown', args=[self.paginator.object_list.first().pk])
            # Do not collect reports' values if page will be redirected
            return

        self.title = self.__get_title(query_params)
        self.parents = None
        if report.root.job.weight == JOB_WEIGHT[0][0]:
            self.parents = get_parents(report, include_self=True)

        self.header, self.values = self.__unknowns_data()

    def __get_ms(self, value, measure):
        if isinstance(value, str):
            value = float(value.replace(',', '.'))
        if measure == 's':
            return value * 1000
        elif measure == 'm':
            return value * 60000
        return value

    def __get_queryset(self, report, query_params):
        qs_filters = {'leaves__report': report}
        annotations = {}
        ordering = 'id'

        # Filter by cpu time
        if 'parent_cpu' in self.view:
            value = self.__get_ms(self.view['parent_cpu'][1], self.view['parent_cpu'][2])
            qs_filters['cpu_time__{}'.format(self.view['parent_cpu'][0])] = value

        # Order by cpu time
        if 'order' in self.view and self.view['order'][1] == 'parent_cpu':
            ordering = 'cpu_time'

        # Filter by wall time
        if 'parent_wall' in self.view:
            value = self.__get_ms(self.view['parent_wall'][1], self.view['parent_wall'][2])
            qs_filters['wall_time__{}'.format(self.view['parent_wall'][0])] = value

        # Order by wall time
        if 'order' in self.view and self.view['order'][1] == 'parent_wall':
            ordering = 'wall_time'

        # Filter by memory
        if 'parent_memory' in self.view:
            value = float(self.view['parent_memory'][1].replace(',', '.'))
            if self.view['parent_memory'][2] == 'KB':
                value *= 1024
            elif self.view['parent_memory'][2] == 'MB':
                value *= 1024 * 1024
            elif self.view['parent_memory'][2] == 'GB':
                value *= 1024 ** 3
            qs_filters['memory__{}'.format(self.view['parent_memory'][0])] = value

        # Order by memory
        if 'order' in self.view and self.view['order'][1] == 'parent_memory':
            ordering = 'memory'

        # Filter by marks number
        if 'confirmed' in query_params:
            qs_filters['cache__marks_confirmed__gt'] = 0
        elif 'marks_number' in self.view:
            if self.view['marks_number'][0] == 'confirmed':
                field = 'cache__marks_confirmed'
            else:
                field = 'cache__marks_total'
            qs_filters["{0}__{1}".format(field, self.view['marks_number'][1])] = int(self.view['marks_number'][2])

        # Filter by attribute(s)
        if 'attr_name' in query_params and 'attr_value' in query_params:
            annotations['attr_value'] = RawSQL(
                "\"{}\".\"attrs\"->>%s".format(self.cache_table),
                (unquote(query_params['attr_name']),)
            )
            qs_filters['attr_value'] = unquote(query_params['attr_value'])
        elif 'attr' in self.view:
            annotations['attr_value'] = RawSQL(
                "\"{}\".\"attrs\"->>%s".format(self.cache_table),
                (self.view['attr'][0],)
            )
            qs_filters['attr_value__{}'.format(self.view['attr'][1])] = self.view['attr'][2]

        # Order by attribute value
        if 'order' in self.view and self.view['order'][1] == 'attr':
            annotations['ordering_attr'] = RawSQL(
                "\"{}\".\"attrs\"->>%s".format(self.cache_table),
                (self.view['order'][2],)
            )
            ordering = 'ordering_attr'

        # Filter by component
        if 'component' in query_params:
            qs_filters['component'] = unquote(query_params['component'])
        elif 'component' in self.view:
            qs_filters['component__{}'.format(self.view['component'][0])] = self.view['component'][1]

        # Filter by problem
        if 'problem' in query_params:
            problem = unquote(query_params['problem'])
            if problem == 'null':
                qs_filters['cache__problems'] = {}
            else:
                qs_filters['cache__problems__has_key'] = problem
        elif 'problem' in self.view:
            qs_filters['cache__problems__has_key'] = self.view['problem'][0].strip()

        # Order direction
        if 'order' in self.view and self.view['order'][0] == 'up':
            ordering = '-' + ordering

        queryset = ReportUnknown.objects
        if annotations:
            queryset = queryset.annotate(**annotations)
        queryset = queryset.filter(**qs_filters).exclude(cache=None).order_by(ordering).select_related('cache')
        num_per_page = self.view['elements'][0] if self.view['elements'] else None
        return paginate_queryset(queryset, query_params.get('page', 1), num_per_page)

    def __get_title(self, query_params):
        title = _('Unknowns')

        # Either problem or attr is supported in kwargs
        if 'problem' in query_params:
            problem = unquote(query_params['problem'])
            if problem == 'null':
                title = _("Unknowns without marks")
            else:
                title = '{0}: {1}'.format(_("Unknowns"), problem)
        elif 'attr_name' in query_params and 'attr_value' in query_params:
            title = _('Unknowns where %(a_name)s is %(a_val)s') % {
                'a_name': unquote(query_params['attr_name']), 'a_val': unquote(query_params['attr_value'])
            }
        return title

    @cached_property
    def selected_columns(self):
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

    @cached_property
    def available_columns(self):
        columns = []
        for col in self.columns_list:
            if ':' in col:
                col_title = get_column_title(col)
            else:
                col_title = REP_MARK_TITLES.get(col, col)
            columns.append({'value': col, 'title': col_title})
        return columns

    def __unknowns_data(self):
        unknowns_ids = list(report.pk for report in self.page)
        cnt = (self.page.number - 1) * self.paginator.per_page + 1

        columns = ['number']
        columns.extend(self.view['columns'])
        attributes = {}
        for r_id, a_name, a_value in ReportAttr.objects.filter(report_id__in=unknowns_ids).order_by('id')\
                .values_list('report_id', 'name', 'value'):
            if a_name not in attributes:
                columns.append(a_name)
                attributes[a_name] = {}
            attributes[a_name][r_id] = a_value

        with_confirmed = 'hidden' not in self.view or 'confirmed_marks' not in self.view['hidden']

        values_data = []
        for report in self.page:
            values_row = []
            for col in columns:
                val = '-'
                href = None
                color = None
                if col in attributes:
                    val = attributes[col].get(report.pk, '-')
                elif col == 'number':
                    val = cnt
                    href = reverse('reports:unknown', args=[report.pk])
                elif col == 'component':
                    val = report.component
                elif col == 'marks_number':
                    if with_confirmed:
                        val = '{0} ({1})'.format(report.cache.marks_confirmed, report.cache.marks_total)
                    else:
                        val = str(report.cache.marks_total)
                elif col == 'tags':
                    if len(report.cache.tags):
                        tags_values = []
                        for tag in sorted(report.cache.tags):
                            if report.cache.tags[tag] > 1:
                                tags_values.append('{0} ({1})'.format(tag, report.cache.tags[tag]))
                            else:
                                tags_values.append(tag)
                        val = ', '.join(tags_values)
                elif col == 'verifiers:cpu':
                    val = HumanizedValue(report.cpu_time, user=self.user).timedelta
                elif col == 'verifiers:wall':
                    val = HumanizedValue(report.wall_time, user=self.user).timedelta
                elif col == 'verifiers:memory':
                    val = HumanizedValue(report.memory, user=self.user).memory
                elif col == 'problems':
                    if len(report.cache.problems):
                        problems_strings = []
                        for problem in sorted(report.cache.problems):
                            if report.cache.problems[problem] > 1:
                                problems_strings.append('{0} ({1})'.format(problem, report.cache.problems[problem]))
                            else:
                                problems_strings.append(problem)
                        val = ', '.join(problems_strings)

                values_row.append({'value': val, 'color': color, 'href': href})
            values_data.append(values_row)
            cnt += 1

        return Header(columns, REP_MARK_TITLES).struct, values_data


class ReportChildrenTable:
    def __init__(self, user, report, view, page=1):
        self.user = user
        self.report = report
        self.view = view

        num_per_page = view['elements'][0] if view['elements'] else None
        self.paginator, self.page = paginate_queryset(self.__get_queryset(), page, num_per_page)

        self.header, self.values = self.__component_data()

    def __get_queryset(self):
        annotations = {}
        qs_filters = {'parent': self.report}

        # Filter by component
        if 'component' in self.view:
            qs_filters['component__' + self.view['component'][0]] = self.view['component'][1]

        # Filter by attribute value
        if 'attr' in self.view:
            annotations['sorting_attr'] = Max(Case(
                When(attrs__name=self.view['attr'][0], then=F('attrs__value')),
                output_field=CharField(), default=Value('')
            ))
            qs_filters['sorting_attr__' + self.view['attr'][1]] = self.view['attr'][2]

        # Get queryset ordering
        ordering = 'id'
        if self.view['order']:
            if self.view['order'][1] == 'component':
                ordering = 'component'
            elif self.view['order'][1] == 'date':
                ordering = 'finish_date'
            elif self.view['order'][1] == 'attr':
                annotations['ordering_attr'] = Max(Case(
                    When(attrs__name=self.view['order'][2], then=F('attrs__value')),
                    output_field=CharField(null=True)
                ))
                ordering = 'ordering_attr'

            ordering = F(ordering)
            if self.view['order'][0] == 'up':
                ordering = ordering.desc(nulls_last=True)
            else:
                ordering = ordering.asc(nulls_last=True)

        queryset = ReportComponent.objects
        if annotations:
            queryset = queryset.values('id').annotate(**annotations)
        return queryset.filter(**qs_filters).order_by(ordering).only('id', 'component')

    def __component_data(self):
        report_ids = list(report.id for report in self.page)

        columns = ['component']
        reports_data = dict((report.id, {
            'component': {'value': report.component, 'href': reverse('reports:component', args=[report.id])}
        }) for report in self.page)

        for r_id, name, value in ReportAttr.objects.filter(report_id__in=report_ids).order_by('id') \
                .values_list('report_id', 'name', 'value'):
            if name not in columns:
                columns.append(name)
            reports_data[r_id][name] = {'value': value}

        values_data = list(
            list(
                reports_data[report.id].get(col, '-') for col in columns
            ) for report in self.page
        )
        return Header(columns, REP_MARK_TITLES).struct, values_data


class FilesForCompetitionArchive:
    obj_attr = 'Program fragment'
    requirement_attr = 'Requirements specification'

    def __init__(self, job, filters):
        try:
            self.root = ReportRoot.objects.get(job=job)
        except ReportRoot.DoesNotExist:
            raise BridgeException(_('The job is not decided'))
        self._attrs = self.__get_attrs()
        self._archives = self.__get_archives()
        self._archives_to_upload = []
        self.__get_archives_to_upload(filters)
        self.stream = ZipStream()
        self.name = 'svcomp.zip'

    def __iter__(self):
        cnt = 0
        names_in_use = set()
        for arch_path, name_pattern in self._archives_to_upload:
            if name_pattern in names_in_use:
                cnt += 1
                arch_name = '%s_%s.zip' % (name_pattern, cnt)
            else:
                arch_name = '%s.zip' % name_pattern
            names_in_use.add(name_pattern)

            for data in self.stream.compress_file(arch_path, arch_name):
                yield data

        yield self.stream.close_stream()

    def __get_archives(self):
        archives = {}
        for report in ReportComponent.objects.filter(root=self.root, verification=True)\
                .exclude(verifier_files='').only('id', 'verifier_files'):
            archives[report.id] = report.verifier_files.path
        return archives

    def __get_attrs(self):
        # Select attributes for all safes, unsafes and unknowns
        attrs = {}
        for report_id, a_name, a_value in ReportAttr.objects\
                .filter(report__root=self.root, name__in=[self.obj_attr, self.requirement_attr]) \
                .exclude(report__reportunsafe=None, report__reportsafe=None, report__reportunknown=None) \
                .values_list('report_id', 'name', 'value'):
            if report_id not in attrs:
                attrs[report_id] = {}
            attrs[report_id][a_name] = a_value
        return attrs

    def __add_archive(self, r_type, r_id, p_id):
        if p_id in self._archives and r_id in self._attrs \
                and self.obj_attr in self._attrs[r_id] \
                and self.requirement_attr in self._attrs[r_id]:

            ver_obj = self._attrs[r_id][self.obj_attr].replace('~', 'HOME').replace('/', '---')
            ver_requirement = self._attrs[r_id][self.requirement_attr].replace(':', '-')
            dirname = 'Unknowns' if r_type == 'f' else 'Unsafes' if r_type == 'u' else 'Safes'

            self._archives_to_upload.append(
                (self._archives[p_id], '{0}/{1}__{2}__{3}'.format(dirname, r_type, ver_requirement, ver_obj))
            )

    def __get_archives_to_upload(self, filters):
        common_filters = {'root': self.root, 'parent__reportcomponent__verification': True}
        if filters.get('safes'):
            for r_id, p_id in ReportSafe.objects.filter(**common_filters).values_list('id', 'parent_id'):
                self.__add_archive('s', r_id, p_id)
        if filters.get('unsafes'):
            for r_id, p_id in ReportUnsafe.objects.filter(**common_filters).values_list('id', 'parent_id'):
                self.__add_archive('u', r_id, p_id)
        if filters.get('problems'):
            for problem_data in filters['problems']:
                if problem_data.get('component') and problem_data.get('problem'):
                    unknowns_qs = ReportUnknown.objects.filter(
                        markreport_set__problem=problem_data['problem'],
                        component=problem_data['component'], **common_filters
                    )
                else:
                    unknowns_qs = ReportUnknown.objects.filter(cache__marks_total=0, **common_filters)
                for r_id, p_id in unknowns_qs.values_list('id', 'parent_id'):
                    self.__add_archive('f', r_id, p_id)
        elif filters.get('unknowns'):
            for r_id, p_id in ReportUnknown.objects.filter(**common_filters).values_list('id', 'parent_id'):
                self.__add_archive('f', r_id, p_id)


def report_attributes_with_parents(report):
    reports_ids = list(report.get_ancestors(include_self=True).values_list('id', flat=True))
    attrs_qs = ReportAttr.objects.filter(report_id__in=reports_ids).order_by('report_id', 'id')
    return list(attrs_qs.values_list('name', 'value'))


def remove_verifier_files(job):
    for report in ReportComponent.objects.filter(root=job.reportroot, verification=True).exclude(verifier_files=''):
        report.verifier_files.delete()


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
        self.name = _('In progress')
        self.color = '#a4e9eb'
        self.href = None
        self.duration = None
        self.__get_status(report)

    def __get_status(self, report):
        if report.finish_date is not None:
            self.duration = report.finish_date - report.start_date
            self.name = _('Finished')
            self.color = '#4ce215'
        try:
            self.href = reverse('reports:unknown', args=[
                ReportUnknown.objects.get(parent=report, component=report.component).id
            ])
            self.name = _('Failed')
            self.color = None
        except ReportUnknown.DoesNotExist:
            pass
        except ReportUnknown.MultipleObjectsReturned:
            self.name = None


class ReportData:
    def __init__(self, report):
        self._report = report
        self.data = self._report.data
        self.type = self.__get_type()

    def __get_type(self):
        component = self._report.component
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


class ComponentLogGenerator(FileWrapper):
    def __init__(self, instance):
        if not instance.log:
            raise BridgeException(_("The component doesn't have log"))
        self.name = "{0}-log.zip".format(instance.component)
        self.size = instance.log.file.size
        super().__init__(instance.log.file, 8192)


class AttrDataGenerator(FileWrapper):
    def __init__(self, instance):
        if not instance.data:
            raise BridgeException(_("The attribute doesn't have data"))
        self.name = 'Attr-Data{}'.format(os.path.splitext(instance.data.file.name)[-1])
        self.size = instance.data.file.size
        super().__init__(instance.data.file, 8192)


class VerifierFilesGenerator(FileWrapper):
    def __init__(self, instance):
        if not instance.verifier_files:
            raise BridgeException(_("The report doesn't have verifier input files"))
        self.name = '%s input files.zip' % instance.component
        self.size = instance.verifier_files.file.size
        super().__init__(instance.verifier_files.file, 8192)


class ErrorTraceFileGenerator(FileWrapper):
    def __init__(self, report):
        content = ArchiveFileContent(report, 'error_trace', ERROR_TRACE_FILE).content
        self.name = 'error trace.json'
        self.size = len(content)
        super().__init__(BytesIO(content), 8192)
