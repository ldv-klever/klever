from django.db import models
from django.contrib.auth.models import User
from Omega.vars import PLANNER_STATUS, PRIORITY, NODE_STATUS, TASK_STATUS
from Omega.formatChecker import RestrictedFileField
from jobs.models import Job


FILE_DIR = 'Service'

class FileData(models.Model):
    description = RestrictedFileField(
        upload_to=FILE_DIR,
        max_upload_size=104857600,
        null=False
    )
    archive = RestrictedFileField(
        upload_to=FILE_DIR,
        max_upload_size=104857600,
        null=False
    )
    description_name = models.CharField(max_length=256)
    archive_name = models.CharField(max_length=256)


class Planner(models.Model):
    name = models.CharField(max_length=128)
    pkey = models.CharField(max_length=12, unique=True)
    status = models.CharField(max_length=12, default='HEALTHY',
                                    choices=PLANNER_STATUS)
    need_auth = models.BooleanField(default=False)
    last_request = models.DateTimeField(auto_now=True)


class PlannerUser(models.Model):
    user = models.ForeignKey(User)
    planner = models.ForeignKey(Planner)
    login = models.CharField(max_length=128)
    password = models.CharField(max_length=128)
    max_priority = models.CharField(max_length=6, choices=PRIORITY)
    last_request = models.DateTimeField()


class NodesConfiguration(models.Model):
    planner = models.ForeignKey(Planner)
    cpu = models.CharField(max_length=256)
    ram = models.PositiveIntegerField()
    memory = models.PositiveIntegerField()
    kernels = models.PositiveSmallIntegerField()


class Node(models.Model):
    config = models.ForeignKey(NodesConfiguration)
    status = models.CharField(max_length=13, choices=NODE_STATUS)
    hostname = models.CharField(max_length=256)
    tasks = models.PositiveSmallIntegerField()  # number
    jobs = models.PositiveSmallIntegerField()  # number
    ram = models.PositiveIntegerField()  # in use
    kernels = models.PositiveSmallIntegerField()  # in use
    memory = models.FloatField()  # in use
    for_tasks = models.BooleanField()  # availability
    for_jobs = models.BooleanField()  # availability


class VerificationTool(models.Model):
    name = models.CharField(max_length=128)
    version = models.CharField(max_length=128)
    usage = models.BooleanField(default=False)


class JobSession(models.Model):
    job = models.ForeignKey(Job)
    tool = models.ForeignKey(VerificationTool)
    priority = models.CharField(max_length=6, choices=PRIORITY)
    status = models.BooleanField(default=True)
    start_date = models.DateTimeField()
    last_request = models.DateTimeField(auto_now=True)
    finish_date = models.DateTimeField(null=True)


class PlannerSession(models.Model):
    planner = models.ForeignKey(Planner)
    session = models.ForeignKey(JobSession)
    priority = models.PositiveSmallIntegerField()


class Task(models.Model):
    planner_session = models.ForeignKey(PlannerSession)
    job_session = models.ForeignKey(JobSession)
    status = models.CharField(max_length=10, choices=TASK_STATUS,
                              default='PENDING')
    files = models.ForeignKey(FileData, null=True)


class TaskSolution(models.Model):
    task = models.ForeignKey(Task)
    # TODO: WHat deafult status?
    status = models.BooleanField(default=True)
    creation = models.DateTimeField()
    files = models.ForeignKey(FileData, null=True)


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


class PlannerTasksResults(TasksResults):
    session = models.OneToOneField(PlannerSession, related_name='statistic')
