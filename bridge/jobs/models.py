from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import pre_delete
from django.dispatch.dispatcher import receiver
from bridge.vars import FORMAT, JOB_CLASSES, JOB_ROLES, JOB_STATUS


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
    parent = models.ForeignKey('self', null=True, on_delete=models.PROTECT, related_name='children')
    status = models.CharField(max_length=1, choices=JOB_STATUS, default='0')

    class Meta:
        db_table = 'job'


class RunHistory(models.Model):
    job = models.ForeignKey(Job)
    configuration = models.ForeignKey(File)
    date = models.DateTimeField(auto_now=True)
    status = models.CharField(choices=JOB_STATUS, max_length=1)

    class Meta:
        db_table = 'job_run_history'


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


# When you add this model to any other, check delete() method for all uses of File
class File(models.Model):
    hash_sum = models.CharField(max_length=255)
    file = models.FileField(upload_to=JOBFILE_DIR, null=False)

    class Meta:
        db_table = 'file'

    def __str__(self):
        return self.hash_sum


@receiver(pre_delete, sender=File)
def file_delete(**kwargs):
    file = kwargs['instance']
    storage, path = file.file.storage, file.file.path
    storage.delete(path)


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
