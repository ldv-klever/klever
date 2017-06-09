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

from django.utils.translation import ugettext_lazy as _, pgettext_lazy as __

FORMAT = 1

DATAFORMAT = (
    ('raw', _('Raw')),
    ('hum', _('Human-readable')),
)

# Do not use error code 500 (Unknown error)
ERRORS = {
    301: _('Wrong request method or not enough request arguments'),
    400: _("You don't have an access to this job"),
    404: _('The job was not found'),
    405: _('One of the selected jobs was not found'),
    504: _('The report was not found'),
    505: _("Couldn't visualize the error trace"),
    507: _("You can't compare the selected jobs"),
    604: _("The mark was not found"),
    605: _('The mark is being deleted')
}

LANGUAGES = (
    ('en', 'English'),
    ('ru', 'Русский'),
)

USER_ROLES = (
    ('0', _('No access')),
    ('1', _('Producer')),
    ('2', _('Manager')),
    ('3', _('Expert')),
    ('4', _('Service user'))
)

JOB_CLASSES = (
    ('0', _('Verification of Linux kernel modules')),
    ('3', _('Validation on commits in Linux kernel Git repositories')),
)

COMPARE_VERDICT = (
    ('0', _('Total safe')),
    ('1', _('Found all unsafes')),
    ('2', _('Found not all unsafes')),
    ('3', _('Unknown')),
    ('4', _('Unmatched'))
)

JOB_ROLES = (
    ('0', _('No access')),
    ('1', _('Observer')),
    ('2', _('Expert')),
    ('3', _('Observer and Operator')),
    ('4', _('Expert and Operator')),
)

JOB_STATUS = (
    ('0', _('Not solved')),
    ('1', _('Pending')),
    ('2', _('Is solving')),
    ('3', _('Solved')),
    ('4', _('Failed')),
    ('5', _('Corrupted')),
    ('6', _('Cancelled')),
    ('7', _('Terminated'))
)

JOB_WEIGHT = (
    ('0', _('Full-weight')),
    ('1', _('Lightweight'))
)

MARK_TYPE = (
    ('0', _('Created')),
    ('1', _('Preset')),
    ('2', _('Uploaded')),
)

MARK_STATUS = (
    ('0', _('Unreported')),
    ('1', _('Reported')),
    ('2', _('Fixed')),
    ('3', _('Rejected')),
)

MARK_UNSAFE = (
    ('0', _('Unknown')),
    ('1', _('Bug')),
    ('2', _('Target bug')),
    ('3', _('False positive')),
)

MARK_SAFE = (
    ('0', _('Unknown')),
    ('1', _('Incorrect proof')),
    ('2', _('Missed target bug')),
)

UNSAFE_VERDICTS = (
    ('0', _('Unknown')),
    ('1', _('Bug')),
    ('2', _('Target bug')),
    ('3', _('False positive')),
    ('4', _('Incompatible marks')),
    ('5', _('Without marks')),
)

SAFE_VERDICTS = (
    ('0', _('Unknown')),
    ('1', _('Incorrect proof')),
    ('2', _('Missed target bug')),
    ('3', _('Incompatible marks')),
    ('4', _('Without marks')),
)

DEF_NUMBER_OF_ELEMENTS = 18

VIEW_TYPES = (
    ('0', 'component attributes'),
    ('1', 'job tree'),
    ('2', 'job view'),
    ('3', 'component children list'),
    ('4', 'unsafes list'),
    ('5', 'safes list'),
    ('6', 'unknowns list'),
    ('7', 'unsafe marks'),
    ('8', 'safe marks'),
    ('9', 'unknown marks'),
    ('10', 'unsafe associated marks'),
    ('11', 'safe associated marks'),
    ('12', 'unknown associated marks')
)

JOB_TREE_DEF_VIEW = {
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
}

VIEWJOB_DEF_VIEW = {
    'data': [
        'unsafes', 'safes', 'unknowns', 'resources', 'tags_safe', 'tags_unsafe',
        'safes_attr_stat', 'unsafes_attr_stat', 'unknowns_attr_stat'
    ],
    # 'hidden': ['unknowns_nomark', 'unknowns_total', 'resource_total'],
    'attr_stat': ['Rule specification']

    # FILTERS:
    # unknown_component: [iexact|istartswith|icontains, <any text>]
    # unknown_problem: [iexact|istartswith|icontains, <any text>]
    # resource_component: [iexact|istartswith|icontains, <any text>]
    # safe_tag: [iexact|istartswith|icontains, <any text>]
    # unsafe_tag: [iexact|istartswith|icontains, <any text>]
    # attr_stat_filter: [iexact|istartswith|icontains, <any text>]
}

REPORT_CHILDREN_DEF_VIEW = {
    'elements': [DEF_NUMBER_OF_ELEMENTS],
    # order: [attr|component|date, down|up, <attribute name in case of attr or any>]
    'order': ['component', 'down', ''],

    # FILTERS:
    # component: [<iexact|istartswith|icontains>, <any string>]
    # attr: [<attribute name separated by ':'>, <iexact|istartswith>, <any string>]

    # EXAMPLES:
    # 'component': ['istartswith', 'v'],
    # 'attr': ['LKVOG strategy:Name', 'istartswith', 'Separate']
}

UNSAFE_LIST_DEF_VIEW = {
    'elements': [DEF_NUMBER_OF_ELEMENTS],
    'columns': ['marks_number', 'report_verdict', 'tags', 'parent_cpu'],
    # 'order': ['down', 'Rule specification'],
    # 'attr': ['LKVOG strategy:Name', 'istartswith', 'Separate']
}

SAFE_LIST_DEF_VIEW = {
    'columns': ['marks_number', 'report_verdict', 'tags', 'parent_cpu'],
    'elements': [DEF_NUMBER_OF_ELEMENTS],
    # 'order': ['down', 'Rule specification'],
    # 'attr': ['LKVOG strategy:Name', 'istartswith', 'Separate']
}

UNKNOWN_LIST_DEF_VIEW = {
    'elements': [DEF_NUMBER_OF_ELEMENTS],
    # 'order': ['up', 'Rule specification'],
    # 'component': ['istartswith', 'v'],
    # 'attr': ['LKVOG strategy:Name', 'istartswith', 'Separate']
}

MARKS_SAFE_VIEW = {
    'columns': ['num_of_links', 'verdict', 'tags', 'status', 'author', 'format'],
    # order: [num_of_links|attr, <any text, '' for 'num_of_links' at first index>],
    'order': ['up', 'change_date', ''],

    # FILTERS:
    # status: [is|isnot, <id from MARK_STATUS>]
    # verdict: [is|isnot, <id from UNSAFE_VERDICTS>]
    # author: [<author id>]
    # source: [is|isnot, <id from MARK_TYPE>]
    # attr: [<Attr name>, iexact|istartswith, <Attr value>]

    # EXAMPLES:
    # 'status': ['is', '0'],
    # 'verdict': ['is', '0'],
    # 'author': [1]
    # 'source': ['is', '2'],
    # 'attr': ['Rule specification', 'iexact', 'linux:mutex'],
}

MARKS_UNSAFE_VIEW = {
    'columns': ['num_of_links', 'verdict', 'tags', 'status', 'author', 'format'],
    # order: [num_of_links|attr, <any text, '' for 'num_of_links' at first index>],
    'order': ['up', 'change_date', ''],

    # FILTERS:
    # status: [is|isnot, <id from MARK_STATUS>]
    # verdict: [is|isnot, <id from UNSAFE_VERDICTS>]
    # author: [<author id>]
    # source: [is|isnot, <id from MARK_TYPE>]
    # attr: [<Attr name>, iexact|istartswith, <Attr value>]

    # EXAMPLES:
    # 'status': ['is', '0'],
    # 'verdict': ['is', '0'],
    # 'author': [1]
    # 'source': ['is', '2'],
    # 'attr': ['Rule specification', 'iexact', 'linux:mutex'],
}

MARKS_UNKNOWN_VIEW = {
    'columns': ['num_of_links', 'status', 'component', 'author', 'format', 'pattern'],
    'order': ['up', 'change_date'],

    # FILTERS:
    # status: [is|isnot, <id from MARK_STATUS>]
    # component: [is|startswith, <any text>]
    # author: [<author id>]
    # source: [is|isnot, <id from MARK_TYPE>]

    # EXAMPLES:
    # 'status': ['is', '0'],
    # 'component': ['startswith', '0'],
    # 'author': [1]
    # 'source': ['is', '2'],
}

UNSAFE_MARKS_VIEW = {
    'columns': ['verdict', 'similarity', 'status', 'mark_type', 'tags', 'ass_type', 'ass_author', 'description'],

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

SAFE_MARKS_VIEW = {
    'columns': ['verdict', 'status', 'mark_type', 'tags', 'ass_type', 'ass_author', 'description'],

    # FILTERS:
    # verdict: <list of identifiers from MARK_UNSAFE>
    # status: <list of identifiers from MARK_STATUS>
    # ass_type: <list of identifiers from ASSOCIATION_TYPE>

    # EXAMPLES:
    # 'verdict': ['0', '2'],
    # 'status': ['1'],
    # 'ass_type': ['0', '1'],
}

UNKNOWN_MARKS_VIEW = {
    'columns': ['status', 'mark_type', 'ass_type', 'ass_author', 'description'],

    # FILTERS:
    # status: <list of identifiers from MARK_STATUS>
    # ass_type: <list of identifiers from ASSOCIATION_TYPE>

    # EXAMPLES:
    # 'status': ['1'],
    # 'ass_type': ['0', '1'],
}

SCHEDULER_STATUS = (
    ('HEALTHY', _('Healthy')),
    ('AILING', _('Ailing')),
    ('DISCONNECTED', _('Disconnected'))
)

SCHEDULER_TYPE = (
    ('0', 'Klever'),
    ('1', 'VerifierCloud')
)

PRIORITY = (
    ('URGENT', _('Urgent')),
    ('HIGH', _('High')),
    ('LOW', _('Low')),
    ('IDLE', _('Idle'))
)

NODE_STATUS = (
    ('USER_OCCUPIED', _('User occupied')),
    ('HEALTHY', _('Healthy')),
    ('AILING', _('Ailing')),
    ('DISCONNECTED', _('Disconnected'))
)

TASK_STATUS = (
    ('PENDING', _('Pending')),
    ('PROCESSING', _('Processing')),
    ('FINISHED', __('task status', 'Finished')),
    ('ERROR', _('Error')),
    ('CANCELLED', _('Cancelled'))
)

MARKS_COMPARE_ATTRS = {
    JOB_CLASSES[0][0]: ['Rule specification', 'Verification object'],
    JOB_CLASSES[1][0]: ['Rule specification', 'Verification object'],
}


JOBS_COMPARE_ATTRS = {
    JOB_CLASSES[0][0]: ['Verification object', 'Rule specification'],
    JOB_CLASSES[1][0]: ['Name', 'Verification object', 'Rule specification'],
}

# TODO: keys and values are almost the same and thus can be refactored.
AVTG_PRIORITY = [
    ('balance', _('Balance')),
    ('rule specifications', _('Rule specifications')),
    ('verification objects', _('Verification objects')),
]

KLEVER_CORE_PARALLELISM = (
    ('sequential', _('Sequentially')),
    ('slow', _('Slowly')),
    ('quick', _('Quickly')),
    ('very quick', _('Very quickly'))
)

KLEVER_CORE_FORMATTERS = (
    ('brief', _('Briefly')),
    ('detailed', _('In detail')),
    ('paranoid', _('Paranoidly'))
)

START_JOB_DEFAULT_MODES = {
    'production': _('Production'),
    'development': _('Development'),
    'paranoid development': _('Paranoid development')
}

REPORT_FILES_ARCHIVE = 'data.zip'

# You can set translatable text _("Unknown error")
UNKNOWN_ERROR = 'Unknown error'

ASSOCIATION_TYPE = (
    ('0', _('Automatic')),
    ('1', _('Confirmed')),
    ('2', _('Unconfirmed'))
)
