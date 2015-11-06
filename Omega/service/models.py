from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch.dispatcher import receiver
from django.contrib.auth.models import User
from Omega.formatChecker import RestrictedFileField
from Omega.vars import PRIORITY, NODE_STATUS, TASK_STATUS, SCHEDULER_STATUS
from jobs.models import Job


FILE_DIR = 'Service'


class TaskFileData(models.Model):
    description = models.TextField()
    name = models.CharField(max_length=256)
    source = RestrictedFileField(
        upload_to=FILE_DIR, null=False,
        max_upload_size=104857600
    )

    class Meta:
        db_table = 'service_task_files'


class SolutionFileData(models.Model):
    description = models.TextField(null=True)
    name = models.CharField(max_length=256)
    source = RestrictedFileField(
        upload_to=FILE_DIR, null=False,
        max_upload_size=104857600
    )

    class Meta:
        db_table = 'service_solution_files'


@receiver(pre_delete, sender=TaskFileData)
def task_filedata_delete(**kwargs):
    file = kwargs['instance']
    storage, path = file.source.storage, file.source.path
    storage.delete(path)


@receiver(pre_delete, sender=SolutionFileData)
def soluition_filedata_delete(**kwargs):
    file = kwargs['instance']
    storage, path = file.source.storage, file.source.path
    storage.delete(path)


class VerificationTool(models.Model):
    name = models.CharField(max_length=128)
    version = models.CharField(max_length=128)

    class Meta:
        db_table = 'service_verification_tool'


class Scheduler(models.Model):
    name = models.CharField(max_length=128, unique=True)
    pkey = models.CharField(max_length=12, unique=True)
    status = models.CharField(max_length=12, default='HEALTHY',
                              choices=SCHEDULER_STATUS)
    need_auth = models.BooleanField(default=False)
    last_request = models.DateTimeField(auto_now=True)
    for_jobs = models.BooleanField(default=False)
    tools = models.ManyToManyField(VerificationTool)

    class Meta:
        db_table = 'service_scheduler'


class SchedulerUser(models.Model):
    user = models.ForeignKey(User)
    scheduler = models.ForeignKey(Scheduler)
    login = models.CharField(max_length=128)
    password = models.CharField(max_length=128)
    max_priority = models.CharField(max_length=6, choices=PRIORITY,
                                    default='LOW')
    last_request = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'service_scheduler_user'


class NodesConfiguration(models.Model):
    scheduler = models.ForeignKey(Scheduler)
    cpu = models.CharField(max_length=256)
    ram = models.PositiveIntegerField()
    memory = models.PositiveIntegerField()
    cores = models.PositiveSmallIntegerField()

    class Meta:
        db_table = 'service_nodes_configuration'


class Workload(models.Model):
    tasks = models.PositiveSmallIntegerField()  # number of solving
    jobs = models.PositiveSmallIntegerField()  # number of solving
    ram = models.PositiveIntegerField()  # in use
    cores = models.PositiveSmallIntegerField()  # in use
    memory = models.FloatField()  # in use
    for_tasks = models.BooleanField()  # reserved
    for_jobs = models.BooleanField()  # reserved

    class Meta:
        db_table = 'service_workload'


class Node(models.Model):
    config = models.ForeignKey(NodesConfiguration)
    status = models.CharField(max_length=13, choices=NODE_STATUS)
    hostname = models.CharField(max_length=256)
    workload = models.OneToOneField(Workload, null=True,
                                    on_delete=models.SET_NULL)

    class Meta:
        db_table = 'service_node'


@receiver(pre_delete, sender=Node)
def node_delete_signal(**kwargs):
    node = kwargs['instance']
    if node.workload is not None:
        node.workload.delete()


class JobSession(models.Model):
    job = models.OneToOneField(Job)
    job_scheduler = models.ForeignKey(Scheduler)
    priority = models.CharField(max_length=6, choices=PRIORITY)
    start_date = models.DateTimeField()
    last_request = models.DateTimeField(auto_now=True)
    finish_date = models.DateTimeField(null=True)

    class Meta:
        db_table = 'service_job_session'


class SchedulerSession(models.Model):
    scheduler = models.ForeignKey(Scheduler)
    session = models.ForeignKey(JobSession)
    priority = models.PositiveSmallIntegerField()

    class Meta:
        db_table = 'service_scheduler_session'


class Task(models.Model):
    scheduler_session = models.ForeignKey(SchedulerSession)
    job_session = models.ForeignKey(JobSession)
    status = models.CharField(max_length=10, choices=TASK_STATUS,
                              default='PENDING')
    files = models.OneToOneField(TaskFileData, null=True,
                                 on_delete=models.SET_NULL)

    class Meta:
        db_table = 'service_task'


@receiver(pre_delete, sender=Task)
def task_delete_signal(**kwargs):
    task = kwargs['instance']
    if task.files is not None:
        task.files.delete()


class TaskSolution(models.Model):
    task = models.ForeignKey(Task)
    status = models.BooleanField(default=False)
    creation = models.DateTimeField()
    files = models.OneToOneField(SolutionFileData, null=True,
                                 on_delete=models.SET_NULL)

    class Meta:
        db_table = 'service_solution'


@receiver(pre_delete, sender=TaskSolution)
def solution_delete_signal(**kwargs):
    solution = kwargs['instance']
    if solution.files is not None:
        solution.files.delete()


class TasksResults(models.Model):
    tasks_total = models.PositiveSmallIntegerField(default=0)
    tasks_finished = models.PositiveSmallIntegerField(default=0)
    tasks_error = models.PositiveSmallIntegerField(default=0)
    tasks_lost = models.PositiveSmallIntegerField(default=0)
    solutions = models.PositiveSmallIntegerField(default=0)

    class Meta:
        abstract = True


class JobTasksResults(TasksResults):
    session = models.OneToOneField(JobSession, related_name='statistic')

    class Meta:
        db_table = 'cache_job_task_results'


class SchedulerTasksResults(TasksResults):
    session = models.OneToOneField(SchedulerSession, related_name='statistic')

    class Meta:
        db_table = 'cache_scheduler_task_results'
