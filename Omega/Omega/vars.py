from django.utils.translation import ugettext as _

FORMAT = 1

JOB_CLASSES = (
    ('ker', _('Verification of Linux kernel modules')),
    ('git', _('Verification of commits to Linux kernel Git repositories')),
    ('cpr', _('Verification of C programs')),
)

JOB_ROLES = (
    ('none', _('no access')),
    ('obs', _('observer')),
    ('exp', _('expert')),
    ('obop', _('observer and operator')),
    ('exop', _('expert and operator')),
)