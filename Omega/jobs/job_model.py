from django.db import models
from django.utils.translation import ugettext as _
from django.contrib.auth.models import User
from Omega.vars import FORMAT, JOB_CLASSES, JOB_ROLES


class Job(models.Model):
    format = models.PositiveSmallIntegerField(default=FORMAT)
    version = models.PositiveSmallIntegerField(default=1)
    identifier = models.CharField(max_length=255, unique=True)
    change_author = models.ForeignKey(User, blank=True, null=True,
                                      on_delete=models.SET_NULL)
    change_date = models.DateTimeField(auto_now=True)
    type = models.CharField(
        max_length=3,
        choices=JOB_CLASSES,
        default='ker',
        verbose_name=_('job class')
    )
    parent = models.ForeignKey('self', null=True, blank=True,
                               on_delete=models.PROTECT, related_name='+')
    name = models.CharField(max_length=150, default=_('Verification job'))
    global_role = models.CharField(max_length=4, choices=JOB_ROLES,
                                   default='none')
    configuration = models.TextField()
    comment = models.TextField()

    def __str__(self):
        return str(self.pk)

    class Meta:
        db_table = 'job'