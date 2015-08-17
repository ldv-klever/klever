from django.db import models
from django.contrib.auth.models import User
from Omega.vars import FORMAT, JOB_CLASSES, MARK_STATUS, MARK_UNSAFE, MARK_SAFE
from reports.models import Attr, ReportUnsafe, ReportSafe
from jobs.models import Job


# Tables with functions
class MarkUnsafeConvert(models.Model):
    name = models.CharField(max_length=30)
    description = models.CharField(max_length=1000)

    def __str__(self):
        return self.name


class MarkUnsafeCompare(models.Model):
    hash_sum = models.CharField(max_length=100)
    name = models.CharField(max_length=30)
    body = models.TextField()
    description = models.CharField(max_length=1000)

    def __str__(self):
        return self.name


class MarkDefaultFunctions(models.Model):
    convert = models.OneToOneField(MarkUnsafeConvert)
    compare = models.OneToOneField(MarkUnsafeCompare)

    def __str__(self):
        return "Default functions"


# Abstract tables
class Mark(models.Model):
    identifier = models.CharField(max_length=255, unique=True)
    job = models.ForeignKey(Job, null=True, on_delete=models.SET_NULL,
                            related_name="%(class)s")
    format = models.PositiveSmallIntegerField(default=FORMAT)
    version = models.PositiveSmallIntegerField(default=1)
    type = models.CharField(max_length=1, choices=JOB_CLASSES, default='0')
    author = models.ForeignKey(User, related_name="%(class)s", null=True,
                               on_delete=models.SET_NULL)
    status = models.CharField(max_length=1, choices=MARK_STATUS, default='0')
    is_modifiable = models.BooleanField(default=True)
    change_date = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.identifier

    class Meta:
        abstract = True


class MarkHistory(models.Model):
    version = models.PositiveSmallIntegerField()
    author = models.ForeignKey(User, null=True, on_delete=models.SET_NULL,
                               related_name="%(class)s")
    status = models.CharField(max_length=1, choices=MARK_STATUS, default='0')
    change_date = models.DateTimeField()
    comment = models.TextField()

    class Meta:
        abstract = True


# Safes tables
class MarkSafe(Mark):
    verdict = models.CharField(max_length=1, choices=MARK_SAFE, default='0')


class MarkSafeHistory(MarkHistory):
    mark = models.ForeignKey(MarkSafe)
    verdict = models.CharField(max_length=1, choices=MARK_SAFE)


class MarkSafeAttr(models.Model):
    mark = models.ForeignKey(MarkSafeHistory)
    attr = models.ForeignKey(Attr)
    is_compare = models.BooleanField(default=True)


class MarkSafeReport(models.Model):
    mark = models.ForeignKey(MarkSafe)
    report = models.ForeignKey(ReportSafe)

    class Meta:
        db_table = "cache_mark_safe_report"


# Unsafes tables
class MarkUnsafe(Mark):
    verdict = models.CharField(max_length=1, choices=MARK_UNSAFE, default='0')
    function = models.ForeignKey(MarkUnsafeCompare)
    error_trace = models.BinaryField(null=True)


class MarkUnsafeHistory(MarkHistory):
    mark = models.ForeignKey(MarkUnsafe)
    verdict = models.CharField(max_length=1, choices=MARK_UNSAFE)
    function = models.ForeignKey(MarkUnsafeCompare)


class MarkUnsafeAttr(models.Model):
    mark = models.ForeignKey(MarkUnsafeHistory)
    attr = models.ForeignKey(Attr)
    is_compare = models.BooleanField(default=True)


class MarkUnsafeReport(models.Model):
    mark = models.ForeignKey(MarkUnsafe)
    report = models.ForeignKey(ReportUnsafe)
    result = models.FloatField()
    broken = models.BooleanField(default=False)

    class Meta:
        db_table = "cache_mark_unsafe_report"


# Tags tables
class SafeTag(models.Model):
    tag = models.CharField(max_length=1023)

    class Meta:
        db_table = "mark_safe_tag"


class UnsafeTag(models.Model):
    tag = models.CharField(max_length=1023)

    class Meta:
        db_table = "mark_unsafe_tag"


class MarkSafeTag(models.Model):
    job = models.ForeignKey(Job, related_name='safe_tags')
    tag = models.ForeignKey(SafeTag, related_name='+')
    number = models.IntegerField(default=0)

    def __str__(self):
        return self.tag.tag

    class Meta:
        db_table = "cache_job_mark_safe_tag"


class MarkUnsafeTag(models.Model):
    job = models.ForeignKey(Job, related_name='unsafe_tags')
    tag = models.ForeignKey(UnsafeTag, related_name='+')
    number = models.IntegerField(default=0)

    def __str__(self):
        return self.tag.tag

    class Meta:
        db_table = 'cache_job_mark_unsafe_tag'
