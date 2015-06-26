from django.db import models
from django.utils.translation import ugettext as _

class Mark(models.Model):
    id = models.AutoField(primary_key=True)
    identifier = models.CharField(max_length=255)
    format = models.PositiveSmallIntegerField()
    version = models.PositiveSmallIntegerField()
    # TODO: author_id

    CLASS = (
        ('0', _('linux kernel modules')),
        ('1', _('linux kernel git repository commits')),
        ('2', _('c programs')),
    )
    job_class = models.CharField(max_length=1, choices=CLASS, default='0')
    
    STATUS = (
        ('0', _('Unreported')),
        ('1', _('Reported')),
        ('2', _('Fixed')),
        ('3', _('Rejected')),
    )
    status = models.CharField(max_length=1, choices=STATUS, default='0')
    
    is_modifiable = models.BooleanField()
    change_date = models.DateTimeField()
    comment = models.TextField(null=True)

    def __str__(self):
        return self.id


