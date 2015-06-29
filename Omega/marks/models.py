from django.db import models
from django.utils.translation import ugettext as _
from django.contrib.auth.models import User
from Omega.vars import FORMAT, JOB_CLASSES


class Mark(models.Model):
    id = models.AutoField(primary_key=True)
    identifier = models.CharField(max_length=255)
    format = models.PositiveSmallIntegerField(default=FORMAT)
    version = models.PositiveSmallIntegerField(default=1)
    author = models.ForeignKey(User)
    job_type = models.CharField(
        max_length=3,
        choices=JOB_CLASSES,
        default='ker',
        verbose_name=_('job class')
    )
    STATUS = (
        ('0', _('Unreported')),
        ('1', _('Reported')),
        ('2', _('Fixed')),
        ('3', _('Rejected')),
    )
    status = models.CharField(max_length=1, choices=STATUS, default='0')
    is_modifiable = models.BooleanField()
    change_date = models.DateTimeField(auto_now=True)
    comment = models.TextField()

    def __str__(self):
        return self.id

    class Meta:
        db_table = 'mark'


class SafeTag(models.Model):
    tag = models.CharField(max_length=1023)

    class Meta:
        db_table = "mark_safe_tag"


class UnsafeTag(models.Model):
    tag = models.CharField(max_length=1023)

    class Meta:
        db_table = "mark_unsafe_tag"


class UnknownProblem(models.Model):
    name = models.CharField(max_length=1023)

    class Meta:
        db_table = 'cache_mark_unknown_problem'
