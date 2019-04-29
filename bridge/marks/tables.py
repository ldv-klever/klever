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
from datetime import timedelta

from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import F, Count, Case, When, Sum, Q
from django.db.models.expressions import RawSQL
from django.template import loader
from django.urls import reverse
from django.utils.text import format_lazy
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _, ungettext_lazy
from django.utils.timezone import now

from bridge.tableHead import Header
from bridge.vars import MARK_SAFE, MARK_UNSAFE, MARK_STATUS, VIEW_TYPES, ASSOCIATION_TYPE, SAFE_VERDICTS,\
    UNSAFE_VERDICTS, MARK_SOURCE, USER_ROLES
from bridge.utils import unique_id, BridgeException

from users.models import User
from jobs.models import Job
from reports.models import ReportSafe, ReportUnsafe, ReportUnknown, ReportAttr
from marks.models import MarkSafe, MarkUnsafe, MarkUnknown,\
    MarkSafeAttr, MarkUnsafeAttr, MarkUnknownAttr,\
    MarkSafeHistory, MarkUnsafeHistory, MarkUnknownHistory, \
    MarkSafeTag, MarkUnsafeTag, SafeAssociationLike, UnsafeAssociationLike, UnknownAssociationLike,\
    MarkSafeReport, MarkUnsafeReport, MarkUnknownReport

from users.utils import DEF_NUMBER_OF_ELEMENTS, HumanizedValue
from jobs.utils import JobAccess
from marks.utils import UNSAFE_COLOR, SAFE_COLOR, STATUS_COLOR, MarkAccess
from marks.UnsafeUtils import DEFAULT_COMPARE
from marks.tags import TagsInfo
from marks.querysets import ListQuery
from caches.models import SafeMarkAssociationChanges, UnsafeMarkAssociationChanges, UnknownMarkAssociationChanges


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
    'problem_pattern': _('Problem pattern'),
    'checkbox': '',
    'source': _('Source'),
    'ass_type': _('Association type'),
    'automatic': _('Automatic association'),
    'tags': _('Tags'),
    'likes': format_lazy('{0}/{1}', _('Likes'), _('Dislikes')),
    'buttons': '',
    'description': _('Description'),
    'total_similarity': _('Total similarity'),
    'identifier': _('Identifier')
}

CHANGE_COLOR = {
    '0': '#FF8533',
    '1': '#00B800',
    '2': '#D11919'
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
        cache.table_data = {
            'href': reverse('marks:mark', args=[self.mark_type, self.mark.pk]),
            'values': self.values, 'attrs': self.attrs
        }
        cache.save()
        return str(cache.identifier)


class ReportMarksTableBase:
    report_type = None
    supported_columns = []
    marks_model = None
    likes_model = None
    ordering = ('-markreport_set__id',)

    def __init__(self, user, report, view):
        self.user = user
        self.report = report
        self.view = view
        self.can_mark = MarkAccess(user, report=report).can_create
        self.statuses = MARK_STATUS
        self.ass_types = ASSOCIATION_TYPE
        self.verdicts = None
        self.values, self.header = self.__get_values()

    @cached_property
    def selected_columns(self):
        columns = []
        supported_columns = set(self.supported_columns)
        for col in self.view['columns']:
            if col in supported_columns:
                columns.append({'value': col, 'title': MARK_TITLES.get(col, col)})
        return columns

    @cached_property
    def available_columns(self):
        columns = []
        for col in self.supported_columns:
            columns.append({'value': col, 'title': MARK_TITLES.get(col, col)})
        return columns

    @cached_property
    def columns(self):
        columns = ['mark_num']
        columns.extend(list(col['value'] for col in self.selected_columns))
        columns.append('likes')
        if self.can_mark:
            columns.append('buttons')
        return columns

    def __get_likes_data(self):
        assert self.likes_model is not None, 'Wrong usage'
        queryset = self.likes_model.objects.filter(association__report=self.report).select_related('author').order_by(
            'author__username', 'author__first_name', 'author__last_name'
        ).only(
            'association_id', 'dislike', 'author_id', 'author__username', 'author__first_name', 'author__last_name'
        )
        likes = {}
        dislikes = {}
        for ass_like in queryset:
            author_data = {
                'href': reverse('users:show-profile', args=[ass_like.author_id]),
                'value': ass_like.author.get_full_name()
            }
            if ass_like.dislike:
                dislikes.setdefault(ass_like.association_id, [])
                dislikes[ass_like.association_id].append(author_data)
            else:
                likes.setdefault(ass_like.association_id, [])
                likes[ass_like.association_id].append(author_data)
        return likes, dislikes

    @cached_property
    def queryset(self):
        assert self.marks_model is not None, 'Wrong usage'

        qs_filters = {'version': F('versions__version'), 'markreport_set__report_id': self.report.id}
        if 'status' in self.view:
            qs_filters['versions__status__in'] = self.view['status']
        if 'verdict' in self.view:
            qs_filters['verdict__in'] = self.view['verdict']
        if 'ass_type' in self.view:
            qs_filters['markreport_set__type__in'] = self.view['ass_type']
        if 'similarity' in self.view:
            qs_filters['markreport_set__result__gte'] = int(self.view['similarity'][0]) / 100

        annotations = {'ass_id': F('markreport_set__id')}
        columns_set = set(self.columns)
        fields = ['id', 'ass_id']
        if 'verdict' in columns_set:
            fields.append('verdict')
        if 'problem' in columns_set:
            annotations['problem'] = F('markreport_set__problem')
            fields.extend(['problem', 'link'])
        if 'similarity' in columns_set:
            annotations['similarity'] = F('markreport_set__result')
            annotations['error'] = F('markreport_set__error')
            fields.extend(['similarity', 'error'])
        if 'status' in columns_set:
            annotations['status'] = F('versions__status')
            fields.append('status')
        if 'source' in columns_set:
            fields.append('source')
        if 'tags' in columns_set:
            fields.append('cache_tags')
        if 'ass_type' in columns_set:
            annotations['ass_type'] = F('markreport_set__type')
            fields.append('ass_type')
        if 'ass_author' in columns_set:
            annotations['ass_author'] = F('markreport_set__author')
            fields.append('ass_author')
        if 'description' in columns_set:
            annotations['description'] = F('versions__description')
            fields.append('description')
        if 'change_date' in columns_set:
            annotations['change_date'] = F('versions__change_date')
            fields.append('change_date')
        if 'author' in columns_set:
            fields.extend([
                'versions__author__id', 'versions__author__username',
                'versions__author__first_name', 'versions__author__last_name'
            ])
        return self.marks_model.objects.filter(**qs_filters).order_by(*self.ordering)\
            .annotate(**annotations).values(*fields)

    @cached_property
    def authors(self):
        if 'author' not in self.columns and 'ass_author' not in self.columns:
            return {}
        users_ids = set()
        for mark_data in self.queryset:
            if 'author' in mark_data:
                users_ids.add(mark_data['author'])
            if 'ass_author' in mark_data:
                users_ids.add(mark_data['ass_author'])
        return dict((usr.id, usr) for usr in User.objects.filter(id__in=users_ids))

    def __get_values(self):
        value_data = []

        likes, dislikes = self.__get_likes_data()
        status_dict = dict(self.statuses)
        source_dict = dict(MARK_SOURCE)
        ass_type_dict = dict(self.ass_types)

        cnt = 1
        for mark_data in self.queryset:
            row_data = []
            for col in self.columns:
                val = '-'
                href = None
                color = None
                if col == 'mark_num':
                    val = cnt
                    href = reverse('marks:{}'.format(self.report_type), args=[mark_data['id']])
                elif col == 'verdict':
                    val = self.marks_model(verdict=mark_data['verdict']).get_verdict_display()
                    if self.report_type == 'unsafe':
                        color = UNSAFE_COLOR[mark_data['verdict']]
                    else:
                        color = SAFE_COLOR[mark_data['verdict']]
                elif col == 'problem':
                    val = mark_data['problem']
                    problem_link = mark_data['link']
                    if problem_link is not None:
                        if not problem_link.startswith('http'):
                            problem_link = 'http://' + problem_link
                        href = problem_link
                elif col == 'similarity':
                    if mark_data['error'] is not None:
                        val = mark_data['error']
                        color = result_color(0)
                    else:
                        val = "{:.0%}".format(mark_data['similarity'])
                        color = result_color(mark_data['similarity'])
                elif col == 'status':
                    val = status_dict[mark_data['status']]
                    color = STATUS_COLOR[mark_data['status']]
                elif col == 'source':
                    val = source_dict[mark_data['source']]
                elif col == 'tags':
                    if mark_data['cache_tags']:
                        val = '; '.join(sorted(mark_data['cache_tags']))
                elif col == 'ass_type':
                    val = {
                        'id': mark_data['id'], 'origin': mark_data['ass_type'],
                        'display': ass_type_dict[mark_data['ass_type']]
                    }
                    if mark_data['ass_type'] != ASSOCIATION_TYPE[1][0]:
                        val['confirm_url'] = reverse(
                            'marks:api-confirm-{}'.format(self.report_type),
                            args=[mark_data['ass_id']]
                        )
                    if mark_data['ass_type'] != ASSOCIATION_TYPE[2][0]:
                        val['unconfirm_url'] = reverse(
                            'marks:api-confirm-{}'.format(self.report_type),
                            args=[mark_data['ass_id']]
                        )
                    color = ASSOCIATION_TYPE_COLOR[mark_data['ass_type']]
                elif col == 'ass_author':
                    if mark_data['ass_author'] and mark_data['ass_author'] in self.authors:
                        val = self.authors[mark_data['ass_author']].get_full_name()
                        href = reverse('users:show-profile', args=[mark_data['ass_author']])
                elif col == 'description':
                    if len(mark_data['description']):
                        val = mark_data['description']
                elif col == 'likes':
                    val = {
                        'id': mark_data['id'],
                        'likes': likes.get(mark_data['ass_id'], []),
                        'dislikes': dislikes.get(mark_data['ass_id'], []),
                        'like_url': reverse('marks:api-like-{}'.format(self.report_type), args=[mark_data['ass_id']])
                    }
                elif col == 'buttons':
                    val = {
                        'edit': reverse('marks:{}-edit-inl'.format(self.report_type), args=[mark_data['id']]),
                        'delete': reverse('marks:api-{}-detail'.format(self.report_type), args=[mark_data['id']]),
                    }
                elif col == 'change_date':
                    val = mark_data['cahnge_date']
                elif col == 'author':
                    if mark_data['author'] and mark_data['author'] in self.authors:
                        val = self.authors[mark_data['author']].get_full_name()
                        href = reverse('users:show-profile', args=[mark_data['author']])
                row_data.append({'value': val, 'color': color, 'column': col, 'href': href})
            cnt += 1
            value_data.append(row_data)
        return value_data, Header(self.columns, MARK_TITLES).struct


class SafeReportMarksTable(ReportMarksTableBase):
    report_type = 'safe'
    supported_columns = [
        'verdict', 'status', 'source', 'tags', 'ass_type',
        'ass_author', 'description', 'change_date', 'author'
    ]
    marks_model = MarkSafe
    likes_model = SafeAssociationLike

    def __init__(self, user, report, view):
        super().__init__(user, report, view)
        self.verdicts = MARK_SAFE


class UnsafeReportMarksTable(ReportMarksTableBase):
    report_type = 'unsafe'
    supported_columns = [
        'verdict', 'similarity', 'status', 'source', 'tags', 'ass_type',
        'ass_author', 'description', 'change_date', 'author'
    ]
    marks_model = MarkUnsafe
    likes_model = UnsafeAssociationLike
    ordering = ('-markreport_set__id', '-markreport_set__result')

    def __init__(self, user, report, view):
        super().__init__(user, report, view)
        self.verdicts = MARK_UNSAFE


class UnknownReportMarksTable(ReportMarksTableBase):
    report_type = 'unknown'
    supported_columns = [
        'problem', 'status', 'source', 'ass_type', 'ass_author',
        'description', 'change_date', 'author'
    ]
    marks_model = MarkUnknown
    likes_model = UnknownAssociationLike

    def __init__(self, user, report, view):
        super().__init__(user, report, view)


# Table data for showing links between the specified report and marks
class ReportMarkTable:
    def __init__(self, user, report, view):
        self.user = user
        self.report = report
        self.view = view
        self.can_mark = MarkAccess(user, report=report).can_create
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
            orders = ['-result', '-id']
        else:
            orders = ['-id']
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
                    href = reverse('marks:{}'.format(self.type), args=[mark_rep.mark_id])
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
                    # TODO
                    # val = mark_rep.mark.get_status_display()
                    val = 'TODO'
                    # color = STATUS_COLOR[mark_rep.mark.status]
                elif col == 'source':
                    val = mark_rep.mark.get_source_display()
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
                    href = reverse('users:show-profile', args=[mark_rep.author_id])
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
                        href = reverse('users:show-profile', args=[mark_rep.mark.author_id])
                row_data.append({'value': val, 'color': color, 'column': col, 'href': href})
            cnt += 1
            value_data.append(row_data)
        return value_data


class MarksTableBase:
    mark_type = ''
    mark_table = None
    columns_list = []
    attrs_model = None
    versions_model = None

    def __init__(self, user, view, query_params):
        self.user = user
        self.view = view
        self._page_number = query_params.get('page', 1)
        self.paginator, self.page = self.get_queryset()
        self.authors = User.objects.all()
        self.verdicts = None
        self.statuses = MARK_STATUS
        self.sources = MARK_SOURCE
        self.title = ''

        self.header, self.values = self.marks_data()

    @cached_property
    def is_manager(self):
        return self.user.role == USER_ROLES[2][0]

    @cached_property
    def selected_columns(self):
        supported_columns = set(self.columns_list)
        columns = []
        for col in self.view['columns']:
            if col not in supported_columns:
                continue
            col_title = col
            if col_title in MARK_TITLES:
                col_title = MARK_TITLES[col_title]
            columns.append({'value': col, 'title': col_title})
        return columns

    @cached_property
    def available_columns(self):
        columns = []
        for col in self.columns_list:
            col_title = col
            if col_title in MARK_TITLES:
                col_title = MARK_TITLES[col_title]
            columns.append({'value': col, 'title': col_title})
        return columns

    def get_queryset(self):
        assert self.versions_model is not None, 'Please define the mark versions model'
        assert self.mark_table is not None, 'Please define marks table name'

        qs_filters = {'version': F('mark__version')}
        annotations = {}

        # Filters
        if 'identifier' in self.view:
            qs_filters['mark__identifier'] = self.view['identifier']
        if 'status' in self.view:
            qs_filters['status__in'] = self.view['status']
        if 'verdict' in self.view:
            qs_filters['verdict__in'] = self.view['verdict']
        if 'source' in self.view:
            qs_filters['mark__source__in'] = self.view['source']
        if 'author' in self.view:
            qs_filters['author_id'] = self.view['author']
        if 'attr' in self.view:
            annotations['attr_value'] = RawSQL(
                "\"{}\".\"cache_attrs\"->>%s".format(self.mark_table),
                (self.view['attr'][0],)
            )
            qs_filters['attr_value__{}'.format(self.view['attr'][1])] = self.view['attr'][2]
        if 'change_date' in self.view:
            value = now() - timedelta(**{self.view['change_date'][2]: int(self.view['change_date'][1])})
            qs_filters['change_date__{}'.format(self.view['change_date'][0])] = value
        if 'component' in self.view:
            qs_filters['component__{}'.format(self.view['component'][0])] = self.view['component'][1]

        # Sorting
        ordering = 'id'
        if 'order' in self.view:
            if self.view['order'][1] == 'change_date':
                ordering = 'change_date'
            elif self.view['order'][1] == 'num_of_links':
                ordering = 'mark__cache_links'
            elif self.view['order'][1] == 'component':
                ordering = 'mark__component'
            elif self.view['order'][1] == 'attr':
                annotations['ordering_attr'] = RawSQL(
                    "\"{}\".\"cache_attrs\"->>%s".format(self.mark_table),
                    (self.view['order'][2],)
                )
                ordering = 'ordering_attr'
            if self.view['order'][0] == 'up':
                ordering = '-' + ordering

        view_columns = set(self.view['columns'])
        select_only = ['mark__id']
        select_related = ['mark']
        if 'identifier' in view_columns:
            select_only.append('mark__identifier')
        if 'format' in view_columns:
            select_only.append('mark__format')
        if 'source' in view_columns:
            select_only.append('mark__source')
        if 'change_date' in view_columns:
            select_only.append('change_date')
        if 'author' in view_columns:
            select_related.append('author')
            select_only.extend(['author__id', 'author__first_name', 'author__last_name', 'author__username'])
        if 'status' in view_columns:
            select_only.append('status')
        if 'tags' in view_columns:
            select_only.append('mark__cache_tags')
        if 'verdict' in view_columns:
            select_only.append('verdict')
        if 'num_of_links' in view_columns:
            select_only.append('mark__cache_links')
        if 'component' in view_columns:
            select_only.append('mark__component')
        if 'problem_pattern' in view_columns:
            select_only.append('problem_pattern')

        queryset = self.versions_model.objects
        if annotations:
            queryset = queryset.annotate(**annotations)
        queryset = queryset.filter(**qs_filters).order_by(ordering).select_related(*select_related).only(*select_only)

        return self.paginate_queryset(queryset, self._page_number)

    def paginate_queryset(self, queryset, page):
        num_per_page = DEF_NUMBER_OF_ELEMENTS
        if 'elements' in self.view:
            num_per_page = int(self.view['elements'][0])

        paginator = Paginator(queryset, num_per_page)
        try:
            page_number = int(page)
        except ValueError:
            if page == 'last':
                page_number = paginator.num_pages
            else:
                raise BridgeException()
        try:
            values = paginator.page(page_number)
        except PageNotAnInteger:
            values = paginator.page(1)
        except EmptyPage:
            values = paginator.page(paginator.num_pages)
        return paginator, values

    @cached_property
    def marks_ids(self):
        return list(mark_version.mark_id for mark_version in self.page)

    def __get_attrs(self):
        qs_filters = {
            'mark_version__mark_id__in': self.marks_ids,
            'mark_version__mark__version': F('mark_version__version'),
            'is_compare': True
        }
        fields = ['mark_version__mark_id', 'name', 'value']

        assert self.attrs_model is not None, 'Please define the mark attributes model'
        attrs_qs = self.attrs_model.objects.filter(**qs_filters).order_by('id').values_list(*fields)

        attr_columns = []
        attributes = {}
        for m_id, a_name, a_value in attrs_qs:
            if a_name not in attributes:
                attr_columns.append(a_name)
                attributes[a_name] = {}
            attributes[a_name][m_id] = a_value
        return attr_columns, attributes

    def get_value(self, column, mark_version):
        assert isinstance(column, str) and isinstance(mark_version, self.mark_table)
        return '-', None, None

    def marks_data(self):
        cnt = (self.page.number - 1) * self.paginator.per_page + 1

        columns = ['checkbox', 'number'] if self.is_manager else ['number']
        columns.extend(self.view['columns'])

        # We collecting attributes from separate request to ensure the order of attributes columns is right
        attr_columns, attributes = self.__get_attrs()
        columns.extend(attr_columns)

        values_data = []
        for mark_version in self.page:
            mark_id = mark_version.mark_id
            values_row = []
            for col in columns:
                val = '-'
                href = None
                color = None
                if col == 'checkbox':
                    values_row.append({'checkbox': mark_id})
                    continue
                elif col in attributes:
                    val = attributes[col].get(mark_id, '-')
                elif col == 'number':
                    val = cnt
                    href = reverse('marks:{}'.format(self.mark_type), args=[mark_id])
                elif col == 'num_of_links':
                    val = mark_version.mark.cache_links
                elif col == 'tags':
                    if mark_version.mark.cache_tags:
                        val = ','.join(mark_version.mark.cache_tags)
                elif col == 'status':
                    val = mark_version.get_status_display()
                    color = STATUS_COLOR[mark_version.status]
                elif col == 'author' and mark_version.author:
                    val = mark_version.author.get_full_name()
                    href = reverse('users:show-profile', args=[mark_version.author_id])
                elif col == 'change_date':
                    val = mark_version.change_date
                    if self.user.data_format == 'hum':
                        val = HumanizedValue.get_templated_text('{% load humanize %}{{ date|naturaltime }}', date=val)
                elif col == 'source':
                    val = mark_version.mark.get_source_display()
                elif col == 'format':
                    val = mark_version.mark.format
                elif col == 'identifier':
                    val = str(mark_version.mark.identifier)
                else:
                    val, href, color = self.get_value(col, mark_version)

                values_row.append({'value': val, 'color': color, 'href': href})
            values_data.append(values_row)
            cnt += 1
        return Header(columns, MARK_TITLES).struct, values_data


class SafeMarksTable(MarksTableBase):
    mark_type = 'safe'
    mark_table = 'mark_safe'
    columns_list = [
        'num_of_links', 'verdict', 'tags', 'status', 'author',
        'change_date', 'format', 'source', 'identifier'
    ]
    attrs_model = MarkSafeAttr
    versions_model = MarkSafeHistory

    def __init__(self, user, view, query_params):
        super(SafeMarksTable, self).__init__(user, view, query_params)
        self.verdicts = MARK_SAFE
        self.title = _('Safe marks')

    def get_value(self, column, mark_version):
        val = '-'
        href = None
        color = None
        if column == 'verdict':
            val = mark_version.get_verdict_display()
            color = SAFE_COLOR[mark_version.verdict]
        return val, href, color


class UnsafeMarksTable(MarksTableBase):
    mark_type = 'unsafe'
    mark_table = 'mark_unsafe'
    columns_list = [
        'num_of_links', 'verdict', 'total_similarity', 'tags', 'status',
        'author', 'change_date', 'format', 'source', 'identifier'
    ]
    attrs_model = MarkUnsafeAttr
    versions_model = MarkUnsafeHistory

    def __init__(self, user, view, query_params):
        super(UnsafeMarksTable, self).__init__(user, view, query_params)
        self.verdicts = MARK_UNSAFE
        self.title = _('Unsafe marks')

    @cached_property
    def total_similarities(self):
        data = {}
        markreport_qs = MarkUnsafeReport.objects.filter(mark_id__in=self.marks_ids) \
            .values('mark_id').annotate(number=Count('id'), result_sum=Sum('result')) \
            .values_list('mark_id', 'number', 'result_sum')
        for m_id, number, result_sum in markreport_qs:
            data[m_id] = (result_sum / number) if number > 0 else 0
        return data

    def get_value(self, column, mark_version):
        val = '-'
        href = None
        color = None
        if column == 'verdict':
            val = mark_version.get_verdict_display()
            color = UNSAFE_COLOR[mark_version.verdict]
        elif column == 'total_similarity':
            val = '%d%%' % int(self.total_similarities.get(mark_version.mark_id, 0) * 100)
        return val, href, color


class UnknownMarksTable(MarksTableBase):
    mark_type = 'unknown'
    mark_table = 'mark_unknown'
    columns_list = [
        'num_of_links', 'component', 'problem_pattern', 'status', 'author',
        'change_date', 'format', 'source', 'identifier'
    ]
    attrs_model = MarkUnknownAttr
    versions_model = MarkUnknownHistory

    def __init__(self, user, view, query_params):
        super(UnknownMarksTable, self).__init__(user, view, query_params)
        self.title = _('Unknown marks')

    def get_value(self, column, mark_version):
        val = '-'
        href = None
        color = None
        if column == 'component':
            val = mark_version.mark.component
        elif column == 'problem_pattern':
            val = mark_version.problem_pattern
        return val, href, color


class MarkAssociationsBase:
    columns_list = []
    likes_model = None
    mark_reports_model = None

    def __init__(self, user, mark, view, query_params):
        self.user = user
        self.mark = mark
        self.view = view

        self._page_number = query_params.get('page', 1)
        self.paginator, self.page = self.get_queryset()
        self.authors = User.objects.all()

        self.ass_types = ASSOCIATION_TYPE

        self.header, self.values = self.__get_data()

    @cached_property
    def type(self):
        if isinstance(self.mark, MarkUnsafe):
            return 'unsafe'
        elif isinstance(self.mark, MarkSafe):
            return 'safe'
        elif isinstance(self.mark, MarkUnknown):
            return 'unknown'
        raise ValueError('Wrong argument provided')

    @cached_property
    def selected_columns(self):
        columns = []
        supported_columns = set(self.columns_list)
        for col in self.view['columns']:
            if col not in supported_columns:
                continue
            columns.append({'value': col, 'title': MARK_TITLES.get(col, col)})
        return columns

    @cached_property
    def available_columns(self):
        return list({'value': col, 'title': MARK_TITLES.get(col, col)} for col in self.columns_list)

    def get_queryset(self):
        assert self.mark_reports_model is not None, 'Please define the associations model'
        # assert self.mark_table is not None, 'Please define marks table name'

        qs_filters = {'mark_id': self.mark.id}

        # Filters
        if 'similarity' in self.view:
            qs_filters['result__{}'.format(self.view['similarity'][0])] = int(self.view['similarity'][1]) / 100
        if 'ass_type' in self.view:
            qs_filters['type__in'] = self.view['ass_type']

        # Sorting
        ordering = 'id'

        view_columns = set(self.view['columns'])
        select_only = ['id', 'report__root_id', 'report__root__job__id', 'report__root__job__name']
        if self.type == 'unsafe':
            select_only.append('report__trace_id')
        else:
            select_only.append('report__id')
        select_related = ['report', 'report__root__job']

        if 'similarity' in view_columns:
            select_only.append('result')
        if 'ass_type' in view_columns:
            select_only.append('type')
        if 'ass_author' in view_columns:
            select_related.append('author')
            select_only.extend(['author__id', 'author__first_name', 'author__last_name', 'author__username'])

        queryset = self.mark_reports_model.objects.filter(**qs_filters)\
            .select_related(*select_related).order_by(ordering).only(*select_only)

        return self.paginate_queryset(queryset, self._page_number)

    def paginate_queryset(self, queryset, page):
        num_per_page = DEF_NUMBER_OF_ELEMENTS
        if 'elements' in self.view:
            num_per_page = int(self.view['elements'][0])

        paginator = Paginator(queryset, num_per_page)
        try:
            page_number = int(page)
        except ValueError:
            if page == 'last':
                page_number = paginator.num_pages
            else:
                raise BridgeException()
        try:
            values = paginator.page(page_number)
        except PageNotAnInteger:
            values = paginator.page(1)
        except EmptyPage:
            values = paginator.page(paginator.num_pages)
        return paginator, values

    @cached_property
    def mr_ids(self):
        return list(mr.id for mr in self.page)

    @cached_property
    def likes_data(self):
        assert self.likes_model is not None, 'Please define associations likes model'

        data = {}
        likes_qs = self.likes_model.objects.values('association_id').annotate(
            dislikes=Count(Case(When(dislike=True, then=1))),
            likes=Count(Case(When(dislike=False, then=1)))
        ).values_list('association_id', 'likes', 'dislikes')
        for ass_id, likes_num, dislikes_num in likes_qs:
            data[ass_id] = {
                'likes': likes_num,
                'dislikes': dislikes_num
            }
        return data

    @cached_property
    def can_view_jobs(self):
        jobs_qs = Job.objects.filter(id__in=set(mr.report.root.job_id for mr in self.page))
        return JobAccess(self.user).can_view_jobs(jobs_qs)

    def __get_data(self):
        cnt = (self.page.number - 1) * self.paginator.per_page + 1
        columns = ['report'] + self.view['columns']

        values = []
        for mark_report in self.page:
            report = mark_report.report
            cnt += 1
            values_str = []
            for col in columns:
                val = '-'
                color = None
                href = None
                if col == 'report':
                    val = cnt
                    if report.root.job.id in self.can_view_jobs:
                        if self.type == 'unsafe':
                            href = reverse('reports:unsafe', args=[str(report.trace_id)])
                        else:
                            href = reverse('reports:%s' % self.type, args=[report.id])
                elif col == 'job':
                    val = report.root.job.name
                    if report.root.job.id in self.can_view_jobs:
                        href = reverse('jobs:job', args=[report.root.job.id])
                elif col == 'ass_type':
                    val = mark_report.get_type_display()
                elif col == 'ass_author':
                    if mark_report.author:
                        val = mark_report.author.get_full_name()
                        href = reverse('users:show-profile', args=[mark_report.author_id])
                elif col == 'likes' and mark_report.id in self.likes_data:
                    val = '{} / {}'.format(
                        self.likes_data[mark_report.id]['likes'],
                        self.likes_data[mark_report.id]['dislikes']
                    )
                else:
                    val, href, color = self.get_value(col, mark_report)

                values_str.append({'value': val, 'href': href, 'color': color})
            values.append(values_str)
        return Header(columns, MARK_TITLES).struct, values

    def get_value(self, column, mark_report):
        assert isinstance(column, str)
        assert mark_report is not None
        return '-', None, None


class SafeAssociationsTable(MarkAssociationsBase):
    columns_list = ['job', 'ass_type', 'ass_author', 'likes']
    likes_model = SafeAssociationLike
    mark_reports_model = MarkSafeReport


class UnsafeAssociationsTable(MarkAssociationsBase):
    columns_list = ['job', 'similarity', 'ass_type', 'ass_author', 'likes']
    likes_model = UnsafeAssociationLike
    mark_reports_model = MarkUnsafeReport

    def get_value(self, column, mark_report):
        val = '-'
        href = None
        color = None
        if column == 'similarity':
            if mark_report.error is not None:
                val = mark_report.error
                color = result_color(0)
            else:
                val = "{:.0%}".format(mark_report.result)
                color = result_color(mark_report.result)
        return val, href, color


class UnknownAssociationsTable(MarkAssociationsBase):
    columns_list = ['job', 'ass_type', 'ass_author', 'likes']
    likes_model = UnknownAssociationLike
    mark_reports_model = MarkUnknownReport


class AssociationChangesTableOld:
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
                    val = loader.get_template('marks/tags-problems-changes.html')\
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


class AssChangesBase:
    model = None
    verdicts = None
    supported_columns = []
    report_cache_table = None

    def __init__(self, cache_id, view):
        self._cache_id = cache_id
        self.view = view
        self.header, self.values = self.__get_values()

    @cached_property
    def selected_columns(self):
        supported_columns = set(self.supported_columns)
        columns = []
        for col in self.view['columns']:
            if col in supported_columns:
                columns.append({'value': col, 'title': MARK_TITLES.get(col, col)})
        return columns

    @cached_property
    def available_columns(self):
        columns = []
        for col in self.supported_columns:
            columns.append({'value': col, 'title': MARK_TITLES.get(col, col)})
        return columns

    def __get_sum_verdict(self, cache_obj):
        if self.model == SafeMarkAssociationChanges:
            vtmpl = '<span class="safe-verdict-{value}">{text}</span>'
        elif self.model == UnsafeMarkAssociationChanges:
            vtmpl = '<span class="unsafe-verdict-{value}">{text}</span>'
        else:
            return '-'
        if cache_obj.verdict_old == cache_obj.verdict_new:
            return vtmpl.format(value=cache_obj.verdict_new, text=cache_obj.get_verdict_new_display())
        return '<i class="ui long arrow right icon"></i>'.join([
            vtmpl.format(value=cache_obj.verdict_old, text=cache_obj.get_verdict_old_display()),
            vtmpl.format(value=cache_obj.verdict_new, text=cache_obj.get_verdict_new_display())
        ])

    def __get_tags_or_problems(self, data_old, data_new):
        context = {}
        if self.model == SafeMarkAssociationChanges:
            context['type'] = 'safe'
        elif self.model == UnsafeMarkAssociationChanges:
            context['type'] = 'unsafe'
        else:
            context['type'] = 'unknown'
        changes = {}
        for name, num in data_old.items():
            changes[name] = [num, 0]
        for name, num in data_new.items():
            if name in changes:
                changes[name][1] = num
            else:
                changes[name] = [0, num]
        context['changes'] = list((name, changes[name][0], changes[name][1]) for name in sorted(changes))
        return loader.get_template('marks/tags-problems-changes.html').render(context)

    def __get_kind_html(self, cache_obj):
        return '<span style="color: {};">{}</span>'.format(
            CHANGE_COLOR[cache_obj.kind], cache_obj.get_kind_display()
        )

    def get_queryset(self):
        qs_filters = Q(identifier=self._cache_id)
        annotations = {}
        select_related = []
        select_only = ['mark_id', 'report_id']
        if self.model == UnsafeMarkAssociationChanges:
            select_only.append('report__trace_id')
        if 'change_kind' in self.view:
            qs_filters &= Q(kind__in=self.view['change_kind'])
        if 'verdict_old' in self.view:
            qs_filters &= Q(verdict_old__in=self.view['verdict_old'])
        if 'verdict_new' in self.view:
            qs_filters &= Q(verdict_new__in=self.view['verdict_new'])
        if 'job_title' in self.view:
            qs_filters &= Q(**{'job__name__{}'.format(self.view['job_title'][0]): self.view['job_title'][1]})
        if 'format' in self.view:
            format_filter = Q(job__format=self.view['format'][1])
            if self.view['format'][0] == 'is':
                qs_filters &= format_filter
            else:
                qs_filters &= ~format_filter
        if 'attr' in self.view:
            select_related.extend(['report', 'report__cache'])
            annotations['attr_value'] = RawSQL(
                "\"{}\".\"attrs\"->>%s".format(self.report_cache_table),
                (self.view['attr'][0],)
            )
            qs_filters &= Q(**{'attr_value__{}'.format(self.view['attr'][1]): self.view['attr'][2]})
            qs_filters &= ~Q(report__cache=None)

        if 'hidden' in self.view and 'unchanged' in self.view['hidden']:
            if self.model == UnknownMarkAssociationChanges:
                qs_filters &= ~Q(problems_new=F('problems_old'))
            else:
                qs_filters &= ~Q(verdict_new=F('verdict_old'))
                qs_filters &= ~Q(tags_new=F('tags_old'))

        selected_columns = set(self.view['columns'])
        if 'change_kind' in selected_columns:
            select_only.append('kind')
        if 'job' in selected_columns:
            select_only.extend(['job__id', 'job__name'])
        if 'format' in selected_columns:
            select_only.extend(['job__format'])
        if 'sum_verdict' in selected_columns:
            select_only.extend(['verdict_old', 'verdict_new'])
        if 'tags' in selected_columns:
            select_only.extend(['tags_old', 'tags_new'])
        if 'problems' in selected_columns:
            select_only.extend(['problems_old', 'problems_new'])

        queryset = self.model.objects
        if annotations:
            queryset = queryset.annotate(**annotations)
        queryset = queryset.filter(qs_filters)
        if select_related:
            queryset = queryset.select_related(*select_related)
        return queryset.only(*select_only)

    def __get_values(self):
        queryset = self.get_queryset()
        columns = ['report']
        columns.extend(self.view['columns'])

        # Get attributes columns and values
        attributes = {}
        attrs_qs = ReportAttr.objects.filter(report_id__in=list(cache_obj.report_id for cache_obj in queryset)).order_by('id')
        for attr in attrs_qs.only('name', 'value', 'report_id'):
            if attr.name not in attributes:
                attributes[attr.name] = {}
                columns.append(attr.name)
            attributes[attr.name][attr.report_id] = attr.value

        cnt = 0
        values = []
        for cache_obj in queryset:
            cnt += 1
            values_str = []
            for col in columns:
                val = '-'
                href = None
                html = None
                if col in attributes:
                    val = attributes[col].get(cache_obj.report_id, '-')
                elif col == 'report':
                    val = cnt
                    if self.model == SafeMarkAssociationChanges:
                        href = reverse('reports:safe', args=[cache_obj.report_id])
                    elif self.model == UnsafeMarkAssociationChanges:
                        href = reverse('reports:unsafe', args=[cache_obj.report.trace_id])
                    else:
                        href = reverse('reports:unknown', args=[cache_obj.report_id])
                elif col == 'sum_verdict':
                    html = self.__get_sum_verdict(cache_obj)
                elif col == 'change_kind':
                    html = self.__get_kind_html(cache_obj)
                elif col == 'job':
                    val = cache_obj.job.name
                    href = reverse('jobs:job', args=[cache_obj.job.id])
                elif col == 'format':
                    val = cache_obj.job.format
                elif col == 'tags':
                    html = self.__get_tags_or_problems(cache_obj.tags_old, cache_obj.tags_new)
                elif col == 'problems':
                    html = self.__get_tags_or_problems(cache_obj.problems_old, cache_obj.problems_new)
                values_str.append({'value': str(val), 'href': href, 'html': html})
            values.append(values_str)
        return Header(columns, MARK_TITLES).struct, values


class SafeAssChanges(AssChangesBase):
    model = SafeMarkAssociationChanges
    verdicts = SAFE_VERDICTS
    supported_columns = ['change_kind', 'job', 'format', 'sum_verdict', 'tags']
    report_cache_table = 'cache_safe'


class UnsafeAssChanges(AssChangesBase):
    model = UnsafeMarkAssociationChanges
    verdicts = UNSAFE_VERDICTS
    supported_columns = ['change_kind', 'job', 'format', 'sum_verdict', 'tags']
    report_cache_table = 'cache_unsafe'


class UnknownAssChanges(AssChangesBase):
    model = UnknownMarkAssociationChanges
    supported_columns = ['change_kind', 'job', 'format', 'problems']
    report_cache_table = 'cache_unknown'


class AssociationChangesTable:
    def __init__(self, cache_id, view):
        self.view = view
        self._data = changes_obj.table_data
        self._problems_names = {}
        self.href = self._data['href']

        self.verdicts = None
        if self.view['type'] == VIEW_TYPES[16][0]:
            self.verdicts = SAFE_VERDICTS
        elif self.view['type'] == VIEW_TYPES[17][0]:
            self.verdicts = UNSAFE_VERDICTS

        self.columns = self.__get_columns()
        self.header = Header(self.columns, MARK_TITLES).struct
        self.values = self.__get_values()

    @cached_property
    def selected_columns(self):
        columns = []
        for col in self.view['columns']:
            if col not in self.__supported_columns():
                return []
            col_title = col
            if col_title in MARK_TITLES:
                col_title = MARK_TITLES[col_title]
            columns.append({'value': col, 'title': col_title})
        return columns

    @cached_property
    def available_columns(self):
        columns = []
        for col in self.__supported_columns():
            col_title = col
            if col_title in MARK_TITLES:
                col_title = MARK_TITLES[col_title]
            columns.append({'value': col, 'title': col_title})
        return columns

    def __supported_columns(self):
        supported_columns = ['change_kind', 'job', 'format']
        if self.view['type'] in {VIEW_TYPES[16][0], VIEW_TYPES[17][0]}:
            supported_columns.append('sum_verdict')
            supported_columns.append('tags')
        else:
            supported_columns.append('problems')
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
                    val = loader.get_template('marks/tags-problems-changes.html')\
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
