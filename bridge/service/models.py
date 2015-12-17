from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch.dispatcher import receiver
from django.contrib.auth.models import User
from bridge.formatChecker import RestrictedFileField
from bridge.vars import PRIORITY, NODE_STATUS, TASK_STATUS, SCHEDULER_STATUS, SCHEDULER_TYPE
from jobs.models import Job

FILE_DIR = 'Service'


class Scheduler(models.Model):
    type = models.CharField(max_length=1, choices=SCHEDULER_TYPE)
    status = models.CharField(max_length=12, choices=SCHEDULER_STATUS, default='AILING')

    class Meta:
        db_table = 'scheduler'


class VerificationTool(models.Model):
    scheduler = models.ForeignKey(Scheduler)
    name = models.CharField(max_length=128)
    version = models.CharField(max_length=128)

    class Meta:
        db_table = 'verification_tool'


class SchedulerUser(models.Model):
    user = models.OneToOneField(User)
    login = models.CharField(max_length=128)
    password = models.CharField(max_length=128)

    class Meta:
        db_table = 'scheduler_user'


class NodesConfiguration(models.Model):
    cpu = models.CharField(max_length=128)
    cores = models.PositiveSmallIntegerField()
    ram = models.BigIntegerField()
    memory = models.BigIntegerField()

    class Meta:
        db_table = 'nodes_configuration'


class Workload(models.Model):
    jobs = models.PositiveIntegerField()
    tasks = models.PositiveIntegerField()
    cores = models.PositiveSmallIntegerField()
    ram = models.BigIntegerField()
    memory = models.BigIntegerField()
    for_tasks = models.BooleanField()
    for_jobs = models.BooleanField()

    class Meta:
        db_table = 'workload'


class Node(models.Model):
    config = models.ForeignKey(NodesConfiguration)
    status = models.CharField(max_length=13, choices=NODE_STATUS)
    hostname = models.CharField(max_length=128)
    workload = models.OneToOneField(Workload, null=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = 'node'


@receiver(pre_delete, sender=Node)
def node_delete_signal(**kwargs):
    node = kwargs['instance']
    if node.workload is not None:
        node.workload.delete()


class SolvingProgress(models.Model):
    job = models.OneToOneField(Job)
    priority = models.CharField(max_length=6, choices=PRIORITY)
    scheduler = models.ForeignKey(Scheduler)
    start_date = models.DateTimeField(null=True)
    finish_date = models.DateTimeField(null=True)
    tasks_total = models.PositiveIntegerField(default=0)
    tasks_pending = models.PositiveIntegerField(default=0)
    tasks_processing = models.PositiveIntegerField(default=0)
    tasks_finished = models.PositiveIntegerField(default=0)
    tasks_error = models.PositiveIntegerField(default=0)
    tasks_cancelled = models.PositiveIntegerField(default=0)
    solutions = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=1024, null=True)
    configuration = models.BinaryField()

    class Meta:
        db_table = 'solving_progress'


class Task(models.Model):
    progress = models.ForeignKey(SolvingProgress)
    status = models.CharField(max_length=10, choices=TASK_STATUS, default='PENDING')
    error = models.CharField(max_length=1024, null=True)
    description = models.BinaryField()
    archname = models.CharField(max_length=256)  # Original name of the archive
    archive = RestrictedFileField(upload_to=FILE_DIR, null=False, max_upload_size=104857600)

    class Meta:
        db_table = 'task'


@receiver(pre_delete, sender=Task)
def task_delete_signal(**kwargs):
    task = kwargs['instance']
    storage, path = task.archive.storage, task.archive.path
    storage.delete(path)


class Solution(models.Model):
    task = models.OneToOneField(Task)
    description = models.BinaryField()
    archname = models.CharField(max_length=256)  # Original name of the archive
    archive = RestrictedFileField(upload_to=FILE_DIR, null=False, max_upload_size=104857600)

    class Meta:
        db_table = 'solution'


@receiver(pre_delete, sender=Solution)
def solution_delete(**kwargs):
    file = kwargs['instance']
    storage, path = file.archive.storage, file.archive.path
    storage.delete(path)
