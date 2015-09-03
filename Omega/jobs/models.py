from django.db import models
from django.contrib.auth.models import User
from Omega.formatChecker import RestrictedFileField
from Omega.vars import FORMAT, JOB_CLASSES, JOB_ROLES, JOB_STATUS


JOBFILE_DIR = 'Files'


class JobBase(models.Model):
    name = models.CharField(max_length=150)
    change_author = models.ForeignKey(User, blank=True, null=True,
                                      on_delete=models.SET_NULL,
                                      related_name="%(class)s")

    class Meta:
        abstract = True


class Job(JobBase):
    format = models.PositiveSmallIntegerField(default=FORMAT)
    type = models.CharField(max_length=1, choices=JOB_CLASSES, default='0')
    version = models.PositiveSmallIntegerField(default=1)
    change_date = models.DateTimeField(auto_now=True)
    identifier = models.CharField(max_length=255, unique=True)
    parent = models.ForeignKey('self', null=True, on_delete=models.PROTECT,
                               related_name='children')
    status = models.CharField(max_length=1, choices=JOB_STATUS, default='0')

    class Meta:
        db_table = 'job'


class JobHistory(JobBase):
    job = models.ForeignKey(Job, related_name='versions')
    version = models.PositiveSmallIntegerField()
    change_date = models.DateTimeField()
    comment = models.CharField(max_length=255, default='')
    parent = models.ForeignKey(Job, null=True, on_delete=models.SET_NULL,
                               related_name='+')
    global_role = models.CharField(max_length=1, choices=JOB_ROLES, default='0')
    description = models.TextField(default='')

    class Meta:
        db_table = 'jobhistory'


class ReportRoot(models.Model):
    user = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    job = models.OneToOneField(Job)
    last_request_date = models.DateTimeField()

    class Meta:
        db_table = 'report_root'


class File(models.Model):
    hash_sum = models.CharField(max_length=255)
    file = RestrictedFileField(
        upload_to=JOBFILE_DIR,
        max_upload_size=104857600,
        null=False
    )

    class Meta:
        db_table = 'file'

    def __str__(self):
        return self.hash_sum


class FileSystem(models.Model):
    job = models.ForeignKey(JobHistory)
    file = models.ForeignKey(File, null=True)
    name = models.CharField(max_length=150)
    parent = models.ForeignKey('self', null=True, related_name='children')

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'file_system'


class UserRole(models.Model):
    user = models.ForeignKey(User, related_name='+')
    job = models.ForeignKey(JobHistory)
    role = models.CharField(max_length=1, choices=JOB_ROLES)

    class Meta:
        db_table = 'user_job_role'
