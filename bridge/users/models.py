#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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

from django.db import models
from django.conf import settings
from django.contrib.auth.models import User

from bridge.vars import LANGUAGES, USER_ROLES, DATAFORMAT, VIEW_TYPES


class Extended(models.Model):
    user = models.OneToOneField(User, models.CASCADE)
    accuracy = models.SmallIntegerField(default=settings.DEF_USER['accuracy'])
    data_format = models.CharField(max_length=3, choices=DATAFORMAT, default=settings.DEF_USER['dataformat'])
    language = models.CharField(max_length=2, choices=LANGUAGES, default=settings.DEF_USER['language'])
    role = models.CharField(max_length=1, choices=USER_ROLES, default='0')
    timezone = models.CharField(max_length=255, default=settings.DEF_USER['timezone'])
    assumptions = models.BooleanField(default=settings.DEF_USER['assumptions'])
    triangles = models.BooleanField(default=settings.DEF_USER['triangles'])
    coverage_data = models.BooleanField(default=settings.DEF_USER['coverage_data'])

    def __str__(self):
        return self.user.username

    class Meta:
        db_table = 'user_extended'


class View(models.Model):
    author = models.ForeignKey(User, models.CASCADE)
    type = models.CharField(max_length=2, choices=VIEW_TYPES, default=VIEW_TYPES[1][0])
    shared = models.BooleanField(default=False)
    name = models.CharField(max_length=255)
    view = models.TextField()

    def __str__(self):
        return self.name

    class Meta:
        db_table = "view"


class PreferableView(models.Model):
    user = models.ForeignKey(User, models.CASCADE)
    view = models.ForeignKey(View, models.CASCADE, related_name='+')

    def __str__(self):
        return self.view.name

    class Meta:
        db_table = "user_preferable_view"


class Notifications(models.Model):
    user = models.OneToOneField(User, models.CASCADE)
    settings = models.CharField(max_length=255)
    self_ntf = models.BooleanField(default=True)
