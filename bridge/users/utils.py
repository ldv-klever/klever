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
from datetime import date

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.template import Template, Context
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.functional import cached_property

from bridge.vars import DATAFORMAT
from bridge.utils import BridgeException

from users.models import DataView, PreferableView, User


DEF_NUMBER_OF_ELEMENTS = 18

JOB_TREE_VIEW = {
    'columns': ['role', 'author', 'creation_date', 'status', 'unsafe:total', 'problem:total', 'safe:total'],
    # jobs_order: [up|down, name|creation_date]
    # decisions_order: [up|down, start_date|finish_date]
    'jobs_order': ['up', 'creation_date'],
    'decisions_order': ['up', 'start_date'],

    # FILTERS:
    # hidden: list with values: 'without_decision', 'detailed_verdicts'
    # title: [iexact|istartswith|icontains, <any text>]
    # author: [is|isnot, <id from User model>]
    # creation_date: [gt|lt, <int number>, weeks|days|hours|minutes]
    # status: <list of identifiers from DECISION_STATUS>
    # resource_component: [iexact|istartswith|icontains, <any text>]
    # problem_component: [iexact|istartswith|icontains, <any text>]
    # priority: [le|e|me, <identifier from PRIORITY>]
    # finish_date: [is|older|younger, <month number>, <year>]

    # EXAMPLES:
    # 'hidden': ['without_decision']
    # 'title': ['istartswith', 'Title of the job'],
    # 'author': ['is', '1'],
    # 'creation_date': ['gt', '2', 'weeks'],
    # 'status': ['2', '5', '1'],
    # 'resource_component': ['istartswith', 'D'],
    # 'problem_component': ['iexact', 'BLAST'],
    # 'priority': ['me', 'LOW'],
    # 'finish_date': ['is', '1', '2016'],
    # 'hidden': ['detailed_verdicts']
}

JOB_DATA_VIEW = {
    'data': ['unsafes', 'safes', 'unknowns', 'resources', 'tags_safe', 'tags_unsafe', 'attr_stat'],
    # 'hidden': ['unknowns_nomark', 'unknowns_total', 'resource_total', 'detailed_verdicts'],
    'attr_stat': ['Requirements specification']

    # FILTERS:
    # unknown_component: [iexact|istartswith|icontains, <any text>]
    # unknown_problem: [iexact|istartswith|icontains, <any text>]
    # resource_component: [iexact|istartswith|icontains, <any text>]
    # attr_stat_filter: [iexact|istartswith|icontains, <any text>]
}

REPORT_CHILDREN_VIEW = {
    'elements': [DEF_NUMBER_OF_ELEMENTS],
    # order: [down|up, attr|component|date, <attribute name in case of attr or any>]
    'order': ['down', 'component', ''],

    # FILTERS:
    # component: [<iexact|istartswith|icontains>, <any string>]
    # attr: [<attribute name separated by ':'>, <iexact|istartswith>, <any string>]

    # EXAMPLES:
    # 'component': ['istartswith', 'v'],
    # 'attr': ['LKVOG strategy:Name', 'istartswith', 'Separate']
}

UNSAFES_VIEW = {
    'elements': [DEF_NUMBER_OF_ELEMENTS],
    'columns': [
        'marks_number', 'report_verdict', 'report_status', 'tags',
        'verifier:cpu', 'verifier:wall', 'verifier:memory'
    ],
    # order: [up|down, attr|parent_cpu|parent_wall|parent_memory, <any text, not empty for attr only>]
    # 'order': ['down', 'attr', 'Requirement'],
    # 'attr': ['LKVOG strategy:Name', 'istartswith', 'Separate']
    # 'verdict': [<ids from UNSAFE_VERDICTS>]
    # 'hidden': ['confirmed_marks']
    # 'marks_number': [confirmed|total, iexact|lte|gte, <positive integer number>]
    # 'parent_cpu': [lt|gt, <number>, m|s|ms]
    # 'parent_wall': [lt|gt, <number>, m|s|ms]
    # 'parent_memory': [lt|gt, <number>, b|Kb|Mb|Gb]
}

SAFES_VIEW = {
    'columns': ['marks_number', 'report_verdict', 'tags', 'verifier:cpu', 'verifier:wall', 'verifier:memory'],
    'elements': [DEF_NUMBER_OF_ELEMENTS],
    # order: [up|down, attr|parent_cpu|parent_wall|parent_memory, <any text, not empty for attr only>]
    # 'order': ['down', 'attr', 'Requirement'],
    # 'attr': ['LKVOG strategy:Name', 'istartswith', 'Separate']
    # 'verdict': [<ids from SAFE_VERDICTS>]
    # 'hidden': ['confirmed_marks']
    # 'marks_number': [confirmed|total, iexact|lte|gte, <positive integer number>]
    # 'parent_cpu': [lt|gt, <number>, m|s|ms]
    # 'parent_wall': [lt|gt, <number>, m|s|ms]
    # 'parent_memory': [lt|gt, <number>, b|Kb|Mb|Gb]
}

UNKNOWNS_VIEW = {
    'columns': ['component', 'marks_number', 'problems', 'verifier:cpu', 'verifier:wall', 'verifier:memory'],
    'elements': [DEF_NUMBER_OF_ELEMENTS],
    # order: [up|down, component|attr|parent_cpu|parent_wall|parent_memory, <any text, not empty for attr only>]
    'order': ['down', 'component', ''],
    # 'component': ['istartswith', 'v'],
    # 'attr': ['LKVOG strategy:Name', 'istartswith', 'Separate']
    # 'marks_number': [confirmed|total, iexact|lte|gte, <positive integer number>]
    # 'parent_cpu': [lt|gt, <number>, m|s|ms]
    # 'parent_wall': [lt|gt, <number>, m|s|ms]
    # 'parent_memory': [lt|gt, <number>, b|Kb|Mb|Gb]
    # 'problem': [<problem name>]
}

UNSAFE_MARKS_VIEW = {
    'elements': [DEF_NUMBER_OF_ELEMENTS],
    'columns': ['num_of_links', 'verdict', 'threshold', 'tags', 'status', 'author'],
    # order: [up|down, change_date|num_of_links|attr, <any text, empty if not attr>]
    'order': ['up', 'change_date', ''],

    # FILTERS:
    # identifier: [<mark identifier>]
    # status: [<ids from MARK_STATUS>]
    # verdict: [<ids from MARK_UNSAFE>]
    # author: [<author id>]
    # source: [<ids from MARK_SOURCE>]
    # attr: [<Attr name>, iexact|istartswith|iendswith|icontains, <Attr value>]
    # change_date: [younger|older, <int number>, weeks|days|hours|minutes]

    # EXAMPLES:
    # 'status': ['0'],
    # 'verdict': ['0'],
    # 'author': [1]
    # 'source': ['2'],
    # 'attr': ['Requirement', 'iexact', 'linux:mutex'],
}

SAFE_MARKS_VIEW = {
    'elements': [DEF_NUMBER_OF_ELEMENTS],
    'columns': ['num_of_links', 'verdict', 'tags', 'author'],
    # order: [up|down, change_date|num_of_links|attr, <any text, empty if not attr>]
    'order': ['up', 'change_date', ''],

    # FILTERS:
    # identifier: [<mark identifier>]
    # verdict: [<ids from MARK_SAFE>]
    # author: [<author id>]
    # source: [<ids from MARK_SOURCE>]
    # attr: [<Attr name>, iexact|istartswith|iendswith|icontains, <Attr value>]
    # change_date: [younger|older, <int number>, weeks|days|hours|minutes]

    # EXAMPLES:
    # 'verdict': ['0'],
    # 'author': [1]
    # 'source': ['2'],
    # 'attr': ['Requirement', 'iexact', 'linux:mutex'],
}

UNKNOWN_MARKS_VIEW = {
    'elements': [DEF_NUMBER_OF_ELEMENTS],
    'columns': ['num_of_links', 'component', 'author', 'problem_pattern'],
    # order: [up|down, change_date|num_of_links|attr|component, <any text, empty if not attr>]
    'order': ['up', 'change_date'],

    # FILTERS:
    # identifier: [<mark identifier>]
    # component: [iexact|istartswith, <any text>]
    # author: [<author id>]
    # source: [<ids from MARK_SOURCE>]
    # attr: [<Attr name>, iexact|istartswith|iendswith|icontains, <Attr value>]
    # change_date: [younger|older, <int number>, weeks|days|hours|minutes]

    # EXAMPLES:
    # 'component': ['istartswith', 'Com'],
    # 'author': [1]
    # 'source': ['2'],
}

UNSAFE_ASS_MARKS_VIEW = {
    'columns': ['verdict', 'similarity', 'status', 'tags', 'ass_author', 'description'],

    # FILTERS:
    # verdict: <list of identifiers from MARK_UNSAFE>
    # similarity: [exact|lt|gt, "<integer>"]
    # status: <list of identifiers from MARK_STATUS>
    # ass_type: <list of identifiers from ASSOCIATION_TYPE>
    # associated: <list with any value>

    # EXAMPLES:
    # 'verdict': ['0', '2'],
    # 'similarity': ['0'],
    # 'status': ['1'],
    # 'ass_type': ['0', '1'],
    # 'associated': [True]
}

SAFE_ASS_MARKS_VIEW = {
    'columns': ['verdict', 'tags', 'ass_author', 'description'],

    # FILTERS:
    # verdict: <list of identifiers from MARK_UNSAFE>
    # ass_type: <list of identifiers from ASSOCIATION_TYPE>
    # associated: <list with any value>

    # EXAMPLES:
    # 'verdict': ['0', '2'],
    # 'ass_type': ['0', '1'],
    # 'associated': [True]
}

UNKNOWN_ASS_MARKS_VIEW = {
    'columns': ['ass_author', 'description'],

    # FILTERS:
    # ass_type: <list of identifiers from ASSOCIATION_TYPE>
    # associated: <list with any value>

    # EXAMPLES:
    # 'ass_type': ['0', '1'],
    # 'associated': [True]
}

UNSAFE_MARK_ASS_REPORTS_VIEW = {
    'elements': [DEF_NUMBER_OF_ELEMENTS],
    'columns': ['decision', 'similarity', 'associated', 'ass_type', 'ass_author', 'likes'],

    # FILTERS:
    # similarity: [exact|lt|gt, "<integer>"]
    # ass_type: <list of identifiers from ASSOCIATION_TYPE>
    # associated: <list with any value>

    # EXAMPLES:
    # 'similarity': ['gt', '30'],
    # 'ass_type': ['0', '1'],
    # 'associated': [True]
}

SAFE_MARK_ASS_REPORTS_VIEW = {
    'elements': [DEF_NUMBER_OF_ELEMENTS],
    'columns': ['decision', 'associated', 'ass_type', 'ass_author', 'likes'],

    # FILTERS:
    # ass_type: <list of identifiers from ASSOCIATION_TYPE>
    # associated: <list with any value>

    # EXAMPLES:
    # 'ass_type': ['0', '1'],
    # 'associated': [True]
}

UNKNOWN_MARK_ASS_REPORTS_VIEW = {
    'elements': [DEF_NUMBER_OF_ELEMENTS],
    'columns': ['decision', 'associated', 'ass_type', 'ass_author', 'likes'],

    # FILTERS:
    # ass_type: <list of identifiers from ASSOCIATION_TYPE>
    # associated: <list with any value>

    # EXAMPLES:
    # 'ass_type': ['0', '1'],
    # 'associated': [True]
}

SAFE_ASSOCIATION_CHANGES_VIEW = {
    'columns': ['change_kind', 'sum_verdict', 'tags', 'decision'],
    # FILTERS:
    'hidden': ['unchanged']
    # change_kind: <sublist from ['changed', 'new', 'deleted']>
    # old_verdict: <list of identifiers from SAFE_VERDICTS>
    # new_verdict: <list of identifiers from SAFE_VERDICTS>
    # decision_title: [iexact|istartswith|icontains, <any text>]
    # attr: [<Attr name>, iexact|istartswith, <Attr value>]
}
UNSAFE_ASSOCIATION_CHANGES_VIEW = {
    'columns': ['change_kind', 'sum_verdict', 'sum_status', 'tags', 'decision'],
    # FILTERS:
    'hidden': ['unchanged']
    # change_kind: <sublist from ['changed', 'new', 'deleted']>
    # old_verdict: <list of identifiers from UNSAFE_VERDICTS>
    # new_verdict: <list of identifiers from UNSAFE_VERDICTS>
    # decision_title: [iexact|istartswith|icontains, <any text>]
    # attr: [<Attr name>, iexact|istartswith, <Attr value>]
}
UNKNOWN_ASSOCIATION_CHANGES_VIEW = {
    'columns': ['change_kind', 'decision', 'problems'],
    # FILTERS:
    # change_kind: <sublist from ['changed', 'new', 'deleted']>
    # decision_title: [iexact|istartswith|icontains, <any text>]
    # attr: [<Attr name>, iexact|istartswith, <Attr value>]
}

DEFAULT_VIEW = {
    '1': JOB_TREE_VIEW,
    '2': JOB_DATA_VIEW,
    '3': REPORT_CHILDREN_VIEW,
    '4': UNSAFES_VIEW,
    '5': SAFES_VIEW,
    '6': UNKNOWNS_VIEW,
    '7': UNSAFE_MARKS_VIEW,
    '8': SAFE_MARKS_VIEW,
    '9': UNKNOWN_MARKS_VIEW,
    '10': UNSAFE_ASS_MARKS_VIEW,
    '11': SAFE_ASS_MARKS_VIEW,
    '12': UNKNOWN_ASS_MARKS_VIEW,
    '13': UNSAFE_MARK_ASS_REPORTS_VIEW,
    '14': SAFE_MARK_ASS_REPORTS_VIEW,
    '15': UNKNOWN_MARK_ASS_REPORTS_VIEW,
    '16': SAFE_ASSOCIATION_CHANGES_VIEW,
    '17': UNSAFE_ASSOCIATION_CHANGES_VIEW,
    '18': UNKNOWN_ASSOCIATION_CHANGES_VIEW
}


class ViewData:
    def __init__(self, user, view_type, request_args):
        self.user = user
        self._type = view_type[0]
        self._template = self.__get_template(view_type[1])
        self._title = _('View')
        self._unsaved = False
        self._view, self._view_id = self.__get_view(request_args)

    def __contains__(self, item):
        return item in self._view

    def __getitem__(self, item):
        if item == 'type':
            return self._type
        elif item == 'template':
            return self._template
        elif item == 'viewtitle':
            return self._title
        elif item == 'views':
            return self._views
        elif item == 'view_id':
            return self._view_id
        elif item == 'is_unsaved':
            return self._unsaved
        return self._view.get(item)

    def __get_template(self, view_name):
        return 'users/views/{0}.html'.format(view_name)

    @cached_property
    def _views(self):
        qs_filters = Q(type=self._type) & (Q(author=self.user) | Q(shared=True))
        return DataView.objects.filter(qs_filters).select_related('author').order_by('name')

    def __get_view(self, request_args):
        if request_args.get('view_type') != self._type:
            # Try to get preferable view
            pref_view = PreferableView.objects.filter(view__type=self._type, user=self.user) \
                .select_related('view').first()
            if pref_view:
                self._title = '{0} ({1})'.format(self._title, pref_view.view.name)
                return pref_view.view.view, pref_view.view_id
        elif request_args.get('view'):
            # Try to get view from query params
            self._title = '{0} ({1})'.format(self._title, _('unsaved'))
            self._unsaved = True
            return json.loads(request_args['view']), None
        elif request_args.get('view_id'):
            # If view_id is provided and it is not the default
            if request_args['view_id'] != 'default':
                user_view = DataView.objects.filter(
                    Q(id=int(request_args['view_id']), type=self._type) & (Q(shared=True) | Q(author=self.user))
                ).first()
                if user_view:
                    self._title = '{0} ({1})'.format(self._title, user_view.name)
                    return user_view.view, user_view.id

        # Return default view
        self._title = '{0} ({1})'.format(self._title, _('Default'))
        return DEFAULT_VIEW[self._type], 'default'


class HumanizedValue:
    measures = {
        'time': {
            'default': _('ms'),
            'humanized': ((1000, _('s')), (60, _('min')), (60, _('h')))
        },
        'memory': {
            'default': _('B'),
            'humanized': ((1000, _('KB')), (1000, _('MB')), (1000, _('GB')))
        }
    }

    def __init__(self, value, user=None, default='-'):
        self.initial_value = value
        self.default = default
        self.user = user

    @cached_property
    def humanized(self):
        return isinstance(self.user, User) and self.user.data_format == DATAFORMAT[1][0]

    @property
    def date(self):
        # datetime is subclass of date
        if not isinstance(self.initial_value, date):
            return self.default

        # Get template for the date
        return self.get_templated_text(
            '{%% load humanize %%}{{ date|%s }}' % ('naturaltime' if self.humanized else 'date:"r"'),
            date=self.initial_value
        )

    @property
    def timedelta(self):
        # value is milliseconds
        if not isinstance(self.initial_value, int):
            return self.default

        value, postfix = self.__value_with_postfix('time')
        return self.get_templated_text(
            '{% load l10n %}{{ value }} {{ postfix }}', value=value, postfix=postfix
        )

    @property
    def memory(self):
        # value is bytes
        if not isinstance(self.initial_value, int):
            return self.default

        value, postfix = self.__value_with_postfix('memory')
        return self.get_templated_text(
            '{% load l10n %}{{ value }} {{ postfix }}', value=value, postfix=postfix
        )

    @property
    def float(self):
        if isinstance(self.initial_value, int):
            self.initial_value = float(self.initial_value)
        elif not isinstance(self.initial_value, float):
            return self.default
        return str(self.__round_float(self.initial_value))

    def __round_float(self, value):
        if not self.humanized:
            return value
        accuracy = int(self.user.accuracy)
        fpart_len = len(str(round(value)))
        if fpart_len > accuracy:
            tmp_div = 10 ** (fpart_len - accuracy)
            return round(value / tmp_div) * tmp_div
        if fpart_len < accuracy:
            return round(value, accuracy - fpart_len)
        return round(value)

    def __value_with_postfix(self, value_type):
        value = self.initial_value
        if value_type not in self.measures:
            return value, ''

        postfix = self.measures[value_type]['default']

        if not self.humanized:
            # Return initial_value with default postfix
            return value, postfix

        for m, p in self.measures[value_type]['humanized']:
            new_value = value / m
            if new_value < 1:
                break
            postfix = p
            value = new_value
        value = self.__round_float(value)
        return value, postfix

    @classmethod
    def get_templated_text(cls, template, **kwargs):
        return Template(template).render(Context(kwargs))


class UserActionsHistory:
    def __init__(self, user, author):
        self.user = user
        self.author = author
        self.activity = self.get_activity()

    def get_activity(self):
        activity = self.get_safe_marks_activity()
        activity.extend(self.get_unsafe_marks_activity())
        activity.extend(self.get_unknowns_marks_activity())
        activity = sorted(activity, key=lambda x: x['date'], reverse=True)
        return activity[:50]

    def get_safe_marks_activity(self):
        from marks.models import MarkSafeHistory

        versions_qs = MarkSafeHistory.objects.filter(author=self.author)\
            .select_related('mark').order_by('-change_date')\
            .only('id', 'change_date', 'comment', 'mark__identifier', 'version', 'mark_id')

        marks_activity = []
        for act in versions_qs[:30]:
            comment_display = act.comment
            if len(comment_display) > 50:
                comment_display = comment_display[:47] + '...'
            marks_activity.append({
                'date': act.change_date,
                'comment': act.comment,
                'comment_display': comment_display,
                'action': 'create' if act.version == 1 else 'change',
                'type': _('Safes mark'),
                'name': str(act.mark.identifier),
                'href': reverse('marks:safe', args=[act.mark_id]),
            })
        return marks_activity

    def get_unsafe_marks_activity(self):
        from marks.models import MarkUnsafeHistory

        versions_qs = MarkUnsafeHistory.objects.filter(author=self.author)\
            .select_related('mark').order_by('-change_date')\
            .only('id', 'change_date', 'comment', 'mark__identifier', 'version', 'mark_id')

        marks_activity = []
        for act in versions_qs[:30]:
            comment_display = act.comment
            if len(comment_display) > 50:
                comment_display = comment_display[:47] + '...'
            marks_activity.append({
                'date': act.change_date,
                'comment': act.comment,
                'comment_display': comment_display,
                'action': 'create' if act.version == 1 else 'change',
                'type': _('Unsafes mark'),
                'name': str(act.mark.identifier),
                'href': reverse('marks:unsafe', args=[act.mark_id]),
            })
        return marks_activity

    def get_unknowns_marks_activity(self):
        from marks.models import MarkUnknownHistory

        versions_qs = MarkUnknownHistory.objects.filter(author=self.author)\
            .select_related('mark').order_by('-change_date')\
            .only('id', 'change_date', 'comment', 'mark__identifier', 'version', 'mark_id')

        marks_activity = []
        for act in versions_qs[:30]:
            comment_display = act.comment
            if len(comment_display) > 50:
                comment_display = comment_display[:47] + '...'
            marks_activity.append({
                'date': act.change_date,
                'comment': act.comment,
                'comment_display': comment_display,
                'action': 'create' if act.version == 1 else 'change',
                'type': _('Unknowns mark'),
                'name': str(act.mark.identifier),
                'href': reverse('marks:unknown', args=[act.mark_id]),
            })
        return marks_activity


def paginate_queryset(queryset, page, num_per_page=None):
    num_per_page = max(int(num_per_page), 1) if num_per_page else DEF_NUMBER_OF_ELEMENTS

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
