from django.db import models
from django.contrib.auth.models import User
from Omega.vars import FORMAT, JOB_CLASSES, JOB_ROLES, JOB_STATUS


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
    parent = models.ForeignKey('self', null=True, blank=True,
                               on_delete=models.PROTECT,
                               related_name='children_set')

    class Meta:
        db_table = 'job'


class JobHistory(JobBase):
    job = models.ForeignKey(Job)
    version = models.PositiveSmallIntegerField()
    change_date = models.DateTimeField()
    comment = models.CharField(max_length=255, default='')
    parent = models.ForeignKey(Job, null=True, blank=True,
                               on_delete=models.SET_NULL, related_name='+')
    global_role = models.CharField(max_length=1, choices=JOB_ROLES, default='0')
    description = models.TextField(default='')

    class Meta:
        db_table = 'jobhistory'


class JobStatus(models.Model):
    job = models.OneToOneField(Job)
    status = models.CharField(max_length=1, choices=JOB_STATUS, default='0')

    class Meta:
        db_table = 'jobstatus'

    def __str__(self):
        return self.job.name
