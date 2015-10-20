import json
import pytz
from datetime import datetime, timedelta
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _
from Omega.vars import JOB_STATUS
from jobs.utils import JobAccess
from reports.models import ReportRoot
from service.models import *


# Case 3.1.1 (3)
class CreateTask(object):
    def __init__(self, session, description, archive, priority):
        self.error = None
        if priority not in list(x[0] for x in PRIORITY):
            self.error = "Wrong priority"
            return
        try:
            json.loads(description)
        except Exception as e:
            print(e)
            self.error = 'Wrong description format'
            return
        self.jobsession = session
        if not self.jobsession.status:
            self.error = 'Session is not active'
            return
        self.jobsession.save()
        if compare_priority(self.jobsession.priority, priority):
            self.error = 'Priority of the task is too big'
            return
        self.task_id = self.__create_task(description, archive)

    def __create_task(self, description, archive):
        scheduler_session = self.__get_scheduler_session()
        if scheduler_session is None:
            self.error = 'No available schedulers'
            return
        files = TaskFileData.objects.create(description=description,
                                            name=archive.name, source=archive)
        task = Task.objects.create(job_session=self.jobsession,
                                   scheduler_session=scheduler_session,
                                   files=files)

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


# Case 3.1.1 (4)
class GetTaskStatus(object):
    def __init__(self, task):
        self.error = None
        self.task = task
        if not self.task.job_session.status:
            self.error = 'Session is not active'
            return
        self.task.job_session.save()
        self.status = self.__check_task()

    def __check_task(self):
        status = self.task.status
        if status in [TASK_STATUS[2][0], TASK_STATUS[3][0]]:
            remove_task(self.task)
        return status


# Case 3.1.1 (5)
class GetSolution(object):
    def __init__(self, task):
        self.error = None
        self.task = task
        if not self.task.job_session.status:
            self.error = 'Session is not active'
            return
        self.task.job_session.save()
        if self.task.status != TASK_STATUS[4][0]:
            self.error = 'Task is not finished'
            return
        self.files = self.__get_files()

    def __get_files(self):
        if len(self.task.tasksolution_set.all()) != 1:
            self.error = 'Wrong number of solutions'
            return None
        solution = self.task.tasksolution_set.get()
        if not solution.status:
            self.error = 'The solution is not ready for downloading'
            return None
        if solution.files is None:
            self.error = 'Solution files were not found'
            return None
        return solution.files


# Case 3.1.1 (6)
class RemoveTask(object):
    def __init__(self, task):
        self.error = None
        self.task = task
        if not self.task.job_session.status:
            self.error = 'Session is not active'
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


# Case 3.1.1 (7)
class StopTaskDecision(object):
    def __init__(self, task):
        self.error = None
        self.task = task
        if not self.task.job_session.status:
            self.error = _('Session is not active')
            return
        self.task.job_session.save()
        if self.task.status in [TASK_STATUS[0][0], TASK_STATUS[1][0]]:
            self.__new_unknown()
        else:
            self.__set_counters()
        remove_task(self.task)

    def __new_unknown(self):
        self.task.job_session.statistic.tasks_lost += 1
        self.task.job_session.statistic.save()
        self.task.scheduler_session.statistic.tasks_lost += 1
        self.task.scheduler_session.statistic.save()

    def __set_counters(self):
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


# Case 3.1.1 (8)
class CloseSession(object):
    def __init__(self, job):
        self.error = None
        try:
            self.jobsession = job.jobsession
        except ObjectDoesNotExist:
            self.error = 'Session was not found'
            return
        self.__close_session()
        if self.error is None:
            self.__finish_tasks()

    def __close_session(self):
        if self.jobsession.finish_date is not None:
            self.error = 'Session is not active'
            return None
        self.jobsession.finish_date = current_date()
        self.jobsession.status = False
        self.jobsession.save()

    def __finish_tasks(self):
        for task in self.jobsession.task_set.filter(
                status__in=[TASK_STATUS[0][0], TASK_STATUS[1][0]]):
            task.status = TASK_STATUS[3][0]
            self.jobsession.statistic.tasks_lost += 1
            self.jobsession.statistic.save()
            task.scheduler_session.statistic.tasks_lost += 1
            task.scheduler_session.statistic.save()
            remove_task(task)


# Case 3.1.2 (2)
class AddScheduler(object):
    def __init__(self, name, pkey, need_auth, for_jobs):
        self.error = None
        if len(name) == 0 or len(pkey) == 0 or not isinstance(need_auth, bool) \
                or not isinstance(for_jobs, bool) \
                or len(pkey) > 12 or len(name) > 128:
            self.error = 'Wrong arguments'
            return
        self.__add_scheduler(name, pkey, need_auth, for_jobs)

    def __add_scheduler(self, name, pkey, need_auth, for_jobs):
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
        scheduler.for_jobs = for_jobs
        scheduler.save()


# Case 3.1.2 (3)
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
            print(e)
            self.error = "Unknown error"

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
        new_list = {
            'pending': [],
            'processing': [],
            'finished': [],
            'error': [],
            'unknown': []
        }
        found_ids = []
        for task in Task.objects.filter(
                scheduler_session__scheduler=self.scheduler):
            found_ids.append(task.pk)
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
        for task_id in data['tasks']['pending']:
            if task_id not in found_ids:
                new_list['unknown'].append(task_id)
        for task_id in data['tasks']['processing']:
            if task_id not in found_ids:
                new_list['unknown'].append(task_id)
        data['tasks'] = new_list
        for root in ReportRoot.objects.filter(job_scheduler=self.scheduler):
            data = self.__add_job_descripion(root, data)
        try:
            return json.dumps(data)
        except ValueError:
            self.error = "Can't dump json data"
            return None

    def __add_solutions(self, task_id, data):
        self.ccc = 0
        data['solutions'][task_id] = []
        for solution in TaskSolution.objects.filter(task_id=task_id):
            data['solutions'][task_id].append(
                json.loads(solution.files.description)
            )
        return data

    def __add_job_descripion(self, root, data):
        self.ccc = 0
        if root.job.identifier in data['jobs']:
            return data
        data['jobs'] = {
            root.job.identifier: {'schedulers': []}
        }
        for sch_id in json.loads(root.schedulers):
            try:
                scheduler = Scheduler.objects.get(pk=int(sch_id))
            except ObjectDoesNotExist:
                continue
            data['jobs'][root.job.identifier]['schedulers']\
                .append(scheduler.name)
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
        operator = task.job_session.job.reportroot.user
        data['task descriptions'][task.pk] = {
            'user': operator.username,
            'description': json.loads(task.files.description)
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
        data = self.__add_solutions(task.pk, data)
        return data


# Case 3.1.2 (4)
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


# Case 3.1.2 (5)
class SaveSolution(object):
    def __init__(self, task_id, pkey, archive, description=None):
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
            files=SolutionFileData.objects.create(
                description=description, name=archive.name, source=archive
            )
        )
        self.task.job_session.statistic.solutions += 1
        self.task.job_session.statistic.save()
        self.task.scheduler_session.statistic.solutions += 1
        self.task.scheduler_session.statistic.save()


# Case 3.1.2 (6)
class SetNodes(object):
    def __init__(self, pkey, node_data):
        self.error = None
        try:
            self.scheduler = Scheduler.objects.get(pkey=pkey)
        except ObjectDoesNotExist:
            self.error = 'Scheduler was not found'
            return
        self.scheduler.save()
        try:
            self.__read_node_data(node_data)
        except IndexError or KeyError:
            self.error = "Wrong nodes data format"
        except Exception as e:
            print(e)
            self.error = "Unknown error"

    def __read_node_data(self, nodes_data):
        self.scheduler.nodesconfiguration_set.all().delete()
        for config in json.loads(nodes_data):
            nodes_conf, crtd = NodesConfiguration.objects.create(
                scheduler=self.scheduler, cpu=config['CPU model'],
                cores=config['CPUs'], ram=config['RAM'],
                memory=config['disk'])
            for node_data in config['nodes']:
                self.__create_node(nodes_conf, node_data)

    def __create_node(self, conf, data):
        self.ccc = 0
        if 'workload' not in data:
            return
        Node.objects.create(
            config=conf, hostname=data['address'], status=data['status'],
            ram=data['workload']['RAM reserved'],
            cores=data['workload']['CPUs reserved'],
            memory=data['workload']['disk space reserved'],
            jobs=data['workload']['jobs solving'],
            tasks=data['workload']['tasks solving'],
            for_jobs=data['workload']['reserved for jobs'],
            for_tasks=data['workload']['reserved for tasks']
        )


# Case 3.1.2 (7)
class UpdateTools(object):
    def __init__(self, pkey, tools_data):
        self.error = None
        try:
            self.scheduler = Scheduler.objects.get(pkey=pkey)
        except ObjectDoesNotExist:
            self.error = 'Scheduler was not found'
            return
        self.scheduler.save()
        try:
            self.__read_tools_data(tools_data)
        except ValueError or KeyError:
            self.error = "Wrong tools data format"
        except Exception as e:
            print(e)
            self.error = "Unknown error"

    def __read_tools_data(self, data):
        for tool in data:
            self.scheduler.tools.clear()
            tool, crtd = VerificationTool.objects.get_or_create(
                name=tool['tool'], version=tool['version'])
            self.scheduler.tools.add(tool)
        for tool in VerificationTool.objects.all():
            if len(tool.scheduler_set.all()) == 0:
                tool.delete()


# Case 3.1.3 (1)
class CheckSchedulers(object):
    def __init__(self, minutes, statuses):
        self.statuses = statuses
        self.__check_by_time(minutes)
        self.__check_by_status()

    def __check_by_time(self, minutes):
        max_waiting = current_date() - timedelta(minutes=float(minutes))
        for scheduler in Scheduler.objects.filter(
                Q(last_request__lt=max_waiting) &
                ~Q(name__in=list(self.statuses))):
            self.__close_sessions(scheduler)
            scheduler.status = SCHEDULER_STATUS[2][0]
            scheduler.save()

    def __check_by_status(self):
        for sch_name in self.statuses:
            try:
                scheduler = Scheduler.objects.get(name=sch_name)
            except ObjectDoesNotExist:
                continue
            if self.statuses[sch_name] != SCHEDULER_STATUS[0][0]:
                self.__clear_tasks(sch_name)
                self.__close_sessions(scheduler)
            if self.statuses[sch_name] in list(x[0] for x in SCHEDULER_STATUS) \
                    and scheduler.status != self.statuses[sch_name]:
                scheduler.status = self.statuses[sch_name]
                scheduler.save()

    def __clear_tasks(self, sch_name):
        self.ccc = 0
        for task in Task.objects.filter(
                scheduler_session__scheduler__name=sch_name):
            if task.status in [TASK_STATUS[0][0], TASK_STATUS[1][0]]:
                task.files.delete()
                task.status = TASK_STATUS[3][0]
                task.save()
                for solution in task.tasksolution_set.all():
                    solution.files.delete()

    def __close_sessions(self, scheduler):
        self.ccc = 0
        for reportroot in scheduler.reportroot_set.all():
            try:
                reportroot.job.status = JOB_STATUS[4][0]
                reportroot.job.save()
                CloseSession(reportroot.job)
            except ObjectDoesNotExist:
                continue


# Case 3.1,3 (2)
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


# Case 3.1.3 (3)
def close_old_active_sessions(minutes):
    minutes_ago = current_date() - timedelta(minutes=float(minutes))
    for jobsession in JobSession.objects.filter(
            last_request__lt=minutes_ago, status=True):
        CloseSession(jobsession.job)


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
        solution.files.delete()
    task.delete()


def current_date():
    return pytz.timezone('UTC').localize(datetime.now())


class UserJobs(object):
    def __init__(self, user):
        self.user = user
        self.data = self.__get_jobs()

    def __get_jobs(self):
        data = []
        for root in ReportRoot.objects.filter(user=self.user):
            try:
                jobsession = root.job.jobsession
            except ObjectDoesNotExist:
                continue
            tasks_finished = jobsession.statistic.tasks_error + \
                jobsession.statistic.tasks_lost + \
                jobsession.statistic.tasks_finished
            tasks_total = jobsession.statistic.tasks_total
            if tasks_total == 0:
                progress = 100
            else:
                progress = int(100 * tasks_finished/tasks_total)
            data_str = {
                'job': root.job,
                'priority': jobsession.get_priority_display(),
                'start_date': jobsession.start_date,
                'finish_date': '-',
                'tasks_finished': tasks_finished,
                'wall_time': '-',
                'tasks_total': tasks_total,
                'progress': progress
            }
            if jobsession.finish_date is not None:
                data_str['finish_date'] = jobsession.finish_date
                data_str['wall_time'] = (jobsession.finish_date -
                                         jobsession.start_date).seconds
            data.append(data_str)
        return data


class SchedulerTable(object):
    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.scheduler_data = self.__scheduler_data()
        self.tools = VerificationTool.objects.all()
        self.nodes = Node.objects.filter(config__scheduler=self.scheduler)

    def __scheduler_data(self):
        ram_total = 0
        ram_occupied = 0
        memory_total = 0
        memory_occupied = 0
        cores_total = 0
        cores_occupied = 0
        cores = []
        for nodes_conf in self.scheduler.nodesconfiguration_set.all():
            conf_cores_total = 0
            conf_cores_occupied = 0
            for node in nodes_conf.node_set.all():
                ram_total += nodes_conf.ram
                ram_occupied += node.ram
                memory_total += nodes_conf.memory
                memory_occupied += node.memory
                cores_total += nodes_conf.cores
                cores_occupied += node.cores
                conf_cores_total += nodes_conf.cores
                conf_cores_occupied += node.cores
            cores.append({
                'name': nodes_conf.cpu,
                'value': "%s/%s" % (conf_cores_occupied, conf_cores_total)
            })
        data = {
            'ram': "%s/%s" % (ram_occupied, ram_total),
            'memory': "%s/%s" % (memory_occupied, memory_total),
            'cores_total': "%s/%s" % (cores_occupied, cores_total),
            'cores': cores,
            'rowspan': 1 + len(cores)
        }
        return data


class SessionsTable(object):
    def __init__(self):
        self.data = self.__get_data()

    def __get_data(self):
        self.ccc = 0
        data = []
        for session in JobSession.objects.all():
            rowdata = {
                'session': session,
                'finish_date': '-',
                'wall_time': '-'
            }
            if session.finish_date is not None:
                rowdata['finish_date'] = session.finish_date
                rowdata['wall_time'] = \
                    (session.finish_date - session.start_date).seconds + \
                    ' ' + _('s')
            tasks_finished = session.statistic.tasks_error + \
                session.statistic.tasks_lost + \
                session.statistic.tasks_finished
            tasks_total = session.statistic.tasks_total
            if tasks_total == 0:
                progress = 100
            else:
                progress = int(100 * tasks_finished/tasks_total)
            rowdata['progress'] = progress
            rowdata['progress_text'] = \
                '%s%% (%s/%s)' % (progress, tasks_finished, tasks_total)
            data.append(rowdata)
        return data


class SchedulerSessionsTable(object):
    def __init__(self, jobsession):
        self.jobsession = jobsession
        self.data = self.__get_data()

    def __get_data(self):
        data = []
        for session in self.jobsession.schedulersession_set.all():
            rowdata = {
                'session': session
            }
            tasks_finished = session.statistic.tasks_error + \
                session.statistic.tasks_lost + \
                session.statistic.tasks_finished
            tasks_total = session.statistic.tasks_total
            if tasks_total == 0:
                progress = 100
            else:
                progress = int(100 * tasks_finished/tasks_total)
            rowdata['progress'] = progress
            rowdata['progress_text'] = \
                '%s%% (%s/%s)' % (progress, tasks_finished, tasks_total)
            data.append(rowdata)
        return data


class SchedulerJobSessionsTable(object):
    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.data = self.__get_data()

    def __get_data(self):
        data = []
        jobsesions = []
        for sch_session in self.scheduler.schedulersession_set.all():
            if sch_session.session not in jobsesions:
                jobsesions.append(sch_session.session)
        for session in jobsesions:
            rowdata = {
                'session': session,
                'finish_date': '-',
                'wall_time': '-'
            }
            if session.finish_date is not None:
                rowdata['finish_date'] = session.finish_date
                rowdata['wall_time'] = \
                    (session.finish_date - session.start_date).seconds + \
                    ' ' + _('s')
            tasks_finished = session.statistic.tasks_error + \
                session.statistic.tasks_lost + \
                session.statistic.tasks_finished
            tasks_total = session.statistic.tasks_total
            if tasks_total == 0:
                progress = 100
            else:
                progress = int(100 * tasks_finished/tasks_total)
            rowdata['progress'] = progress
            rowdata['progress_text'] = \
                '%s%% (%s/%s)' % (progress, tasks_finished, tasks_total)
            data.append(rowdata)
        return data


def get_available_schedulers(user):
    schedulers = []
    has_for_job = False
    for scheduler in Scheduler.objects.all():
        sch_data = {
            'pk': scheduler.pk,
            'name': scheduler.name,
            'available': True,
            'auth_error': False,
            'for_jobs': scheduler.for_jobs
        }
        if scheduler.for_jobs:
            has_for_job = True
        if scheduler.status != SCHEDULER_STATUS[0][0]:
            sch_data['available'] = False
        if scheduler.need_auth:
            if len(scheduler.scheduleruser_set.filter(user=user)) == 0:
                sch_data['auth_error'] = True
        schedulers.append(sch_data)
    if has_for_job:
        return schedulers
    return []


def get_priorities(user, schedulers):
    try:
        scheduler_ids = json.loads(schedulers)
    except Exception as e:
        print(e)
        return None
    priorities = []
    for sch_id in scheduler_ids:
        try:
            scheduler = Scheduler.objects.get(pk=int(sch_id[0]))
        except ObjectDoesNotExist:
            continue
        if scheduler.need_auth:
            try:
                priorities.append(scheduler.scheduleruser_set
                                  .filter(user=user)[0].max_priority)
            except IndexError:
                continue
    user_priorities = []
    for pr in reversed(PRIORITY):
        user_priorities.append(pr)
        if pr[0] in priorities:
            return user_priorities


class StartJobDecision(object):
    def __init__(self, user, job_id, priority, job_sch_id, schedulers):
        self.error = None
        if not isinstance(user, User) \
                or priority not in [pr[0] for pr in PRIORITY]:
            self.error = _('Unknown error')
            return
        self.operator = user
        self.priority = priority
        self.job_scheduler = self.__get_scheduler(job_sch_id)
        if self.error is not None:
            return
        self.job = self.__get_job(job_id)
        if self.error is not None:
            return
        self.jobsession = self.__create_job_session()
        if self.error is not None:
            return
        self.__check_schedulers(schedulers)
        if self.error is not None:
            return
        try:
            self.job.reportroot.delete()
        except ObjectDoesNotExist:
            pass
        ReportRoot.objects.create(user=self.operator, job=self.job)
        self.job.status = JOB_STATUS[1][0]
        self.job.save()

    def __get_scheduler(self, sch_id):
        try:
            return Scheduler.objects.get(pk=int(sch_id))
        except ObjectDoesNotExist:
            self.error = _('Scheduler was not found')
            return
        except ValueError:
            self.error = _('Unknown error')
            return

    def __get_job(self, job_id):
        try:
            job = Job.objects.get(pk=int(job_id))
        except ObjectDoesNotExist:
            self.error = _('Job was not found')
            return
        except ValueError:
            self.error = _('Unknown error')
            return
        if not JobAccess(self.operator, job).can_decide():
            self.error = _("You don't have access to start decision")
            return
        return job

    def __create_job_session(self):
        try:
            jobsession = JobSession.objects.get(job=self.job)
            if jobsession.finish_date is None:
                self.error = _("The job has opened session")
                return None
            for task in jobsession.task_set.all():
                remove_task(task)
            jobsession.delete()
        except ObjectDoesNotExist:
            pass
        jobsession = JobSession.objects.create(
            job=self.job, start_date=current_date(), priority=self.priority,
            job_scheduler=self.job_scheduler
        )
        JobTasksResults.objects.create(session=jobsession)
        return jobsession

    def __check_schedulers(self, schedulers):
        has_available = False
        scheduler_priority = 0
        try:
            schedulers = json.loads(schedulers)
        except Exception as e:
            print(e)
            self.error = _("Unknown error")
            return
        for sch_pk in schedulers:
            scheduler = self.__get_scheduler(sch_pk)
            if self.error is not None:
                return
            if scheduler.need_auth:
                try:
                    scheduler_user = scheduler.scheduleruser_set.filter(
                        user=self.operator)[0]
                except IndexError:
                    continue
                if compare_priority(scheduler_user.max_priority,
                                    self.priority):
                    continue
            if scheduler.status == SCHEDULER_STATUS[0][0]:
                has_available = True
            self.__create_scheduler_session(scheduler, scheduler_priority)
            scheduler_priority += 1
        if not has_available:
            self.error = CloseSession(self.jobsession.job).error
            if self.error is None:
                self.error = _('Session was closed due to '
                               'there are no available schedulers')

    def __create_scheduler_session(self, scheduler, priority):
        scheduler_session = SchedulerSession.objects.create(
            priority=priority, scheduler=scheduler, session=self.jobsession
        )
        SchedulerTasksResults.objects.create(session=scheduler_session)
