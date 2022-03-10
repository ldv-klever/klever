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

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from bridge.vars import SAFE_VERDICTS, UNSAFE_VERDICTS, UNSAFE_STATUS

from jobs.models import Decision
from reports.models import ReportSafe, ReportUnsafe, ReportUnknown
from marks.models import MarkSafe, MarkUnsafe, MarkUnknown

ASSOCIATION_CHANGE_KIND = (
    ('0', _('Changed')),
    ('1', _('New')),
    ('2', _('Deleted'))
)


class ReportSafeCache(models.Model):
    decision = models.ForeignKey(Decision, models.CASCADE, related_name='+')
    report = models.OneToOneField(ReportSafe, models.CASCADE, related_name='cache')
    attrs = models.JSONField(default=dict)
    marks_confirmed = models.PositiveIntegerField(default=0)
    marks_automatic = models.PositiveIntegerField(default=0)
    marks_total = models.PositiveIntegerField(default=0)
    verdict = models.CharField(max_length=1, choices=SAFE_VERDICTS, default=SAFE_VERDICTS[4][0])
    tags = models.JSONField(default=dict)

    class Meta:
        db_table = 'cache_safe'


class ReportUnsafeCache(models.Model):
    decision = models.ForeignKey(Decision, models.CASCADE, related_name='+')
    report = models.OneToOneField(ReportUnsafe, models.CASCADE, related_name='cache')
    attrs = models.JSONField(default=dict)
    marks_confirmed = models.PositiveIntegerField(default=0)
    marks_automatic = models.PositiveIntegerField(default=0)
    marks_total = models.PositiveIntegerField(default=0)
    verdict = models.CharField(max_length=1, choices=UNSAFE_VERDICTS, default=UNSAFE_VERDICTS[5][0])
    status = models.CharField(max_length=1, null=True, choices=UNSAFE_STATUS)
    tags = models.JSONField(default=dict)

    class Meta:
        db_table = 'cache_unsafe'


class ReportUnknownCache(models.Model):
    decision = models.ForeignKey(Decision, models.CASCADE, related_name='+')
    report = models.OneToOneField(ReportUnknown, models.CASCADE, related_name='cache')
    attrs = models.JSONField(default=dict)
    marks_confirmed = models.PositiveIntegerField(default=0)
    marks_automatic = models.PositiveIntegerField(default=0)
    marks_total = models.PositiveIntegerField(default=0)
    problems = models.JSONField(default=dict)

    class Meta:
        db_table = 'cache_unknown'


class SafeMarkAssociationChanges(models.Model):
    identifier = models.UUIDField(default=uuid.uuid4)
    mark = models.ForeignKey(MarkSafe, models.CASCADE)
    decision = models.ForeignKey(Decision, models.CASCADE)
    report = models.ForeignKey(ReportSafe, models.CASCADE)
    kind = models.CharField(max_length=1, choices=ASSOCIATION_CHANGE_KIND)
    verdict_old = models.CharField(max_length=1, choices=SAFE_VERDICTS)
    verdict_new = models.CharField(max_length=1, choices=SAFE_VERDICTS)
    tags_old = models.JSONField()
    tags_new = models.JSONField()

    class Meta:
        db_table = 'cache_safe_mark_associations_changes'


class UnsafeMarkAssociationChanges(models.Model):
    identifier = models.UUIDField(default=uuid.uuid4)
    mark = models.ForeignKey(MarkUnsafe, models.CASCADE)
    decision = models.ForeignKey(Decision, models.CASCADE)
    report = models.ForeignKey(ReportUnsafe, models.CASCADE)
    kind = models.CharField(max_length=1, choices=ASSOCIATION_CHANGE_KIND)
    verdict_old = models.CharField(max_length=1, choices=UNSAFE_VERDICTS)
    verdict_new = models.CharField(max_length=1, choices=UNSAFE_VERDICTS)
    status_old = models.CharField(max_length=1, choices=UNSAFE_STATUS, null=True)
    status_new = models.CharField(max_length=1, choices=UNSAFE_STATUS, null=True)
    tags_old = models.JSONField()
    tags_new = models.JSONField()

    class Meta:
        db_table = 'cache_unsafe_mark_associations_changes'


class UnknownMarkAssociationChanges(models.Model):
    identifier = models.UUIDField(default=uuid.uuid4)
    mark = models.ForeignKey(MarkUnknown, models.CASCADE)
    decision = models.ForeignKey(Decision, models.CASCADE)
    report = models.ForeignKey(ReportUnknown, models.CASCADE)
    kind = models.CharField(max_length=1, choices=ASSOCIATION_CHANGE_KIND)
    problems_old = models.JSONField(default=dict)
    problems_new = models.JSONField(default=dict)

    class Meta:
        db_table = 'cache_unknown_mark_associations_changes'
