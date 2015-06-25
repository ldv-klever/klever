from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import ugettext as _


class UserExtended(models.Model):
    LANGUAGES = (
        ('en', 'English'),
        ('ru', 'Русский'),
    )
    USER_ROLES = (
        ('none', _('No access')),
        ('prod', _('Producer')),
        ('man', _('Manager')),
        ('prmn', _('Producer and Manager')),
        ('adm', _('Administrator')),
    )
    user = models.OneToOneField(User)
    change_date = models.DateTimeField(auto_now=True)
    change_author = models.ForeignKey(User, related_name='+')
    accuracy = models.SmallIntegerField(default=2)
    language = models.CharField(max_length=2, choices=LANGUAGES, default='en')
    role = models.CharField(max_length=4, choices=USER_ROLES, default='none')
    timezone = models.CharField(max_length=255)

    def __str__(self):
        return self.user.username
