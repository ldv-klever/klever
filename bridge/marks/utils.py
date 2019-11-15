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

from bridge.vars import USER_ROLES, JOB_ROLES, ASSOCIATION_TYPE, COMPARE_FUNCTIONS, CONVERT_FUNCTIONS

from users.models import User
from jobs.models import Job
from reports.models import ReportUnsafe, ReportSafe, ReportUnknown
from marks.models import MarkSafe, MarkUnsafe, MarkUnknown, ConvertedTrace


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
    def _is_author(self):
        return self._mark_valid and self._user_valid and self.mark.author == self.user

    @cached_property
    def _is_expert(self):
        return self._user_valid and self.user.role == USER_ROLES[3][0]

    def __is_job_expert(self, job):
        if not self._user_valid or not job:
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
        job = None
        if self._mark_valid:
            job = self.mark.job
        if self._report_valid:
            job = Job.objects.filter(reportroot__id=self.report.root_id).first()
        return self.__is_job_expert(job)

    @cached_property
    def can_edit(self):
        if not self._mark_valid or not self._user_valid:
            return False
        if self._is_manager or self._is_author:
            # Only managers and authors can edit non-modifiable marks
            return True
        if not self.mark.is_modifiable:
            # Mark is not modifiable
            return False
        # Experts and job experts can edit the mark
        return self._is_expert or self._job_expert

    @cached_property
    def can_create(self):
        if not self._user_valid or not self._report_valid:
            return False
        # All managers, experts and job experts can create marks
        return self._is_manager or self._is_expert or self._job_expert

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
        if self._is_manager:
            return True
        if self._mark_valid:
            # On edition stage author of the mark can freeze it
            return self._is_author
        # On creation stage all users can freeze their marks
        return True

    def can_remove_versions(self, versions_qs):
        if not self._user_valid or not self._mark_valid:
            return False
        # Nobody can remove last version
        if any(mv.version == self.mark.version for mv in versions_qs):
            return False
        # Manager and versions author can remove other versions
        if self._is_manager or all(mv.author == self.user for mv in versions_qs):
            return True
        # Experts can remove versions if mark is not frozen.
        return self._is_expert and self.mark.is_modifiable


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
        if self.type != 'unsafe' or self.v1.status == self.v2.status:
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


class RemoveMarksBase:
    model = None
    associations_model = None

    def __init__(self, **kwargs):
        self._qs_kwargs = kwargs
        self._marks_qs = self.__get_marks_qs()
        if not self._marks_qs.exists():
            # Nothing to delete
            return
        self.affected_reports = self.__get_affected_reports()
        self._marks_qs.delete()
        self.update_associated()

    def __get_marks_qs(self):
        assert self.model
        return self.model.objects.filter(**self._qs_kwargs)

    def __get_affected_reports(self):
        assert self.associations_model
        qs_filters = dict(('mark__{}'.format(k), v) for k, v in self._qs_kwargs.items())
        return set(self.associations_model.objects.filter(**qs_filters).values_list('report_id', flat=True))

    @property
    def without_associations_qs(self):
        # Find reports that has marks associations when all association are disabled. It can be in 2 cases:
        # 1) All marks are unconfirmed
        # 2) All confirmed associations were with deleted marks
        # We need to update 2nd case, so auto-associations are counting again
        changed_ids = self.affected_reports - set(self.associations_model.objects.filter(
            report_id__in=self.affected_reports, associated=True
        ).values_list('report_id', flat=True))
        return self.associations_model.objects.filter(report_id__in=changed_ids).exclude(type=ASSOCIATION_TYPE[2][0])

    def update_associated(self):
        self.without_associations_qs.update(associated=True)


class ConfirmAssociationBase:
    model = None

    def __init__(self, author, association_obj):
        assert self.model
        self._author = author
        self.association = association_obj
        self.__confirm()

    def recalculate_cache(self, report_id):
        raise NotImplementedError('Please implement the method!')

    def can_confirm_validation(self):
        pass

    def __confirm(self):
        self.can_confirm_validation()

        # Already confirmed
        if self.association.type == ASSOCIATION_TYPE[1][0]:
            return

        # Update association
        self.association.author = self._author
        self.association.type = ASSOCIATION_TYPE[1][0]
        self.association.associated = True
        self.association.save()

        # Do not count automatic associations as there is already confirmed one
        self.model.objects.filter(
            report_id=self.association.report_id, associated=True, type=ASSOCIATION_TYPE[0][0]
        ).update(associated=False)

        # Recalculate verdicts and numbers of associations
        self.recalculate_cache(self.association.report_id)


class UnconfirmAssociationBase:
    model = None

    def __init__(self, author, association_obj):
        assert self.model
        self._author = author
        self._object = association_obj
        self.__unconfirm()

    def get_automatically_associated_qs(self):
        return self.model.objects.filter(
            report_id=self._object.report_id, associated=False
        ).exclude(type=ASSOCIATION_TYPE[2][0])

    def recalculate_cache(self, report_id):
        raise NotImplementedError('Please implement the method!')

    def __unconfirm(self):
        # Already unconfirmed
        if self._object.type == ASSOCIATION_TYPE[2][0]:
            return
        was_confirmed = bool(self._object.type == ASSOCIATION_TYPE[1][0])
        self._object.author = self._author
        self._object.type = ASSOCIATION_TYPE[2][0]
        self._object.associated = False
        self._object.save()

        if was_confirmed and not self.model.objects\
                .filter(report_id=self._object.report_id, type=ASSOCIATION_TYPE[1][0]).exists():
            # The report has lost the only confirmed mark,
            # so we need recalculate what associations we need to count for caches
            queryset = self.get_automatically_associated_qs()
            queryset.update(associated=True)

        self.recalculate_cache(self._object.report_id)
