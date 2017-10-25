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

from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch.dispatcher import receiver
from bridge.vars import FORMAT, MARK_STATUS, MARK_UNSAFE, MARK_SAFE, MARK_TYPE, ASSOCIATION_TYPE
from reports.models import Attr, ReportUnsafe, ReportSafe, ReportComponent, Component, ReportUnknown, AttrName
from jobs.models import Job

CONVERTED_DIR = 'Error-traces'


class ConvertedTraces(models.Model):
    hash_sum = models.CharField(max_length=255, db_index=True)
    file = models.FileField(upload_to=CONVERTED_DIR, null=False)

    class Meta:
        db_table = 'file'

    def __str__(self):
        return self.hash_sum


@receiver(pre_delete, sender=ConvertedTraces)
def converted_delete(**kwargs):
    file = kwargs['instance']
    storage, path = file.file.storage, file.file.path
    storage.delete(path)


class UnknownProblem(models.Model):
    name = models.CharField(max_length=15, db_index=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'cache_mark_unknown_problem'


# Tables with functions
class MarkUnsafeConvert(models.Model):
    name = models.CharField(max_length=30, db_index=True)
    description = models.CharField(max_length=1000, default='')

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'mark_unsafe_convert'


class MarkUnsafeCompare(models.Model):
    convert = models.ForeignKey(MarkUnsafeConvert)
    name = models.CharField(max_length=30, db_index=True)
    description = models.CharField(max_length=1000, default='')

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'mark_unsafe_compare'


# Abstract tables
class Mark(models.Model):
    identifier = models.CharField(max_length=255, unique=True)
    job = models.ForeignKey(Job, null=True, on_delete=models.SET_NULL, related_name='+')
    format = models.PositiveSmallIntegerField(default=FORMAT)
    version = models.PositiveSmallIntegerField(default=1)
    author = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name='+')
    status = models.CharField(max_length=1, choices=MARK_STATUS, default='0')
    is_modifiable = models.BooleanField(default=True)
    change_date = models.DateTimeField(auto_now=True)
    description = models.TextField(default='')
    type = models.CharField(max_length=1, choices=MARK_TYPE, default=MARK_TYPE[0][0])

    def __str__(self):
        return self.identifier

    class Meta:
        abstract = True


class MarkHistory(models.Model):
    version = models.PositiveSmallIntegerField()
    author = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name='+')
    status = models.CharField(max_length=1, choices=MARK_STATUS, default='0')
    change_date = models.DateTimeField()
    comment = models.TextField()
    description = models.TextField()

    class Meta:
        abstract = True


# Safes tables
class MarkSafe(Mark):
    verdict = models.CharField(max_length=1, choices=MARK_SAFE, default='0')

    class Meta:
        db_table = 'mark_safe'


class MarkSafeHistory(MarkHistory):
    mark = models.ForeignKey(MarkSafe, related_name='versions')
    verdict = models.CharField(max_length=1, choices=MARK_SAFE)

    class Meta:
        db_table = 'mark_safe_history'


class MarkSafeAttr(models.Model):
    mark = models.ForeignKey(MarkSafeHistory, related_name='attrs')
    attr = models.ForeignKey(Attr)
    is_compare = models.BooleanField(default=True)

    class Meta:
        db_table = 'mark_safe_attr'


class MarkSafeReport(models.Model):
    mark = models.ForeignKey(MarkSafe, related_name='markreport_set')
    report = models.ForeignKey(ReportSafe, related_name='markreport_set')
    type = models.CharField(max_length=1, choices=ASSOCIATION_TYPE, default='0')
    author = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = "cache_mark_safe_report"


class SafeAssociationLike(models.Model):
    association = models.ForeignKey(MarkSafeReport)
    author = models.ForeignKey(User)
    dislike = models.BooleanField(default=False)

    class Meta:
        db_table = "mark_safe_association_like"


# Unsafes tables
class MarkUnsafe(Mark):
    verdict = models.CharField(max_length=1, choices=MARK_UNSAFE, default='0')
    function = models.ForeignKey(MarkUnsafeCompare)

    class Meta:
        db_table = 'mark_unsafe'


class MarkUnsafeHistory(MarkHistory):
    mark = models.ForeignKey(MarkUnsafe, related_name='versions')
    verdict = models.CharField(max_length=1, choices=MARK_UNSAFE)
    function = models.ForeignKey(MarkUnsafeCompare)
    error_trace = models.ForeignKey(ConvertedTraces)

    class Meta:
        db_table = 'mark_unsafe_history'


class MarkUnsafeAttr(models.Model):
    mark = models.ForeignKey(MarkUnsafeHistory, related_name='attrs')
    attr = models.ForeignKey(Attr)
    is_compare = models.BooleanField(default=True)

    class Meta:
        db_table = 'mark_unsafe_attr'


class MarkUnsafeReport(models.Model):
    mark = models.ForeignKey(MarkUnsafe, related_name='markreport_set')
    report = models.ForeignKey(ReportUnsafe, related_name='markreport_set')
    type = models.CharField(max_length=1, choices=ASSOCIATION_TYPE, default='0')
    result = models.FloatField()
    error = models.TextField(null=True)
    author = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = "cache_mark_unsafe_report"


class UnsafeAssociationLike(models.Model):
    association = models.ForeignKey(MarkUnsafeReport)
    author = models.ForeignKey(User)
    dislike = models.BooleanField(default=False)

    class Meta:
        db_table = "mark_unsafe_association_like"


# Tags tables
class SafeTag(models.Model):
    author = models.ForeignKey(User)
    parent = models.ForeignKey('self', null=True, related_name='children')
    tag = models.CharField(max_length=32, db_index=True)
    description = models.TextField(default='')
    populated = models.BooleanField(default=False)

    class Meta:
        db_table = "mark_safe_tag"


class UnsafeTag(models.Model):
    author = models.ForeignKey(User)
    parent = models.ForeignKey('self', null=True, related_name='children')
    tag = models.CharField(max_length=32, db_index=True)
    description = models.TextField(default='')
    populated = models.BooleanField(default=False)

    class Meta:
        db_table = "mark_unsafe_tag"


class ReportSafeTag(models.Model):
    report = models.ForeignKey(ReportComponent, related_name='safe_tags')
    tag = models.ForeignKey(SafeTag)
    number = models.IntegerField(default=0)

    def __str__(self):
        return self.tag.tag

    class Meta:
        db_table = "cache_report_safe_tag"


class ReportUnsafeTag(models.Model):
    report = models.ForeignKey(ReportComponent, related_name='unsafe_tags')
    tag = models.ForeignKey(UnsafeTag, related_name='+')
    number = models.IntegerField(default=0)

    def __str__(self):
        return self.tag.tag

    class Meta:
        db_table = 'cache_report_unsafe_tag'


class MarkSafeTag(models.Model):
    mark_version = models.ForeignKey(MarkSafeHistory, related_name='tags')
    tag = models.ForeignKey(SafeTag, related_name='+')

    def __str__(self):
        return self.tag.tag

    class Meta:
        db_table = "cache_mark_safe_tag"


class MarkUnsafeTag(models.Model):
    mark_version = models.ForeignKey(MarkUnsafeHistory, related_name='tags')
    tag = models.ForeignKey(UnsafeTag, related_name='+')

    def __str__(self):
        return self.tag.tag

    class Meta:
        db_table = 'cache_mark_unsafe_tag'


class UnsafeReportTag(models.Model):
    report = models.ForeignKey(ReportUnsafe, related_name='tags')
    tag = models.ForeignKey(UnsafeTag)
    number = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'cache_unsafe_report_unsafe_tag'


class SafeReportTag(models.Model):
    report = models.ForeignKey(ReportSafe, related_name='tags')
    tag = models.ForeignKey(SafeTag)
    number = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'cache_safe_report_safe_tag'


# For unknowns
class MarkUnknown(Mark):
    component = models.ForeignKey(Component, on_delete=models.PROTECT)
    function = models.TextField()
    is_regexp = models.BooleanField(default=True)
    problem_pattern = models.CharField(max_length=15)
    link = models.URLField(null=True)

    class Meta:
        db_table = 'mark_unknown'
        index_together = ['component', 'problem_pattern']


class MarkUnknownHistory(MarkHistory):
    mark = models.ForeignKey(MarkUnknown, related_name='versions')
    function = models.TextField()
    is_regexp = models.BooleanField(default=True)
    problem_pattern = models.CharField(max_length=100)
    link = models.URLField(null=True)

    class Meta:
        db_table = 'mark_unknown_history'


class MarkUnknownReport(models.Model):
    mark = models.ForeignKey(MarkUnknown, related_name='markreport_set')
    report = models.ForeignKey(ReportUnknown, related_name='markreport_set')
    problem = models.ForeignKey(UnknownProblem, on_delete=models.PROTECT)
    type = models.CharField(max_length=1, choices=ASSOCIATION_TYPE, default='0')
    author = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = 'cache_mark_unknown_report'


class UnknownAssociationLike(models.Model):
    association = models.ForeignKey(MarkUnknownReport)
    author = models.ForeignKey(User)
    dislike = models.BooleanField(default=False)

    class Meta:
        db_table = "mark_unknown_association_like"


class ComponentMarkUnknownProblem(models.Model):
    report = models.ForeignKey(ReportComponent, related_name='mark_unknowns_cache')
    component = models.ForeignKey(Component, related_name='+', on_delete=models.PROTECT)
    problem = models.ForeignKey(UnknownProblem, null=True, on_delete=models.PROTECT)
    number = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'cache_report_component_mark_unknown_problem'


class MarkAssociationsChanges(models.Model):
    user = models.ForeignKey(User)
    identifier = models.CharField(max_length=255, unique=True)
    table_data = models.TextField()

    class Meta:
        db_table = 'cache_mark_associations_changes'


class ErrorTraceConvertionCache(models.Model):
    unsafe = models.ForeignKey(ReportUnsafe)
    function = models.ForeignKey(MarkUnsafeConvert)
    converted = models.ForeignKey(ConvertedTraces)

    class Meta:
        db_table = 'cache_error_trace_converted'


class SafeTagAccess(models.Model):
    user = models.ForeignKey(User)
    tag = models.ForeignKey(SafeTag)
    modification = models.BooleanField(default=False)
    child_creation = models.BooleanField(default=False)

    class Meta:
        db_table = 'marks_safe_tag_access'


class UnsafeTagAccess(models.Model):
    user = models.ForeignKey(User)
    tag = models.ForeignKey(UnsafeTag)
    modification = models.BooleanField(default=False)
    child_creation = models.BooleanField(default=False)

    class Meta:
        db_table = 'marks_unsafe_tag_access'
