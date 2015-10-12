import pytz
import json
from datetime import datetime, timedelta
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.utils.translation import ugettext_lazy as _
from django.db.models import Q
from service.models import *
from Omega.vars import PRIORITY, SCHEDULER_STATUS, JOB_STATUS


# Case 3.1.1.(2). FINISHED
class InitSession(object):
    def __init__(self, job, max_priority, schedulers,
                 verifier_name, verifier_version):
        self.error = None
        if not (isinstance(job, Job) and
                max_priority in [pr[0] for pr in PRIORITY] and
                len(verifier_name) > 0 and len(verifier_version) > 0):
            self.error = 'Wrong arguments'
            return
        self.max_priority = max_priority
        self.schedulers = schedulers
        self.jobsession = self.__create_job_session(
            self.__get_verifier(verifier_name, verifier_version), job)
        self.__check_schedulers()
        self.__check_verifiers()

    def __create_job_session(self, verifier, job):
        jobsession = JobSession.objects.create(
            job=job, start_date=current_date(), priority=self.max_priority,
            tool=verifier
        )
        JobTasksResults.objects.create(session=jobsession)
        return jobsession

    def __check_schedulers(self):
        has_available = False
        scheduler_priority = 0
        try:
            operator = self.jobsession.job.reportroot.user
        except ObjectDoesNotExist:
            self.error = "Job is not solving"
            CloseSession(self.jobsession.pk)
            return
        for scheduler in self.schedulers:
            try:
                scheduler = Scheduler.objects.get(name=scheduler)
            except ObjectDoesNotExist:
                self.error = "One of the schedulers doesn't exist"
                CloseSession(self.jobsession.pk)
                return
            if scheduler.need_auth:
                try:
                    scheduler_user = scheduler.scheduleruser_set.filter(
                        user=operator)[0]
                except IndexError:
                    continue
                if compare_priority(scheduler_user.max_priority,
                                    self.max_priority):
                    continue
            if scheduler.status == SCHEDULER_STATUS[0][0]:
                has_available = True
            self.__create_scheduler_session(scheduler, scheduler_priority)
            scheduler_priority += 1
        if not has_available:
            self.error = CloseSession(self.jobsession.pk).error
            if self.error is None:
                self.error = 'Session was closed due to ' \
                             'there are no available schedulers'

    def __create_scheduler_session(self, scheduler, priority):
        scheduler_session = SchedulerSession.objects.create(
            priority=priority, scheduler=scheduler, session=self.jobsession
        )
        SchedulerTasksResults.objects.create(session=scheduler_session)

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


# Case 3.1.1.(8). FINISHED
class CloseSession(object):
    def __init__(self, session_id):
        self.error = None
        try:
            self.session_id = int(session_id)
        except ValueError:
            self.error = "Wrong argument: session id"
            return
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
        jobsession.status = False
        jobsession.save()
        return jobsession

    def __finish_tasks(self):
        for task in self.jobsession.task_set.filter(
                status__in=[TASK_STATUS[0][0], TASK_STATUS[1][0]]):
            task.status = TASK_STATUS[3][0]
            self.jobsession.statistic.tasks_lost += 1
            self.jobsession.statistic.save()
            task.scheduler_session.statistic.tasks_lost += 1
            task.scheduler_session.statistic.save()
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
        scheduler_session = self.__get_scheduler_session()
        if scheduler_session is None:
            self.error = 'No available schedulers'
            return
        task = Task.objects.create(job_session=self.jobsession,
                                   scheduler_session=scheduler_session)
        task.files = upload_new_files(description, archive)
        task.save()
        scheduler_session.statistic.tasks_total += 1
        scheduler_session.statistic.save()
        self.jobsession.statistic.tasks_total += 1
        self.jobsession.statistic.save()
        return task.pk

    def __get_scheduler_session(self):
        sessions = self.jobsession.schedulersession_set.filter(
            scheduler__status=SCHEDULER_STATUS[0][0]
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
            self.error = 'Task is not finished'
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
            self.task.scheduler_session.statistic.tasks_error += 1
            self.task.scheduler_session.statistic.save()
        elif self.task.status == TASK_STATUS[3][0]:
            self.task.job_session.statistic.tasks_lost += 1
            self.task.job_session.statistic.save()
            self.task.scheduler_session.statistic.tasks_lost += 1
            self.task.scheduler_session.statistic.save()
        elif self.task.status == TASK_STATUS[4][0]:
            self.task.job_session.statistic.tasks_finished += 1
            self.task.job_session.statistic.save()
            self.task.scheduler_session.statistic.tasks_finished += 1
            self.task.scheduler_session.statistic.save()


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
        self.task.scheduler_session.statistic.tasks_lost += 1
        self.task.scheduler_session.statistic.save()


# Case 3.1.2 (2). FINISHED
class AddScheduler(object):
    def __init__(self, name, pkey, need_auth):
        self.error = None
        if len(name) == 0 or len(pkey) == 0 or not isinstance(need_auth, bool) \
                or len(pkey) > 12 or len(name) > 128:
            self.error = 'Wrong arguments'
            return
        self.__add_scheduler(name, pkey, need_auth)

    def __add_scheduler(self, name, pkey, need_auth):
        try:
            scheduler = Scheduler.objects.get(name=name)
        except ObjectDoesNotExist:
            try:
                Scheduler.objects.get(pkey=pkey)
                self.error = 'Scheduler with specified key already exists'
                return
            except ObjectDoesNotExist:
                pass
            scheduler = Scheduler()
            scheduler.name = name
        scheduler.need_auth = need_auth
        scheduler.pkey = pkey
        scheduler.save()


# Case 3.1.2 (3)
# TODO: tests
class GetTasks(object):
    def __init__(self, scheduler, tasks):
        self.error = None
        self.scheduler = scheduler
        self.scheduler.save()
        try:
            self.data = self.__get_tasks(tasks)
        except KeyError or IndexError:
            self.error = 'Wrong task data format'
        except Exception as e:
            self.error = e

    def __get_tasks(self, data):
        data = json.loads(data)
        status_map = {
            'pending': TASK_STATUS[0][0],
            'processing': TASK_STATUS[1][0],
            'finished': TASK_STATUS[4][0],
            'error': TASK_STATUS[2][0],
            'unknown': TASK_STATUS[3][0]
        }
        all_tasks = {
            'pending': [],
            'processing': [],
            'finished': [],
            'error': [],
            'unknown': []
        }
        new_list = {}
        new_list.update(all_tasks)
        for task in Task.objects.filter(
                scheduler_session__scheduler=self.scheduler):
            for status in status_map:
                if status_map[status] == task.status:
                    all_tasks[status].append(task)
        for task in all_tasks['pending']:
            if task.pk in data['tasks']['pending']:
                new_list['pending'].append(task.pk)
            elif task.pk in data['tasks']['processing']:
                task.status = status_map['processing']
                task.save()
                new_list['processing'].append(task.pk)
            elif task.pk in data['tasks']['finished']:
                task.status = status_map['finished']
                task.save()
                new_list['finished'].append(task.pk)
                self.__update_solutions(task)
            elif task.pk in data['tasks']['error']:
                task.status = status_map['error']
                task.save()
                new_list['error'].append(task.pk)
            elif task.pk in data['tasks']['unknown']:
                task.status = status_map['unknown']
                task.save()
                new_list['unknown'].append(task.pk)
            else:
                new_list['pending'].append(task.pk)
                data = self.__add_description(task, data)
                data = self.__add_job_descripion(task.job_session.job, data)
        for task in all_tasks['processing']:
            if task.pk in data['tasks']['processing']:
                new_list['processing'].append(task.pk)
            elif task.pk in data['tasks']['finished']:
                task.status = status_map['finished']
                task.save()
                new_list['finished'].append(task.pk)
                self.__update_solutions(task)
            elif task.pk in data['tasks']['error']:
                task.status = status_map['error']
                task.save()
                new_list['error'].append(task.pk)
            elif task.pk in data['tasks']['unknown']:
                task.status = status_map['unknown']
                task.save()
                new_list['unknown'].append(task.pk)
            elif task.pk not in data['tasks']['pending']:
                new_list['processing'].append(task.pk)
                data = self.__add_description(task, data)
                data = self.__add_job_descripion(task.job_session.job, data)
        for task in all_tasks['error']:
            if task.pk in data['tasks']['pending']:
                new_list['error'].append(task.pk)
            elif task.pk in data['tasks']['processing']:
                new_list['error'].append(task.pk)
        for task in all_tasks['unknown']:
            if task.pk in data['tasks']['pending']:
                new_list['unknown'].append(task.pk)
            elif task.pk in data['tasks']['processing']:
                new_list['unknown'].append(task.pk)
        data['tasks'] = {}
        data['tasks'].update(new_list)
        for job in Job.objects.filter(status=JOB_STATUS[1][0]):
            try:
                for sch_id in json.loads(job.reportroot.schedulers):
                    if self.scheduler.pk == int(sch_id):
                        data = self.__add_job_descripion(job, data)
                        job.reportroot.schedulers = '[]'
                        job.reportroot.save()
                        break
            except ObjectDoesNotExist:
                self.error = 'Unknown error, data was corrupted'
                return None
        try:
            return json.dumps(data)
        except ValueError:
            self.error = "Can't dump json data"
            return None

    def __add_job_descripion(self, job, data):
        self.ccc = 0
        if job.identifier in data['jobs']:
            return data
        data['jobs'] = {
            job.identifier: {'schedulers': []}
        }
        for sch_id in json.loads(job.reportroot.schedulers):
            try:
                scheduler = Scheduler.objects.get(pk=int(sch_id))
            except ObjectDoesNotExist:
                continue
            data['jobs'][job.identifier]['schedulers'].append(scheduler.name)
        return data

    def __update_solutions(self, task):
        self.ccc = 0
        solutions = task.tasksolution_set.order_by('-creation')
        if len(solutions) >= 1:
            solutions[0].status = True
            solutions[0].save()
            for solution in solutions[1:]:
                solution.files.delete()
                solution.delete()

    def __add_description(self, task, data):
        self.ccc = 0
        with open(task.files.description) as f:
            description = json.load(f)
        operator = task.job_session.job.reportroot.user
        data['task descriptions'][task.pk] = {
            'user': operator.username,
            'description': description
        }
        if task.scheduler_session.scheduler.need_auth:
            if operator.username in data['users']:
                return data
            try:
                scheduler_user = task.scheduler_session.scheduler\
                    .scheduleruser_set.get(user=operator)
            except ObjectDoesNotExist:
                return data
            except MultipleObjectsReturned:
                scheduler_user = task.scheduler_session.scheduler.scheduleruser_set\
                    .filter(user=operator)[0]
            data['users'][operator.username] = {
                'login': scheduler_user.login,
                'password': scheduler_user.password
            }
        return data


# Case 3.1.2 (4). DONE
# self.task.files contains needed files in case of self.error is None
class GetTaskData(object):
    def __init__(self, task_id, pkey):
        self.error = None
        try:
            self.scheduler = Scheduler.objects.get(pkey=pkey)
        except ObjectDoesNotExist:
            self.error = "Scheduler with specified key doesn't exist"
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
            self.scheduler = Scheduler.objects.get(pkey=pkey)
        except ObjectDoesNotExist:
            self.error = "Scheduler with specified key doesn't exist"
            return
        self.scheduler.save()
        self.__create_solution(description, archive)

    def __create_solution(self, description, archive):
        TaskSolution.objects.create(
            task=self.task, creation=current_date(),
            files=upload_new_files(description, archive)
        )
        self.task.job_session.statistic.solutions += 1
        self.task.job_session.statistic.save()
        self.task.scheduler_session.statistic.solutions += 1
        self.task.scheduler_session.statistic.save()


# Case 3.1.2 (6). DONE
class SetNodes(object):
    def __init__(self, pkey, node_data):
        self.error = None
        try:
            self.scheduler = Scheduler.objects.get(pkey=pkey)
        except ObjectDoesNotExist:
            self.error = 'Scheduler was not found'
            return
        self.scheduler.save()
        self.__read_node_data(node_data)

    def __read_node_data(self, node_data_file):
        with open(node_data_file) as f:
            node_data = json.load(f)
        nodes_opts = ['CPU model', 'CPUs', 'RAM', 'disk', 'nodes']
        node_opts = ['address', 'status', 'CPUs reserved', 'RAM reserved',
                     'disk space reserved', 'tasks solving', 'jobs solving',
                     'reserved for jobs', 'reserved for tasks']
        if not isinstance(node_data, dict) \
                or any(x not in node_data for x in nodes_opts):
            self.error = 'Wrong node data format'
            return
        if not isinstance(node_data['nodes'], list) \
                or any(not isinstance(n, dict) for n in node_data['nodes']):
            self.error = 'Wrong node data format'
            return
        for node in node_data['nodes']:
            if any(x not in node for x in node_opts):
                self.error = 'Wrong node data format'
                return
        try:
            nodes_conf = NodesConfiguration.objects.get(
                scheduler=self.scheduler)
        except ObjectDoesNotExist:
            nodes_conf = NodesConfiguration()
            nodes_conf.scheduler = self.scheduler
        nodes_conf.cpu = node_data['CPU model']
        nodes_conf.kernels = node_data['CPUs']
        nodes_conf.ram = node_data['RAM']
        nodes_conf.memory = node_data['disk']
        nodes_conf.save()
        Node.objects.filter(config=nodes_conf).delete()
        for node in node_data['nodes']:
            Node.objects.create(
                config=nodes_conf, status=node['status'],
                ram=node['RAM reserved'], kernels=node['CPUs reserved'],
                memory=node['disk space reserved'], hostname=node['address'],
                jobs=node['jobs solving'], tasks=node['tasks solving'],
                for_jobs=node['reserved for jobs'],
                for_tasks=node['reserved for tasks']
            )


# Case 3.1.2 (7). DONE
class UpdateTools(object):
    def __init__(self, pkey, tools_data):
        self.error = None
        try:
            self.scheduler = Scheduler.objects.get(pkey=pkey)
        except ObjectDoesNotExist:
            self.error = 'Scheduler was not found'
            return
        self.scheduler.save()
        self.__read_tools_data(tools_data)

    def __read_tools_data(self, tools_file):
        with open(tools_file) as f:
            data = json.load(f)
        if not isinstance(data, list) \
                or any(not isinstance(x, dict) for x in data):
            self.error = 'Wrong tools data format'
            return
        for tool in data:
            if any(x not in tool for x in ['tool', 'version']):
                self.error = 'Wrong tools data format'
                return
        VerificationTool.objects.filter(usage=False).delete()
        for tool in data:
            VerificationTool.objects.get_or_create(name=tool['tool'],
                                                   version=tool['version'])


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
    return priority1 > priority2


def remove_task(task):
    task.files.delete()
    for solution in task.tasksolution_set.all():
        # TODO: check if it deletes files from the disc
        solution.files.delete()
    task.delete()


def current_date():
    return pytz.timezone('UTC').localize(datetime.now())


def upload_new_files(description, archive):
    return FileData.objects.create(
        description=description, description_name=description.name,
        archive=archive, archive_name=archive.name
    )


# Case 3.1.3 (1). FINISHED
def change_schedulers_status():
    Scheduler.objects.filter(
        last_request__lt=(current_date() - timedelta(minutes=1))
    ).update(status=SCHEDULER_STATUS[2][0])


# Case 3.1,3 (2). FINISHED
def delete_old_sessions(hours):
    for jobsession in JobSession.objects.filter(
            finish_date__lt=(current_date() - timedelta(hours=float(hours)))):
        for task in Task.objects.filter(
                ~Q(files=None) & Q(job_session=jobsession)):
            task.files.delete()
        for solution in TaskSolution.objects.filter(
                ~Q(files=None) & Q(task__job_session=jobsession)):
            solution.files.delete()
        jobsession.delete()


# Case 3.1,3 (3). FINISHED
def close_old_active_sessions(minutes):
    minutes_ago = current_date() - timedelta(minutes=float(minutes))
    for jobsession in JobSession.objects.filter(
            last_request__lt=minutes_ago, status=True):
        CloseSession(jobsession.pk)
