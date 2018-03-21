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
from django.contrib.auth.models import User
from django.db.models.signals import pre_delete
from django.dispatch.dispatcher import receiver
from bridge.vars import FORMAT, JOB_CLASSES, JOB_ROLES, JOB_STATUS, JOB_WEIGHT

JOBFILE_DIR = 'Job'


class JobFile(models.Model):
    hash_sum = models.CharField(max_length=255, db_index=True)
    file = models.FileField(upload_to=JOBFILE_DIR, null=False)

    class Meta:
        db_table = 'job_file'

    def __str__(self):
        return self.hash_sum


@receiver(pre_delete, sender=JobFile)
def jobfile_delete_signal(**kwargs):
    file = kwargs['instance']
    storage, path = file.file.storage, file.file.path
    try:
        storage.delete(path)
    except PermissionError:
        pass


class Job(models.Model):
    name = models.CharField(max_length=150, unique=True, db_index=True)
    change_author = models.ForeignKey(User, blank=True, null=True, on_delete=models.SET_NULL, related_name='+')
    format = models.PositiveSmallIntegerField(default=FORMAT)
    type = models.CharField(max_length=1, choices=JOB_CLASSES, default='0')
    version = models.PositiveSmallIntegerField(default=1)
    change_date = models.DateTimeField(auto_now=True)
    identifier = models.CharField(max_length=255, unique=True, db_index=True)
    parent = models.ForeignKey('self', null=True, related_name='children')
    status = models.CharField(max_length=1, choices=JOB_STATUS, default=JOB_STATUS[0][0])
    weight = models.CharField(max_length=1, choices=JOB_WEIGHT, default=JOB_WEIGHT[0][0])
    safe_marks = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'job'


class RunHistory(models.Model):
    job = models.ForeignKey(Job)
    operator = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name='+')
    configuration = models.ForeignKey(JobFile)
    date = models.DateTimeField()
    status = models.CharField(choices=JOB_STATUS, max_length=1, default=JOB_STATUS[1][0])

    class Meta:
        db_table = 'job_run_history'


class JobHistory(models.Model):
    job = models.ForeignKey(Job, related_name='versions')
    change_author = models.ForeignKey(User, blank=True, null=True, on_delete=models.SET_NULL, related_name='+')
    version = models.PositiveSmallIntegerField()
    change_date = models.DateTimeField()
    comment = models.CharField(max_length=255, default='')
    parent = models.ForeignKey(Job, null=True, on_delete=models.SET_NULL, related_name='+')
    global_role = models.CharField(max_length=1, choices=JOB_ROLES, default='0')
    description = models.TextField(default='')

    class Meta:
        db_table = 'jobhistory'
        index_together = ['job', 'version']


class FileSystem(models.Model):
    job = models.ForeignKey(JobHistory)
    file = models.ForeignKey(JobFile, null=True)
    name = models.CharField(max_length=128)
    parent = models.ForeignKey('self', null=True, related_name='children')

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'file_system'


class UserRole(models.Model):
    user = models.ForeignKey(User)
    job = models.ForeignKey(JobHistory)
    role = models.CharField(max_length=1, choices=JOB_ROLES)

    class Meta:
        db_table = 'user_job_role'
