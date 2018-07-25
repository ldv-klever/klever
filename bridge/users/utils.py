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

from django.db.models import Q
from django.utils.translation import ugettext_lazy as _, string_concat

from users.models import View


DEF_NUMBER_OF_ELEMENTS = 18

JOB_TREE_VIEW = {
    'columns': ['name', 'role', 'author', 'date', 'status', 'unsafe:total', 'problem:total', 'safe:total'],
    # order: [up|down, title|date|start|finish]
    'order': ['up', 'date'],

    # FILTERS:
    # title: [iexact|istartswith|icontains, <any text>]
    # change_author: [is|isnot, <id from User model>]
    # change_date: [younger|older, <int number>, weeks|days|hours|minutes]
    # status: <list of identifiers from JOB_STATUS>
    # resource_component: [iexact|istartswith|icontains, <any text>]
    # problem_component: [iexact|istartswith|icontains, <any text>]
    # problem_problem: [iexact|istartswith|icontains, <any text>]
    # format: [is|isnot, <number>]
    # priority: [le|e|me, <identifier from PRIORITY>]
    # finish_date: [is|older|younger, <month number>, <year>]

    # EXAMPLES:
    # 'title': ['istartswith', 'Title of the job'],
    # 'change_author': ['is', '1'],
    # 'change_date': ['younger', '2', 'weeks'],
    # 'status': ['2', '5', '1'],
    # 'resource_component': ['istartswith', 'D'],
    # 'problem_component': ['iexact', 'BLAST'],
    # 'problem_problem': ['icontains', '1'],
    # 'format': ['is', '1'],
    # 'priority': ['me', 'LOW'],
    # 'finish_date': ['is', '1', '2016'],
    # 'hidden': ['confirmed_marks']
}

JOB_DATA_VIEW = {
    'data': [
        'unsafes', 'safes', 'unknowns', 'resources', 'tags_safe', 'tags_unsafe',
        'safes_attr_stat', 'unsafes_attr_stat', 'unknowns_attr_stat'
    ],
    # 'hidden': ['unknowns_nomark', 'unknowns_total', 'resource_total', 'confirmed_marks'],
    'attr_stat': ['Rule specification']

    # FILTERS:
    # unknown_component: [iexact|istartswith|icontains, <any text>]
    # unknown_problem: [iexact|istartswith|icontains, <any text>]
    # resource_component: [iexact|istartswith|icontains, <any text>]
    # compinst: [iexact|istartswith|icontains, <any text>]
    # safe_tag: [iexact|istartswith|icontains, <any text>]
    # unsafe_tag: [iexact|istartswith|icontains, <any text>]
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
    'columns': ['marks_number', 'report_verdict', 'tags', 'verifiers:cpu', 'verifiers:wall', 'verifiers:memory'],
    # order: [up|down, attr|parent_cpu|parent_wall|parent_memory, <any text, not empty for attr only>]
    # 'order': ['down', 'attr', 'Rule specification'],
    # 'attr': ['LKVOG strategy:Name', 'istartswith', 'Separate']
    # 'verdict': [<ids from UNSAFE_VERDICTS>]
    # 'hidden': ['confirmed_marks']
    # 'marks_number': [confirmed|total, iexact|lte|gte, <positive integer number>]
    # 'tags': [<string of tags separated with ';'>]
    # 'parent_cpu': [lt|gt, <number>, m|s|ms]
    # 'parent_wall': [lt|gt, <number>, m|s|ms]
    # 'parent_memory': [lt|gt, <number>, b|Kb|Mb|Gb]
}

SAFES_VIEW = {
    'columns': ['marks_number', 'report_verdict', 'tags', 'verifiers:cpu', 'verifiers:wall', 'verifiers:memory'],
    'elements': [DEF_NUMBER_OF_ELEMENTS],
    # order: [up|down, attr|parent_cpu|parent_wall|parent_memory, <any text, not empty for attr only>]
    # 'order': ['down', 'attr', 'Rule specification'],
    # 'attr': ['LKVOG strategy:Name', 'istartswith', 'Separate']
    # 'verdict': [<ids from SAFE_VERDICTS>]
    # 'hidden': ['confirmed_marks']
    # 'marks_number': [confirmed|total, iexact|lte|gte, <positive integer number>]
    # 'tags': [<string of tags separated with ';'>]
    # 'parent_cpu': [lt|gt, <number>, m|s|ms]
    # 'parent_wall': [lt|gt, <number>, m|s|ms]
    # 'parent_memory': [lt|gt, <number>, b|Kb|Mb|Gb]
}

UNKNOWNS_VIEW = {
    'columns': ['component', 'marks_number', 'problems', 'verifiers:cpu', 'verifiers:wall', 'verifiers:memory'],
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
    'columns': ['num_of_links', 'verdict', 'tags', 'status', 'author', 'format'],
    # order: [up|down, change_date|num_of_links|attr, <any text, empty if not attr>]
    'order': ['up', 'change_date', ''],

    # FILTERS:
    # status: [is|isnot, <id from MARK_STATUS>]
    # verdict: [is|isnot, <id from MARK_UNSAFE>]
    # author: [<author id>]
    # source: [is|isnot, <id from MARK_TYPE>]
    # attr: [<Attr name>, iexact|istartswith, <Attr value>]
    # change_date: [younger|older, <int number>, weeks|days|hours|minutes]

    # EXAMPLES:
    # 'status': ['is', '0'],
    # 'verdict': ['is', '0'],
    # 'author': [1]
    # 'source': ['is', '2'],
    # 'attr': ['Rule specification', 'iexact', 'linux:mutex'],
}

SAFE_MARKS_VIEW = {
    'elements': [DEF_NUMBER_OF_ELEMENTS],
    'columns': ['num_of_links', 'verdict', 'tags', 'status', 'author', 'format'],
    # order: [up|down, change_date|num_of_links|attr, <any text, empty if not attr>]
    'order': ['up', 'change_date', ''],

    # FILTERS:
    # status: [is|isnot, <id from MARK_STATUS>]
    # verdict: [is|isnot, <id from MARK_SAFE>]
    # author: [<author id>]
    # source: [is|isnot, <id from MARK_TYPE>]
    # attr: [<Attr name>, iexact|istartswith, <Attr value>]
    # change_date: [younger|older, <int number>, weeks|days|hours|minutes]

    # EXAMPLES:
    # 'status': ['is', '0'],
    # 'verdict': ['is', '0'],
    # 'author': [1]
    # 'source': ['is', '2'],
    # 'attr': ['Rule specification', 'iexact', 'linux:mutex'],
}

UNKNOWN_MARKS_VIEW = {
    'elements': [DEF_NUMBER_OF_ELEMENTS],
    'columns': ['num_of_links', 'status', 'component', 'author', 'format', 'pattern'],
    # order: [up|down, change_date|num_of_links|attr, <any text, empty if not attr>]
    'order': ['up', 'change_date'],

    # FILTERS:
    # status: [is|isnot, <id from MARK_STATUS>]
    # component: [is|startswith, <any text>]
    # author: [<author id>]
    # source: [is|isnot, <id from MARK_TYPE>]
    # attr: [<Attr name>, iexact|istartswith, <Attr value>]
    # change_date: [younger|older, <int number>, weeks|days|hours|minutes]

    # EXAMPLES:
    # 'status': ['is', '0'],
    # 'component': ['startswith', '0'],
    # 'author': [1]
    # 'source': ['is', '2'],
}

UNSAFE_ASS_MARKS_VIEW = {
    'columns': ['verdict', 'similarity', 'status', 'source', 'tags', 'ass_type', 'ass_author', 'description'],

    # FILTERS:
    # verdict: <list of identifiers from MARK_UNSAFE>
    # similarity: <sublist from ['0', '50', '100']>
    # status: <list of identifiers from MARK_STATUS>
    # ass_type: <list of identifiers from ASSOCIATION_TYPE>

    # EXAMPLES:
    # 'verdict': ['0', '2'],
    'similarity': ['50', '100'],
    # 'status': ['1'],
    # 'ass_type': ['0', '1'],
}

SAFE_ASS_MARKS_VIEW = {
    'columns': ['verdict', 'status', 'source', 'tags', 'ass_type', 'ass_author', 'description'],

    # FILTERS:
    # verdict: <list of identifiers from MARK_UNSAFE>
    # status: <list of identifiers from MARK_STATUS>
    # ass_type: <list of identifiers from ASSOCIATION_TYPE>

    # EXAMPLES:
    # 'verdict': ['0', '2'],
    # 'status': ['1'],
    # 'ass_type': ['0', '1'],
}

UNKNOWN_ASS_MARKS_VIEW = {
    'columns': ['status', 'source', 'ass_type', 'ass_author', 'description'],

    # FILTERS:
    # status: <list of identifiers from MARK_STATUS>
    # ass_type: <list of identifiers from ASSOCIATION_TYPE>

    # EXAMPLES:
    # 'status': ['1'],
    # 'ass_type': ['0', '1'],
}

UNSAFE_MARK_ASS_REPORTS_VIEW = {
    'elements': [DEF_NUMBER_OF_ELEMENTS],
    'columns': ['job', 'similarity', 'ass_type', 'ass_author', 'likes'],

    # FILTERS:
    # similarity: <sublist from ['0', '50', '100']>
    # ass_type: <list of identifiers from ASSOCIATION_TYPE>

    # EXAMPLES:
    'similarity': ['50', '100'],
    # 'ass_type': ['0', '1'],
}

SAFE_MARK_ASS_REPORTS_VIEW = {
    'elements': [DEF_NUMBER_OF_ELEMENTS],
    'columns': ['job', 'ass_type', 'ass_author', 'likes'],

    # FILTERS:
    # ass_type: <list of identifiers from ASSOCIATION_TYPE>

    # EXAMPLES:
    # 'ass_type': ['0', '1'],
}

UNKNOWN_MARK_ASS_REPORTS_VIEW = {
    'elements': [DEF_NUMBER_OF_ELEMENTS],
    'columns': ['job', 'ass_type', 'ass_author', 'likes'],

    # FILTERS:
    # ass_type: <list of identifiers from ASSOCIATION_TYPE>

    # EXAMPLES:
    # 'ass_type': ['0', '1'],
}

SAFE_ASSOCIATION_CHANGES_VIEW = {
    'columns': ['change_kind', 'sum_verdict', 'tags', 'job', 'format'],
    # FILTERS:
    'hidden': ['unchanged']
    # change_kind: <sublist from ['changed', 'new', 'deleted']>
    # old_verdict: <list of identifiers from SAFE_VERDICTS>
    # new_verdict: <list of identifiers from SAFE_VERDICTS>
    # job_title: [iexact|istartswith|icontains, <any text>]
    # format: [is|isnot, <number>]
    # attr: [<Attr name>, iexact|istartswith, <Attr value>]
}
UNSAFE_ASSOCIATION_CHANGES_VIEW = {
    'columns': ['change_kind', 'sum_verdict', 'tags', 'job', 'format'],
    # FILTERS:
    'hidden': ['unchanged']
    # change_kind: <sublist from ['changed', 'new', 'deleted']>
    # old_verdict: <list of identifiers from UNSAFE_VERDICTS>
    # new_verdict: <list of identifiers from UNSAFE_VERDICTS>
    # job_title: [iexact|istartswith|icontains, <any text>]
    # format: [is|isnot, <number>]
    # attr: [<Attr name>, iexact|istartswith, <Attr value>]
}
UNKNOWN_ASSOCIATION_CHANGES_VIEW = {
    'columns': ['change_kind', 'job', 'format', 'problems'],
    # FILTERS:
    # change_kind: <sublist from ['changed', 'new', 'deleted']>
    # job_title: [iexact|istartswith|icontains, <any text>]
    # format: [is|isnot, <number>]
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
        self._title = ''
        self._views = self.__views()
        self._view = None
        self._view_id = None
        self.__get_args(request_args)
        self.__get_view()

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
        return self._view.get(item)

    def __get_template(self, view_name):
        return 'users/views/{0}.html'.format(view_name)

    def __get_args(self, request_args):
        if request_args.get('view_type') == self._type:
            self._view = request_args.get('view')
            self._view_id = request_args.get('view_id')

    def __views(self):
        return View.objects.filter(Q(type=self._type) & (Q(author=self.user) | Q(shared=True))).order_by('name')

    def __get_view(self):
        if self._view is not None:
            self._title = string_concat(_('View'), ' (', _('unsaved'), ')')
            self._view = json.loads(self._view)
            return
        if self._view_id is None:
            pref_view = self.user.preferableview_set.filter(view__type=self._type).first()
            if pref_view:
                self._title = string_concat(_('View'), ' (%s)' % pref_view.view.name)
                self._view_id = pref_view.view_id
                self._view = json.loads(pref_view.view.view)
                return
        elif self._view_id != 'default':
            user_view = View.objects.filter(
                Q(id=self._view_id, type=self._type) & (Q(shared=True) | Q(author=self.user))
            ).first()
            if user_view:
                self._title = string_concat(_('View'), ' (%s)' % user_view.name)
                self._view_id = user_view.id
                self._view = json.loads(user_view.view)
                return
        self._title = string_concat(_('View'), ' (', _('Default'), ')')
        self._view_id = 'default'
        self._view = DEFAULT_VIEW[self._type]
