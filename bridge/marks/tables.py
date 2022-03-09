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

from datetime import timedelta

from django.db.models import F, Count, Case, When, Sum, Q
from django.db.models.expressions import RawSQL
from django.template import loader
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.text import format_lazy
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from bridge.vars import (
    MARK_SAFE, MARK_UNSAFE, ASSOCIATION_TYPE, MARK_SOURCE, USER_ROLES, MARK_STATUS, SAFE_VERDICTS, UNSAFE_VERDICTS
)

from users.models import User
from jobs.models import Decision
from reports.models import ReportAttr
from marks.models import (
    MarkSafe, MarkUnsafe, MarkUnknown, MarkSafeAttr, MarkUnsafeAttr, MarkUnknownAttr,
    MarkSafeHistory, MarkUnsafeHistory, MarkUnknownHistory,
    SafeAssociationLike, UnsafeAssociationLike, UnknownAssociationLike,
    MarkSafeReport, MarkUnsafeReport, MarkUnknownReport
)
from caches.models import SafeMarkAssociationChanges, UnsafeMarkAssociationChanges, UnknownMarkAssociationChanges

from reports.verdicts import safe_color, unsafe_color, bug_status_color

from users.utils import HumanizedValue, paginate_queryset
from jobs.utils import decisions_with_view_access
from marks.utils import MarkAccess


MARK_TITLES = {
    'mark_num': _('#'),
    'change_kind': _('Association change kind'),
    'verdict': _("Verdict"),
    'sum_verdict': _('Total verdict'),
    'sum_status': _('Total status'),
    'similarity': _('Similarity'),
    'status': _('Status'),
    'author': _('Last change author'),
    'change_date': _('Last change date'),
    'ass_author': _('Association author'),
    'report': _('Report'),
    'decision': _('Decision'),
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
    'identifier': _('Identifier'),
    'threshold': _('Association threshold'),
    'associated': _('Is associated'),
}

CHANGE_COLOR = {
    '0': '#FF8533',
    '1': '#00B800',
    '2': '#D11919'
}


def result_color(result):
    if 0 <= result <= 0.33:
        return '#E60000'
    elif 0.33 < result <= 0.66:
        return '#CC7A29'
    elif 0.66 < result <= 1:
        return '#00CC66'
    return None


class ReportMarksTableBase:
    report_type = None
    supported_columns = []
    marks_model = None
    likes_model = None
    ordering = ('-markreport_set__id',)
    ass_type_block_titles = {
        ASSOCIATION_TYPE[0][0]: _('Dissimilar marks'),
        ASSOCIATION_TYPE[1][0]: _('Marks with rejected associations'),
        ASSOCIATION_TYPE[2][0]: _('Marks with automatic associations'),
        ASSOCIATION_TYPE[3][0]: _('Marks with confirmed associations')
    }

    def __init__(self, user, report, view):
        self.user = user
        self.report = report
        self.view = view
        self.titles = MARK_TITLES
        self.can_mark = MarkAccess(user, report=report).can_create
        self.ass_types = ASSOCIATION_TYPE
        self.statuses = self.verdicts = None

    @cached_property
    def selected_columns(self):
        columns = []
        supported_columns = set(self.supported_columns)
        for col in self.view['columns']:
            if col in supported_columns:
                columns.append({'value': col, 'title': self.titles.get(col, col)})
        return columns

    @cached_property
    def available_columns(self):
        columns = []
        for col in self.supported_columns:
            columns.append({'value': col, 'title': self.titles.get(col, col)})
        return columns

    @cached_property
    def columns(self):
        columns = ['mark_num']
        columns.extend(list(col['value'] for col in self.selected_columns))
        columns.append('likes')
        if self.can_mark:
            columns.append('buttons')
        return columns

    @cached_property
    def likes_data(self):
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
        return {'likes': likes, 'dislikes': dislikes}

    @cached_property
    def queryset(self):
        assert self.marks_model is not None, 'Wrong usage'

        qs_filters = {'version': F('versions__version'), 'markreport_set__report_id': self.report.id}
        if 'status' in self.view:
            qs_filters['status__in'] = self.view['status']
        if 'verdict' in self.view:
            qs_filters['verdict__in'] = self.view['verdict']
        if 'ass_type' in self.view:
            qs_filters['markreport_set__type__in'] = self.view['ass_type']
        if 'similarity' in self.view:
            qs_filters['markreport_set__result__gte'] = int(self.view['similarity'][0]) / 100
        if 'associated' in self.view:
            qs_filters['markreport_set__associated'] = True

        annotations = {
            'ass_id': F('markreport_set__id'),
            'ass_type': F('markreport_set__type')
        }
        columns_set = set(self.columns)
        fields = ['id', 'ass_id', 'ass_type']
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
            fields.append('status')
        if 'source' in columns_set:
            fields.append('source')
        if 'tags' in columns_set:
            fields.append('cache_tags')
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

    @cached_property
    def likes_popups(self):
        likes_data_list = []
        for ass_id in self.likes_data['likes']:
            if self.likes_data['likes'][ass_id]:
                likes_data_list.append({'id': ass_id, 'authors': self.likes_data['likes'][ass_id]})
        for ass_id in self.likes_data['dislikes']:
            if self.likes_data['dislikes'][ass_id]:
                likes_data_list.append({'id': ass_id, 'authors': self.likes_data['dislikes'][ass_id]})
        return likes_data_list

    @cached_property
    def _verdicts_map(self):
        if self.verdicts:
            return dict(self.verdicts)
        return {}

    @cached_property
    def _statuses_map(self):
        if self.statuses:
            return dict(self.statuses)
        return {}

    @cached_property
    def values(self):
        value_data = {
            ASSOCIATION_TYPE[0][0]: {
                'title': self.ass_type_block_titles[ASSOCIATION_TYPE[0][0]],
                'color': '#8f361e',
                'values': []
            },
            ASSOCIATION_TYPE[1][0]: {
                'title': self.ass_type_block_titles[ASSOCIATION_TYPE[1][0]],
                'color': '#c71a2d',
                'values': []
            },
            ASSOCIATION_TYPE[2][0]: {
                'title': self.ass_type_block_titles[ASSOCIATION_TYPE[2][0]],
                'color': '#7506b4',
                'values': []
            },
            ASSOCIATION_TYPE[3][0]: {
                'title': self.ass_type_block_titles[ASSOCIATION_TYPE[3][0]],
                'color': '#3f9f32',
                'values': []
            }
        }

        source_dict = dict(MARK_SOURCE)

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
                    val = self._verdicts_map[mark_data['verdict']]
                    if self.report_type == 'unsafe':
                        color = unsafe_color(mark_data['verdict'])
                    else:
                        color = safe_color(mark_data['verdict'])
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
                    if mark_data['status']:
                        val = self._statuses_map[mark_data['status']]
                        color = bug_status_color(mark_data['status'])
                elif col == 'source':
                    val = source_dict[mark_data['source']]
                elif col == 'tags':
                    if mark_data['cache_tags']:
                        val = '; '.join(x.split(' - ')[-1] for x in sorted(mark_data['cache_tags']))
                elif col == 'ass_author':
                    if mark_data['ass_author'] and mark_data['ass_author'] in self.authors:
                        val = self.authors[mark_data['ass_author']].get_full_name()
                        href = reverse('users:show-profile', args=[mark_data['ass_author']])
                elif col == 'description':
                    if len(mark_data['description']):
                        val = mark_data['description']
                elif col == 'likes':
                    val = {
                        'id': mark_data['ass_id'],
                        'likes_num': len(self.likes_data['likes'].get(mark_data['ass_id'], [])),
                        'dislikes_num': len(self.likes_data['dislikes'].get(mark_data['ass_id'], [])),
                        'like_url': reverse('marks:api-like-{}'.format(self.report_type), args=[mark_data['ass_id']])
                    }
                elif col == 'buttons':
                    val = {
                        'edit': reverse('marks:{}-edit-inl'.format(self.report_type), args=[mark_data['id']]),
                        'delete': reverse('marks:api-{}-detail'.format(self.report_type), args=[mark_data['id']]),
                    }
                    if mark_data['ass_type'] in {ASSOCIATION_TYPE[1][0], ASSOCIATION_TYPE[2][0]}:
                        val['confirm'] = reverse(
                            'marks:api-confirm-{}'.format(self.report_type), args=[mark_data['ass_id']]
                        )
                    if mark_data['ass_type'] in {ASSOCIATION_TYPE[2][0], ASSOCIATION_TYPE[3][0]}:
                        val['unconfirm'] = reverse(
                            'marks:api-confirm-{}'.format(self.report_type), args=[mark_data['ass_id']]
                        )
                elif col == 'change_date':
                    val = mark_data['cahnge_date']
                elif col == 'author':
                    if mark_data['author'] and mark_data['author'] in self.authors:
                        val = self.authors[mark_data['author']].get_full_name()
                        href = reverse('users:show-profile', args=[mark_data['author']])
                row_data.append({'value': val, 'color': color, 'column': col, 'href': href})
            cnt += 1
            value_data[mark_data['ass_type']]['values'].append(row_data)
        return list(value_data[at] for at in sorted(value_data, reverse=True) if value_data[at]['values'])


class SafeReportMarksTable(ReportMarksTableBase):
    report_type = 'safe'
    supported_columns = ['verdict', 'source', 'tags', 'ass_author', 'description', 'change_date', 'author']
    marks_model = MarkSafe
    likes_model = SafeAssociationLike

    def __init__(self, user, report, view):
        super().__init__(user, report, view)
        self.verdicts = MARK_SAFE


class UnsafeReportMarksTable(ReportMarksTableBase):
    report_type = 'unsafe'
    supported_columns = [
        'verdict', 'similarity', 'status', 'source', 'tags', 'ass_author', 'description', 'change_date', 'author'
    ]
    marks_model = MarkUnsafe
    likes_model = UnsafeAssociationLike
    ordering = ('-markreport_set__result', '-markreport_set__id')
    ass_type_block_titles = {
        ASSOCIATION_TYPE[0][0]: _('Dissimilar marks'),
        ASSOCIATION_TYPE[1][0]: _('Similar marks with rejected associations'),
        ASSOCIATION_TYPE[2][0]: _('Similar marks with automatic associations'),
        ASSOCIATION_TYPE[3][0]: _('Similar marks with confirmed associations')
    }

    def __init__(self, user, report, view):
        super().__init__(user, report, view)
        self.verdicts = MARK_UNSAFE
        self.statuses = MARK_STATUS


class UnknownReportMarksTable(ReportMarksTableBase):
    report_type = 'unknown'
    supported_columns = ['problem', 'source', 'ass_author', 'description', 'change_date', 'author']
    marks_model = MarkUnknown
    likes_model = UnknownAssociationLike

    def __init__(self, user, report, view):
        super().__init__(user, report, view)


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
        self.verdicts = self.statuses = None
        self.sources = MARK_SOURCE
        self.title = ''

        self.titles = MARK_TITLES
        self.columns, self.values = self.marks_data()

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

        view_columns = set(self.view['columns'])
        qs_filters = {'version': F('mark__version')}
        annotations = {}

        if 'num_of_links' in view_columns:
            annotations['num_of_links'] = Count('mark__markreport_set')

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
            qs_filters['author_id'] = self.view['author'][0]
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
            qs_filters['mark__component__{}'.format(self.view['component'][0])] = self.view['component'][1]

        # Sorting
        ordering = 'id'
        if 'order' in self.view:
            if self.view['order'][1] == 'change_date':
                ordering = 'change_date'
            elif self.view['order'][1] == 'component':
                ordering = 'mark__component'
            elif self.view['order'][1] == 'attr':
                annotations['ordering_attr'] = RawSQL(
                    "\"{}\".\"cache_attrs\"->>%s".format(self.mark_table),
                    (self.view['order'][2],)
                )
                ordering = 'ordering_attr'
            elif self.view['order'][1] == 'num_of_links' and 'num_of_links' in annotations:
                ordering = 'num_of_links'
            if self.view['order'][0] == 'up':
                ordering = '-' + ordering

        select_only = ['mark__id']
        select_related = ['mark']
        if 'identifier' in view_columns:
            select_only.append('mark__identifier')
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
        if 'component' in view_columns:
            select_only.append('mark__component')
        if 'problem_pattern' in view_columns:
            select_only.append('problem_pattern')
        if 'threshold' in view_columns:
            select_only.append('threshold')

        queryset = self.versions_model.objects
        if annotations:
            queryset = queryset.annotate(**annotations)
        queryset = queryset.filter(**qs_filters).order_by(ordering).select_related(*select_related).only(*select_only)
        num_per_page = self.view['elements'][0] if self.view['elements'] else None
        return paginate_queryset(queryset, self._page_number, num_per_page)

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

        columns = ['checkbox', 'number']
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
                    val = mark_version.num_of_links
                elif col == 'tags':
                    if mark_version.mark.cache_tags:
                        val = ', '.join(x.split(' - ')[-1] for x in mark_version.mark.cache_tags)
                elif col == 'author' and mark_version.author:
                    val = mark_version.author.get_full_name()
                    href = reverse('users:show-profile', args=[mark_version.author_id])
                elif col == 'change_date':
                    val = mark_version.change_date
                    if self.user.data_format == 'hum':
                        val = HumanizedValue.get_templated_text('{% load humanize %}{{ date|naturaltime }}', date=val)
                elif col == 'source':
                    val = mark_version.mark.get_source_display()
                elif col == 'identifier':
                    val = str(mark_version.mark.identifier)
                else:
                    val, href, color = self.get_value(col, mark_version)

                values_row.append({'value': val, 'color': color, 'href': href})
            values_data.append(values_row)
            cnt += 1
        return columns, values_data


class SafeMarksTable(MarksTableBase):
    mark_type = 'safe'
    mark_table = 'mark_safe'
    columns_list = [
        'num_of_links', 'verdict', 'tags', 'author',
        'change_date', 'source', 'identifier'
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
            color = safe_color(mark_version.verdict)
        return val, href, color


class UnsafeMarksTable(MarksTableBase):
    mark_type = 'unsafe'
    mark_table = 'mark_unsafe'
    columns_list = [
        'num_of_links', 'verdict', 'tags', 'status',
        'author', 'change_date', 'source', 'identifier'
    ]
    attrs_model = MarkUnsafeAttr
    versions_model = MarkUnsafeHistory

    def __init__(self, user, view, query_params):
        super(UnsafeMarksTable, self).__init__(user, view, query_params)
        self.verdicts = MARK_UNSAFE
        self.statuses = MARK_STATUS
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
            color = unsafe_color(mark_version.verdict)
        elif column == 'threshold':
            val = '{}%'.format(mark_version.threshold_percentage)
        elif column == 'status' and mark_version.status:
            val = mark_version.get_status_display()
            color = bug_status_color(mark_version.status)
        return val, href, color


class UnknownMarksTable(MarksTableBase):
    mark_type = 'unknown'
    mark_table = 'mark_unknown'
    columns_list = [
        'num_of_links', 'component', 'problem_pattern', 'author',
        'change_date', 'source', 'identifier'
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

        self.titles = MARK_TITLES
        self.columns, self.values = self.__get_data()

    @cached_property
    def type(self):
        if isinstance(self.mark, MarkSafe):
            return 'safe'
        elif isinstance(self.mark, MarkUnsafe):
            return 'unsafe'
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
        if 'associated' in self.view:
            qs_filters['associated'] = True
        if 'ass_type' in self.view:
            qs_filters['type__in'] = self.view['ass_type']

        # Sorting
        ordering = 'id'

        view_columns = set(self.view['columns'])
        select_related = ['report', 'report__decision']
        select_only = [
            'id', 'report__identifier', 'report__decision_id', 'report__decision__identifier',
            'report__decision__title', 'report__decision__start_date'
        ]

        if 'similarity' in view_columns:
            select_only.append('result')
        if 'associated' in view_columns:
            select_only.append('associated')
        if 'ass_type' in view_columns:
            select_only.append('type')
        if 'ass_author' in view_columns:
            select_related.append('author')
            select_only.extend(['author__id', 'author__first_name', 'author__last_name', 'author__username'])

        queryset = self.mark_reports_model.objects.filter(**qs_filters)\
            .select_related(*select_related).order_by(ordering).only(*select_only)
        num_per_page = self.view['elements'][0] if self.view['elements'] else None
        return paginate_queryset(queryset, self._page_number, num_per_page)

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
    def can_view_decisions(self):
        return decisions_with_view_access(
            self.user, Decision.objects.filter(id__in=set(mr.report.decision_id for mr in self.page))
        )

    def __get_data(self):
        cnt = (self.page.number - 1) * self.paginator.per_page
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
                    if report.decision_id in self.can_view_decisions:
                        # reports:safe, reports:unsafe, reports:unknown
                        href = reverse('reports:%s' % self.type, args=[report.decision.identifier, report.identifier])
                elif col == 'decision':
                    val = report.decision.name
                    if report.decision_id in self.can_view_decisions:
                        href = reverse('jobs:decision', args=[report.decision_id])
                elif col == 'ass_type':
                    val = mark_report.get_type_display()
                elif col == 'associated':
                    val = mark_report.associated
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

                values_str.append({'value': val, 'href': href, 'color': color, 'column': col})
            values.append(values_str)
        return columns, values

    def get_value(self, column, mark_report):
        assert isinstance(column, str)
        assert mark_report is not None
        return '-', None, None


class SafeAssociationsTable(MarkAssociationsBase):
    columns_list = ['decision', 'associated', 'ass_type', 'ass_author', 'likes']
    likes_model = SafeAssociationLike
    mark_reports_model = MarkSafeReport


class UnsafeAssociationsTable(MarkAssociationsBase):
    columns_list = ['decision', 'similarity', 'associated', 'ass_type', 'ass_author', 'likes']
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
    columns_list = ['decision', 'ass_type', 'ass_author', 'likes']
    likes_model = UnknownAssociationLike
    mark_reports_model = MarkUnknownReport


class AssChangesBase:
    model = None
    verdicts = None
    supported_columns = []
    report_cache_table = None

    def __init__(self, cache_id, view):
        self._cache_id = cache_id
        self.view = view
        self.titles = MARK_TITLES
        self.columns, self.values = self.__get_values()

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

    @cached_property
    def type(self):
        if self.model == SafeMarkAssociationChanges:
            return 'safe'
        elif self.model == UnsafeMarkAssociationChanges:
            return 'unsafe'
        elif self.model == UnknownMarkAssociationChanges:
            return 'unknown'
        raise ValueError('Wrong argument provided')

    def get_verdict_html(self, verdict, text):
        raise NotImplementedError

    def get_sum_verdict(self, cache_obj):
        verdicts_html = [self.get_verdict_html(cache_obj.verdict_old, cache_obj.get_verdict_old_display())]
        if cache_obj.verdict_old != cache_obj.verdict_new:
            verdicts_html.append(
                self.get_verdict_html(cache_obj.verdict_new, cache_obj.get_verdict_new_display())
            )
        return '<i class="ui long arrow right icon"></i>'.join(verdicts_html)

    def get_sum_status(self, cache_obj):
        if not isinstance(cache_obj, UnsafeMarkAssociationChanges):
            return '-'

        def get_status_html(status, text):
            if not status:
                return '<i class="ui red ban icon"></i>'
            color = bug_status_color(status)
            if color:
                return '<span style="color: {color};">{text}</span>'.format(color=color, text=text)
            return '<span>{text}</span>'.format(text=text)

        statuses_html = [get_status_html(cache_obj.status_old, cache_obj.get_status_old_display())]
        if cache_obj.status_old != cache_obj.status_new:
            statuses_html.append(get_status_html(cache_obj.status_new, cache_obj.get_status_new_display()))
        return '<i class="ui long arrow right icon"></i>'.join(statuses_html)

    def __get_problems(self, problems_old, problems_new):
        context = {'type': 'mark-problem'}
        changes = {}
        for problem, num in problems_old.items():
            changes[problem] = [num, 0]
        for problem, num in problems_new.items():
            if problem in changes:
                changes[problem][1] = num
            else:
                changes[problem] = [0, num]
        context['changes'] = list((problem, changes[problem][0], changes[problem][1]) for problem in sorted(changes))
        return loader.get_template('marks/tags-problems-changes.html').render(context)

    def __get_tags(self, tags_old, tags_new):
        context = {'type': 'mark-tag'}
        changes = {}
        for name, num in tags_old.items():
            changes[name] = [num, 0]
        for name, num in tags_new.items():
            if name in changes:
                changes[name][1] = num
            else:
                changes[name] = [0, num]
        context['changes'] = list((t.split(' - ')[-1], changes[t][0], changes[t][1]) for t in sorted(changes))
        return loader.get_template('marks/tags-problems-changes.html').render(context)

    def __get_kind_html(self, cache_obj):
        return '<span style="color: {};">{}</span>'.format(
            CHANGE_COLOR[cache_obj.kind], cache_obj.get_kind_display()
        )

    def get_queryset(self):
        qs_filters = Q(identifier=self._cache_id)
        annotations = {}
        select_related = ['report', 'decision']
        select_only = ['mark_id', 'report_id', 'report__identifier', 'decision__identifier']
        if 'change_kind' in self.view:
            qs_filters &= Q(kind__in=self.view['change_kind'])
        if 'verdict_old' in self.view:
            qs_filters &= Q(verdict_old__in=self.view['verdict_old'])
        if 'verdict_new' in self.view:
            qs_filters &= Q(verdict_new__in=self.view['verdict_new'])
        if 'decision_title' in self.view:
            qs_filters &= Q(**{
                'decision__title__{}'.format(self.view['decision_title'][0]): self.view['decision_title'][1]
            })
        if 'attr' in self.view:
            select_related.extend(['report__cache'])
            annotations['attr_value'] = RawSQL(
                "\"{}\".\"attrs\"->>%s".format(self.report_cache_table),
                (self.view['attr'][0],)
            )
            qs_filters &= Q(**{'attr_value__{}'.format(self.view['attr'][1]): self.view['attr'][2]})
            qs_filters &= ~Q(report__cache=None)

        if 'hidden' in self.view and 'unchanged' in self.view['hidden']:
            if self.model == UnknownMarkAssociationChanges:
                qs_filters &= ~Q(problems_new=F('problems_old'))
            elif self.model == UnsafeMarkAssociationChanges:
                qs_filters &= ~Q(verdict_new=F('verdict_old'), tags_new=F('tags_old'), status_new=F('status_old'))
            else:
                qs_filters &= ~Q(verdict_new=F('verdict_old'), tags_new=F('tags_old'))

        selected_columns = set(self.view['columns'])
        if 'change_kind' in selected_columns:
            select_only.append('kind')
        if 'decision' in selected_columns:
            select_only.extend(['decision__id', 'decision__title', 'decision__start_date'])
        if 'sum_verdict' in selected_columns:
            select_only.extend(['verdict_old', 'verdict_new'])
        if 'sum_status' in selected_columns:
            select_only.extend(['status_old', 'status_new'])
        if 'tags' in selected_columns:
            select_only.extend(['tags_old', 'tags_new'])
        if 'problems' in selected_columns:
            select_only.extend(['problems_old', 'problems_new'])

        queryset = self.model.objects
        if annotations:
            queryset = queryset.annotate(**annotations)
        queryset = queryset.filter(qs_filters).select_related(*select_related)
        return queryset.only(*select_only)

    def __get_values(self):
        queryset = self.get_queryset()
        columns = ['report']
        columns.extend(self.view['columns'])

        # Get attributes columns and values
        attributes = {}
        attrs_qs = ReportAttr.objects.filter(
            report_id__in=list(cache_obj.report_id for cache_obj in queryset)
        ).order_by('id')
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
                    # reports:safe, reports:unsafe, reports:unknown
                    href = reverse('reports:%s' % self.type, args=[
                        cache_obj.decision.identifier, cache_obj.report.identifier
                    ])
                elif col == 'sum_verdict':
                    html = self.get_sum_verdict(cache_obj)
                elif col == 'sum_status':
                    html = self.get_sum_status(cache_obj)
                elif col == 'change_kind':
                    html = self.__get_kind_html(cache_obj)
                elif col == 'decision':
                    val = cache_obj.decision.name
                    href = reverse('jobs:decision', args=[cache_obj.decision.id])
                elif col == 'tags':
                    html = self.__get_tags(cache_obj.tags_old, cache_obj.tags_new)
                elif col == 'problems':
                    html = self.__get_problems(cache_obj.problems_old, cache_obj.problems_new)
                values_str.append({'value': str(val), 'href': href, 'html': html})
            values.append(values_str)
        return columns, values


class SafeAssChanges(AssChangesBase):
    model = SafeMarkAssociationChanges
    verdicts = SAFE_VERDICTS
    supported_columns = ['change_kind', 'decision', 'sum_verdict', 'tags']
    report_cache_table = 'cache_safe'

    def get_verdict_html(self, verdict, text):
        color = safe_color(verdict)
        if color:
            return '<span style="color: {color};">{text}</span>'.format(color=color, text=text)
        return '<span>{text}</span>'.format(text=text)


class UnsafeAssChanges(AssChangesBase):
    model = UnsafeMarkAssociationChanges
    verdicts = UNSAFE_VERDICTS
    supported_columns = ['change_kind', 'decision', 'sum_verdict', 'sum_status', 'tags']
    report_cache_table = 'cache_unsafe'

    def get_verdict_html(self, verdict, text):
        color = unsafe_color(verdict)
        if color:
            return '<span style="color: {color};">{text}</span>'.format(color=color, text=text)
        return '<span>{text}</span>'.format(text=text)


class UnknownAssChanges(AssChangesBase):
    model = UnknownMarkAssociationChanges
    supported_columns = ['change_kind', 'decision', 'problems']
    report_cache_table = 'cache_unknown'

    def get_verdict_html(self, *args):
        return '-'
