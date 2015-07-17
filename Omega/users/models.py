from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy as _
from Omega.vars import LANGUAGES, USER_ROLES, VIEW_TYPES


class Extended(models.Model):
    DATAFORMAT = (
        ('row', _('Row')),
        ('hum', _('Human-readable')),
    )
    user = models.OneToOneField(User)
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    change_date = models.DateTimeField(auto_now=True)
    change_author = models.ForeignKey(User, related_name='+')
    accuracy = models.SmallIntegerField(default=2)
    data_format = models.CharField(max_length=3, choices=DATAFORMAT,
                                   default='row')
    language = models.CharField(max_length=2, choices=LANGUAGES, default='en')
    role = models.CharField(max_length=1, choices=USER_ROLES, default='0')
    timezone = models.CharField(max_length=255)

    def __str__(self):
        return self.user.username

    class Meta:
        db_table = 'user_extended'


class View(models.Model):
    author = models.ForeignKey(User)
    type = models.CharField(max_length=1, choices=VIEW_TYPES, default='1')
    name = models.CharField(max_length=255, blank=True)
    view = models.TextField()

    def __str__(self):
        return self.name

    class Meta:
        db_table = "view"


class PreferableView(models.Model):
    user = models.ForeignKey(User)
    view = models.ForeignKey(View, related_name='+', on_delete=models.CASCADE)

    def __str__(self):
        return self.view.name

    class Meta:
        db_table = "user_preferable_view"
