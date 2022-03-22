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

import uuid
from django.db import models
from django.db.models.signals import post_delete
from django.template import Template, Context
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from mptt.models import MPTTModel, TreeForeignKey

from bridge.vars import (
    JOB_ROLES, JOB_UPLOAD_STATUS, PRESET_JOB_TYPE, DECISION_STATUS, DECISION_WEIGHT,
    PRIORITY, SCHEDULER_STATUS, SCHEDULER_TYPE
)
from bridge.utils import WithFilesMixin, remove_instance_files

from users.models import User

JOBFILE_DIR = 'JobFile'
UPLOAD_DIR = 'UploadedJobs'


class JobFile(WithFilesMixin, models.Model):
    hash_sum = models.CharField(max_length=255, db_index=True, unique=True)
    file = models.FileField(upload_to=JOBFILE_DIR, null=False)

    class Meta:
        db_table = 'job_file'

    def __str__(self):
        return self.hash_sum


class PresetJob(MPTTModel):
    parent = TreeForeignKey('self', models.CASCADE, null=True, blank=True, related_name='children')
    identifier = models.UUIDField(db_index=True, null=True)
    name = models.CharField(max_length=150, db_index=True, verbose_name=_('Name'))
    type = models.CharField(max_length=1, choices=PRESET_JOB_TYPE)
    check_date = models.DateTimeField()

    creation_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'job_preset'
        verbose_name = _('Preset job')
        unique_together = [('parent', 'name')]

    class MPTTMeta:
        order_insertion_by = ['creation_date']


class PresetFile(models.Model):
    preset = models.ForeignKey(PresetJob, models.CASCADE)
    name = models.CharField(max_length=1024)
    file = models.ForeignKey(JobFile, models.PROTECT)

    class Meta:
        db_table = 'job_preset_file'


class Job(models.Model):
    preset = models.ForeignKey(PresetJob, models.CASCADE)
    identifier = models.UUIDField(unique=True, db_index=True, default=uuid.uuid4)
    name = models.CharField(max_length=150, db_index=True)
    global_role = models.CharField(max_length=1, choices=JOB_ROLES, default=JOB_ROLES[0][0])

    creation_date = models.DateTimeField(auto_now_add=True)
    author = models.ForeignKey(User, models.SET_NULL, blank=True, null=True, related_name='+')

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'job'


class UploadedJobArchive(WithFilesMixin, models.Model):
    author = models.ForeignKey(User, models.CASCADE)
    name = models.CharField(max_length=128)
    archive = models.FileField(upload_to=UPLOAD_DIR)
    status = models.CharField(max_length=2, choices=JOB_UPLOAD_STATUS, default=JOB_UPLOAD_STATUS[0][0])
    step_progress = models.PositiveIntegerField(default=0)
    job = models.ForeignKey(Job, models.SET_NULL, null=True, related_name='+')  # Filled after upload is started
    start_date = models.DateTimeField(auto_now_add=True)  # Upload archive date
    finish_date = models.DateTimeField(null=True)
    error = models.TextField(null=True)  # Filled if uploading is failed

    class Meta:
        db_table = 'job_uploaded_archives'


class UserRole(models.Model):
    job = models.ForeignKey(Job, models.CASCADE)
    user = models.ForeignKey(User, models.CASCADE)
    role = models.CharField(max_length=1, choices=JOB_ROLES)

    class Meta:
        db_table = 'user_job_role'


class Scheduler(models.Model):
    type = models.CharField(max_length=15, choices=SCHEDULER_TYPE, db_index=True)
    status = models.CharField(max_length=15, choices=SCHEDULER_STATUS, default=SCHEDULER_STATUS[1][0])

    class Meta:
        db_table = 'scheduler'


class Decision(models.Model):
    job = models.ForeignKey(Job, models.CASCADE)
    title = models.CharField(max_length=128, blank=True)
    identifier = models.UUIDField(unique=True, db_index=True, default=uuid.uuid4)
    operator = models.ForeignKey(User, models.SET_NULL, null=True, related_name='decisions')
    status = models.CharField(max_length=1, choices=DECISION_STATUS, default=DECISION_STATUS[1][0])
    weight = models.CharField(max_length=1, choices=DECISION_WEIGHT, default=DECISION_WEIGHT[0][0])

    scheduler = models.ForeignKey(Scheduler, models.CASCADE)
    priority = models.CharField(max_length=6, choices=PRIORITY)

    error = models.TextField(null=True)
    configuration = models.ForeignKey(JobFile, models.CASCADE)

    start_date = models.DateTimeField(default=now)
    finish_date = models.DateTimeField(null=True)

    tasks_total = models.PositiveIntegerField(default=0)
    tasks_pending = models.PositiveIntegerField(default=0)
    tasks_processing = models.PositiveIntegerField(default=0)
    tasks_finished = models.PositiveIntegerField(default=0)
    tasks_error = models.PositiveIntegerField(default=0)
    tasks_cancelled = models.PositiveIntegerField(default=0)
    solutions = models.PositiveIntegerField(default=0)

    total_sj = models.PositiveIntegerField(null=True)
    failed_sj = models.PositiveIntegerField(null=True)
    solved_sj = models.PositiveIntegerField(null=True)
    expected_time_sj = models.PositiveIntegerField(null=True)
    start_sj = models.DateTimeField(null=True)
    finish_sj = models.DateTimeField(null=True)
    gag_text_sj = models.CharField(max_length=128, null=True)

    total_ts = models.PositiveIntegerField(null=True)
    failed_ts = models.PositiveIntegerField(null=True)
    solved_ts = models.PositiveIntegerField(null=True)
    expected_time_ts = models.PositiveIntegerField(null=True)
    start_ts = models.DateTimeField(null=True)
    finish_ts = models.DateTimeField(null=True)
    gag_text_ts = models.CharField(max_length=128, null=True)

    @property
    def is_lightweight(self):
        return self.weight == DECISION_WEIGHT[1][0]

    @property
    def is_finished(self):
        return self.status in {
            DECISION_STATUS[3][0], DECISION_STATUS[4][0], DECISION_STATUS[5][0],
            DECISION_STATUS[7][0], DECISION_STATUS[8][0]
        }

    @property
    def status_color(self):
        if self.status == DECISION_STATUS[1][0]:
            return 'pink'
        if self.status == DECISION_STATUS[2][0]:
            return 'purple'
        if self.status == DECISION_STATUS[3][0]:
            return 'green'
        if self.status in {DECISION_STATUS[4][0], DECISION_STATUS[5][0], DECISION_STATUS[8][0]}:
            return 'red'
        if self.status == DECISION_STATUS[6][0]:
            return 'yellow'
        if self.status == DECISION_STATUS[7][0]:
            return 'orange'
        return 'violet'

    @property
    def name(self):
        return Template("{{ date }}{% if title %} ({{ title }}){% endif %}").render(Context({
            'date': self.start_date, 'title': self.title
        }))

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'decision'


class FileSystem(models.Model):
    decision = models.ForeignKey(Decision, models.CASCADE, related_name='files')
    name = models.CharField(max_length=1024)
    file = models.ForeignKey(JobFile, models.PROTECT)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'file_system'


class DefaultDecisionConfiguration(models.Model):
    user = models.OneToOneField(User, models.CASCADE, related_name='decision_conf')
    file = models.ForeignKey(JobFile, models.CASCADE)

    class Meta:
        db_table = 'jobs_default_decision_conf'


post_delete.connect(remove_instance_files, sender=JobFile)
post_delete.connect(remove_instance_files, sender=UploadedJobArchive)
