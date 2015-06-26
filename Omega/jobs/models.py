from django.db import models
from django.utils.translation import ugettext as _
from Omega.formatChecker import RestrictedFileField
from django.contrib.auth.models import User


JOB_ROLES = (
    ('none', _('no access')),
    ('obs', _('observer')),
    ('exp', _('expert')),
    ('obop', _('observer and operator')),
    ('exop', _('expert and operator')),
)

JOB_CLASSES = (
    ('ker', _('Verification of Linux kernel modules')),
    ('git', _('Verification of commits to Linux kernel Git repositories')),
    ('cpr', _('Verification of C programs')),
)


class Job(models.Model):
    format = models.SmallIntegerField(default=1)
    identifier = models.CharField(max_length=255, unique=True)
    version = models.SmallIntegerField(default=1)
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
                               on_delete=models.SET_NULL)
    name = models.CharField(max_length=1023, default=_('Verification job'))
    global_roles = models.CharField(max_length=4, choices=JOB_ROLES,
                                    default='none')
    config = models.TextField()
    comment = models.TextField()

    class Meta:
        db_table = 'job'


class JobFile(models.Model):
    job = models.ForeignKey(Job)
    file = RestrictedFileField(
        upload_to='JobFiles',
        max_upload_size=104857600,
        null=False
    )

    class Meta:
        db_table = 'job_file'


class UserJobRole(models.Model):
    user = models.ForeignKey(User)
    job = models.ForeignKey(Job)
    role = models.CharField(max_length=4, choices=JOB_ROLES)

    class Meta:
        db_table = 'user_job_role'
