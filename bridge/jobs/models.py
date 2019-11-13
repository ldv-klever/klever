#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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

import uuid
from django.db import models
from django.db.models.signals import post_delete
from mptt.models import MPTTModel, TreeForeignKey

from bridge.vars import JOB_ROLES, JOB_STATUS, JOB_WEIGHT, COVERAGE_DETAILS
from bridge.utils import WithFilesMixin, remove_instance_files

from users.models import User

JOBFILE_DIR = 'Job'


class JobFile(WithFilesMixin, models.Model):
    hash_sum = models.CharField(max_length=255, db_index=True)
    file = models.FileField(upload_to=JOBFILE_DIR, null=False)

    class Meta:
        db_table = 'job_file'

    def __str__(self):
        return self.hash_sum


class Job(MPTTModel):
    identifier = models.UUIDField(unique=True, db_index=True, default=uuid.uuid4)
    name = models.CharField(max_length=150, unique=True, db_index=True)
    parent = TreeForeignKey('self', models.CASCADE, null=True, blank=True, related_name='children')
    version = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=1, choices=JOB_STATUS, default=JOB_STATUS[0][0])
    weight = models.CharField(max_length=1, choices=JOB_WEIGHT, default=JOB_WEIGHT[0][0])
    coverage_details = models.CharField(max_length=1, choices=COVERAGE_DETAILS,
                                        default=COVERAGE_DETAILS[0][0])
    author = models.ForeignKey(User, models.SET_NULL, blank=True, null=True, related_name='jobs')

    def __str__(self):
        return self.name

    @property
    def is_lightweight(self):
        return self.weight == JOB_WEIGHT[1][0]

    class MPTTMeta:
        order_insertion_by = ['name']

    class Meta:
        db_table = 'job'


class RunHistory(models.Model):
    job = models.ForeignKey(Job, models.CASCADE, related_name='run_history')
    operator = models.ForeignKey(User, models.SET_NULL, null=True, related_name='+')
    date = models.DateTimeField(db_index=True)
    status = models.CharField(choices=JOB_STATUS, max_length=1, default=JOB_STATUS[1][0])
    configuration = models.ForeignKey(JobFile, models.CASCADE)

    class Meta:
        db_table = 'job_run_history'


class JobHistory(models.Model):
    job = models.ForeignKey(Job, models.CASCADE, related_name='versions')
    version = models.PositiveSmallIntegerField()
    change_author = models.ForeignKey(User, models.SET_NULL, blank=True, null=True, related_name='+')
    change_date = models.DateTimeField()
    comment = models.CharField(max_length=255, default='', blank=True)

    name = models.CharField(max_length=150)
    global_role = models.CharField(max_length=1, choices=JOB_ROLES, default=JOB_ROLES[0][0])

    class Meta:
        db_table = 'jobhistory'
        index_together = ['job', 'version']
        ordering = ('-version',)


class FileSystem(models.Model):
    job_version = models.ForeignKey(JobHistory, models.CASCADE, related_name='files')
    name = models.CharField(max_length=1024)
    file = models.ForeignKey(JobFile, models.CASCADE)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'file_system'


class UserRole(models.Model):
    job_version = models.ForeignKey(JobHistory, models.CASCADE)
    user = models.ForeignKey(User, models.CASCADE)
    role = models.CharField(max_length=1, choices=JOB_ROLES)

    class Meta:
        db_table = 'user_job_role'


post_delete.connect(remove_instance_files, sender=JobFile)
