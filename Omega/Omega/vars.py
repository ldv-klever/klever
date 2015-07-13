from django.utils.translation import ugettext as _

FORMAT = 1

JOB_CLASSES = (
    ('0', _('Verification of Linux kernel modules')),
    ('1', _('Verification of commits to Linux kernel Git repositories')),
    ('2', _('Verification of C programs')),
)

JOB_ROLES = (
    ('0', _('No access')),
    ('1', _('Observer')),
    ('2', _('Expert')),
    ('3', _('Observer and Operator')),
    ('4', _('Expert and Operator')),
)
