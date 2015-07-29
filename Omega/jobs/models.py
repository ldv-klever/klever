from django.db import models
from django.contrib.auth.models import User
from Omega.formatChecker import RestrictedFileField
from Omega.vars import JOB_ROLES
from jobs.job_model import Job
from marks.models import UnsafeTag, SafeTag, UnknownProblem
from reports.models import Component, Resource, ReportComponent


class File(models.Model):
    job = models.ForeignKey(Job, related_name='files')
    hash_sum = models.CharField(max_length=255)
    file = RestrictedFileField(
        upload_to='JobFiles',
        max_upload_size=104857600,
        null=False
    )

    class Meta:
        db_table = 'file'

    def __str__(self):
        return self.hash_sum


class FileSystem(models.Model):
    job = models.ForeignKey(Job, related_name='file_set')
    file = models.ForeignKey(File, related_name='+', null=True, blank=True)
    name = models.CharField(max_length=150)
    parent = models.ForeignKey('self', null=True, blank=True,
                               related_name='children_set')

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'file_system'


class JobFile(models.Model):
    file = models.ForeignKey(FileSystem)

    class Meta:
        db_table = 'job_file'


class UserRole(models.Model):
    user = models.ForeignKey(User, related_name='+')
    job = models.ForeignKey(Job)
    role = models.CharField(max_length=1, choices=JOB_ROLES)

    class Meta:
        db_table = 'user_job_role'


class Verdict(models.Model):
    report = models.OneToOneField(ReportComponent)
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


class ComponentUnknown(models.Model):
    report = models.ForeignKey(ReportComponent)
    component = models.ForeignKey(Component, related_name='+')
    number = models.IntegerField(default=0)

    class Meta:
        db_table = 'cache_job_component_unknown'


class ComponentMarkUnknownProblem(models.Model):
    report = models.ForeignKey(ReportComponent)
    component = models.ForeignKey(Component)
    problem = models.ForeignKey(UnknownProblem, null=True, blank=True,
                                on_delete=models.SET_NULL)
    number = models.IntegerField(default=0)

    class Meta:
        db_table = 'cache_job_component_mark_unknown_problem'


class ComponentResource(models.Model):
    report = models.ForeignKey(ReportComponent)
    component = models.ForeignKey(Component, null=True, blank=True,
                                  on_delete=models.SET_NULL)
    resource = models.ForeignKey(Resource)

    class Meta:
        db_table = 'cache_job_component_resource'
