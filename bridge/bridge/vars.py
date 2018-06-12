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
    401: _("You don't have an access to one of the selected jobs"),
    404: _('The job was not found'),
    405: _('One of the selected jobs was not found'),
    504: _('The report was not found'),
    505: _("Couldn't visualize the error trace"),
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

# If you change it change values also in comparison.html
COMPARE_VERDICT = (
    ('0', _('Total safe')),
    ('1', _('Found all unsafes')),
    ('2', _('Found not all unsafes')),
    ('3', _('Unknown')),
    ('4', _('Unmatched')),
    ('5', _('Broken'))
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
    ('6', _('Cancelling')),
    ('7', _('Cancelled')),
    ('8', _('Terminated'))
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

VIEW_TYPES = (
    ('0', 'component attributes'),  # Currently unused
    ('1', 'jobTree'),
    ('2', 'DecisionResults'),  # job page
    ('3', 'reportChildren'),
    ('4', 'SafesAndUnsafesList'),  # unsafes list
    ('5', 'SafesAndUnsafesList'),  # safes list
    ('6', 'UnknownsList'),  # unknowns list
    ('7', 'marksList'),  # unsafe marks
    ('8', 'marksList'),  # safe marks
    ('9', 'marksList'),  # unknown marks
    ('10', 'UnsafeAssMarks'),  # unsafe associated marks
    ('11', 'SafeAssMarks'),  # safe associated marks
    ('12', 'UnknownAssMarks'),  # unknown associated marks
    ('13', 'UnsafeAssReports'),  # unsafe mark associated reports
    ('14', 'SafeAndUnknownAssReports'),  # safe mark associated reports
    ('15', 'SafeAndUnknownAssReports'),  # unknown mark associated reports
    ('16', 'AssociationChanges'),  # safe association changes
    ('17', 'AssociationChanges'),  # unsafe association changes
    ('18', 'AssociationChanges')  # unknown association changes
)

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

REPORT_ARCHIVE = {
    'log': 'log.zip',
    'coverage': 'coverage.zip',
    'verifier input': 'VerifierInput.zip',
    'error trace': 'ErrorTrace.zip',
    'sources': 'Sources.zip',
    'proof': 'proof.zip',
    'problem desc': 'ProblemDesc.zip'
}

LOG_FILE = 'log.txt'
COVERAGE_FILE = 'coverage.json'
ERROR_TRACE_FILE = 'error trace.json'
PROBLEM_DESC_FILE = 'problem desc.txt'
PROOF_FILE = 'proof.txt'

# You can set translatable text _("Unknown error")
UNKNOWN_ERROR = 'Unknown error'

ASSOCIATION_TYPE = (
    ('0', _('Automatic')),
    ('1', _('Confirmed')),
    ('2', _('Unconfirmed'))
)
