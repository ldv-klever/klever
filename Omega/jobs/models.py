from django.db import models
from django.utils.translation import ugettext as _
from Omega.formatChecker import RestrictedFileField
from django.contrib.auth.models import User
from marks.models import UnsafeTag, SafeTag
from reports.models import Component
from Omega.vars import FORMAT, JOB_CLASSES, JOB_ROLES
from jobs.job_model import Job


class JobFile(models.Model):
    job = models.ForeignKey(Job, related_name='files')
    file = RestrictedFileField(
        upload_to='JobFiles',
        max_upload_size=104857600,
        null=False
    )

    class Meta:
        db_table = 'job_file'


class JobUserRole(models.Model):
    user = models.ForeignKey(User, related_name='+')
    job = models.ForeignKey(Job)
    role = models.CharField(max_length=4, choices=JOB_ROLES)

    class Meta:
        db_table = 'user_job_role'


class JobVerdict(models.Model):
    job = models.OneToOneField(Job)
    unsafe = models.IntegerField(default=0)
    unsafe_bug = models.IntegerField(default=0)
    unsafe_target_bug = models.IntegerField(default=0)
    unsafe_false_positive = models.IntegerField(default=0)
    unsafe_unknown = models.IntegerField(default=0)
    unsafe_unassociated = models.IntegerField(default=0)
    unsafe_inconclusive = models.IntegerField(default=0)
    safe = models.IntegerField(default=0)
    safe_missed_bug = models.IntegerField(default=0)
    safe_incorrect_proof = models.IntegerField(default=0)
    safe_unknown = models.IntegerField(default=0)
    safe_unassociated = models.IntegerField(default=0)
    safe_inconclusive = models.IntegerField(default=0)
    unknown = models.IntegerField(default=0)

    class Meta:
        db_table = "cache_job_verdict"


class JobMarkSafeTag(models.Model):
    job = models.ForeignKey(Job, related_name='safe_tags')
    mark_safe_tag = models.ForeignKey(SafeTag, related_name='+')
    number = models.IntegerField(default=0)

    class Meta:
        db_table = "cache_job_mark_safe_tag"


class JobMarkUnsafeTag(models.Model):
    job = models.ForeignKey(Job, related_name='unsafe_tags')
    mark_unsafe_tag = models.ForeignKey(UnsafeTag, related_name='+')
    number = models.IntegerField(default=0)

    class Meta:
        db_table = 'cache_job_mark_unsafe_tag'


class JobComponentUnknown(models.Model):
    job = models.ForeignKey(Job)
    component = models.ForeignKey(Component, related_name='+')

    class Meta:
        db_table = 'cache_job_component_unknown'
