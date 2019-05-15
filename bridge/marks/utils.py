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

from difflib import unified_diff

from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _

from bridge.vars import USER_ROLES, JOB_ROLES, MARK_SAFE, MARK_UNSAFE, MARK_STATUS

from users.models import User
from jobs.models import Job
from reports.models import ReportUnsafe, ReportSafe, ReportUnknown
from marks.models import MarkSafe, MarkUnsafe, MarkUnknown, ConvertedTrace

from marks.UnsafeUtils import DEFAULT_COMPARE, COMPARE_FUNCTIONS, CONVERT_FUNCTIONS
from marks.tags import TagsTree, MarkTagsTree


STATUS_COLOR = {
    '0': '#e81919',
    '1': '#FF8533',
    '2': '#FF8533',
    '3': '#00c600',
}

UNSAFE_COLOR = {
    '0': '#cb58ec',
    '1': '#e81919',
    '2': '#e81919',
    '3': '#FF8533',
    '4': '#D11919',  # Incompatible marks
    '5': '#000000',  # Without marks
}

SAFE_COLOR = {
    '0': '#cb58ec',
    '1': '#FF8533',
    '2': '#e81919',
    '3': '#D11919',  # Incompatible marks
    '4': '#000000',  # Without marks
}


class MarkAccess:
    def __init__(self, user, mark=None, report=None):
        self.user = user
        self.mark = mark
        self.report = report

    @cached_property
    def _mark_valid(self):
        return isinstance(self.mark, (MarkSafe, MarkUnsafe, MarkUnknown))

    @cached_property
    def _report_valid(self):
        return isinstance(self.report, (ReportUnsafe, ReportSafe, ReportUnknown))

    @cached_property
    def _user_valid(self):
        return isinstance(self.user, User)

    @cached_property
    def _is_manager(self):
        return self._user_valid and self.user.role == USER_ROLES[2][0]

    @cached_property
    def _is_expert(self):
        return self._user_valid and self.user.role == USER_ROLES[3][0]

    def __is_job_expert(self, job):
        if not self._user_valid:
            return False

        if job.author == self.user:
            # User is author of job for which the mark was applied, he is always expert of such marks
            return True

        last_v = job.versions.get(version=job.version)
        if last_v.global_role in {JOB_ROLES[2][0], JOB_ROLES[4][0]}:
            return True
        user_role = last_v.userrole_set.filter(user=self.user).first()
        return bool(user_role and user_role.role in {JOB_ROLES[2][0], JOB_ROLES[4][0]})

    @cached_property
    def _job_expert(self):
        if not self._user_valid:
            return False
        if self._mark_valid:
            if self.mark.job is None:
                # The mark is not associated with any jobs
                return False
            return self.__is_job_expert(self.mark.job)
        if self._report_valid:
            job = Job.objects.filter(reportroot__id=self.report.root_id).first()
            if job.author == self.user:
                # Author of the job can create marks for it
                return True
            return self.__is_job_expert(self.mark.job)
        return False

    @cached_property
    def can_edit(self):
        if not self._mark_valid or not self._user_valid:
            return False
        if self._is_manager:
            # Only managers can modify non-modifiable marks
            return True
        if not self.mark.is_modifiable:
            return False
        if self._is_expert or self.mark.author == self.user:
            # Authors of mark and experts can edit the mark
            return True
        # If user is expert for the job, then he can edit marks associated with such jobs
        return self._job_expert

    @cached_property
    def can_create(self):
        if not self._user_valid or not self._report_valid:
            return False
        if self._is_manager or self._is_expert:
            # All managers and experts can create marks
            return True
        return self._job_expert

    @cached_property
    def can_upload(self):
        # Only managers and experts can upload marks
        return self._is_manager or self._is_expert

    @cached_property
    def can_delete(self):
        if not self._user_valid:
            return False
        if self._is_manager:
            return True
        if not self.mark.is_modifiable:
            return False
        if self._is_expert:
            return True
        # User can delete the mark if he is author of all versions
        authors = list(set(self.mark.versions.exclude(author=None).values_list('author_id', flat=True)))
        return len(authors) == 1 and authors[0] == self.user.id

    @property
    def can_freeze(self):
        return self._is_manager

    def can_remove_version(self, mark_version):
        if not self._user_valid or not self._mark_valid:
            return False
        # Nobody can remove last version
        # TODO: check if removing first version does not affect anything
        if mark_version.version == self.mark.version:
            return False
        # Manager can remove all other versions
        if self._is_manager:
            return True
        # Others can't remove versions if mark is frozen
        if not self.mark.is_modifiable:
            return False
        # Expert can remove all versions.
        if self._is_expert:
            return True
        # Otherwise only author of mark version can remove it
        return mark_version.author == self.user


class CompareMarkVersions:
    def __init__(self, mark, version1, version2):
        self.mark = mark
        self.v1 = version1
        self.v2 = version2

    @cached_property
    def type(self):
        if isinstance(self.mark, MarkSafe):
            return 'safe'
        elif isinstance(self.mark, MarkUnsafe):
            return 'unsafe'
        return 'unknown'

    @cached_property
    def verdict(self):
        if self.type == 'unknown' or self.v1.verdict == self.v2.verdict:
            return None
        return [
            {'display': self.v1.get_verdict_display(), 'value': self.v1.verdict},
            {'display': self.v2.get_verdict_display(), 'value': self.v2.verdict}
        ]

    @cached_property
    def status(self):
        if self.v1.status == self.v2.status:
            return None
        return [
            {'display': self.v1.get_status_display(), 'value': self.v1.status},
            {'display': self.v2.get_status_display(), 'value': self.v2.status}
        ]

    @cached_property
    def tags(self):
        if self.type == 'unknown':
            return None
        tags1 = set(t for t, in self.v1.tags.values_list('tag__name'))
        tags2 = set(t for t, in self.v2.tags.values_list('tag__name'))
        if tags1 == tags2:
            return None
        return ['; '.join(sorted(tags1)), '; '.join(sorted(tags2))]

    @cached_property
    def unsafe_func(self):
        if self.type != 'unsafe' or self.v1.function == self.v2.function:
            return None
        return [{
            'compare_name': self.v1.function,
            'compare_desc': COMPARE_FUNCTIONS[self.v1.function]['desc'],
            'convert_name': COMPARE_FUNCTIONS[self.v1.function]['convert'],
            'convert_desc': CONVERT_FUNCTIONS[COMPARE_FUNCTIONS[self.v1.function]['convert']]
        }, {
            'compare_name': self.v2.function,
            'compare_desc': COMPARE_FUNCTIONS[self.v2.function]['desc'],
            'convert_name': COMPARE_FUNCTIONS[self.v2.function]['convert'],
            'convert_desc': CONVERT_FUNCTIONS[COMPARE_FUNCTIONS[self.v2.function]['convert']]
        }]

    @cached_property
    def error_trace(self):
        if self.type != 'unsafe' or self.v1.error_trace_id == self.v2.error_trace_id:
            return None
        diff_result = []
        f1 = ConvertedTrace.objects.get(id=self.v1.error_trace_id)
        f2 = ConvertedTrace.objects.get(id=self.v2.error_trace_id)
        with f1.file as fp1, f2.file as fp2:
            for line in unified_diff(fp1.read().decode('utf8').split('\n'), fp2.read().decode('utf8').split('\n')):
                diff_result.append(line)
        return '\n'.join(diff_result)

    @cached_property
    def attrs(self):
        v1_attrs_qs = self.v1.attrs.filter(is_compare=True).order_by('id')
        v2_attrs_qs = self.v2.attrs.filter(is_compare=True).order_by('id')
        if set((a.name, a.value) for a in v1_attrs_qs) == set((a.name, a.value) for a in v2_attrs_qs):
            return None
        return [v1_attrs_qs, v2_attrs_qs]

    @cached_property
    def unknown_func(self):
        if self.type != 'unknown':
            return None
        if self.v1.is_regexp == self.v2.is_regexp and self.v1.function == self.v2.function:
            return None
        return [{'is_regexp': self.v1.is_regexp, 'func': self.v1.function},
                {'is_regexp': self.v2.is_regexp, 'func': self.v2.function}]

    @cached_property
    def problem(self):
        if self.type != 'unknown':
            return None
        if self.v1.problem_pattern == self.v2.problem_pattern and self.v1.link == self.v2.link:
            return None
        return [{'pattern': self.v1.problem_pattern, 'link': self.v1.link},
                {'pattern': self.v2.problem_pattern, 'link': self.v2.link}]


class MarkVersionFormData:
    def __init__(self, mark_type, mark_version=None):
        self.type = mark_type
        self.object = mark_version
        self.statuses = MARK_STATUS

    @property
    def title(self):
        if self.type == 'safe':
            return _('Safes mark')
        elif self.type == 'unsafe':
            return _('Unsafes mark')
        return _('Unknowns mark')

    @property
    def action(self):
        return 'edit' if self.object else 'create'

    @cached_property
    def is_modifiable(self):
        return self.object.mark.is_modifiable if self.object else True

    @cached_property
    def version(self):
        # Should not be called on mark creation
        return self.object.version if self.object else None

    @cached_property
    def status(self):
        return self.object.status if self.object else MARK_STATUS[0][0]

    @property
    def description(self):
        return self.object.description if self.object else ''

    @cached_property
    def verdict(self):
        if self.type == 'safe':
            return self.object.verdict if self.object else MARK_SAFE[0][0]
        elif self.type == 'unsafe':
            return self.object.verdict if self.object else MARK_UNSAFE[0][0]
        return None

    @cached_property
    def verdicts(self):
        if self.type == 'safe':
            return MARK_SAFE
        elif self.type == 'unsafe':
            return MARK_UNSAFE
        return None

    @cached_property
    def function(self):
        if self.type == 'safe':
            return None
        if self.object:
            return self.object.function
        return DEFAULT_COMPARE if self.type == 'unsafe' else ''

    @cached_property
    def functions(self):
        functions_data = []
        for name in sorted(COMPARE_FUNCTIONS):
            functions_data.append({
                'name': name,
                'desc': COMPARE_FUNCTIONS[name]['desc'],
                'convert': {
                    'name': COMPARE_FUNCTIONS[name]['convert'],
                    'desc': CONVERT_FUNCTIONS[COMPARE_FUNCTIONS[name]['convert']]
                }
            })
        return functions_data

    @property
    def compare_desc(self):
        return COMPARE_FUNCTIONS[self.function]['desc']

    @property
    def convert_func(self):
        return {
            'name': COMPARE_FUNCTIONS[self.function]['convert'],
            'desc': CONVERT_FUNCTIONS[COMPARE_FUNCTIONS[self.function]['convert']],
        }

    @property
    def problem_pattern(self):
        return self.object.problem_pattern if self.object else ''

    @property
    def is_regexp(self):
        return self.object.is_regexp if self.object else False

    @property
    def link(self):
        return self.object.link if self.object and self.object.link else ''

    @cached_property
    def tags(self):
        if self.type == 'unknown':
            return None
        if self.object:
            return MarkTagsTree(self.object)
        return TagsTree(self.type, tags_ids=[])

    @cached_property
    def error_trace(self):
        if not self.object or self.type != 'unsafe':
            return
        with self.object.error_trace.file.file as fp:
            return fp.read().decode('utf-8')
