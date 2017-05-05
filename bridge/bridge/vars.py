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

ATTR_STATISTIC = {
    '0': ['Rule specification'],
    '3': ['Rule specification']
}

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

# Default view of the table
JOB_DEF_VIEW = {
    'columns': ['name', 'role', 'author', 'date', 'status', 'unsafe:total', 'problem:total', 'safe:total'],
    # Available orders: ['date', 'status', 'name', 'author']
    'orders': ['-date'],

    # Available filters (id [types], (example value)):
    # name [iexact, istartswith, icontains] (<any text>)
    # change_author [is] (<id in the table>)
    # change_date [younger, older] (weeks|days|hours|minutes: <number>)
    # status ([status identifiers])
    # resource:component [iexact, istartswith, icontains] (<any text>)
    # problem:component [iexact, istartswith, icontains] (<any text>)
    # problem:problem [iexact, istartswith, icontains] (<any text>)
    # format [is] (<number>)
    # finish_date [is, older, younger] (<month:year>)
    'filters': {
        # 'name': {
        #     'type': 'istartswith',
        #     'value': 'Title of the job',
        # },
        # 'change_author': {
        #     'type': 'is',
        #     'value': '1',
        # },
        # 'change_date': {
        #     'type': 'younger',
        #     'value': 'weeks:2',
        # },
        # 'resource_component': {
        #     'type': 'istartswith',
        #     'value': 'D',
        # },
        # 'problem_problem': {
        #     'type': 'icontains',
        #     'value': '1',
        # },
        # 'format': {
        #     'type': 'is',
        #     'value': '1',
        # },
        # 'finish_date': {
        #     'type': 'is',
        #     'value': '1:2016',
        # },
    },
}

VIEW_TYPES = (
    ('1', 'job tree'),
    ('2', 'job view'),
    ('3', 'component children list'),
    ('4', 'unsafes list'),
    ('5', 'safes list'),
    ('6', 'unknowns list'),
    ('7', 'unsafe marks'),
    ('8', 'safe marks'),
    ('9', 'unknown marks')
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

VIEWJOB_DEF_VIEW = {
    # Available data: 'unsafes', 'safes', 'unknowns', 'resources', 'tags_safe', 'tags_unsafe'
    'data': ['unsafes', 'safes', 'unknowns', 'resources', 'tags_safe', 'tags_unsafe', 'safes_attr_stat',
             'unsafes_attr_stat', 'unknowns_attr_stat'],
    # Available filters (id [types], (example value)):
    # unknown_component [iexact, istartswith, icontains] (<any text>)
    # unknown_problem [iexact, istartswith, icontains] (<any text>)
    # resource_component [iexact, istartswith, icontains] (<any text>)
    # safe_tag [iexact, istartswith, icontains] (<any text>)
    # unsafe_tag [iexact, istartswith, icontains] (<any text>)
    # unknowns_total [hide, show]
    # unknowns_nomark [hide, show]
    'filters': {
        # 'unknown_component': {
        #     'type': 'istartswith',
        #     'value': 'D'
        # },
        # 'unknown_problem': {
        #     'type': 'icontains',
        #     'value': 'Problem'
        # },
        # 'resource_component': {
        #     'type': 'icontains',
        #     'value': 'S'
        # },
        # 'safe_tag': {
        #     'type': 'iexact',
        #     'value': 'my:safe:tag:4'
        # },
        # 'unsafe_tag': {
        #     'type': 'istartswith',
        #     'value': 'my:unsafe:'
        # },
        # 'unknowns_total': {
        #     'type': 'hide'
        # },
        # 'unknowns_nomark': {
        #     'type': 'hide'
        # },
        # 'resource_total': {
        #     'type': 'hide'
        # },
    }
}

REPORT_ATTRS_DEF_VIEW = {
    # Available filters (id [types], (example attr), (example value)):
    # component [iexact, istartswith, icontains] (<any text>)
    # attr [iexact, istartswith] (<attribute name separated by ':'>) (<any text>)
    # Available oreders:
    # (<attribute name>|component|date, down|up) - tuple
    'filters': {
        # 'component': {
        #     'type': 'istartswith',
        #     'value': 'v',
        # },
        # 'attr': {
        #     'attr': 'LKVOG strategy:Name',
        #     'type': 'istartswith',
        #     'value': 'Separate'
        # }
    },
    'order': ('component', 'down')
}

UNSAFE_LIST_DEF_VIEW = {
    'columns': ['marks_number', 'report_verdict', 'tags', 'parent_cpu'],
    'order': ('default', 'down'),
    'filters': {
        # 'attr': {
        #     'attr': 'LKVOG strategy:Name',
        #     'type': 'istartswith',
        #     'value': 'Separate'
        # }
    }
}

SAFE_LIST_DEF_VIEW = {
    'columns': ['marks_number', 'report_verdict', 'tags', 'parent_cpu'],
    'order': ('default', 'down'),
    'filters': {
        # 'attr': {
        #     'attr': 'LKVOG strategy:Name',
        #     'type': 'istartswith',
        #     'value': 'Separate'
        # }
    }
}

UNKNOWN_LIST_DEF_VIEW = {
    'order': ('component', 'down'),
    'filters': {
        # 'component': {
        #     'type': 'istartswith',
        #     'value': 'v',
        # },
        # 'attr': {
        #     'attr': 'LKVOG strategy:Name',
        #     'type': 'istartswith',
        #     'value': 'Separate'
        # }
    }
}

# Available filters (id [types], (example value)):
# verdict [is, isnot] (<verdict id>)
# status [is, isnot] (<status id>)
# author [is] (<author id>)
MARKS_SAFE_VIEW = {
    'columns': ['num_of_links', 'verdict', 'tags', 'status', 'author', 'format'],
    # 'order': 'num_of_links',
    'filters': {
        # 'verdict': {
        #     'type': 'is',
        #     'value': '0',
        # },
        # 'status': {
        #     'type': 'is',
        #     'value': '1'
        # },
        # 'author': {
        #     'type': 'is',
        #     'value': 0
        # }
    }
}

# Available filters (id [types], (example value)):
# verdict [is, isnot] (<verdict id>)
# status [is, isnot] (<status id>)
# author [is] (<author id>)
MARKS_UNSAFE_VIEW = {
    'columns': ['num_of_links', 'verdict', 'tags', 'status', 'author', 'format'],
    # 'order': 'num_of_links',
    'filters': {
        # 'verdict': {
        #     'type': 'is',
        #     'value': '2',
        # },
        # 'status': {
        #     'type': 'is',
        #     'value': '1',
        # },
        # 'author': {
        #     'type': 'is',
        #     'value': 1,
        # },
        # 'attr': {
        #     'attr': 'Entry point',
        #     'type': 'istartswith',
        #     'value': 'ldv_entry_POINT_1'
        # }
    }
}

# Available filters (id [types], (example value)):
# status [is, isnot] (<status id>)
# author [is] (<author id>)
MARKS_UNKNOWN_VIEW = {
    'columns': ['num_of_links', 'status', 'component', 'author', 'format', 'pattern'],
    # 'order': 'num_of_links',
    'filters': {
        # 'status': {
        #     'type': 'is',
        #     'value': '0',
        # },
        # 'author': {
        #     'type': 'is',
        #     'value': 1,
        # },

    }
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
