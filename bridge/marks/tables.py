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

import json

from django.core.urlresolvers import reverse
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, F, Count, Case, When
from django.template import Template, Context
from django.utils.translation import ugettext_lazy as _, ungettext_lazy, string_concat

from bridge.tableHead import Header
from bridge.vars import MARKS_COMPARE_ATTRS, MARK_SAFE, MARK_UNSAFE, MARK_STATUS, VIEW_TYPES, ASSOCIATION_TYPE
from bridge.utils import unique_id

from reports.models import ReportSafe, ReportUnsafe, ReportUnknown
from marks.models import MarkSafe, MarkUnsafe, MarkUnknown, MarkAssociationsChanges, MarkSafeAttr, MarkUnsafeAttr, \
    MarkUnsafeCompare, MarkUnsafeConvert, MarkSafeHistory, MarkUnsafeHistory, MarkUnknownHistory, \
    MarkSafeTag, MarkUnsafeTag, SafeAssociationLike, UnsafeAssociationLike, UnknownAssociationLike

from users.utils import ViewData, DEF_NUMBER_OF_ELEMENTS
from jobs.utils import JobAccess
from marks.CompareTrace import DEFAULT_COMPARE
from marks.ConvertTrace import DEFAULT_CONVERT


MARK_TITLES = {
    'mark_num': '№',
    'change_kind': _('Change kind'),
    'verdict': _("Verdict"),
    'sum_verdict': _('Total verdict'),
    'similarity': _('Similarity'),
    'status': _('Status'),
    'author': _('Last change author'),
    'change_date': _('Last change date'),
    'ass_author': _('Association author'),
    'report': _('Report'),
    'job': _('Job'),
    'format': _('Format'),
    'number': '№',
    'num_of_links': _('Number of associated leaf reports'),
    'problem': _("Problem"),
    'component': _('Component'),
    'pattern': _('Problem pattern'),
    'checkbox': '',
    'source': _('Source'),
    'ass_type': _('Association type'),
    'automatic': _('Automatic association'),
    'tags': _('Tags'),
    'likes': string_concat(_('Likes'), '/', _('Dislikes')),
    'buttons': '',
    'description': _('Description'),
}

STATUS_COLOR = {
    '0': '#D11919',
    '1': '#FF8533',
    '2': '#FF8533',
    '3': '#00B800',
}

UNSAFE_COLOR = {
    '0': '#A739CC',
    '1': '#D11919',
    '2': '#D11919',
    '3': '#FF8533',
    '4': '#D11919',
    '5': '#000000',
}

SAFE_COLOR = {
    '0': '#A739CC',
    '1': '#FF8533',
    '2': '#D11919',
    '3': '#D11919',
    '4': '#000000',
}

CHANGE_DATA = {
    '=': (_("Changed"), '#FF8533'),
    '+': (_("New"), '#00B800'),
    '-': (_("Deleted"), '#D11919')
}

ASSOCIATION_TYPE_COLOR = {
    '0': '#7506b4',
    '1': '#3f9f32',
    '2': '#c71a2d'
}


def result_color(result):
    if 0 <= result <= 0.33:
        return '#E60000'
    elif 0.33 < result <= 0.66:
        return '#CC7A29'
    elif 0.66 < result <= 1:
        return '#00CC66'
    return None


class MarkChangesTable:
    def __init__(self, user, mark, changes):
        self.columns = ['report', 'change_kind', 'sum_verdict', 'job', 'format']
        if isinstance(mark, MarkUnknown):
            self.columns = ['report', 'change_kind', 'job', 'format']
        self.mark = mark
        self.changes = changes
        self.__accessed_changes(user)
        if not isinstance(mark, MarkUnknown):
            self.attr_values_data = self.__add_attrs()
        if isinstance(mark, MarkUnsafe):
            self.values = self.__get_unsafe_values()
            self.mark_type = 'unsafe'
        elif isinstance(mark, MarkSafe):
            self.values = self.__get_safe_values()
            self.mark_type = 'safe'
        elif isinstance(mark, MarkUnknown):
            self.values = self.__get_unknown_values()
            self.mark_type = 'unknown'
        else:
            return
        self.cache_id = self.__save_data(user)

    def __save_data(self, user):
        try:
            cache = MarkAssociationsChanges.objects.get(user=user)
        except ObjectDoesNotExist:
            cache = MarkAssociationsChanges(user=user)
        cache.identifier = unique_id()
        cache.table_data = json.dumps({
            'mark_type': self.mark_type,
            'mark_id': self.mark.pk,
            'columns': self.columns,
            'values': self.values
        }, ensure_ascii=False, sort_keys=True, indent=4)
        cache.save()
        return cache.identifier

    def __accessed_changes(self, user):
        for report in self.changes:
            if not JobAccess(user, report.root.job).can_view():
                del self.changes[report]

    def __add_attrs(self):
        data = {}
        columns = []
        for report in self.changes:
            for ra in report.attrs.order_by('id').values_list('attr__name__name', 'attr__value'):
                if ra[0] not in columns:
                    columns.append(ra[0])
                if ra[0] not in data:
                    data[ra[0]] = {}
                data[ra[0]][report] = ra[1]
        values = {}
        for report in self.changes:
            values[report] = {}
            for col in columns:
                cell_val = '-'
                if report in data[col]:
                    cell_val = data[col][report]
                values[report][col] = cell_val
        self.columns.extend(columns)
        return values

    def __get_unsafe_values(self):

        def get_verdict_change(rep):
            if all(x in self.changes[rep] for x in {'verdict1', 'verdict2'}):
                tmp_unsafe = ReportUnsafe()
                tmp_unsafe.verdict = self.changes[rep]['verdict1']
                val1 = tmp_unsafe.get_verdict_display()
                if self.changes[rep]['verdict1'] == self.changes[rep]['verdict2']:
                    return '<span style="color:%s">%s</span>' % (UNSAFE_COLOR[self.changes[rep]['verdict1']], val1)
                tmp_unsafe.verdict = self.changes[rep]['verdict2']
                val2 = tmp_unsafe.get_verdict_display()
                return '<span style="color:%s">%s</span> -> <span style="color:%s">%s</span>' % (
                    UNSAFE_COLOR[self.changes[rep]['verdict1']], val1, UNSAFE_COLOR[self.changes[rep]['verdict2']], val2
                )
            return '<span style="color:%s">%s</span>' % (UNSAFE_COLOR[rep.verdict], rep.get_verdict_display())

        values = []

        cnt = 0
        for report in self.changes:
            cnt += 1
            values_str = []
            for col in self.columns:
                val = '-'
                color = None
                href = None
                if col in self.attr_values_data[report]:
                    val = self.attr_values_data[report][col]
                elif col == 'report':
                    val = cnt
                    href = reverse('reports:unsafe', args=[report.pk])
                elif col == 'sum_verdict':
                    val = get_verdict_change(report)
                elif col == 'status':
                    val = self.__status_change()
                elif col == 'change_kind':
                    if self.changes[report]['kind'] in CHANGE_DATA:
                        val = CHANGE_DATA[self.changes[report]['kind']][0]
                        color = CHANGE_DATA[self.changes[report]['kind']][1]
                elif col == 'author':
                    if self.mark.author is not None:
                        val = self.mark.author.get_full_name()
                        href = reverse('users:show_profile', args=[self.mark.author_id])
                elif col == 'job':
                    val = report.root.job.name
                    href = reverse('jobs:job', args=[report.root.job_id])
                elif col == 'format':
                    val = report.root.job.format
                values_str.append({
                    'value': str(val),
                    'color': color,
                    'href': href
                })
            values.append(values_str)
        return values

    def __get_safe_values(self):

        def get_verdict_change(rep):
            if all(x in self.changes[rep] for x in {'verdict1', 'verdict2'}):
                tmp_safe = ReportSafe()
                tmp_safe.verdict = self.changes[rep]['verdict1']
                val1 = tmp_safe.get_verdict_display()
                if self.changes[rep]['verdict1'] == self.changes[rep]['verdict2']:
                    return '<span style="color:%s">%s</span>' % (SAFE_COLOR[self.changes[rep]['verdict1']], val1)
                tmp_safe.verdict = self.changes[rep]['verdict2']
                val2 = tmp_safe.get_verdict_display()
                return '<span style="color:%s">%s</span> -> <span style="color:%s">%s</span>' % (
                    SAFE_COLOR[self.changes[rep]['verdict1']], val1, SAFE_COLOR[self.changes[rep]['verdict2']], val2
                )
            return '<span style="color:%s">%s</span>' % (SAFE_COLOR[rep.verdict], rep.get_verdict_display())

        values = []

        cnt = 0
        for report in self.changes:
            cnt += 1
            values_str = []
            for col in self.columns:
                val = '-'
                color = None
                href = None
                if col in self.attr_values_data[report]:
                    val = self.attr_values_data[report][col]
                elif col == 'report':
                    val = cnt
                    href = reverse('reports:safe', args=[report.pk])
                elif col == 'sum_verdict':
                    val = get_verdict_change(report)
                elif col == 'status':
                    val = self.__status_change()
                elif col == 'change_kind':
                    if self.changes[report]['kind'] in CHANGE_DATA:
                        val = CHANGE_DATA[self.changes[report]['kind']][0]
                        color = CHANGE_DATA[self.changes[report]['kind']][1]
                elif col == 'author':
                    if self.mark.author is not None:
                        val = self.mark.author.get_full_name()
                        href = reverse('users:show_profile', args=[self.mark.author_id])
                elif col == 'job':
                    val = report.root.job.name
                    href = reverse('jobs:job', args=[report.root.job_id])
                elif col == 'format':
                    val = report.root.job.format
                values_str.append({
                    'value': str(val),
                    'color': color,
                    'href': href
                })
            values.append(values_str)
        return values

    def __status_change(self):
        version_set = self.mark.versions.all().order_by('-version')
        last_version = version_set[0]
        try:
            prev_version = version_set[1]
        except IndexError:
            return '<span style="color:%s">%s</span>' % (
                STATUS_COLOR[last_version.status], last_version.get_status_display()
            )
        if prev_version.status == last_version.status:
            return '<span style="color:%s">%s</span>' % (
                STATUS_COLOR[last_version.status], last_version.get_status_display()
            )
        return '<span style="color:%s">%s</span> -> <span style="color:%s">%s</span>' % (
            STATUS_COLOR[prev_version.status], prev_version.get_status_display(),
            STATUS_COLOR[last_version.status], last_version.get_status_display()
        )

    def __get_unknown_values(self):
        values = []
        cnt = 0
        for report in self.changes:
            cnt += 1
            values_str = []
            for col in self.columns:
                val = '-'
                color = None
                href = None
                if col == 'report':
                    val = cnt
                    href = reverse('reports:unknown', args=[report.pk])
                elif col == 'status':
                    val = self.__status_change()
                elif col == 'change_kind':
                    if self.changes[report]['kind'] in CHANGE_DATA:
                        val = CHANGE_DATA[self.changes[report]['kind']][0]
                        color = CHANGE_DATA[self.changes[report]['kind']][1]
                elif col == 'author':
                    if self.mark.author is not None:
                        val = self.mark.author.get_full_name()
                        href = reverse('users:show_profile', args=[self.mark.author_id])
                elif col == 'job':
                    val = report.root.job.name
                    href = reverse('jobs:job', args=[report.root.job_id])
                elif col == 'format':
                    val = report.root.job.format
                values_str.append({
                    'value': str(val),
                    'color': color,
                    'href': href
                })
            values.append(values_str)
        return values


# Table data for showing links between the specified report and marks
class ReportMarkTable:
    def __init__(self, user, report, view=None, view_id=None):
        self.report = report
        self.user = user
        self.statuses = MARK_STATUS
        self.ass_types = ASSOCIATION_TYPE
        if isinstance(report, ReportUnsafe):
            self.type = 'unsafe'
            self.verdicts = MARK_UNSAFE
        elif isinstance(report, ReportSafe):
            self.type = 'safe'
            self.verdicts = MARK_SAFE
        elif isinstance(report, ReportUnknown):
            self.type = 'unknown'
        else:
            return

        view_types = {'unsafe': VIEW_TYPES[10][0], 'safe': VIEW_TYPES[11][0], 'unknown': VIEW_TYPES[12][0]}
        self.view = ViewData(self.user, view_types[self.type], view=view, view_id=view_id)

        self.selected_columns = self.__selected()
        self.available_columns = self.__available()

        self.columns = self.__get_columns()
        self.header = Header(self.columns, MARK_TITLES).struct
        self.values = self.__get_values()

    def __selected(self):
        columns = []
        for col in self.view['columns']:
            if col not in self.__supported_columns():
                return []
            col_title = col
            if col_title in MARK_TITLES:
                col_title = MARK_TITLES[col_title]
            columns.append({'value': col, 'title': col_title})
        return columns

    def __available(self):
        columns = []
        for col in self.__supported_columns():
            col_title = col
            if col_title in MARK_TITLES:
                col_title = MARK_TITLES[col_title]
            columns.append({'value': col, 'title': col_title})
        return columns

    def __supported_columns(self):
        if self.type == 'safe':
            return ['verdict', 'status', 'source', 'tags', 'ass_type',
                    'ass_author', 'description', 'change_date', 'author']
        elif self.type == 'unsafe':
            return ['verdict', 'similarity', 'status', 'source', 'tags', 'ass_type',
                    'ass_author', 'description', 'change_date', 'author']
        return ['problem', 'status', 'source', 'ass_type', 'ass_author', 'description', 'change_date', 'author']

    def __get_columns(self):
        columns = ['mark_num']
        columns.extend(self.view['columns'])
        columns.append('likes')
        columns.append('buttons')
        return columns

    def __get_values(self):
        value_data = []
        likes = {}
        dislikes = {}
        cnt = 1

        likes_model = {'safe': SafeAssociationLike, 'unsafe': UnsafeAssociationLike, 'unknown': UnknownAssociationLike}
        for ass_like in likes_model[self.type].objects.filter(association__report=self.report):
            if ass_like.dislike:
                if ass_like.association_id not in dislikes:
                    dislikes[ass_like.association_id] = []
                dislikes[ass_like.association_id].append((ass_like.author.get_full_name(), ass_like.author_id))
            else:
                if ass_like.association_id not in likes:
                    likes[ass_like.association_id] = []
                likes[ass_like.association_id].append((ass_like.author.get_full_name(), ass_like.author_id))
        if self.type == 'unsafe':
            orders = ['-result', '-mark__change_date']
        else:
            orders = ['-mark__change_date']
        for mark_rep in self.report.markreport_set.select_related('mark', 'mark__author').order_by(*orders):
            if 'status' in self.view and mark_rep.mark.status not in self.view['status']:
                continue
            if 'verdict' in self.view and mark_rep.mark.verdict not in self.view['verdict']:
                continue
            if 'similarity' in self.view:
                if '0' not in self.view['similarity'] and mark_rep.result == 0:
                    continue
                if '100' not in self.view['similarity'] and mark_rep.result == 1:
                    continue
                if '50' not in self.view['similarity'] and 0 < mark_rep.result < 1:
                    continue
            if 'ass_type' in self.view and mark_rep.type not in self.view['ass_type']:
                continue
            row_data = []
            for col in self.columns:
                val = '-'
                href = None
                color = None
                if col == 'mark_num':
                    val = cnt
                    href = '%s?report_to_redirect=%s' % (
                        reverse('marks:view_mark', args=[self.type, mark_rep.mark_id]), self.report.pk
                    )
                elif col == 'verdict' and self.type != 'unknown':
                    val = mark_rep.mark.get_verdict_display()
                    if self.type == 'unsafe':
                        color = UNSAFE_COLOR[mark_rep.mark.verdict]
                    else:
                        color = SAFE_COLOR[mark_rep.mark.verdict]
                elif col == 'problem' and self.type == 'unknown':
                    val = mark_rep.problem.name
                    problem_link = mark_rep.mark.link
                    if problem_link is not None:
                        if not problem_link.startswith('http'):
                            problem_link = 'http://' + mark_rep.mark.link
                        href = problem_link
                elif col == 'similarity' and self.type == 'unsafe':
                    if mark_rep.error is not None:
                        val = mark_rep.error
                        color = result_color(0)
                    else:
                        val = "{:.0%}".format(mark_rep.result)
                        color = result_color(mark_rep.result)
                elif col == 'status':
                    val = mark_rep.mark.get_status_display()
                    color = STATUS_COLOR[mark_rep.mark.status]
                elif col == 'source':
                    val = mark_rep.mark.get_type_display()
                elif col == 'tags' and self.type != 'unknown':
                    tags_filters = {
                        'mark_version__mark_id': mark_rep.mark_id,
                        'mark_version__version': F('mark_version__mark__version')
                    }
                    tags = set()
                    tags_model = {'safe': MarkSafeTag, 'unsafe': MarkUnsafeTag}
                    for tag, in tags_model[self.type].objects.filter(**tags_filters).values_list('tag__tag'):
                        tags.add(tag)
                    if len(tags) > 0:
                        val = '; '.join(sorted(tags))
                elif col == 'ass_type':
                    val = mark_rep.get_type_display()
                    color = ASSOCIATION_TYPE_COLOR[mark_rep.type]
                elif col == 'ass_author' and mark_rep.author is not None:
                    val = mark_rep.author.get_full_name()
                    href = reverse('users:show_profile', args=[mark_rep.author_id])
                elif col == 'description' and len(mark_rep.mark.description) > 0:
                    val = mark_rep.mark.description
                elif col == 'likes':
                    val = (
                        mark_rep.mark_id,
                        list(sorted(likes.get(mark_rep.id, []))),
                        list(sorted(dislikes.get(mark_rep.id, [])))
                    )
                elif col == 'buttons':
                    val = (mark_rep.mark_id, mark_rep.type)
                elif col == 'change_date':
                    val = mark_rep.mark.change_date
                elif col == 'author':
                    val = mark_rep.mark.author.get_full_name()
                    if mark_rep.mark.author:
                        href = reverse('users:show_profile', args=[mark_rep.mark.author_id])
                row_data.append({'value': val, 'color': color, 'column': col, 'href': href})
            cnt += 1
            value_data.append(row_data)
        return value_data


class MarksList:
    def __init__(self, user, marks_type, view=None, view_id=None, page=1):
        self.user = user
        self.type = marks_type
        if self.type not in {'unsafe', 'safe', 'unknown'}:
            return
        self.authors = []

        view_types = {'unsafe': VIEW_TYPES[7][0], 'safe': VIEW_TYPES[8][0], 'unknown': VIEW_TYPES[9][0]}
        self.view = ViewData(self.user, view_types[self.type], view=view, view_id=view_id)

        self.selected_columns = self.__selected()
        self.available_columns = self.__available()

        self.columns = self.__get_columns()
        self.marks = self.__get_marks()
        if self.type != 'unknown':
            self.attr_values = self.__get_attrs()

        self.header = Header(self.columns, MARK_TITLES).struct
        self.values = self.__get_page(page, self.__get_values())

    def __selected(self):
        columns = []
        for col in self.view['columns']:
            if col not in self.__supported_columns():
                return []
            col_title = col
            if col_title in MARK_TITLES:
                col_title = MARK_TITLES[col_title]
            columns.append({'value': col, 'title': col_title})
        return columns

    def __available(self):
        columns = []
        for col in self.__supported_columns():
            col_title = col
            if col_title in MARK_TITLES:
                col_title = MARK_TITLES[col_title]
            columns.append({'value': col, 'title': col_title})
        return columns

    def __supported_columns(self):
        if self.type == 'unknown':
            return ['num_of_links', 'component', 'status', 'author', 'change_date', 'format', 'pattern', 'source']
        return ['num_of_links', 'verdict', 'tags', 'status', 'author', 'change_date', 'format', 'source']

    def __get_columns(self):
        columns = ['checkbox', 'mark_num']
        columns.extend(self.view['columns'])
        return columns

    def __get_marks(self):
        filters = {}
        unfilter = {'version': 0}
        if 'status' in self.view:
            if self.view['status'][0] == 'is':
                filters['status'] = self.view['status'][1]
            else:
                unfilter['status'] = self.view['status'][1]
        if 'verdict' in self.view:
            if self.view['verdict'][0] == 'is':
                filters['verdict'] = self.view['verdict'][1]
            else:
                unfilter['verdict'] = self.view['verdict'][1]
        if 'component' in self.view:
            if self.view['component'][0] == 'is':
                filters['component__name'] = self.view['component'][1]
            elif self.view['component'][0] == 'startswith':
                filters['component__name__istartswith'] = self.view['component'][1]
        if 'author' in self.view:
            filters['author_id'] = self.view['author'][0]
        if 'source' in self.view:
            if self.view['source'][0] == 'is':
                filters['type'] = self.view['source'][1]
            else:
                unfilter['type'] = self.view['source'][1]
        table_filters = Q(**filters)
        for uf in unfilter:
            table_filters = table_filters & ~Q(**{uf: unfilter[uf]})
        order_field = 'id'
        if self.view['order'][1] == 'change_date':
            order_field = 'change_date'
        if self.type == 'unsafe':
            return MarkUnsafe.objects.filter(table_filters).order_by(order_field)
        elif self.type == 'safe':
            return MarkSafe.objects.filter(table_filters).order_by(order_field)
        return MarkUnknown.objects.filter(table_filters).order_by(order_field)

    def __get_attrs(self):
        if self.type == 'safe':
            vers_model = MarkSafeHistory
            attr_model = MarkSafeAttr
        else:
            vers_model = MarkUnsafeHistory
            attr_model = MarkUnsafeAttr
        last_versions = vers_model.objects.filter(version=F('mark__version'), mark__in=self.marks)

        data = {}
        attr_order = {}
        for ma in attr_model.objects.filter(mark__in=last_versions).order_by('id')\
                .values_list('mark__mark_id', 'attr__name__name', 'attr__value'):
            if ma[0] not in data:
                data[ma[0]] = {}
                attr_order[ma[0]] = []
            data[ma[0]][ma[1]] = ma[2]
            attr_order[ma[0]].append(ma[1])

        columns = []
        for mark in self.marks:
            if mark.id in attr_order:
                for a_name in attr_order[mark.id]:
                    if a_name not in columns:
                        columns.append(a_name)

        values = {}
        for mark in self.marks:
            values[mark] = {}
            for col in columns:
                cell_val = '-'
                if mark.id in data and col in data[mark.id]:
                    cell_val = data[mark.id][col]
                values[mark][col] = cell_val
        self.columns.extend(columns)
        return values

    def __get_values(self):
        view_tags = []
        if 'tags' in self.view:
            view_tags = list(x.strip() for x in self.view['tags'][0].split(';'))

        values = []
        for mark in self.marks:
            if mark.author not in self.authors:
                self.authors.append(mark.author)
            values_str = []
            order_by_value = ''
            for col in self.columns:
                if col in {'mark_num', 'checkbox'}:
                    continue
                val = '-'
                color = None
                href = None
                if self.type != 'unknown' and col in self.attr_values[mark]:
                    val = self.attr_values[mark][col]
                    if self.__get_order() == col:
                        order_by_value = val
                    if not self.__filter_attr(col, val):
                        break
                elif col == 'num_of_links':
                    val = mark.markreport_set.count()
                    if self.__get_order() == 'num_of_links':
                        order_by_value = val
                    if self.type == 'unsafe':
                        broken = mark.markreport_set.exclude(error=None).count()
                        if broken > 0:
                            val = ungettext_lazy(
                                '%(all)s (%(broken)s is broken)', '%(all)s (%(broken)s are broken)', broken
                            ) % {'all': len(mark.markreport_set.all()), 'broken': broken}
                elif col == 'verdict':
                    val = mark.get_verdict_display()
                    if self.type == 'safe':
                        color = SAFE_COLOR[mark.verdict]
                    else:
                        color = UNSAFE_COLOR[mark.verdict]
                elif col == 'status':
                    val = mark.get_status_display()
                    color = STATUS_COLOR[mark.status]
                elif col == 'author':
                    if mark.author is not None:
                        val = mark.author.get_full_name()
                        href = reverse('users:show_profile', args=[mark.author_id])
                elif col == 'change_date':
                    val = mark.change_date
                    if self.user.extended.data_format == 'hum':
                        val = Template('{% load humanize %}{{ date|naturaltime }}').render(Context({'date': val}))
                elif col == 'format':
                    val = mark.format
                elif col == 'component':
                    val = mark.component.name
                elif col == 'pattern':
                    val = mark.problem_pattern
                elif col == 'source':
                    val = mark.get_type_display()
                elif col == 'tags':
                    last_v = mark.versions.get(version=mark.version)
                    if last_v is None:
                        val = '-'
                    else:
                        tags = list(tag['tag__tag'] for tag in last_v.tags.order_by('tag__tag').values('tag__tag'))
                        if 'tags' in self.view and any(t not in tags for t in view_tags):
                            break
                        val = '; '.join(tags)
                        if val == '':
                            val = '-'
                values_str.append({'color': color, 'value': val, 'href': href})
            else:
                values.append((order_by_value, mark.id, values_str))

        ordered_values = []
        if self.__get_order() == 'num_of_links':
            for ord_by, mark_id, val_str in sorted(values, key=lambda x: x[0]):
                ordered_values.append((mark_id, val_str))
        elif isinstance(self.__get_order(), str):
            for ord_by, mark_id, val_str in sorted(values, key=lambda x: x[0]):
                ordered_values.append((mark_id, val_str))
        else:
            ordered_values = list((x[1], x[2]) for x in values)
        if self.view['order'][0] == 'up':
            ordered_values = list(reversed(ordered_values))

        final_values = []
        cnt = 1
        for mark_id, valstr in ordered_values:
            valstr.insert(0, {'value': cnt, 'href': reverse('marks:view_mark', args=[self.type, mark_id])})
            valstr.insert(0, {'checkbox': mark_id})
            final_values.append(valstr)
            cnt += 1
        return final_values

    def __filter_attr(self, attribute, value):
        if 'attr' in self.view and self.view['attr'][0] == attribute:
            ftype = self.view['attr'][1]
            fvalue = self.view['attr'][2]
            if ftype == 'iexact' and fvalue.lower() != value.lower():
                return False
            elif ftype == 'istartswith' and not value.lower().startswith(fvalue.lower()):
                return False
        return True

    def __get_order(self):
        if self.view['order'][1] == 'attr' and len(self.view['order'][2]) > 0:
            return self.view['order'][2]
        elif self.view['order'][1] == 'num_of_links':
            return 'num_of_links'
        elif self.view['order'][1] == 'change_date':
            return 'change_date'
        return None

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


class MarkData:
    def __init__(self, mark_type, mark_version=None, report=None):
        self.type = mark_type
        self.mark_version = mark_version
        self.verdicts = self.__verdict_info()
        self.statuses = self.__status_info()
        if isinstance(self.mark_version, MarkUnsafeHistory) or isinstance(report, ReportUnsafe):
            self.comparison, self.compare_desc = self.__functions('compare')
            self.convertion, self.convert_desc = self.__functions('convert')
        self.unknown_data = self.__unknown_info()
        self.attributes = self.__get_attributes(report)
        self.description = ''
        if isinstance(self.mark_version, (MarkUnsafeHistory, MarkSafeHistory, MarkUnknownHistory)):
            self.description = self.mark_version.description

    def __get_attributes(self, report):
        values = []
        if isinstance(self.mark_version, (MarkUnsafeHistory, MarkSafeHistory)):
            values = list(
                self.mark_version.attrs.order_by('id').values_list('attr__name__name', 'attr__value', 'is_compare')
            )
        elif isinstance(report, (ReportUnsafe, ReportSafe)):
            for ra in report.attrs.order_by('id').values_list('attr__name__name', 'attr__value'):
                is_compare = False
                if report.root.job.type in MARKS_COMPARE_ATTRS and ra[0] in MARKS_COMPARE_ATTRS[report.root.job.type]:
                    is_compare = True
                ra += (is_compare,)
                values.append(ra)
        else:
            return None
        return values

    def __unknown_info(self):
        if not isinstance(self.mark_version, MarkUnknownHistory):
            return []
        return [self.mark_version.function, self.mark_version.problem_pattern, self.mark_version.link]

    def __verdict_info(self):
        verdicts = []
        if self.type == 'unsafe':
            for verdict in MARK_UNSAFE:
                verdict_data = {
                    'title': verdict[1],
                    'value': verdict[0],
                    'checked': False,
                    'color': UNSAFE_COLOR[verdict[0]]
                }
                if (isinstance(self.mark_version, MarkUnsafeHistory) and
                        verdict_data['value'] == self.mark_version.verdict) or \
                        (not isinstance(self.mark_version, MarkUnsafeHistory) and verdict_data['value'] == '0'):
                    verdict_data['checked'] = True
                verdicts.append(verdict_data)
        elif self.type == 'safe':
            for verdict in MARK_SAFE:
                verdict_data = {
                    'title': verdict[1],
                    'value': verdict[0],
                    'checked': False,
                    'color': SAFE_COLOR[verdict[0]]
                }
                if (isinstance(self.mark_version, MarkSafeHistory) and
                        verdict_data['value'] == self.mark_version.verdict) or \
                        (not isinstance(self.mark_version, MarkSafeHistory) and verdict_data['value'] == '0'):
                    verdict_data['checked'] = True
                verdicts.append(verdict_data)
        return verdicts

    def __status_info(self):
        statuses = []
        for verdict in MARK_STATUS:
            status_data = {
                'title': verdict[1],
                'value': verdict[0],
                'checked': False,
                'color': STATUS_COLOR[verdict[0]]
            }
            if (isinstance(self.mark_version, (MarkUnsafeHistory, MarkSafeHistory, MarkUnknownHistory)) and
                    verdict[0] == self.mark_version.status) or \
                    (self.mark_version is None and verdict[0] == MARK_STATUS[0][0]):
                status_data['checked'] = True
            statuses.append(status_data)
        return statuses

    def __functions(self, func_type='compare'):
        if self.type != 'unsafe':
            return [], None
        functions = []
        if func_type == 'compare':
            selected_description = None

            for f in MarkUnsafeCompare.objects.order_by('name'):
                func_data = {
                    'name': f.name,
                    'selected': False,
                    'value': f.pk,
                }
                if isinstance(self.mark_version, MarkUnsafeHistory):
                    if self.mark_version.function == f:
                        func_data['selected'] = True
                        selected_description = f.description
                elif f.name == DEFAULT_COMPARE:
                    func_data['selected'] = True
                    selected_description = f.description
                functions.append(func_data)
        elif func_type == 'convert':
            if self.mark_version is not None:
                return [], None

            selected_description = None

            for f in MarkUnsafeConvert.objects.order_by('name'):
                func_data = {
                    'name': f.name,
                    'selected': False,
                    'value': f.pk,
                }
                if f.name == DEFAULT_CONVERT:
                    func_data['selected'] = True
                    selected_description = f.description
                functions.append(func_data)
        else:
            return [], None
        return functions, selected_description


# Table data for showing links between the specified mark and reports
class MarkReportsTable(object):
    def __init__(self, user, mark, view=None, view_id=None):
        self.user = user
        self.mark = mark

        if isinstance(self.mark, MarkUnsafe):
            self.type = 'unsafe'
        elif isinstance(self.mark, MarkSafe):
            self.type = 'safe'
        elif isinstance(self.mark, MarkUnknown):
            self.type = 'unknown'
        else:
            return

        view_types = {'unsafe': VIEW_TYPES[13][0], 'safe': VIEW_TYPES[14][0], 'unknown': VIEW_TYPES[15][0]}
        self.view = ViewData(self.user, view_types[self.type], view=view, view_id=view_id)

        self.selected_columns = self.__selected()
        self.available_columns = self.__available()

        self.columns = self.__get_columns()
        self.header = Header(self.columns, MARK_TITLES).struct
        self.values = self.__get_values()

    def __selected(self):
        columns = []
        for col in self.view['columns']:
            if col not in self.__supported_columns():
                return []
            col_title = col
            if col_title in MARK_TITLES:
                col_title = MARK_TITLES[col_title]
            columns.append({'value': col, 'title': col_title})
        return columns

    def __available(self):
        columns = []
        for col in self.__supported_columns():
            col_title = col
            if col_title in MARK_TITLES:
                col_title = MARK_TITLES[col_title]
            columns.append({'value': col, 'title': col_title})
        return columns

    def __supported_columns(self):
        if self.type == 'unsafe':
            return ['job', 'similarity', 'ass_type', 'ass_author', 'likes']
        return ['job', 'ass_type', 'ass_author', 'likes']

    def __get_columns(self):
        columns = ['report']
        columns.extend(self.view['columns'])
        return columns

    def __get_values(self):
        likes = {}
        dislikes = {}
        if 'likes' in self.columns:
            likes_model = {
                'safe': SafeAssociationLike, 'unsafe': UnsafeAssociationLike, 'unknown': UnknownAssociationLike
            }
            for ass_id, l_num, dl_num in likes_model[self.type].objects.values('association_id')\
                    .annotate(dislikes=Count(Case(When(dislike=True, then=1))),
                              likes=Count(Case(When(dislike=False, then=1))))\
                    .values_list('association_id', 'likes', 'dislikes'):
                likes[ass_id] = l_num
                dislikes[ass_id] = dl_num

        values = []
        cnt = 0
        for mark_report in self.mark.markreport_set.select_related('report', 'report__root__job').order_by('id'):
            if 'similarity' in self.view:
                if '0' not in self.view['similarity'] and mark_report.result == 0:
                    continue
                if '100' not in self.view['similarity'] and mark_report.result == 1:
                    continue
                if '50' not in self.view['similarity'] and 0 < mark_report.result < 1:
                    continue
            if 'ass_type' in self.view and mark_report.type not in self.view['ass_type']:
                continue

            report = mark_report.report
            cnt += 1
            values_str = []
            for col in self.columns:
                val = '-'
                color = None
                href = None
                if col == 'report':
                    val = cnt
                    if JobAccess(self.user, report.root.job).can_view():
                        href = reverse('reports:%s' % self.type, args=[report.id])
                elif col == 'similarity':
                    if mark_report.error is not None:
                        val = mark_report.error
                        color = result_color(0)
                    else:
                        val = "{:.0%}".format(mark_report.result)
                        color = result_color(mark_report.result)
                elif col == 'job':
                    val = report.root.job.name
                    if JobAccess(self.user, report.root.job).can_view():
                        href = reverse('jobs:job', args=[report.root.job_id])
                elif col == 'ass_type':
                    val = mark_report.get_type_display()
                elif col == 'ass_author':
                    if mark_report.author:
                        val = mark_report.author.get_full_name()
                        href = reverse('users:show_profile', args=[mark_report.author_id])
                elif col == 'likes':
                    val = '%s/%s' % (likes.get(mark_report.id, 0), dislikes.get(mark_report.id, 0))
                values_str.append({'value': val, 'href': href, 'color': color})
            values.append(values_str)
        return values
