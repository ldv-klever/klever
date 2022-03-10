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

import json
import os
from collections import OrderedDict
from io import BytesIO
from urllib.parse import unquote
from wsgiref.util import FileWrapper

from django.db.models import Max, Case, When, F, Q, CharField, Value
from django.db.models.expressions import RawSQL
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.functional import cached_property

from bridge.vars import UNSAFE_VERDICTS, UNSAFE_STATUS, SAFE_VERDICTS, DECISION_WEIGHT, ERROR_TRACE_FILE, SUBJOB_NAME
from bridge.utils import BridgeException, ArchiveFileContent
from bridge.ZipGenerator import ZipStream

from jobs.models import PresetJob, Job, Decision
from reports.models import (
    Report, ReportComponent, ReportAttr, ReportUnsafe, ReportSafe, ReportUnknown, CoverageArchive, ReportImage
)
from caches.models import ReportSafeCache, ReportUnsafeCache, ReportUnknownCache

from users.utils import HumanizedValue, paginate_queryset
from reports.verdicts import safe_color, unsafe_color, bug_status_color


REP_MARK_TITLES = {
    'mark_num': _('Mark'),
    'mark_verdict': _("Verdict"),
    'mark_result': _('Similarity'),
    'mark_status': _('Status'),
    'number': _('#'),
    'component': _('Component'),

    'marks_number': _("Similar marks associations"),
    'marks_number:confirmed': _("Confirmed"),
    'marks_number:automatic': _("Automatic"),
    'report_verdict': _("Total verdict"),
    'report_status': _("Total status"),

    'tags': _('Tags'),
    'verifier': _('Verifier'),
    'verifier:cpu': _('CPU time'),
    'verifier:wall': _('Wall time'),
    'verifier:memory': _('Memory size'),
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
    reports_qs = ReportComponent.objects.filter(id__in=parents_ids).select_related('decision')\
        .order_by('id').only('id', 'identifier', 'component', 'decision_id', 'decision__identifier')
    for report in reports_qs:
        parents_data.append({
            'id': report.id, 'component': report.component,
            'url': reverse('reports:component', args=[report.decision.identifier, report.identifier])
        })

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


def leaf_verifier_files_url(report):
    parent_qs = ReportComponent.objects.filter(id=report.parent_id, verification=True).exclude(verifier_files='')
    if parent_qs.exists():
        return reverse('reports:download_files', args=[report.parent_id])
    return None


def collapse_reports(decision):
    if decision.weight == DECISION_WEIGHT[1][0]:
        # The decision is already lightweight
        return

    if ReportComponent.objects.filter(decision=decision, component=SUBJOB_NAME).exists():
        return
    core = ReportComponent.objects.get(decision=decision, parent=None)
    ReportComponent.objects.filter(decision=decision, verification=True).update(parent=core)
    ReportUnknown.objects.filter(decision=decision, parent__reportcomponent__verification=False).update(parent=core)

    # Non-verification reports except Core
    reports_qs = ReportComponent.objects.filter(decision=decision).exclude(Q(verification=True) | Q(parent=None))

    # Update core original and additional sources
    report_with_original = reports_qs.exclude(original_sources=None).first()
    if report_with_original:
        core.original_sources = report_with_original.original_sources
    report_with_additional = reports_qs.exclude(additional_sources=None).first()
    if report_with_additional:
        core.additional_sources = report_with_additional.additional_sources
    core.save()

    # Move coverage to core
    CoverageArchive.objects.filter(report__decision=decision, report__verification=False).update(report=core)

    # Remove all non-verification reports except Core
    reports_qs.delete()

    # Rebuild mptt tree of the current decision
    Report.objects.partial_rebuild(core.tree_id)

    # Update decision weight
    decision.weight = DECISION_WEIGHT[1][0]
    decision.save()


def report_attributes_with_parents(report):
    reports_ids = list(report.get_ancestors(include_self=True).values_list('id', flat=True))
    attrs_qs = ReportAttr.objects.filter(report_id__in=reports_ids).order_by('report_id', 'id')
    return list(attrs_qs.values_list('name', 'value'))


def get_report_data_type(component, data):
    if component == 'Core' and isinstance(data, dict) and all(isinstance(res, dict) for res in data.values()):
        if all(x in res for x in ['ideal verdict', 'verdict'] for res in data.values()):
            return 'Core:testing'
        elif all(x in res for x in ['before fix', 'after fix'] for res in data.values()) \
                and all('verdict' in data[mod]['before fix'] and 'verdict' in data[mod]['after fix'] for mod in data):
            return 'Core:validation'
    elif component == 'PFG' and isinstance(data, dict):
        return 'PRG:lines'
    return 'Unknown'


class ReportAttrsTable:
    def __init__(self, report):
        self._report = report
        self.columns, self.values = self.__self_data()

    def __self_data(self):
        columns = []
        values = []
        for ra in self._report.attrs.order_by('id'):
            columns.append(ra.name)
            values.append((ra.value, ra.id if ra.data else None))
        return columns, values


class SafesTable:
    columns_list = ['marks_number', 'report_verdict', 'tags', 'verifier:cpu', 'verifier:wall', 'verifier:memory']
    confirmed_col = 'marks_number:confirmed'
    automatic_col = 'marks_number:automatic'

    def __init__(self, user, report, view, query_params):
        self.user = user
        self.view = view
        self._params = query_params
        self.paginator, self.page = self.__get_queryset(report)

        if not self.view['is_unsaved'] and self.paginator.count == 1:
            safe_obj = self.paginator.object_list.first()
            self.redirect = reverse('reports:safe', args=[safe_obj.decision.identifier, safe_obj.identifier])

            # Do not collect reports' values if page will be redirected
            return

        self.verdicts = SAFE_VERDICTS
        self.title = self.__get_title()
        self.parents = None
        if report.decision.weight == DECISION_WEIGHT[0][0]:
            self.parents = get_parents(report, include_self=True)

        self.titles = REP_MARK_TITLES
        self.columns, self.values = self.__safes_data()

    @cached_property
    def _manual(self):
        if 'manual' not in self._params:
            return None
        return bool(int(self._params['manual']))

    @cached_property
    def _detailed(self):
        return 'hidden' not in self.view or 'confirmed_marks' not in self.view['hidden']

    @cached_property
    def _cache_db_table(self):
        return getattr(ReportSafeCache, '_meta').db_table

    @cached_property
    def _columns_set(self):
        return set(self.columns_list)

    def __get_ms(self, value, measure):
        if isinstance(value, str):
            value = float(value.replace(',', '.'))
        if measure == 's':
            return value * 1000
        elif measure == 'm':
            return value * 60000
        return value

    def __get_queryset(self, report):
        qs_filters = {'leaves__report': report}
        annotations = {}
        ordering = 'id'

        # Filter by verdict
        if 'verdict' in self._params:
            qs_filters['cache__verdict'] = self._params['verdict']
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
        if self._manual is True:
            qs_filters['cache__marks_confirmed__gt'] = 0
        elif self._manual is False:
            qs_filters['cache__marks_confirmed'] = 0
            qs_filters['cache__marks_automatic__gt'] = 0
        elif 'marks_number' in self.view:
            if self.view['marks_number'][0] == 'confirmed':
                field = 'cache__marks_confirmed'
            elif self.view['marks_number'][0] == 'automatic':
                field = 'cache__marks_automatic'
            else:
                field = 'cache__marks_total'
            qs_filters["{0}__{1}".format(field, self.view['marks_number'][1])] = int(self.view['marks_number'][2])

        # Filter by tags
        if 'tag' in self._params:
            qs_filters['cache__tags__has_key'] = unquote(self._params['tag'])

        # Filter by attribute(s)
        if 'attr_name' in self._params and 'attr_value' in self._params:
            attr_name = unquote(self._params['attr_name'])
            attr_value = unquote(self._params['attr_value'])
            annotations['attr_value'] = RawSQL(
                "\"{}\".\"attrs\"->>%s".format(self._cache_db_table),
                (attr_name,)
            )
            qs_filters['attr_value'] = attr_value
        elif 'attr' in self.view:
            annotations['attr_value'] = RawSQL(
                "\"{}\".\"attrs\"->>%s".format(self._cache_db_table),
                (self.view['attr'][0],)
            )
            qs_filters['attr_value__{}'.format(self.view['attr'][1])] = self.view['attr'][2]

        # Sorting by attribute value
        if 'order' in self.view and self.view['order'][1] == 'attr':
            annotations['ordering_attr'] = RawSQL(
                "\"{}\".\"attrs\"->>%s".format(self._cache_db_table),
                (self.view['order'][2],)
            )
            ordering = 'ordering_attr'

        # Order direction
        if 'order' in self.view and self.view['order'][0] == 'up':
            ordering = '-' + ordering

        queryset = ReportSafe.objects
        if annotations:
            queryset = queryset.annotate(**annotations)
        queryset = queryset.filter(**qs_filters).exclude(cache=None)\
            .order_by(ordering).select_related('cache', 'decision')
        num_per_page = self.view['elements'][0] if self.view['elements'] else None
        return paginate_queryset(queryset, self._params.get('page', 1), num_per_page)

    def __get_title(self):
        title = _('Safes')

        # Either verdict, tag or attr is supported in kwargs
        if 'verdict' in self._params:
            verdict_title = dict(SAFE_VERDICTS)[self._params['verdict']]
            if self._manual is True:
                title = '{}: {} {}'.format(_("Safes"), _('manually assessed'), verdict_title)
            elif self._manual is False:
                title = '{}: {} {}'.format(_("Safes"), _('automatically assessed'), verdict_title)
            else:
                title = '{}: {}'.format(_("Safes"), verdict_title)
        elif 'tag' in self._params:
            title = '{0}: {1}'.format(_("Safes"), unquote(self._params['tag']))
        elif 'attr_name' in self._params and 'attr_value' in self._params:
            title = _('Safes where %(a_name)s is %(a_val)s') % {
                'a_name': unquote(self._params['attr_name']),
                'a_val': unquote(self._params['attr_value'])
            }
        return title

    @cached_property
    def selected_columns(self):
        columns = []
        for col in self.view['columns']:
            if col not in self._columns_set:
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

    @cached_property
    def _attributes(self):
        queryset = ReportAttr.objects.filter(report_id__in=list(report.pk for report in self.page))\
            .order_by('id').values_list('report_id', 'name', 'value')
        attributes = OrderedDict()
        for r_id, a_name, a_value in queryset:
            if a_name not in attributes:
                attributes[a_name] = {}
            attributes[a_name][r_id] = a_value
        return attributes

    def __safes_data(self):
        cnt = (self.page.number - 1) * self.paginator.per_page + 1

        # Collect columns
        columns = ['number']
        for view_col in self.view['columns']:
            if view_col == 'marks_number' and self._detailed:
                columns.extend([self.confirmed_col, self.automatic_col])
            else:
                columns.append(view_col)
        columns.extend(list(self._attributes))

        verdicts_dict = dict(SAFE_VERDICTS)

        values_data = []
        for report in self.page:
            values_row = []
            for col in columns:
                val = '-'
                href = None
                color = None
                if col in self._attributes:
                    val = self._attributes[col].get(report.pk, '-')
                elif col == 'number':
                    val = cnt
                    href = reverse('reports:safe', args=[report.decision.identifier, report.identifier])
                elif col == 'marks_number':
                    val = str(report.cache.marks_total)
                elif col == self.confirmed_col:
                    val = str(report.cache.marks_confirmed)
                elif col == self.automatic_col:
                    val = str(report.cache.marks_automatic)
                elif col == 'report_verdict':
                    val = verdicts_dict[report.cache.verdict]
                    color = safe_color(report.cache.verdict)
                elif col == 'tags':
                    if len(report.cache.tags):
                        tags_values = []
                        for tag in sorted(report.cache.tags):
                            shortname = tag.split(' - ')[-1]
                            if report.cache.tags[tag] > 1:
                                tags_values.append('{0} ({1})'.format(shortname, report.cache.tags[tag]))
                            else:
                                tags_values.append(shortname)
                        val = ', '.join(tags_values)
                elif col == 'verifier:cpu':
                    val = HumanizedValue(report.cpu_time, user=self.user).timedelta
                elif col == 'verifier:wall':
                    val = HumanizedValue(report.wall_time, user=self.user).timedelta
                elif col == 'verifier:memory':
                    val = HumanizedValue(report.memory, user=self.user).memory
                values_row.append({'value': val, 'color': color, 'href': href})
            values_data.append(values_row)
            cnt += 1

        return columns, values_data


class UnsafesTable:
    columns_list = [
        'marks_number', 'report_verdict', 'report_status', 'tags',
        'verifier:cpu', 'verifier:wall', 'verifier:memory'
    ]
    confirmed_col = 'marks_number:confirmed'
    automatic_col = 'marks_number:automatic'

    def __init__(self, user, report, view, query_params):
        self.user = user
        self.view = view
        self._params = query_params
        self.paginator, self.page = self.__get_queryset(report)

        if not self.view['is_unsaved'] and self.paginator.count == 1:
            unsafe_obj = self.paginator.object_list.first()
            self.redirect = reverse('reports:unsafe', args=[unsafe_obj.decision.identifier, unsafe_obj.identifier])
            # Do not collect reports' values if page will be redirected
            return

        self.verdicts = UNSAFE_VERDICTS

        self.title = self.__get_title()
        self.parents = None
        if report.decision.weight == DECISION_WEIGHT[0][0]:
            self.parents = get_parents(report, include_self=True)

        self.titles = REP_MARK_TITLES
        self.columns, self.values = self.__unsafes_data()

    @cached_property
    def _manual(self):
        if 'manual' not in self._params:
            return None
        return bool(int(self._params['manual']))

    @cached_property
    def _detailed(self):
        return 'hidden' not in self.view or 'confirmed_marks' not in self.view['hidden']

    @cached_property
    def _cache_db_table(self):
        return getattr(ReportUnsafeCache, '_meta').db_table

    @cached_property
    def _columns_set(self):
        return set(self.columns_list)

    def __get_ms(self, value, measure):
        if isinstance(value, str):
            value = float(value.replace(',', '.'))
        if measure == 's':
            return value * 1000
        elif measure == 'm':
            return value * 60000
        return value

    def __get_queryset(self, report):
        qs_filters = {'leaves__report': report}
        annotations = {}
        ordering = 'id'

        # Filter by verdict
        if 'verdict' in self._params:
            qs_filters['cache__verdict'] = self._params['verdict']
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
        if self._manual is True:
            qs_filters['cache__marks_confirmed__gt'] = 0
        elif self._manual is False:
            qs_filters['cache__marks_confirmed'] = 0
            qs_filters['cache__marks_automatic__gt'] = 0
        elif 'marks_number' in self.view:
            if self.view['marks_number'][0] == 'confirmed':
                field = 'cache__marks_confirmed'
            elif self.view['marks_number'][0] == 'automatic':
                field = 'cache__marks_automatic'
            else:
                field = 'cache__marks_total'
            qs_filters["{0}__{1}".format(field, self.view['marks_number'][1])] = int(self.view['marks_number'][2])

        # Filter by tags
        if 'tag' in self._params:
            qs_filters['cache__tags__has_key'] = unquote(self._params['tag'])

        # Filter by attribute(s)
        if 'attr_name' in self._params and 'attr_value' in self._params:
            annotations['attr_value'] = RawSQL(
                "\"{}\".\"attrs\"->>%s".format(self._cache_db_table),
                (unquote(self._params['attr_name']),)
            )
            qs_filters['attr_value'] = unquote(self._params['attr_value'])
        elif 'attr' in self.view:
            annotations['attr_value'] = RawSQL(
                "\"{}\".\"attrs\"->>%s".format(self._cache_db_table),
                (self.view['attr'][0],)
            )
            qs_filters['attr_value__{}'.format(self.view['attr'][1])] = self.view['attr'][2]

        # Order by attribute value
        if 'order' in self.view and self.view['order'][1] == 'attr':
            annotations['ordering_attr'] = RawSQL(
                "\"{}\".\"attrs\"->>%s".format(self._cache_db_table),
                (self.view['order'][2],)
            )
            ordering = 'ordering_attr'

        # Order direction
        if 'order' in self.view and self.view['order'][0] == 'up':
            ordering = '-' + ordering

        queryset = ReportUnsafe.objects
        if annotations:
            queryset = queryset.annotate(**annotations)
        queryset = queryset.filter(**qs_filters).exclude(cache=None).order_by(ordering)\
            .select_related('cache', 'decision')
        num_per_page = self.view['elements'][0] if self.view['elements'] else None
        return paginate_queryset(queryset, self._params.get('page', 1), num_per_page)

    def __get_title(self):
        title = _('Unsafes')

        # Either verdict, tag or attr is supported in kwargs
        if 'verdict' in self._params:
            verdict_title = dict(UNSAFE_VERDICTS)[self._params['verdict']]
            if self._manual is True:
                title = '{}: {} {}'.format(_("Unsafes"), _('manually assessed'), verdict_title)
            elif self._manual is False:
                title = '{}: {} {}'.format(_("Unsafes"), _('automatically assessed'), verdict_title)
            else:
                title = '{}: {}'.format(_("Unsafes"), verdict_title)
        elif 'tag' in self._params:
            title = '{0}: {1}'.format(_("Unsafes"), unquote(self._params['tag']))
        elif 'attr_name' in self._params and 'attr_value' in self._params:
            title = _('Unsafes where %(a_name)s is %(a_val)s') % {
                'a_name': unquote(self._params['attr_name']),
                'a_val': unquote(self._params['attr_value'])
            }
        return title

    @cached_property
    def selected_columns(self):
        columns = []
        for col in self.view['columns']:
            if col not in self._columns_set:
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

    @cached_property
    def _attributes(self):
        queryset = ReportAttr.objects.filter(report_id__in=list(report.pk for report in self.page)) \
            .order_by('id').values_list('report_id', 'name', 'value')
        attributes = OrderedDict()
        for r_id, a_name, a_value in queryset:
            if a_name not in attributes:
                attributes[a_name] = {}
            attributes[a_name][r_id] = a_value
        return attributes

    def __unsafes_data(self):
        cnt = (self.page.number - 1) * self.paginator.per_page + 1

        # Collect columns
        columns = ['number']
        for view_col in self.view['columns']:
            if view_col == 'marks_number' and self._detailed:
                columns.extend([self.confirmed_col, self.automatic_col])
            else:
                columns.append(view_col)
        columns.extend(list(self._attributes))

        verdicts_dict = dict(UNSAFE_VERDICTS)
        statuses_dict = dict(UNSAFE_STATUS)

        values_data = []
        for report in self.page:
            values_row = []
            for col in columns:
                val = '-'
                href = None
                color = None
                if col in self._attributes:
                    val = self._attributes[col].get(report.pk, '-')
                elif col == 'number':
                    val = cnt
                    href = reverse('reports:unsafe', args=[report.decision.identifier, report.identifier])
                elif col == 'marks_number':
                    val = str(report.cache.marks_total)
                elif col == self.confirmed_col:
                    val = str(report.cache.marks_confirmed)
                elif col == self.automatic_col:
                    val = str(report.cache.marks_automatic)
                elif col == 'report_verdict':
                    val = verdicts_dict[report.cache.verdict]
                    color = unsafe_color(report.cache.verdict)
                elif col == 'report_status':
                    if report.cache.status:
                        val = statuses_dict[report.cache.status]
                        color = bug_status_color(report.cache.status)
                elif col == 'tags':
                    if len(report.cache.tags):
                        tags_values = []
                        for tag in sorted(report.cache.tags):
                            shortname = tag.split(' - ')[-1]
                            if report.cache.tags[tag] > 1:
                                tags_values.append('{0} ({1})'.format(shortname, report.cache.tags[tag]))
                            else:
                                tags_values.append(shortname)
                        val = ', '.join(tags_values)
                elif col == 'verifier:cpu':
                    val = HumanizedValue(report.cpu_time, user=self.user).timedelta
                elif col == 'verifier:wall':
                    val = HumanizedValue(report.wall_time, user=self.user).timedelta
                elif col == 'verifier:memory':
                    val = HumanizedValue(report.memory, user=self.user).memory
                values_row.append({'value': val, 'color': color, 'href': href})
            values_data.append(values_row)
            cnt += 1

        return columns, values_data


class UnknownsTable:
    columns_list = ['component', 'marks_number', 'problems', 'verifier:cpu', 'verifier:wall', 'verifier:memory']
    confirmed_col = 'marks_number:confirmed'
    automatic_col = 'marks_number:automatic'

    def __init__(self, user, report, view, query_params):
        self.user = user
        self.view = view
        self._params = query_params
        self.paginator, self.page = self.__get_queryset(report)

        if not self.view['is_unsaved'] and self.paginator.count == 1:
            unknown_obj = self.paginator.object_list.first()
            self.redirect = reverse('reports:unknown', args=[unknown_obj.decision.identifier, unknown_obj.identifier])
            # Do not collect reports' values if page will be redirected
            return

        self.title = self.__get_title()
        self.parents = None
        if report.decision.weight == DECISION_WEIGHT[0][0]:
            self.parents = get_parents(report, include_self=True)

        self.titles = REP_MARK_TITLES
        self.columns, self.values = self.__unknowns_data()

    @cached_property
    def _manual(self):
        if 'manual' not in self._params:
            return None
        return bool(int(self._params['manual']))

    @cached_property
    def _detailed(self):
        return 'hidden' not in self.view or 'confirmed_marks' not in self.view['hidden']

    @cached_property
    def _cache_db_table(self):
        return getattr(ReportUnknownCache, '_meta').db_table

    @cached_property
    def _columns_set(self):
        return set(self.columns_list)

    def __get_ms(self, value, measure):
        if isinstance(value, str):
            value = float(value.replace(',', '.'))
        if measure == 's':
            return value * 1000
        elif measure == 'm':
            return value * 60000
        return value

    def __get_queryset(self, report):
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
        if self._manual is True:
            qs_filters['cache__marks_confirmed__gt'] = 0
        elif self._manual is False:
            qs_filters['cache__marks_confirmed'] = 0
            qs_filters['cache__marks_automatic__gt'] = 0
        elif 'marks_number' in self.view:
            if self.view['marks_number'][0] == 'confirmed':
                field = 'cache__marks_confirmed'
            elif self.view['marks_number'][0] == 'automatic':
                field = 'cache__marks_automatic'
            else:
                field = 'cache__marks_total'
            qs_filters["{0}__{1}".format(field, self.view['marks_number'][1])] = int(self.view['marks_number'][2])

        # Filter by attribute(s)
        if 'attr_name' in self._params and 'attr_value' in self._params:
            annotations['attr_value'] = RawSQL(
                "\"{}\".\"attrs\"->>%s".format(self._cache_db_table),
                (unquote(self._params['attr_name']),)
            )
            qs_filters['attr_value'] = unquote(self._params['attr_value'])
        elif 'attr' in self.view:
            annotations['attr_value'] = RawSQL(
                "\"{}\".\"attrs\"->>%s".format(self._cache_db_table),
                (self.view['attr'][0],)
            )
            qs_filters['attr_value__{}'.format(self.view['attr'][1])] = self.view['attr'][2]

        # Order by attribute value
        if 'order' in self.view and self.view['order'][1] == 'attr':
            annotations['ordering_attr'] = RawSQL(
                "\"{}\".\"attrs\"->>%s".format(self._cache_db_table),
                (self.view['order'][2],)
            )
            ordering = 'ordering_attr'

        # Filter by component
        if 'component' in self._params:
            qs_filters['component'] = unquote(self._params['component'])
        elif 'component' in self.view:
            qs_filters['component__{}'.format(self.view['component'][0])] = self.view['component'][1]

        # Filter by problem
        if 'problem' in self._params:
            problem = unquote(self._params['problem'])
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
        queryset = queryset.filter(**qs_filters).exclude(cache=None).order_by(ordering)\
            .select_related('cache', 'decision')
        num_per_page = self.view['elements'][0] if self.view['elements'] else None
        return paginate_queryset(queryset, self._params.get('page', 1), num_per_page)

    def __get_title(self):
        title = _('Unknowns')

        # Either problem or attr is supported in kwargs
        if 'problem' in self._params:
            problem = unquote(self._params['problem'])
            if problem == 'null':
                title = _("Unknowns without marks")
            elif self._manual is True:
                title = '{}: {} {}'.format(_("Unknowns"), _('manually assessed'), problem)
            elif self._manual is False:
                title = '{}: {} {}'.format(_("Unknowns"), _('automatically assessed'), problem)
            else:
                title = '{}: {}'.format(_("Unknowns"), problem)
        elif 'attr_name' in self._params and 'attr_value' in self._params:
            title = _('Unknowns where %(a_name)s is %(a_val)s') % {
                'a_name': unquote(self._params['attr_name']), 'a_val': unquote(self._params['attr_value'])
            }
        return title

    @cached_property
    def selected_columns(self):
        columns = []
        for col in self.view['columns']:
            if col not in self._columns_set:
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

    @cached_property
    def _attributes(self):
        queryset = ReportAttr.objects.filter(report_id__in=list(report.pk for report in self.page)) \
            .order_by('id').values_list('report_id', 'name', 'value')
        attributes = OrderedDict()
        for r_id, a_name, a_value in queryset:
            if a_name not in attributes:
                attributes[a_name] = {}
            attributes[a_name][r_id] = a_value
        return attributes

    def __unknowns_data(self):
        cnt = (self.page.number - 1) * self.paginator.per_page + 1

        # Collect columns
        columns = ['number']
        for view_col in self.view['columns']:
            if view_col == 'marks_number' and self._detailed:
                columns.extend([self.confirmed_col, self.automatic_col])
            else:
                columns.append(view_col)
        columns.extend(list(self._attributes))

        values_data = []
        for report in self.page:
            values_row = []
            for col in columns:
                val = '-'
                href = None
                color = None
                if col in self._attributes:
                    val = self._attributes[col].get(report.pk, '-')
                elif col == 'number':
                    val = cnt
                    href = reverse('reports:unknown', args=[report.decision.identifier, report.identifier])
                elif col == 'component':
                    val = report.component
                elif col == 'marks_number':
                    val = str(report.cache.marks_total)
                elif col == self.confirmed_col:
                    val = str(report.cache.marks_confirmed)
                elif col == self.automatic_col:
                    val = str(report.cache.marks_automatic)
                elif col == 'verifier:cpu':
                    val = HumanizedValue(report.cpu_time, user=self.user).timedelta
                elif col == 'verifier:wall':
                    val = HumanizedValue(report.wall_time, user=self.user).timedelta
                elif col == 'verifier:memory':
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

        return columns, values_data


class ReportChildrenTable:
    def __init__(self, user, report, view, page=1):
        self.user = user
        self.report = report
        self.view = view

        num_per_page = view['elements'][0] if view['elements'] else None
        self.paginator, self.page = paginate_queryset(self.__get_queryset(), page, num_per_page)

        self.titles = REP_MARK_TITLES
        self.columns, self.values = self.__component_data()

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
        return queryset.filter(**qs_filters).order_by(ordering).select_related('decision')\
            .only('id', 'identifier', 'decision_id', 'decision__identifier', 'component')

    def __component_data(self):
        report_ids = list(report.id for report in self.page)

        columns = ['component']
        reports_data = dict((report.id, {
            'component': {
                'value': report.component,
                'href': reverse('reports:component', args=[report.decision.identifier, report.identifier])}
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
        return columns, values_data


class VerifierFilesArchive:
    # These attributes allow to distinguish uniqely all verification tasks within the same job. Sub-job identifier may
    # be not specified. In this case remaining attributes are unique.
    sub_job_identifier_attr = 'Sub-job identifier'
    program_fragment_attr = 'Program fragment'
    requirement_attr = 'Requirements specification'

    def __init__(self, decision, filters):
        self.decision = decision
        self._attrs = self.__get_attrs()
        self._archives = self.__get_archives()
        self._archives_to_upload = []
        self.__get_archives_to_upload(filters)
        self.stream = ZipStream()
        self.name = 'verifier_input_files.zip'

    def __iter__(self):
        names_in_use = set()
        for arch_path, name_pattern in self._archives_to_upload:
            # Do not treat archives with the same names. Indeed, these archives represent exactly the same verification
            # tasks for which a verifier reported several unsafes per each verification task.
            if name_pattern in names_in_use:
                continue
            else:
                arch_name = '%s.zip' % name_pattern
            names_in_use.add(name_pattern)

            for data in self.stream.compress_file(arch_path, arch_name):
                yield data

        yield self.stream.close_stream()

    @cached_property
    def _job_name(self):
        job = Job.objects.filter(id=self.decision.job_id).only('name', 'preset_id').first()
        if not job:
            return 'Job'
        preset_job = PresetJob.objects.get(id=job.preset_id)
        dir_name = ' - '.join(list(preset_job.get_ancestors(include_self=True).values_list('name', flat=True)))
        if Job.objects.filter(preset_id=job.preset_id).count() > 1:
            dir_name += ' - {}'.format(job.name)
        if Decision.objects.filter(job_id=job.id).count() > 1:
            dir_name += ' - {}'.format(self.decision.name)
        return dir_name

    def __get_archives(self):
        archives = {}
        for report in ReportComponent.objects.filter(decision=self.decision, verification=True)\
                .exclude(verifier_files='').only('id', 'verifier_files'):
            archives[report.id] = report.verifier_files.path
        return archives

    def __get_attrs(self):
        # Select attributes for all safes, unsafes and unknowns
        attrs = {}
        for report_id, a_name, a_value in ReportAttr.objects\
                .filter(report__decision=self.decision, name__in=[
                    self.sub_job_identifier_attr,
                    self.program_fragment_attr,
                    self.requirement_attr
                ]) \
                .exclude(report__reportunsafe=None, report__reportsafe=None, report__reportunknown=None) \
                .values_list('report_id', 'name', 'value'):
            if report_id not in attrs:
                attrs[report_id] = {}
            attrs[report_id][a_name] = a_value
        return attrs

    def __add_archive(self, r_type, r_id, p_id):
        if p_id in self._archives and r_id in self._attrs \
                and self.program_fragment_attr in self._attrs[r_id] \
                and self.requirement_attr in self._attrs[r_id]:

            self._archives_to_upload.append((
                self._archives[p_id],
                '{0}/{1}/{2}{3} - {4}'.format(
                    self._job_name,
                    'Unknowns' if r_type == 'f' else 'Unsafes' if r_type == 'u' else 'Safes',
                    self._attrs[r_id][self.sub_job_identifier_attr] + ' - '
                        if self.sub_job_identifier_attr in self._attrs[r_id] else '',
                    self._attrs[r_id][self.program_fragment_attr].replace('/', '---'),
                    self._attrs[r_id][self.requirement_attr]
                )
            ))

    def __get_archives_to_upload(self, filters):
        common_filters = {'decision': self.decision, 'parent__reportcomponent__verification': True}
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
            unknown_obj = ReportUnknown.objects.select_related('decision')\
                .only('identifier', 'decision_id', 'decision__identifier')\
                .get(parent=report, component=report.component)
            self.href = reverse('reports:unknown', args=[unknown_obj.decision.identifier, unknown_obj.identifier])
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
        self.type = self.data[0]['type'] if len(self.data) and 'type' in self.data[0] else 'unknown'
        self.stats = None

        if self.type == 'testing':
            self.__calculate_test_stats()
        elif self.type == 'validation':
            self.__calculate_validation_stats()
        # There is always the only element in a list of PFG data.
        elif self.type == 'PFG':
            self.data = self.data[0]
            # Do not visualize data type. Before this type was already saved explicitly.
            del self.data['type']
        elif self.type == 'EMG':
            # Like for PFG above
            self.data = self.data[0]
            del self.data['type']
        elif self.type == 'unknown' and self.data:
            self.data = json.dumps(self.data, ensure_ascii=True, sort_keys=True, indent=4)

    def __calculate_test_stats(self):
        self.stats = {
            "passed tests": 0,
            "failed tests": 0,
            "missed comments": 0,
            "excessive comments": 0,
            "tests": 0
        }

        for test_result in self.data:
            self.stats["tests"] += 1
            if test_result["ideal verdict"] == test_result["verdict"]:
                self.stats["passed tests"] += 1
                if test_result.get('comment'):
                    self.stats["excessive comments"] += 1
            else:
                self.stats["failed tests"] += 1
                if not test_result.get('comment'):
                    self.stats["missed comments"] += 1

    def __calculate_validation_stats(self):
        self.stats = {
            "found bug before fix and safe after fix": 0,
            "found bug before fix and non-safe after fix": 0,
            "found non-bug before fix and safe after fix": 0,
            "found non-bug before fix and non-safe after fix": 0,
            "missed comments": 0,
            "excessive comments": 0,
            "bugs": 0
        }

        # Merge together validation results before and after bug fixes. They have the same bug identifiers.
        validation_results = dict()
        for validation_result in self.data:
            bug_id = validation_result['bug']
            if bug_id in validation_results:
                validation_results[bug_id].update(validation_result)
            else:
                validation_results[bug_id] = validation_result

        self.data = validation_results.values()

        for validation_result in self.data:
            self.stats["bugs"] += 1

            is_found_bug_before_fix = False

            if "before fix" in validation_result:
                if validation_result["before fix"]["verdict"] == "unsafe":
                    is_found_bug_before_fix = True
                    if validation_result["before fix"]["comment"]:
                        self.stats["excessive comments"] += 1
                elif 'comment' not in validation_result["before fix"] or not validation_result["before fix"]["comment"]:
                    self.stats["missed comments"] += 1

            is_found_safe_after_fix = False

            if "after fix" in validation_result:
                if validation_result["after fix"]["verdict"] == "safe":
                    is_found_safe_after_fix = True
                    if validation_result["after fix"]["comment"]:
                        self.stats["excessive comments"] += 1
                elif 'comment' not in validation_result["after fix"] or not validation_result["after fix"]["comment"]:
                    self.stats["missed comments"] += 1

            if is_found_bug_before_fix:
                if is_found_safe_after_fix:
                    self.stats["found bug before fix and safe after fix"] += 1
                else:
                    self.stats["found bug before fix and non-safe after fix"] += 1
            else:
                if is_found_safe_after_fix:
                    self.stats["found non-bug before fix and safe after fix"] += 1
                else:
                    self.stats["found non-bug before fix and non-safe after fix"] += 1

        return self.stats


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


class ReportPNGGenerator(FileWrapper):
    def __init__(self, report_image_obj):
        assert isinstance(report_image_obj, ReportImage), 'Unknown error'
        self.name = report_image_obj.image.name
        self.size = report_image_obj.image.size
        super().__init__(report_image_obj.image.file, 8192)
