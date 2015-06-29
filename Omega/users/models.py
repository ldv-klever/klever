from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import ugettext as _


USER_ROLES = (
    ('none', _('No access')),
    ('prod', _('Producer')),
    ('man', _('Manager')),
    ('prmn', _('Producer and Manager')),
    ('adm', _('Administrator')),
)

class Extended(models.Model):
    LANGUAGES = (
        ('en', 'English'),
        ('ru', 'Русский'),
    )
    user = models.OneToOneField(User)
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    change_date = models.DateTimeField(auto_now=True)
    change_author = models.ForeignKey(User, related_name='+')
    accuracy = models.SmallIntegerField(default=2)
    language = models.CharField(max_length=2, choices=LANGUAGES, default='en')
    role = models.CharField(max_length=4, choices=USER_ROLES, default='none')
    timezone = models.CharField(max_length=255)

    def __str__(self):
        return self.user.username

    class Meta:
        db_table = 'user_extended'


class View(models.Model):
    author = models.ForeignKey(User, related_name='+')
    name = models.CharField(max_length=255, blank=True)
    view = models.TextField()

    def __str__(self):
        return self.name

    class Meta:
        db_table = "view"


class PreferableView(models.Model):
    user = models.OneToOneField(User)
    view = models.ForeignKey(View, related_name='+', on_delete=models.CASCADE)

    def __str__(self):
        return self.view.name

    class Meta:
        db_table = "user_preferable_view"
