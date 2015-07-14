from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.contrib.auth.models import User
from Omega.vars import FORMAT, JOB_CLASSES, JOB_ROLES


class JobBase(models.Model):
    format = models.PositiveSmallIntegerField(default=FORMAT)
    change_author = models.ForeignKey(User, blank=True, null=True,
                                      on_delete=models.SET_NULL,
                                      related_name="%(class)s")
    name = models.CharField(max_length=150, default=_('Verification job'))
    global_role = models.CharField(max_length=1, choices=JOB_ROLES, default='0')
    configuration = models.TextField()
    comment = models.TextField()
    version = models.PositiveSmallIntegerField(default=1)

    def __str__(self):
        return str(self.pk)

    class Meta:
        abstract=True


class Job(JobBase):
    identifier = models.CharField(max_length=255, unique=True)
    type = models.CharField(
        max_length=1,
        choices=JOB_CLASSES,
        default='0',
        verbose_name=_('job class')
    )
    parent = models.ForeignKey('self', null=True, blank=True,
                               on_delete=models.PROTECT,
                               related_name='children_set')
    change_date = models.DateTimeField(auto_now=True)
    class Meta:
        db_table = 'job'


class JobHistory(JobBase):
    job = models.ForeignKey(Job)
    change_date = models.DateTimeField()
    class Meta:
        db_table = 'jobhistory'
