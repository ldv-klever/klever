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

import json

from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import F, Count, Case, When
from django.template import loader
from django.urls import reverse
from django.utils.text import format_lazy
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _, ungettext_lazy

from bridge.tableHead import Header
from bridge.vars import MARK_SAFE, MARK_UNSAFE, MARK_STATUS, VIEW_TYPES, ASSOCIATION_TYPE, SAFE_VERDICTS,\
    UNSAFE_VERDICTS
from bridge.utils import unique_id, get_templated_text

from reports.models import ReportSafe, ReportUnsafe, ReportUnknown
from marks.models import MarkSafe, MarkUnsafe, MarkUnknown, MarkAssociationsChanges,\
    MarkSafeAttr, MarkUnsafeAttr, MarkUnknownAttr,\
    MarkUnsafeCompare, MarkSafeHistory, MarkUnsafeHistory, MarkUnknownHistory, ConvertedTraces, \
    MarkSafeTag, MarkUnsafeTag, SafeAssociationLike, UnsafeAssociationLike, UnknownAssociationLike, UnknownProblem

from users.utils import DEF_NUMBER_OF_ELEMENTS
from jobs.utils import JobAccess
from marks.utils import UNSAFE_COLOR, SAFE_COLOR, STATUS_COLOR, MarkAccess
from marks.CompareTrace import DEFAULT_COMPARE
from marks.tags import TagsInfo
from marks.querysets import ListQuery


MARK_TITLES = {
    'mark_num': _('#'),
    'change_kind': _('Association change kind'),
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
    'number': _('#'),
    'num_of_links': _('Number of associated leaf reports'),
    'problem': _("Problem"),
    'problems': _("Problems"),
    'component': _('Component'),
    'pattern': _('Problem pattern'),
    'checkbox': '',
    'source': _('Source'),
    'ass_type': _('Association type'),
    'automatic': _('Automatic association'),
    'tags': _('Tags'),
    'likes': format_lazy('{0}/{1}', _('Likes'), _('Dislikes')),
    'buttons': '',
    'description': _('Description'),
    'total_similarity': _('Total similarity'),
}

CHANGE_DATA = {
    'changed': (_("Changed"), '#FF8533'),
    'new': (_("New"), '#00B800'),
    'deleted': (_("Deleted"), '#D11919')
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
        self.mark = mark
        self.changes = changes
        self.__accessed_changes(user)

        if isinstance(mark, MarkUnsafe):
            self.mark_type = 'unsafe'
        elif isinstance(mark, MarkSafe):
            self.mark_type = 'safe'
        elif isinstance(mark, MarkUnknown):
            self.mark_type = 'unknown'
        else:
            return

        self.attrs = []
        self.values = self.__get_values()
        self.cache_id = self.__save_data(user)

    def __accessed_changes(self, user):
        reports_to_del = []
        for report in self.changes:
            if not JobAccess(user, report.root.job).can_view():
                reports_to_del.append(report)
        for report in reports_to_del:
            del self.changes[report]

    def __get_values(self):
        values = {}
        change_kinds = {'-': 'deleted', '=': 'changed', '+': 'new'}
        for report in self.changes:
            if report.id not in values:
                values[report.id] = {
                    'change_kind': change_kinds[self.changes[report]['kind']],
                    'job': [report.root.job.id, report.root.job.name],
                    'format': report.root.job.format
                }
                if self.mark_type == 'unknown':
                    if 'problems' in self.changes[report]:
                        values[report.id]['problems'] = self.changes[report]['problems']
                else:
                    values[report.id]['old_verdict'] = self.changes[report].get('verdict1', report.verdict)
                    values[report.id]['new_verdict'] = self.changes[report].get('verdict2', report.verdict)
                    if 'tags' in self.changes[report]:
                        values[report.id]['tags'] = self.changes[report]['tags']
                    if self.mark_type == 'unsafe':
                        values[report.id]['trace_id'] = report.trace_id
            for a_name, a_value in report.attrs.order_by('id').values_list('attr__name__name', 'attr__value'):
                if a_name not in self.attrs:
                    self.attrs.append(a_name)
                if a_name not in values[report.id]:
                    values[report.id][a_name] = a_value
        return values

    def __save_data(self, user):
        try:
            cache = MarkAssociationsChanges.objects.get(user=user)
        except ObjectDoesNotExist:
            cache = MarkAssociationsChanges(user=user)
        cache.identifier = unique_id()

        cache.table_data = json.dumps({
            'href': reverse('marks:mark', args=[self.mark_type, self.mark.pk]),
            'values': self.values, 'attrs': self.attrs
        }, ensure_ascii=False, sort_keys=True, indent=2)
        cache.save()
        return cache.identifier


# Table data for showing links between the specified report and marks
class ReportMarkTable:
    def __init__(self, user, report, view):
        self.user = user
        self.report = report
        self.view = view
        self.can_mark = MarkAccess(user, report=report).can_create()
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
        if self.can_mark:
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
                        reverse('marks:mark', args=[self.type, mark_rep.mark_id]), self.report.pk
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
                    val = (mark_rep.mark_id, mark_rep.type, mark_rep.get_type_display())
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
                    val = mark_rep.mark_id
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
    def __init__(self, user, marks_type, view, page=1):
        self.user = user
        self.type = marks_type
        self.view = view
        self._page_num = page

        self.page = None
        columns, self.values = self.__marks_data()
        self.header = Header(columns, MARK_TITLES).struct

    @cached_property
    def selected_columns(self):
        columns = []
        for col in self.view['columns']:
            if col not in self.__supported_columns:
                continue
            col_title = col
            if col_title in MARK_TITLES:
                col_title = MARK_TITLES[col_title]
            columns.append({'value': col, 'title': col_title})
        return columns

    @cached_property
    def available_columns(self):
        columns = []
        for col in self.__supported_columns:
            col_title = col
            if col_title in MARK_TITLES:
                col_title = MARK_TITLES[col_title]
            columns.append({'value': col, 'title': col_title})
        return columns

    @cached_property
    def __supported_columns(self):
        columns = {'num_of_links'}
        if self.type == 'unknown':
            columns.update({'component', 'pattern'})
        else:
            columns.update({'verdict', 'tags'})
        if self.type == 'unsafe':
            columns.add('total_similarity')
        columns.update({'status', 'author', 'change_date', 'format', 'source'})
        return columns

    def __paginate_objects(self, objects):
        if 'elements' in self.view:
            paginator = Paginator(objects, int(self.view['elements'][0]))
            self.page = paginator.page(self._page_num)
            return self.page.object_list, self.page.start_index()
        return objects, 1

    def __marks_data(self):
        columns = ['checkbox', 'number']
        columns.extend(self.view['columns'])

        model_map = {'safe': MarkSafe, 'unsafe': MarkUnsafe, 'unknown': MarkUnknown}
        # ReportSafe, self.view, ** self._kwargs
        query = ListQuery(model_map[self.type], self.view)
        objects, cnt = self.__paginate_objects(query.get_objects())

        marks = {}
        ordered_ids = []
        for mark_data in objects:
            ordered_ids.append(mark_data['id'])
            marks[mark_data['id']] = mark_data

        mattr_model = {'safe': MarkSafeAttr, 'unsafe': MarkUnsafeAttr, 'unknown': MarkUnknownAttr}
        MarkSafeAttr.objects.filter()
        attributes = {}
        for r_id, a_name, a_value in mattr_model[self.type].objects\
                .filter(mark__mark_id__in=ordered_ids, mark__version=F('mark__mark__version')).order_by('id')\
                .values_list('mark__mark_id', 'attr__name__name', 'attr__value'):
            if a_name not in attributes:
                columns.append(a_name)
                attributes[a_name] = {}
            attributes[a_name][r_id] = a_value

        values_data = []
        for m_id in ordered_ids:
            values_row = []
            for col in columns:
                if col == 'checkbox':
                    values_row.append({'checkbox': m_id})
                    continue
                val = '-'
                href = None
                color = None
                if col in attributes:
                    val = attributes[col].get(m_id, val)
                elif col == 'number':
                    val = cnt
                    href = reverse('marks:mark', args=[self.type, m_id])
                elif col == 'num_of_links':
                    val = marks[m_id]['num_of_links']
                    broken = marks[m_id].get('broken_links', 0)
                    if broken > 0:
                        val = ungettext_lazy(
                            '%(all)s (%(broken)s is broken)', '%(all)s (%(broken)s are broken)', broken
                        ) % {'all': marks[m_id]['num_of_links'], 'broken': broken}
                elif col == 'verdict':
                    if self.type == 'safe':
                        val = MarkSafe(verdict=marks[m_id]['verdict']).get_verdict_display()
                        color = SAFE_COLOR[marks[m_id]['verdict']]
                    elif self.type == 'unsafe':
                        val = MarkUnsafe(verdict=marks[m_id]['verdict']).get_verdict_display()
                        color = UNSAFE_COLOR[marks[m_id]['verdict']]
                elif col == 'tags':
                    if 'tags' in marks[m_id] and marks[m_id]['tags']:
                        val = ', '.join(sorted(marks[m_id]['tags']))
                elif col == 'status':
                    val = model_map[self.type](status=marks[m_id]['status']).get_status_display()
                    color = STATUS_COLOR[marks[m_id]['status']]
                elif col == 'author':
                    if marks[m_id].get('author_id'):
                        val = '%s %s' % (marks[m_id]['first_name'], marks[m_id]['last_name'])
                        href = reverse('users:show_profile', args=[int(marks[m_id]['author_id'])])
                elif col == 'change_date':
                    val = marks[m_id]['change_date']
                    if self.user.extended.data_format == 'hum':
                        val = get_templated_text('{% load humanize %}{{ date|naturaltime }}', date=val)
                elif col == 'source':
                    val = model_map[self.type](type=marks[m_id]['source']).get_type_display()
                elif col in {'format', 'total_similarity', 'component', 'pattern'}:
                    val = marks[m_id][col]
                values_row.append({'color': color, 'value': val, 'href': href})
            values_data.append(values_row)
            cnt += 1
        return columns, values_data


class MarkData:
    def __init__(self, mark_type, mark_version=None, report=None):
        self.type = mark_type
        self.mark_version = mark_version
        self.verdicts = self.__verdict_info()
        self.statuses = self.__status_info()
        if isinstance(self.mark_version, MarkUnsafeHistory) or isinstance(report, ReportUnsafe):
            self.comparison, self.selected_func = self.__functions()
        self.unknown_data = self.__unknown_info()
        self.attributes = self.__get_attributes(report)

        self.description = ''
        if isinstance(self.mark_version, (MarkUnsafeHistory, MarkSafeHistory, MarkUnknownHistory)):
            self.description = self.mark_version.description

        self.tags = None
        if isinstance(self.mark_version, (MarkUnsafeHistory, MarkSafeHistory)):
            self.tags = TagsInfo(self.type, list(tag.tag.pk for tag in self.mark_version.tags.all()))
        elif isinstance(report, (ReportUnsafe, ReportSafe)):
            self.tags = TagsInfo(self.type, [])

        self.error_trace = None
        if isinstance(self.mark_version, MarkUnsafeHistory):
            with ConvertedTraces.objects.get(id=self.mark_version.error_trace_id).file.file as fp:
                self.error_trace = fp.read().decode('utf8')

        self.author = None
        if isinstance(self.mark_version, (MarkUnsafeHistory, MarkSafeHistory, MarkUnknownHistory)):
            self.author = type(self.mark_version).objects.get(mark=self.mark_version.mark, version=1).author

    def __get_attributes(self, report):
        if isinstance(self.mark_version, (MarkUnsafeHistory, MarkSafeHistory, MarkUnknownHistory)):
            return list(
                self.mark_version.attrs.order_by('id').values_list('attr__name__name', 'attr__value', 'is_compare')
            )
        elif isinstance(report, (ReportUnsafe, ReportSafe, ReportUnknown)):
            return list(report.attrs.order_by('id').values_list('attr__name__name', 'attr__value', 'associate'))
        return None

    def __unknown_info(self):
        if not isinstance(self.mark_version, MarkUnknownHistory):
            return []
        return [
            self.mark_version.function, self.mark_version.problem_pattern,
            self.mark_version.link, self.mark_version.is_regexp
        ]

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

    def __functions(self):
        functions = []
        selected_func = None
        if self.type == 'unsafe':
            for f in MarkUnsafeCompare.objects.order_by('name'):
                func_data = {'id': f.id, 'name': f.name}
                if isinstance(self.mark_version, MarkUnsafeHistory):
                    if self.mark_version.function == f:
                        func_data['selected'] = True
                        selected_func = f
                elif f.name == DEFAULT_COMPARE:
                    func_data['selected'] = True
                    selected_func = f
                functions.append(func_data)
        return functions, selected_func


# Table data for showing links between the specified mark and reports
class MarkReportsTable:
    def __init__(self, user, mark, view, page=1):
        self.user = user
        self.mark = mark
        self.view = view

        if isinstance(self.mark, MarkUnsafe):
            self.type = 'unsafe'
        elif isinstance(self.mark, MarkSafe):
            self.type = 'safe'
        elif isinstance(self.mark, MarkUnknown):
            self.type = 'unknown'
        else:
            return

        self.selected_columns = self.__selected()
        self.available_columns = self.__available()

        self.columns = self.__get_columns()
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
                        if self.type == 'unsafe':
                            href = reverse('reports:unsafe', args=[report.trace_id])
                        else:
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


class AssociationChangesTable:
    def __init__(self, obj, view):
        self.view = view
        self._data = json.loads(obj.table_data)
        self._problems_names = {}
        self.href = self._data['href']

        if self.view['type'] == VIEW_TYPES[16][0]:
            self.verdicts = SAFE_VERDICTS
        elif self.view['type'] == VIEW_TYPES[17][0]:
            self.verdicts = UNSAFE_VERDICTS

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
        supported_columns = ['change_kind', 'job', 'format', 'problems']
        if self.view['type'] in {VIEW_TYPES[16][0], VIEW_TYPES[17][0]}:
            supported_columns.append('sum_verdict')
            supported_columns.append('tags')
        return supported_columns

    def __verdict_change(self, report_id, mark_type):
        vtmpl = '<span style="color:{0}">{1}</span>'
        if mark_type == 'unsafe':
            colors = UNSAFE_COLOR
            tmp_leaf = ReportUnsafe()
        elif mark_type == 'safe':
            colors = SAFE_COLOR
            tmp_leaf = ReportSafe()
        else:
            return '-'

        tmp_leaf.verdict = self._data['values'][report_id]['old_verdict']
        val1 = tmp_leaf.get_verdict_display()
        if self._data['values'][report_id]['old_verdict'] == self._data['values'][report_id]['new_verdict']:
            return vtmpl.format(colors[self._data['values'][report_id]['old_verdict']], val1)

        tmp_leaf.verdict = self._data['values'][report_id]['new_verdict']
        val2 = tmp_leaf.get_verdict_display()
        return '<i class="ui long arrow right icon"></i>'.join([
            vtmpl.format(colors[self._data['values'][report_id]['old_verdict']], val1),
            vtmpl.format(colors[self._data['values'][report_id]['new_verdict']], val2)
        ])

    def __get_columns(self):
        columns = ['report']
        columns.extend(self.view['columns'])
        columns.extend(self._data.get('attrs', []))
        return columns

    def __get_values(self):
        values = []
        if self.view['type'] == VIEW_TYPES[16][0]:
            mark_type = 'safe'
        elif self.view['type'] == VIEW_TYPES[17][0]:
            mark_type = 'unsafe'
        elif self.view['type'] == VIEW_TYPES[18][0]:
            mark_type = 'unknown'
            problems_ids = []
            for r_id in self._data['values']:
                if 'problems' in self._data['values'][r_id]:
                    for p_id in self._data['values'][r_id]['problems']:
                        problems_ids.append(int(p_id))
            for problem in UnknownProblem.objects.filter(id__in=problems_ids):
                self._problems_names[problem.id] = problem.name
        else:
            return []

        cnt = 0
        for report_id in self._data['values']:
            cnt += 1
            values_str = []
            for col in self.columns:
                val = '-'
                color = None
                href = None
                if not self.__filter_row(report_id):
                    cnt -= 1
                    break
                if col == 'report':
                    val = cnt
                    if mark_type == 'unsafe':
                        href = reverse('reports:unsafe', args=[self._data['values'][report_id]['trace_id']])
                    else:
                        href = reverse('reports:%s' % mark_type, args=[report_id])
                elif col == 'sum_verdict':
                    val = self.__verdict_change(report_id, mark_type)
                elif col == 'change_kind':
                    if self._data['values'][report_id]['change_kind'] in CHANGE_DATA:
                        val = CHANGE_DATA[self._data['values'][report_id]['change_kind']][0]
                        color = CHANGE_DATA[self._data['values'][report_id]['change_kind']][1]
                elif col == 'job':
                    val = self._data['values'][report_id]['job'][1]
                    href = reverse('jobs:job', args=[self._data['values'][report_id]['job'][0]])
                elif col == 'format':
                    val = self._data['values'][report_id]['format']
                elif col == 'tags':
                    val = loader.get_template('marks/tagsChanges.html')\
                        .render({'tags': self._data['values'][report_id].get('tags'), 'type': mark_type})
                elif col == 'problems':
                    val = loader.get_template('marks/problemsChanges.html').render({
                        'type': mark_type, 'problems': self.__get_problem_change(self._data['values'][report_id])
                    })
                elif col in self._data['values'][report_id]:
                    val = self._data['values'][report_id][col]
                values_str.append({'value': str(val), 'color': color, 'href': href})
            else:
                values.append(values_str)
        return values

    def __get_problem_change(self, changes):
        problems_change = []
        if 'problems' in changes:
            for p_id in changes['problems']:
                if int(p_id) in self._problems_names:
                    problems_change.append([
                        self._problems_names[int(p_id)], changes['problems'][p_id][0], changes['problems'][p_id][1]
                    ])
        return sorted(problems_change)

    def __filter_row(self, r_id):
        if 'change_kind' in self.view and self._data['values'][r_id]['change_kind'] not in self.view['change_kind']:
                return False
        if 'old_verdict' in self.view and self._data['values'][r_id]['old_verdict'] not in self.view['old_verdict']:
                return False
        if 'new_verdict' in self.view and self._data['values'][r_id]['new_verdict'] not in self.view['new_verdict']:
                return False
        if 'job_title' in self.view:
            job_title = self._data['values'][r_id]['job'][1].lower()
            pattern = self.view['job_title'][1].lower()
            if self.view['job_title'][0] == 'iexact' and job_title != pattern \
                    or self.view['job_title'][0] == 'istartswith' and not job_title.startswith(pattern) \
                    or self.view['job_title'][0] == 'icontains' and pattern not in job_title:
                return False
        if 'format' in self.view:
            view_format = int(self.view['format'][1])
            job_format = int(self._data['values'][r_id]['format'])
            if self.view['format'][0] == 'is' and view_format != job_format \
                    or self.view['format'][0] == 'isnot' and view_format == job_format:
                return False

        if 'attr' in self.view:
            for col in self._data['values'][r_id]:
                if col == self.view['attr'][0]:
                    ftype = self.view['attr'][1]
                    fvalue = self.view['attr'][2]
                    value = self._data['values'][r_id][col]
                    if ftype == 'iexact' and fvalue.lower() != value.lower():
                        return False
                    elif ftype == 'istartswith' and not value.lower().startswith(fvalue.lower()):
                        return False
                    elif ftype == 'icontains' and fvalue.lower() not in value.lower():
                        return False
        if 'hidden' in self.view and 'unchanged' in self.view['hidden']:
            if self._data['values'][r_id]['old_verdict'] == self._data['values'][r_id]['new_verdict'] \
                    and self._data['values'][r_id].get('tags') is None:
                return False
        return True

    def __is_not_used(self):
        pass
