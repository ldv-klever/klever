from django.utils.translation import ugettext as _

FORMAT = 1

JOB_CLASSES = (
    ('ker', _('Verification of Linux kernel modules')),
    ('git', _('Verification of commits to Linux kernel Git repositories')),
    ('cpr', _('Verification of C programs')),
)

JOB_ROLES = (
    ('none', _('No access')),
    ('obs', _('Observer')),
    ('exp', _('Expert')),
    ('obop', _('Observer and Operator')),
    ('exop', _('Expert and Operator')),
)