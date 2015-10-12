from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import pre_delete
from django.dispatch.dispatcher import receiver
from Omega.vars import PRIORITY, NODE_STATUS, TASK_STATUS
from Omega.formatChecker import RestrictedFileField
from jobs.models import Job, Scheduler


FILE_DIR = 'Service'

class FileData(models.Model):
    description = models.TextField()
    archive_name = models.CharField(max_length=256)
    archive = RestrictedFileField(
        upload_to=FILE_DIR,
        max_upload_size=104857600,
        null=False
    )

    class Meta:
        db_table = 'service_service_files'


@receiver(pre_delete, sender=FileData)
def filedata_delete(**kwargs):
    file = kwargs['instance']
    storage, path = file.archive.storage, file.archive.path
    storage.delete(path)


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
    kernels = models.PositiveSmallIntegerField()

    class Meta:
        db_table = 'service_nodes_configuration'


class Node(models.Model):
    config = models.ForeignKey(NodesConfiguration)
    status = models.CharField(max_length=13, choices=NODE_STATUS)
    hostname = models.CharField(max_length=256)
    tasks = models.PositiveSmallIntegerField()  # number of solving
    jobs = models.PositiveSmallIntegerField()  # number of solving
    ram = models.PositiveIntegerField()  # in use
    kernels = models.PositiveSmallIntegerField()  # in use
    memory = models.FloatField()  # in use
    for_tasks = models.BooleanField()  # availability
    for_jobs = models.BooleanField()  # availability

    class Meta:
        db_table = 'service_node'


class VerificationTool(models.Model):
    name = models.CharField(max_length=128)
    version = models.CharField(max_length=128)
    usage = models.BooleanField(default=False)

    class Meta:
        db_table = 'service_verification_tool'


class JobSession(models.Model):
    job = models.ForeignKey(Job)
    tool = models.ForeignKey(VerificationTool)
    priority = models.CharField(max_length=6, choices=PRIORITY)
    status = models.BooleanField(default=True)
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
    files = models.ForeignKey(FileData, null=True)

    class Meta:
        db_table = 'service_task'


class TaskSolution(models.Model):
    task = models.ForeignKey(Task)
    status = models.BooleanField(default=False)
    creation = models.DateTimeField()
    files = models.ForeignKey(FileData, null=True)

    class Meta:
        db_table = 'service_solution'


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
