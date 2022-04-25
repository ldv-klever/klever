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
from django.db.models.signals import post_delete
from django.contrib.postgres.fields import ArrayField
from django.urls import reverse
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from mptt.models import MPTTModel, TreeForeignKey

from bridge.vars import MARK_STATUS, MARK_UNSAFE, MARK_SAFE, MARK_SOURCE, ASSOCIATION_TYPE
from bridge.utils import WithFilesMixin, remove_instance_files

from users.models import User
from jobs.models import Job
from reports.models import MAX_COMPONENT_LEN, ReportUnsafe, ReportSafe, ReportComponent, ReportUnknown, AttrBase

CONVERTED_DIR = 'Error-traces'
MAX_PROBLEM_LEN = 20
MAX_TAG_LEN = 32


class ConvertedTrace(WithFilesMixin, models.Model):
    hash_sum = models.CharField(max_length=255, db_index=True)
    file = models.FileField(upload_to=CONVERTED_DIR, null=False)
    function = models.CharField(max_length=30, db_index=True, verbose_name=_('Convert trace function'))
    trace_cache = models.JSONField()

    class Meta:
        db_table = 'cache_marks_trace'

    def __str__(self):
        return self.hash_sum


# Abstract tables
class Mark(models.Model):
    identifier = models.UUIDField(unique=True, default=uuid.uuid4)
    job = models.ForeignKey(Job, models.SET_NULL, null=True, related_name='+')
    version = models.PositiveSmallIntegerField(default=1)
    # Author of first version
    author = models.ForeignKey(User, models.SET_NULL, null=True, related_name='+')
    is_modifiable = models.BooleanField(default=True)
    source = models.CharField(max_length=1, choices=MARK_SOURCE, default=MARK_SOURCE[0][0])

    # Only with is_compare=True
    cache_attrs = models.JSONField(default=dict)

    def __str__(self):
        return str(self.identifier)

    class Meta:
        abstract = True


class MarkHistory(models.Model):
    version = models.PositiveSmallIntegerField()
    author = models.ForeignKey(User, models.SET_NULL, null=True, related_name='+')
    change_date = models.DateTimeField(default=now)
    comment = models.TextField(blank=True, default='')
    description = models.TextField(blank=True, default='')

    class Meta:
        abstract = True


# Safes tables
class MarkSafe(Mark):
    verdict = models.CharField(max_length=1, choices=MARK_SAFE)
    cache_tags = ArrayField(models.CharField(max_length=1024), default=list)

    class Meta:
        db_table = 'mark_safe'
        verbose_name = _('Safes mark')


class MarkSafeHistory(MarkHistory):
    mark = models.ForeignKey(MarkSafe, models.CASCADE, related_name='versions')
    verdict = models.CharField(max_length=1, choices=MARK_SAFE)

    class Meta:
        db_table = 'mark_safe_history'
        verbose_name = _('Safes mark version')


class MarkSafeAttr(AttrBase):
    mark_version = models.ForeignKey(MarkSafeHistory, models.CASCADE, related_name='attrs')
    is_compare = models.BooleanField(default=True)

    class Meta:
        db_table = 'mark_safe_attr'
        ordering = ('id',)


class MarkSafeReport(models.Model):
    mark = models.ForeignKey(MarkSafe, models.CASCADE, related_name='markreport_set')
    report = models.ForeignKey(ReportSafe, models.CASCADE, related_name='markreport_set')
    type = models.CharField(max_length=1, choices=ASSOCIATION_TYPE, default=ASSOCIATION_TYPE[0][0])
    author = models.ForeignKey(User, models.SET_NULL, null=True)
    associated = models.BooleanField(default=True)

    class Meta:
        db_table = "cache_mark_safe_report"


class SafeAssociationLike(models.Model):
    association = models.ForeignKey(MarkSafeReport, models.CASCADE)
    author = models.ForeignKey(User, models.CASCADE)
    dislike = models.BooleanField(default=False)

    class Meta:
        db_table = "mark_safe_association_like"


# Unsafes tables
class MarkUnsafe(Mark):
    function = models.CharField(max_length=30, db_index=True, verbose_name=_('Compare trace function'))
    regexp = models.TextField(default="")
    error_trace = models.ForeignKey(ConvertedTrace, models.CASCADE, null=True)
    verdict = models.CharField(max_length=1, choices=MARK_UNSAFE)
    status = models.CharField(max_length=1, choices=MARK_STATUS, null=True)
    cache_tags = ArrayField(models.CharField(max_length=1024), default=list)
    threshold = models.FloatField(default=0)

    @property
    def threshold_percentage(self):
        return round(self.threshold * 100)

    class Meta:
        db_table = 'mark_unsafe'
        verbose_name = _('Unsafes mark')


class MarkUnsafeHistory(MarkHistory):
    mark = models.ForeignKey(MarkUnsafe, models.CASCADE, related_name='versions')
    regexp = models.TextField(default="")
    verdict = models.CharField(max_length=1, choices=MARK_UNSAFE)
    status = models.CharField(max_length=1, choices=MARK_STATUS, null=True)
    error_trace = models.ForeignKey(ConvertedTrace, models.CASCADE, null=True)
    threshold = models.FloatField(default=0)

    @property
    def threshold_percentage(self):
        return round(self.threshold * 100)

    class Meta:
        db_table = 'mark_unsafe_history'
        verbose_name = _('Unsafes mark version')


class MarkUnsafeAttr(AttrBase):
    mark_version = models.ForeignKey(MarkUnsafeHistory, models.CASCADE, related_name='attrs')
    is_compare = models.BooleanField(default=True)

    class Meta:
        db_table = 'mark_unsafe_attr'
        ordering = ('id',)


class MarkUnsafeReport(models.Model):
    mark = models.ForeignKey(MarkUnsafe, models.CASCADE, related_name='markreport_set')
    report = models.ForeignKey(ReportUnsafe, models.CASCADE, related_name='markreport_set')
    type = models.CharField(max_length=1, choices=ASSOCIATION_TYPE, default=ASSOCIATION_TYPE[0][0])
    result = models.FloatField()
    error = models.TextField(null=True)
    author = models.ForeignKey(User, models.SET_NULL, null=True)
    associated = models.BooleanField(default=True)

    class Meta:
        db_table = "cache_mark_unsafe_report"


class UnsafeAssociationLike(models.Model):
    association = models.ForeignKey(MarkUnsafeReport, models.CASCADE)
    author = models.ForeignKey(User, models.CASCADE)
    dislike = models.BooleanField(default=False)

    class Meta:
        db_table = "mark_unsafe_association_like"


# Tags tables
class Tag(MPTTModel):
    author = models.ForeignKey(User, models.SET_NULL, null=True)
    parent = TreeForeignKey('self', models.CASCADE, null=True, related_name='children')
    name = models.CharField(max_length=1024, db_index=True, unique=True)
    description = models.TextField(default='', blank=True)
    populated = models.BooleanField(default=False)

    @property
    def url(self):
        return reverse("marks:api-tags-detail", args=[self.id])

    @property
    def access_url(self):
        return reverse("marks:api-tags-access", args=[self.id])

    @property
    def shortname(self):
        return self.name.split(' - ')[-1]

    class Meta:
        db_table = "mark_tag"


class MarkSafeTag(models.Model):
    mark_version = models.ForeignKey(MarkSafeHistory, models.CASCADE, related_name='tags')
    tag = models.ForeignKey(Tag, models.CASCADE, related_name='+')

    def __str__(self):
        return self.tag.name

    class Meta:
        db_table = "cache_mark_safe_tag"


class MarkUnsafeTag(models.Model):
    mark_version = models.ForeignKey(MarkUnsafeHistory, models.CASCADE, related_name='tags')
    tag = models.ForeignKey(Tag, models.CASCADE, related_name='+')

    def __str__(self):
        return self.tag.name

    class Meta:
        db_table = 'cache_mark_unsafe_tag'


# For unknowns
class MarkUnknown(Mark):
    component = models.CharField(max_length=MAX_COMPONENT_LEN)
    function = models.TextField()
    is_regexp = models.BooleanField(default=True)
    problem_pattern = models.CharField(max_length=MAX_PROBLEM_LEN)
    link = models.URLField(null=True, blank=True)

    class Meta:
        db_table = 'mark_unknown'
        index_together = ['component', 'problem_pattern']
        verbose_name = _('Unknowns mark')


class MarkUnknownHistory(MarkHistory):
    mark = models.ForeignKey(MarkUnknown, models.CASCADE, related_name='versions')
    function = models.TextField()
    is_regexp = models.BooleanField(default=True)
    problem_pattern = models.CharField(max_length=MAX_PROBLEM_LEN)
    link = models.URLField(null=True, blank=True)

    class Meta:
        db_table = 'mark_unknown_history'
        verbose_name = _('Unknowns mark version')


class MarkUnknownAttr(AttrBase):
    mark_version = models.ForeignKey(MarkUnknownHistory, models.CASCADE, related_name='attrs')
    is_compare = models.BooleanField(default=True)

    class Meta:
        db_table = 'mark_unknown_attr'


class MarkUnknownReport(models.Model):
    mark = models.ForeignKey(MarkUnknown, models.CASCADE, related_name='markreport_set')
    report = models.ForeignKey(ReportUnknown, models.CASCADE, related_name='markreport_set')
    problem = models.CharField(max_length=MAX_PROBLEM_LEN, db_index=True)
    type = models.CharField(max_length=1, choices=ASSOCIATION_TYPE, default=ASSOCIATION_TYPE[0][0])
    author = models.ForeignKey(User, models.SET_NULL, null=True)
    associated = models.BooleanField(default=True)

    class Meta:
        db_table = 'cache_mark_unknown_report'


class UnknownAssociationLike(models.Model):
    association = models.ForeignKey(MarkUnknownReport, models.CASCADE)
    author = models.ForeignKey(User, models.CASCADE)
    dislike = models.BooleanField(default=False)

    class Meta:
        db_table = "mark_unknown_association_like"


class UnsafeConvertionCache(models.Model):
    unsafe = models.ForeignKey(ReportUnsafe, models.CASCADE)
    converted = models.ForeignKey(ConvertedTrace, models.CASCADE)

    class Meta:
        db_table = 'cache_error_trace_converted'


class TagAccess(models.Model):
    user = models.ForeignKey(User, models.CASCADE)
    tag = models.ForeignKey(Tag, models.CASCADE)
    modification = models.BooleanField(default=False)
    child_creation = models.BooleanField(default=False)

    class Meta:
        db_table = 'mark_tag_access'


post_delete.connect(remove_instance_files, sender=ConvertedTrace)
