#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.fields import JSONField
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import ugettext_lazy as _

from rest_framework.authtoken.models import Token

from bridge.vars import LANGUAGES, USER_ROLES, DATAFORMAT, VIEW_TYPES


class User(AbstractUser):
    accuracy = models.SmallIntegerField(
        verbose_name=_('The number of significant figures'), default=settings.DEF_USER['accuracy'],
        help_text=_('This setting is used just for the human-readable data format')
    )
    data_format = models.CharField(
        verbose_name=_('Data format'), max_length=3, choices=DATAFORMAT, default=settings.DEF_USER['dataformat'],
        help_text=_('Most of dates are not updated automatically, so human-readable dates '
                    'could become outdated until you reload page by hand')
    )
    language = models.CharField(
        verbose_name=_('Language'), max_length=2, choices=LANGUAGES, default=settings.DEF_USER['language']
    )
    role = models.CharField(verbose_name=_('Role'), max_length=1, choices=USER_ROLES, default=USER_ROLES[0][0])
    timezone = models.CharField(verbose_name=_('Time zone'), max_length=255, default=settings.DEF_USER['timezone'])
    assumptions = models.BooleanField(
        verbose_name=_("Error trace assumptions"), default=settings.DEF_USER['assumptions'],
        help_text=_('This setting turns on visualization of error trace assumptions. '
                    'This can take very much time for big error traces.')
    )
    triangles = models.BooleanField(
        verbose_name=_('Error trace closing triangles'), default=settings.DEF_USER['triangles'],
        help_text=_('This setting turns on visualization of error trace closing triangles at the end of each thread.')
    )
    coverage_data = models.BooleanField(
        verbose_name=_("Coverage data"), default=settings.DEF_USER['coverage_data'],
        help_text=_('This setting turns on visualization of coverage data and its statistic.')
    )
    default_threshold = models.FloatField(
        verbose_name=_('Default unsafe marks threshold'), default=0,
        help_text=_('This setting sets default unsafe marks threshold on its creation')
    )
    declarations_number = models.PositiveIntegerField(
        verbose_name=_('Number of declarations in error trace'), default=settings.DEF_USER['declarations_number'],
        help_text=_('Error trace declarations number threshold that should be opened by default')
    )
    notes_level = models.PositiveIntegerField(
        verbose_name=_('Error trace notes level'), default=settings.DEF_USER['notes_level'],
        help_text=_('Error trace notes with level higher than selected one will be ignored')
    )

    # Do not include remote fields here
    REQUIRED_FIELDS = ['email', 'first_name', 'last_name']

    def get_full_name(self):
        return super().get_full_name() or self.username

    @property
    def is_manager(self):
        return self.role == USER_ROLES[2][0]

    @property
    def is_expert(self):
        return self.role == USER_ROLES[3][0]

    @property
    def is_service(self):
        return self.role == USER_ROLES[4][0]

    @property
    def can_create_jobs(self):
        return self.role not in {USER_ROLES[0][0], USER_ROLES[4][0]}

    @property
    def default_threshold_percentage(self):
        return round(self.default_threshold * 100)

    class Meta(AbstractUser.Meta):
        swappable = 'AUTH_USER_MODEL'
        db_table = 'users'


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_auth_token(sender, instance=None, **kwargs):
    if instance.role == USER_ROLES[4][0]:
        Token.objects.get_or_create(user=instance)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def set_admin_role(sender, instance=None, **kwargs):
    if (instance.is_superuser or instance.is_staff) and instance.role != USER_ROLES[2][0]:
        instance.role = USER_ROLES[2][0]
        instance.save()


class DataView(models.Model):
    author = models.ForeignKey(User, models.CASCADE, related_name='views')
    type = models.CharField(max_length=2, choices=VIEW_TYPES)
    shared = models.BooleanField(default=False)
    name = models.CharField(max_length=255)
    view = JSONField()

    def __str__(self):
        return self.name

    class Meta:
        db_table = "data_view"


class PreferableView(models.Model):
    user = models.ForeignKey(User, models.CASCADE)
    view = models.ForeignKey(DataView, models.CASCADE, related_name='+')

    def __str__(self):
        return self.view.name

    class Meta:
        db_table = "user_preferable_view"


class SchedulerUser(models.Model):
    user = models.OneToOneField(User, models.CASCADE)
    login = models.CharField(verbose_name=_('Username'), max_length=128)
    password = models.CharField(max_length=128)

    def __str__(self):
        return '%s (%s)' % (self.login, self.user)

    class Meta:
        db_table = 'scheduler_user'
