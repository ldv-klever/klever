import pytz
import json
from io import BytesIO
import hashlib
from datetime import datetime, timedelta
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.utils.translation import ugettext_lazy as _
from django.db.models import Q
from service.models import *
from Omega.vars import PRIORITY, PLANNER_STATUS


# Case 3.1.1.(2). DONE
# If self.error is None you can get self.jobsession.pk as identifier
# of the new session.
class InitSession(object):
    def __init__(self, job, max_priority, planners,
                 verifier_name, verifier_version):
        self.error = None
        if not (isinstance(job, Job) and
                max_priority in [pr[0] for pr in PRIORITY] and
                len(verifier_name) > 0 and len(verifier_version) > 0):
            self.error = 'Wrong arguments'
            return
        self.max_priority = max_priority
        self.planners = planners
        self.jobsession = self.__create_job_session(
            self.__get_verifier(verifier_name, verifier_version), job)
        self.__check_planners()
        self.__check_verifiers()

    def __create_job_session(self, verifier, job):
        jobsession = JobSession.objects.create(
            job=job, start_date=current_date(), priority=self.max_priority,
            tool=verifier
        )
        JobTasksResults.objects.create(session=jobsession)
        return jobsession

    def __check_planners(self):
        has_available = False
        planner_priority = 0
        for planner in self.planners:
            try:
                planner = Planner.objects.get(name=planner)
            except ObjectDoesNotExist:
                self.error = "One of the planners doesn't exist"
                return
            if planner.need_auth:
                try:
                    operator = self.jobsession.job.reportroot.user
                except ObjectDoesNotExist:
                    self.error = "Job is not for solving"
                    return
                try:
                    planner_user = planner.planneruser_set.get(user=operator)
                except ObjectDoesNotExist:
                    continue
                except MultipleObjectsReturned:
                    print('Too many users for one planner')
                    planner_user = planner.planneruser_set.all()[0]
                if compare_priority(planner_user.max_priority,
                                    self.max_priority):
                    continue
            if planner.status == PLANNER_STATUS[0][0]:
                has_available = True
            self.__create_planner_session(planner, planner_priority)
            planner_priority += 1
        if not has_available:
            self.error = CloseSession(self.jobsession.pk).error

    def __create_planner_session(self, planner, priority):
        planner_session = PlannerSession.objects.create(
            priority=priority, planner=planner, session=self.jobsession
        )
        PlannerTasksResults.objects.create(session=planner_session)

    def __get_verifier(self, name, version):
        self.ccc = 0
        verifier = VerificationTool.objects.get_or_create(
            name=name, version=version)[0]
        verifier.usage = True
        verifier.save()
        return verifier

    def __check_verifiers(self):
        if len(JobSession.objects.filter(tool=self.jobsession.tool,
                                         finish_date=None)) == 0:
            self.jobsession.tool.usage = False
            self.jobsession.tool.save()


# Case 3.1.1.(8). DONE
# If self.error is None everything is OK.
class CloseSession(object):
    def __init__(self, session_id):
        self.session_id = int(session_id)
        self.error = None
        self.jobsession = self.__close_session()
        if self.error is None:
            self.__finish_tasks()

    def __close_session(self):
        try:
            jobsession = JobSession.objects.get(pk=self.session_id)
        except ObjectDoesNotExist:
            self.error = 'Session was not found'
            return None
        if jobsession.finish_date is not None:
            self.error = 'Session is not active'
            return None
        jobsession.finish_date = current_date()
        jobsession.save()
        return jobsession

    def __finish_tasks(self):
        for task in self.jobsession.task_set.filter(
                status__in=[TASK_STATUS[0][0], TASK_STATUS[1][0]]):
            task.status = TASK_STATUS[3][0]
            self.jobsession.statistic.tasks_lost += 1
            self.jobsession.statistic.save()
            task.planner_session.statistic.tasks_lost += 1
            task.planner_session.statistic.save()
            remove_task(task)


# Case 3.1.1.(3). DONE
class CreateTask(object):
    def __init__(self, session_id, description, archive, priority):
        self.error = None
        try:
            self.jobsession = JobSession.objects.get(pk=int(session_id))
            if not self.jobsession.status:
                self.error = 'Session is not active'
                return
        except ObjectDoesNotExist:
            self.error = 'Session was not found'
            return
        if compare_priority(self.jobsession.priority, priority):
            self.error = 'Priority of the task is too big'
            return
        self.jobsession.save()
        self.task_id = self.__create_task(description, archive)

    def __create_task(self, description, archive):
        planner_session = self.__get_planner_session()
        if planner_session is None:
            self.error = 'No available planners'
            return
        task = Task.objects.create(job_session=self.jobsession,
                                   planner_session=planner_session)
        task.files = upload_new_files(description, archive)
        task.save()
        planner_session.statistic.tasks_total += 1
        planner_session.statistic.save()
        self.jobsession.statistic.tasks_total += 1
        self.jobsession.statistic.save()
        return task.pk

    def __get_planner_session(self):
        sessions = self.jobsession.plannersession_set.filter(
            planner__status=PLANNER_STATUS[0][0]
        ).order_by('priority')
        if len(sessions) > 0:
            return sessions[0]
        return None


# Case 3.1.1.(4). DONE
class GetTaskStatus(object):
    def __init__(self, task_id):
        self.error = None
        try:
            self.task = Task.objects.get(pk=int(task_id))
            if not self.task.job_session.status:
                self.error = 'Session is not active'
                return
        except ObjectDoesNotExist:
            self.error = 'Task was not found'
            return
        self.task.job_session.save()
        self.status = self.__check_task()

    def __check_task(self):
        status = self.task.status
        if status in [TASK_STATUS[2][0], TASK_STATUS[3][0]]:
            remove_task(self.task)
        return status


# Case 3.1.1.(5). DONE
# In case of success self.files contains needed files.
class GetSolution(object):
    def __init__(self, task_id):
        self.error = None
        try:
            self.task = Task.objects.get(pk=int(task_id))
            if not self.task.job_session.status:
                self.error = _('Session is not active')
                return
        except ObjectDoesNotExist:
            self.error = _('Task was not found')
            return
        self.task.job_session.save()
        if self.task.status != TASK_STATUS[4][0]:
            self.error = 'Status of the task is not finished'
        self.files = self.__get_files()

    def __get_files(self):
        if len(self.task.tasksolution_set.all()) != 1:
            self.error = 'Wrong number of solutions'
            return None
        solution = self.task.tasksolution_set.get()
        if solution.files is None:
            self.error = 'Solution files were not found'
            return None
        return solution.files


# Case 3.1.1. (6). DONE
# self.error is None if success
class RemoveTask(object):
    def __init__(self, task_id):
        self.error = None
        try:
            self.task = Task.objects.get(pk=int(task_id))
            if not self.task.job_session.status:
                self.error = _('Session is not active')
                return
        except ObjectDoesNotExist:
            self.error = _('Task was not found')
            return
        self.task.job_session.save()
        if self.task.status in [TASK_STATUS[0][0], TASK_STATUS[1][0]]:
            self.error = 'Status of the task is wrong'
            return
        self.__prepare_for_delete()
        remove_task(self.task)

    def __prepare_for_delete(self):
        if self.task.status == TASK_STATUS[2][0]:
            self.task.job_session.statistic.tasks_error += 1
            self.task.job_session.statistic.save()
            self.task.planner_session.statistic.tasks_error += 1
            self.task.planner_session.statistic.save()
        elif self.task.status == TASK_STATUS[3][0]:
            self.task.job_session.statistic.tasks_lost += 1
            self.task.job_session.statistic.save()
            self.task.planner_session.statistic.tasks_lost += 1
            self.task.planner_session.statistic.save()
        elif self.task.status == TASK_STATUS[4][0]:
            self.task.job_session.statistic.tasks_finished += 1
            self.task.job_session.statistic.save()
            self.task.planner_session.statistic.tasks_finished += 1
            self.task.planner_session.statistic.save()


# Case 3.1.1. (7). DONE
# self.error is None if success
class StopDecision(object):
    def __init__(self, task_id):
        self.error = None
        try:
            self.task = Task.objects.get(pk=int(task_id))
            if not self.task.job_session.status:
                self.error = _('Session is not active')
                return
        except ObjectDoesNotExist:
            self.error = _('Task was not found')
            return
        self.task.job_session.save()
        if self.task.status not in [TASK_STATUS[0][0], TASK_STATUS[1][0]]:
            self.error = 'Status of the task is wrong'
            return
        self.__prepare_for_delete()
        remove_task(self.task)

    def __prepare_for_delete(self):
        self.task.job_session.statistic.tasks_lost += 1
        self.task.job_session.statistic.save()
        self.task.planner_session.statistic.tasks_lost += 1
        self.task.planner_session.statistic.save()


# Case 3.1.2 (2). DONE
class AddPlanner(object):
    def __init__(self, name, pkey, need_auth):
        self.error = None
        if not (len(name) == 0 or len(pkey) == 0 and isinstance(need_auth, bool)):
            self.error = 'Wrong arguments'
            return
        self.__add_planner(name, pkey, need_auth)

    def __add_planner(self, name, pkey, need_auth):
        try:
            planner = Planner.objects.get(name=name)
        except ObjectDoesNotExist:
            try:
                Planner.objects.get(pkey=pkey)
                self.error = 'Planner with specified key already exists'
                return
            except ObjectDoesNotExist:
                pass
            planner = Planner()
            planner.name = name
        planner.need_auth = need_auth
        planner.pkey = pkey
        planner.save()


# Case 3.1.2 (3)
class GetTasks(object):
    def __init__(self, pkey, tasks):
        self.error = None
        try:
            planner = Planner.objects.get(pkey=pkey)
        except ObjectDoesNotExist:
            self.error = "Planner doesn't exist"
            return
        planner.save()
        self.__parse_tasks(tasks)

    def __parse_tasks(self, tasks):
        with open(tasks) as data_file:
            data = json.load(data_file)


# Case 3.1.2 (4). DONE
# self.task.files contains needed files in case of self.error is None
class GetTaskData(object):
    def __init__(self, task_id, pkey):
        self.error = None
        try:
            self.planner = Planner.objects.get(pkey=pkey)
        except ObjectDoesNotExist:
            self.error = "Planner with specified key doesn't exist"
            return
        try:
            self.task = Task.objects.get(pk=int(task_id))
        except ObjectDoesNotExist:
            self.error = "Task with specified id doesn't exist"
            return
        if self.task.files is None:
            self.error = "Task files doesn't exist"
            return


# Case 3.1.2. (5). DONE
class SaveSolution(object):
    def __init__(self, task_id, pkey, description, archive):
        self.error = None
        try:
            self.task = Task.objects.get(pk=int(task_id))
        except ObjectDoesNotExist:
            self.error = _('Task was not found')
            return
        try:
            self.planner = Planner.objects.get(pkey=pkey)
        except ObjectDoesNotExist:
            self.error = "Planner with specified key doesn't exist"
            return
        self.planner.save()
        self.__create_solution(description, archive)

    def __create_solution(self, description, archive):
        TaskSolution.objects.create(
            task=self.task, creation=current_date(),
            files=upload_new_files(description, archive)
        )
        self.task.job_session.statistic.solutions += 1
        self.task.job_session.statistic.save()
        self.task.planner_session.statistic.solutions += 1
        self.task.planner_session.statistic.save()


def compare_priority(priority1, priority2):
    cnt = 0
    for pr in PRIORITY:
        cnt += 1
        if pr[0] == priority1:
            priority1 = cnt
        if pr[0] == priority2:
            priority2 = cnt
    if not isinstance(priority1, int):
        priority1 = 0
    if not isinstance(priority2, int):
        priority2 = 0
    return priority1 < priority2


def remove_task(task):
    task.files.delete()
    for solution in task.tasksolution_set.all():
        # TODO: check if it deletes files from disc
        solution.files.delete()
    task.delete()


def current_date():
    return pytz.timezone('UTC').localize(datetime.now())


def upload_new_files(description, archive):
    return FileData.objects.create(
        description=description, description_name=description.name,
        archive=archive, archive_name=archive.name
    )

# Case 3.1.3 (1). DONE
def check_planners():
    Planner.objects.all(
        last_request__lt=(current_date() - timedelta(minutes=1))
    ).update(status=PLANNER_STATUS[2][0])


# Case 3.1,3 (2). DONE
def clear_sessions(hours):
    for jobsession in JobSession.objects.filter(
            finish_date__lt=(current_date() - timedelta(hours=int(hours)))):
        for task in Task.objects.filter(
                ~Q(files=None) & Q(job_session=jobsession)):
            task.files.delete()
        for solution in TaskSolution.objects.filter(
                ~Q(files=None) & Q(task__job_session=jobsession)):
            solution.files.delete()
        jobsession.delete()


# Case 3.1,3 (3). DONE
def clear_active_sessions(minutes):
    minutes_ago = current_date() - timedelta(minutes=int(minutes))
    for jobsession in JobSession.objects.filter(last_request__lt=minutes_ago):
        CloseSession(jobsession.pk)
