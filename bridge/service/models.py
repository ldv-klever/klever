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

from django.db import models
from django.db.models.signals import post_delete

from bridge.vars import NODE_STATUS, TASK_STATUS
from bridge.utils import WithFilesMixin, remove_instance_files

from users.models import User
from jobs.models import Scheduler, Decision

SERVICE_DIR = 'Service'


class VerificationTool(models.Model):
    scheduler = models.ForeignKey(Scheduler, models.CASCADE)
    name = models.CharField(max_length=128)
    version = models.CharField(max_length=128)

    class Meta:
        db_table = 'verification_tool'


class NodesConfiguration(models.Model):
    cpu_model = models.CharField(verbose_name='CPU model', max_length=128)
    cpu_number = models.PositiveSmallIntegerField(verbose_name='CPU number')
    ram_memory = models.PositiveIntegerField(verbose_name='RAM memory')
    disk_memory = models.PositiveIntegerField(verbose_name='Disk memory')

    class Meta:
        db_table = 'nodes_configuration'


class Node(models.Model):
    hostname = models.CharField(max_length=128)
    status = models.CharField(max_length=13, choices=NODE_STATUS)
    config = models.ForeignKey(NodesConfiguration, models.CASCADE)

    class Meta:
        db_table = 'node'


class Workload(models.Model):
    node = models.OneToOneField(Node, models.CASCADE, related_name='workload')
    reserved_cpu_number = models.PositiveSmallIntegerField(verbose_name='Reserved CPU number')
    reserved_ram_memory = models.PositiveIntegerField(verbose_name='Reserved RAM memory')
    reserved_disk_memory = models.PositiveIntegerField(verbose_name='Reserved disk memory')
    running_verification_jobs = models.PositiveIntegerField(verbose_name='Running verification jobs')
    running_verification_tasks = models.PositiveIntegerField(verbose_name='Running verification tasks')
    available_for_jobs = models.BooleanField(verbose_name='Available for jobs')
    available_for_tasks = models.BooleanField(verbose_name='Available for tasks')

    class Meta:
        db_table = 'workload'


class Task(WithFilesMixin, models.Model):
    decision = models.ForeignKey(Decision, models.CASCADE, related_name='tasks')
    status = models.CharField(max_length=10, choices=TASK_STATUS, default=TASK_STATUS[0][0])
    error = models.CharField(max_length=1024, null=True)
    filename = models.CharField(max_length=256)
    archive = models.FileField(upload_to=SERVICE_DIR)
    description = models.JSONField()

    class Meta:
        db_table = 'task'


class Solution(WithFilesMixin, models.Model):
    decision = models.ForeignKey(Decision, models.CASCADE, related_name='solutions_set')
    task = models.OneToOneField(Task, models.CASCADE, related_name='solution')
    filename = models.CharField(max_length=256)
    archive = models.FileField(upload_to=SERVICE_DIR)
    description = models.JSONField()

    class Meta:
        db_table = 'solution'


post_delete.connect(remove_instance_files, sender=Task)
post_delete.connect(remove_instance_files, sender=Solution)
