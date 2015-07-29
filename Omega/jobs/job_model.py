from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.contrib.auth.models import User
from Omega.vars import FORMAT, JOB_CLASSES, JOB_ROLES, JOB_STATUS


class JobBase(models.Model):
    format = models.PositiveSmallIntegerField(default=FORMAT)
    change_author = models.ForeignKey(User, blank=True, null=True,
                                      on_delete=models.SET_NULL,
                                      related_name="%(class)s")
    name = models.CharField(max_length=150)
    global_role = models.CharField(max_length=1, choices=JOB_ROLES, default='0')
    configuration = models.TextField()
    description = models.TextField()
    version = models.PositiveSmallIntegerField(default=1)

    def __str__(self):
        return str(self.pk)

    class Meta:
        abstract = True


class Job(JobBase):
    type = models.CharField(
        max_length=1,
        choices=JOB_CLASSES,
        default='0'
    )
    parent = models.ForeignKey('self', null=True, blank=True,
                               on_delete=models.PROTECT,
                               related_name='children_set')
    change_date = models.DateTimeField(auto_now=True)
    identifier = models.CharField(max_length=255, unique=True)

    class Meta:
        db_table = 'job'


class JobHistory(JobBase):
    job = models.ForeignKey(Job)
    change_date = models.DateTimeField()
    comment = models.CharField(max_length=255)
    parent = models.ForeignKey(Job, null=True, blank=True,
                               on_delete=models.SET_NULL,
                               related_name='old_children_set')

    class Meta:
        db_table = 'jobhistory'


class JobStatus(models.Model):
    job = models.OneToOneField(Job)
    status = models.CharField(max_length=1, choices=JOB_STATUS, default='0')

    class Meta:
        db_table = 'jobstatus'

    def __str__(self):
        return self.job.name
