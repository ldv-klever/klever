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

import uuid

from django.db import models
from django.contrib.postgres.fields import JSONField
from django.utils.translation import ugettext_lazy as _

from bridge.vars import SAFE_VERDICTS, UNSAFE_VERDICTS

from jobs.models import Job
from reports.models import ReportSafe, ReportUnsafe, ReportUnknown
from marks.models import MarkSafe, MarkUnsafe, MarkUnknown

ASSOCIATION_CHANGE_KIND = (
    ('0', _('Changed')),
    ('1', _('New')),
    ('2', _('Deleted'))
)


class ReportSafeCache(models.Model):
    job = models.ForeignKey(Job, models.CASCADE, related_name='+')
    report = models.OneToOneField(ReportSafe, models.CASCADE, related_name='cache')
    attrs = JSONField(default=dict)
    marks_total = models.PositiveIntegerField(default=0)
    marks_confirmed = models.PositiveIntegerField(default=0)
    verdict = models.CharField(max_length=1, choices=SAFE_VERDICTS, default=SAFE_VERDICTS[4][0])
    tags = JSONField(default=dict)

    class Meta:
        db_table = 'cache_safe'


class ReportUnsafeCache(models.Model):
    job = models.ForeignKey(Job, models.CASCADE, related_name='+')
    report = models.OneToOneField(ReportUnsafe, models.CASCADE, related_name='cache')
    attrs = JSONField(default=dict)
    marks_total = models.PositiveIntegerField(default=0)
    marks_confirmed = models.PositiveIntegerField(default=0)
    total_similarity = models.FloatField(default=0)
    verdict = models.CharField(max_length=1, choices=UNSAFE_VERDICTS, default=UNSAFE_VERDICTS[5][0])
    tags = JSONField(default=dict)

    class Meta:
        db_table = 'cache_unsafe'


class ReportUnknownCache(models.Model):
    job = models.ForeignKey(Job, models.CASCADE, related_name='+')
    report = models.OneToOneField(ReportUnknown, models.CASCADE, related_name='cache')
    attrs = JSONField(default=dict)
    marks_total = models.PositiveIntegerField(default=0)
    marks_confirmed = models.PositiveIntegerField(default=0)
    problems = JSONField(default=dict)

    class Meta:
        db_table = 'cache_unknown'


class SafeMarkAssociationChanges(models.Model):
    identifier = models.UUIDField(default=uuid.uuid4)
    mark = models.ForeignKey(MarkSafe, models.CASCADE)
    job = models.ForeignKey(Job, models.CASCADE)
    report = models.ForeignKey(ReportSafe, models.CASCADE)
    kind = models.CharField(max_length=1, choices=ASSOCIATION_CHANGE_KIND)
    verdict_old = models.CharField(max_length=1, choices=SAFE_VERDICTS)
    verdict_new = models.CharField(max_length=1, choices=SAFE_VERDICTS)
    tags_old = JSONField()
    tags_new = JSONField()

    class Meta:
        db_table = 'cache_safe_mark_associations_changes'


class UnsafeMarkAssociationChanges(models.Model):
    identifier = models.UUIDField(default=uuid.uuid4)
    mark = models.ForeignKey(MarkUnsafe, models.CASCADE)
    job = models.ForeignKey(Job, models.CASCADE)
    report = models.ForeignKey(ReportUnsafe, models.CASCADE)
    kind = models.CharField(max_length=1, choices=ASSOCIATION_CHANGE_KIND)
    verdict_old = models.CharField(max_length=1, choices=UNSAFE_VERDICTS)
    verdict_new = models.CharField(max_length=1, choices=UNSAFE_VERDICTS)
    tags_old = JSONField()
    tags_new = JSONField()
    total_similarity_old = models.FloatField()
    total_similarity_new = models.FloatField()

    class Meta:
        db_table = 'cache_unsafe_mark_associations_changes'


class UnknownMarkAssociationChanges(models.Model):
    identifier = models.UUIDField(default=uuid.uuid4)
    mark = models.ForeignKey(MarkUnknown, models.CASCADE)
    job = models.ForeignKey(Job, models.CASCADE)
    report = models.ForeignKey(ReportUnknown, models.CASCADE)
    kind = models.CharField(max_length=1, choices=ASSOCIATION_CHANGE_KIND)
    problems_old = JSONField(default=dict)
    problems_new = JSONField(default=dict)

    class Meta:
        db_table = 'cache_unknown_mark_associations_changes'
