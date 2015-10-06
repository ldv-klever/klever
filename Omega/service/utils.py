import pytz
from datetime import datetime
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.utils.translation import ugettext_lazy as _
from service.models import *
from Omega.vars import PRIORITY, PLANNER_AVAILABILITY


# Case 3.1.1.(2).
# If self.error is None you can get self.jobsession.pk as identifier
# of the new session.
class InitSession(object):
    def __init__(self, user, job, max_priority, planners,
                 verifier_name, verifier_version):
        self.error = None
        self.job = job
        self.user = user
        self.max_priority = max_priority
        self.planners = planners
        self.jobsession = None
        self.__create_job_session(
            self.__get_verifier(verifier_name, verifier_version)
        )
        self.__check_planners()
        self.__check_verifiers()

    def __create_job_session(self, verifier):
        self.jobsession = JobSession()
        self.jobsession.job = self.job
        self.jobsession.start_date = \
            pytz.timezone('UTC').localize(datetime.now())
        self.jobsession.priority = self.max_priority
        self.jobsession.tool = verifier
        self.jobsession.save()
        self.jobsession.statistic.save()

    def __check_planners(self):
        has_available = False
        planner_priority = 0
        good_planners = []
        for planner in self.planners:
            try:
                planner = Planner.objects.get(name=planner)
            except ObjectDoesNotExist:
                self.error = _("One of the planners doesn't exist")
                return []
            if planner.need_auth:
                try:
                    planner_user = planner.planneruser_set.get(user=self.user)
                except ObjectDoesNotExist:
                    continue
                if compare_priority(planner_user.max_priority,
                                    self.max_priority):
                    continue
            if planner.availability == PLANNER_AVAILABILITY[0][0]:
                has_available = True
            good_planners.append(planner)
            self.__create_planner_session(planner, planner_priority)
            planner_priority += 1
        if not has_available:
            self.error = CloseSession(self.jobsession.pk).error

    def __create_planner_session(self, planner, priority):
        planner_session = PlannerSession()
        planner_session.priority = priority
        planner_session.planner = planner
        planner_session.session = self.jobsession
        planner_session.save()
        planner_session.statistic.save()

    def __get_verifier(self, name, version):
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


# Case 3.1.1.(7).
class CloseSession(object):
    def __init__(self, session_id):
        self.session_id = int(session_id)
        self.error = self.__close_session()

    def __close_session(self):
        try:
            jobsession = JobSession.objects.get(pk=self.session_id)
        except ObjectDoesNotExist:
            return _('Session was not found')
        if jobsession.finish_date is not None:
            return _('Session is not active')
        jobsession.finish_date = pytz.timezone('UTC').localize(datetime.now())
        jobsession.save()
        # TODO: other actions
        return None


# Case 3.1.1.(3).
class CreateTask(object):
    def __init__(self, session_id, description, archive, priority):
        self.error = None
        try:
            self.jobsession = JobSession.objects.get(pk=int(session_id))
            if not self.jobsession.status:
                self.error = _('Session is not active')
                return
        except ObjectDoesNotExist:
            self.error = _('Session was not found')
            return
        if compare_priority(self.jobsession.priority, priority):
            self.error = _('Priority of the task is too big')
            return
        # TODO: check if it reload last request date
        self.jobsession.save()
        self.__create_task()

    def __create_task(self):
        planner_session = self.__get_planner()
        if planner_session is None:
            self.error = _('No available planners')
            return
        task = Task()
        task.job_session = self.jobsession
        task.planner_session = planner_session
        task.save()
        planner_session.statistic.tasks_total += 1
        planner_session.statistic.save()
        self.jobsession.statistic.tasks_total += 1
        self.jobsession.statistic.save()
        # TODO: save files

    def __get_planner(self):
        sessions = self.jobsession.plannersession_set.filter(
            planner__availability=PLANNER_AVAILABILITY[0][0]
        ).order_by('priority')
        if len(sessions) > 0:
            return sessions[0]
        return None


# Case 3.1.1.(4).
class CheckTaskStatus(object):
    def __init__(self, task_id):
        try:
            self.task = Task.objects.get(pk=int(task_id))
            if not self.task.job_session.status:
                self.error = _('Session is not active')
                return
        except ObjectDoesNotExist:
            self.error = _('Task was not found')
            return
        self.task.job_session.save()
        self.status = self.__check_task()

    def __check_task(self):
        status = self.task.status
        if status == TASK_STATUS[2][0]:
            self.task.job_session.statistic.tasks_error += 1
            self.task.job_session.statistic.save()
            self.task.planner_session.statistic.tasks_error += 1
            self.task.planner_session.statistic.save()
            remove_task(self.task)
        elif status == TASK_STATUS[3][0]:
            self.task.job_session.statistic.tasks_lost += 1
            self.task.job_session.statistic.save()
            self.task.planner_session.statistic.tasks_lost += 1
            self.task.planner_session.statistic.save()
            remove_task(self.task)
        return status


# Case 3.1.1.(5).
class GetSolution(object):
    def __init__(self, task_id):
        try:
            self.task = Task.objects.get(pk=int(task_id))
            if not self.task.job_session.status:
                self.error = _('Session is not active')
                return
        except ObjectDoesNotExist:
            self.error = _('Task was not found')
            return
        self.task.job_session.save()
        # TODO: what to do if there are several solutions of the task?


# Case 3.1.2 (1)
class AddPlanner(object):
    def __init__(self, name, pkey, need_auth):
        self.name = name
        self.pkey = pkey
        self.need_auth = need_auth

    def __add_planner(self):
        try:
            planner = Planner.objects.get(name=self.name)
        except ObjectDoesNotExist:
            planner = Planner()
            planner.name = self.name
        planner.need_auth = self.need_auth
        planner.pkey = self.pkey
        planner.save()


# Case 3.1.2 (2)
class GetTask(object):
    def __init__(self, name, pkey, tasks):
        self.error = None
        try:
            planner = Planner.objects.get(name=name)
            if planner.pkey != pkey:
                self.error = _("Planner key is not valid")
                return
        except ObjectDoesNotExist:
            self.error = _("Planner doesn't exist")
            return


# Case 3.1.2 (3)
class GetTaskData(object):
    def __init__(self, task_id, pkey):
        self.error = None
        try:
            self.planner = Planner.objects.get(pkey=pkey)
        except ObjectDoesNotExist:
            self.error = _("Planner with specified key doesn't exist")
            return
        except MultipleObjectsReturned:
            self.error = _("Too many planners with specified key")
            return
        try:
            self.task = Task.objects.get(pk=int(task_id))
        except ObjectDoesNotExist:
            self.error = _("Task with specified id doesn't exist")
            return
        self.__get_task_data()

    def __get_task_data(self):
        try:
            archive = self.task.archive.file
            description = self.task.description.file
        except ObjectDoesNotExist:
            self.error = _("One of the files doesn't exist")
            return
        # TODO: read files and send it
        return


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
    task.archive.delete()
    task.description.delete()
    for solution in task.tasksolution_set.all():
        solution.archive.delete()
        solution.description.delete()
    task.delete()
