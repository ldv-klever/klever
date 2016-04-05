import json
from io import BytesIO
from django.core.exceptions import ObjectDoesNotExist
from django.core.files import File as NewFile
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _
from django.utils.timezone import now
from bridge.vars import JOB_STATUS
from bridge.utils import logger, file_checksum
from jobs.models import RunHistory
from jobs.utils import JobAccess, File, change_job_status
from reports.models import ReportRoot, ReportUnknown, ReportComponent
from service.models import *


# Case 3.1(3) DONE
class ScheduleTask(object):
    def __init__(self, job_id, description, archive):
        self.error = None
        self.job = self.__get_job(job_id)
        if self.error is not None:
            return
        try:
            priority = json.loads(description)['priority']
        except Exception as e:
            logger.exception("Json parsing error: %s" % e, stack_info=True)
            self.error = 'Wrong description format'
            return
        if priority not in list(x[0] for x in PRIORITY):
            self.error = "Wrong priority"
            return
        try:
            self.progress = self.job.solvingprogress
        except ObjectDoesNotExist:
            self.error = 'Solving progress of the job was not found'
            return
        if self.progress.job.status != JOB_STATUS[2][0]:
            self.error = "The job is not processing"
            return
        if self.progress.scheduler.status == SCHEDULER_STATUS[2][0]:
            self.error = 'The scheduler for tasks is disconnected'
            return
        if self.error is not None:
            return
        if compare_priority(self.progress.priority, priority):
            self.error = 'Priority of the task is too big'
            return
        self.task_id = self.__create_task(description, archive)

    def __get_job(self, job_id):
        try:
            return Job.objects.get(pk=int(job_id))
        except ObjectDoesNotExist:
            self.error = 'Job was not found was not found' % job_id
            return
        except ValueError:
            self.error = 'Unknown error'
            return

    def __create_task(self, description, archive):
        task = Task.objects.create(progress=self.progress, archname=archive.name,
                                   archive=archive, description=description.encode('utf8'))
        self.progress.tasks_total += 1
        self.progress.tasks_pending += 1
        self.progress.save()
        new_description = json.loads(task.description.decode('utf8'))
        new_description['id'] = task.pk
        task.description = json.dumps(new_description).encode('utf8')
        task.save()
        return task.pk


# Case 3.1(4) DONE
class GetTaskStatus(object):
    def __init__(self, task_id):
        self.error = None
        try:
            self.task = Task.objects.get(pk=int(task_id))
        except ObjectDoesNotExist:
            self.error = 'The task was not found'
            return
        except ValueError:
            self.error = 'Incorrect task id (integer needed)'
            return
        if self.task.progress.job.status != JOB_STATUS[2][0]:
            self.error = "The job is not processing"
            return
        self.status = self.task.status


# Case 3.1(5) DONE
class GetSolution(object):
    def __init__(self, task_id):
        self.error = None
        try:
            self.task = Task.objects.get(pk=int(task_id))
        except ObjectDoesNotExist:
            self.error = 'The task was not found'
            return
        except ValueError:
            self.error = 'Incorrect task id (integer needed)'
            return
        if self.task.progress.job.status != JOB_STATUS[2][0]:
            self.error = "The job is not processing"
            return
        if self.task.status == TASK_STATUS[3][0]:
            if self.task.error is None:
                self.error = "The task was finished with error but doesn't have its description"
        elif self.task.status == TASK_STATUS[2][0]:
            self.solution = self.__get_solution()
        else:
            self.error = 'The task is not finished'

    def __get_solution(self):
        try:
            solution = self.task.solution
        except ObjectDoesNotExist:
            self.error = "The solution of the finished task doesn't exist"
            return None
        return solution


# Case 3.1(6) DONE
class RemoveTask(object):
    def __init__(self, task_id):
        self.error = None
        try:
            self.task = Task.objects.get(pk=int(task_id))
        except ObjectDoesNotExist:
            self.error = 'The task was not found'
            return
        except ValueError:
            self.error = 'Incorrect task id (integer needed)'
            return
        if self.task.progress.job.status != JOB_STATUS[2][0]:
            self.error = "The job is not processing"
            return
        if self.task.status == TASK_STATUS[3][0]:
            if self.task.error is None:
                self.error = "The task was finished with error but doesn't have its description"
                return
        elif self.task.status == TASK_STATUS[2][0]:
            try:
                self.task.solution
            except ObjectDoesNotExist:
                self.error = "The solution of the finished task doesn't exist"
                return
        else:
            self.error = 'The task is not finished'
            return
        try:
            self.task.delete()
        except Exception as e:
            logger.exception(e, stack_info=True)
            self.error = 'Task was not deleted, error occured'


# Case 3.1(7) DONE
class CancelTask(object):
    def __init__(self, task_id):
        self.error = None
        try:
            self.task = Task.objects.get(pk=int(task_id))
        except ObjectDoesNotExist:
            self.error = 'The task was not found'
            return
        except ValueError:
            self.error = 'Incorrect task id (integer needed)'
            return
        if self.task.progress.job.status != JOB_STATUS[2][0]:
            self.error = "The job is not processing"
            return
        if self.task.status == TASK_STATUS[0][0]:
            if self.task.progress.tasks_pending > 0:
                self.task.progress.tasks_pending -= 1
        elif self.task.status == TASK_STATUS[1][0]:
            if self.task.progress.tasks_pending > 0:
                self.task.progress.tasks_processing -= 1
        else:
            self.error = 'The task status is wrong'
            return
        try:
            self.task.delete()
            self.task.progress.tasks_cancelled += 1
            self.task.progress.save()
        except Exception as e:
            logger.exception(e, stack_info=True)
            self.error = 'Task was not deleted, error occured'


# Case 3.1(8)
class KleverCoreFinishDecision(object):
    def __init__(self, job, error=None):
        self.error = None
        try:
            self.progress = job.solvingprogress
        except ObjectDoesNotExist:
            self.error = "The job doesn't have solving progress"
            change_job_status(job, JOB_STATUS[5][0])
            return
        self.error = None
        for task in job.solvingprogress.task_set.all():
            if task.status not in [TASK_STATUS[2][0], TASK_STATUS[3][0]]:
                self.error = 'There are unfinished tasks'
            RemoveTask(task.pk)
        self.progress.finish_date = now()
        if error is not None:
            self.progress.error = error
            change_job_status(job, JOB_STATUS[5][0])
        elif self.error is not None:
            self.progress.error = self.error
            change_job_status(job, JOB_STATUS[5][0])
        self.progress.save()


# Case 3.1(2)
class KleverCoreStartDecision(object):
    def __init__(self, job):
        self.error = None
        self.job = job
        self.__start()

    def __start(self):
        try:
            progress = self.job.solvingprogress
        except ObjectDoesNotExist:
            self.error = 'Solving progress was not found'
            return
        if progress.start_date is not None:
            self.error = 'Solving progress already has start date'
            return
        elif progress.finish_date is not None:
            self.error = 'Solving progress already has finish date'
            return
        progress.start_date = now()
        progress.save()


# Case 3.4(6) DONE
class StopDecision(object):
    def __init__(self, job):
        self.error = None
        self.job = job
        try:
            self.progress = self.job.solvingprogress
        except ObjectDoesNotExist:
            self.error = _('The job solving progress does not exist')
            return
        if self.progress.job.status not in [JOB_STATUS[1][0], JOB_STATUS[2][0]]:
            self.error = _("Only pending and processing jobs can be stopped")
            return
        self.__clear_tasks()
        if self.error is not None:
            return
        change_job_status(job, JOB_STATUS[6][0])

    def __clear_tasks(self):
        for task in self.progress.task_set.all():
            if task.status == TASK_STATUS[1][0]:
                self.progress.tasks_processing -= 1
                self.progress.tasks_cancelled += 1
            elif task.status == TASK_STATUS[0][0]:
                self.progress.tasks_pending -= 1
                self.progress.tasks_cancelled += 1
            try:
                task.delete()
            except Exception as e:
                logger.exception(e, stack_info=True)
        self.progress.finish_date = now()
        self.progress.error = "The job was cancelled"
        self.progress.save()


# Case 3.2(2) DONE
class GetTasks(object):
    def __init__(self, sch_type, tasks):
        self.error = None
        self.scheduler = self.__get_scheduler(sch_type)
        if self.error is not None:
            return
        self.data = {}
        try:
            self.data = self.__get_tasks(tasks)
            if self.error is not None:
                # TODO: notify admin with email
                logger.error(self.error, stack_info=True)
        except KeyError or IndexError:
            self.error = 'Wrong task data format'
        except Exception as e:
            logger.exception(e, stack_info=True)
            self.error = "Unknown error"

    def __get_scheduler(self, sch_type):
        try:
            return Scheduler.objects.get(type=sch_type)
        except ObjectDoesNotExist:
            self.error = "The scheduler was not found"
            return None

    def __get_tasks(self, data):
        data = json.loads(data)
        new_data = {
            'tasks': {
                'pending': [],
                'processing': [],
                'error': [],
                'finished': []
            },
            'task errors': {},
            'task descriptions': {},
            'task solutions': {},
            'jobs': {
                'pending': [],
                'processing': [],
                'error': [],
                'finished': [],
                'cancelled': []
            },
            'job errors': {},
            'job configurations': {}
        }
        status_map = {
            'pending': TASK_STATUS[0][0],
            'processing': TASK_STATUS[1][0],
            'finished': TASK_STATUS[2][0],
            'error': TASK_STATUS[3][0],
            'cancelled': TASK_STATUS[4][0]
        }
        all_tasks = {
            'pending': [],
            'processing': [],
            'error': [],
            'finished': [],
            'cancelled': []
        }
        found_ids = []
        for task in Task.objects.filter(progress__scheduler=self.scheduler):
            found_ids.append(task.pk)
            for status in status_map:
                if status_map[status] == task.status:
                    all_tasks[status].append(task)
        for task in all_tasks['pending']:
            if str(task.pk) in data['tasks']['pending']:
                new_data['tasks']['pending'].append(str(task.pk))
                new_data = self.__add_description(task, new_data)
                new_data = self.__add_solution(task, new_data)
            elif str(task.pk) in data['tasks']['processing']:
                task.status = status_map['processing']
                task.save()
                if task.progress.tasks_pending > 0:
                    task.progress.tasks_pending -= 1
                task.progress.tasks_processing += 1
                task.progress.save()
                new_data['tasks']['processing'].append(str(task.pk))
                new_data = self.__add_description(task, new_data)
                new_data = self.__add_solution(task, new_data)
            elif str(task.pk) in data['tasks']['finished']:
                task.status = status_map['finished']
                task.save()
                try:
                    task.solution
                except ObjectDoesNotExist:
                    # TODO: notify admin with email
                    logger.exception(
                        "Solution was not found for the pending->finished task with id '%s'" % task.pk,
                        stack_info=True
                    )
                if task.progress.tasks_pending > 0:
                    task.progress.tasks_pending -= 1
                task.progress.tasks_finished += 1
                task.progress.save()
            elif str(task.pk) in data['tasks']['error']:
                task.status = status_map['error']
                if str(task.pk) in data['task errors']:
                    task.error = data['task errors'][str(task.pk)]
                else:
                    task.error = "The scheduler hasn't given error description"
                task.save()
                if task.progress.tasks_pending > 0:
                    task.progress.tasks_pending -= 1
                task.progress.tasks_error += 1
                task.progress.save()
            else:
                new_data['tasks']['pending'].append(str(task.pk))
                new_data = self.__add_description(task, new_data)
                new_data = self.__add_solution(task, new_data)
        for task in all_tasks['processing']:
            if str(task.pk) in data['tasks']['pending']:
                task.status = status_map['pending']
                task.save()
                if task.progress.tasks_processing > 0:
                    task.progress.tasks_processing -= 1
                task.progress.tasks_pending += 1
                task.progress.save()
                new_data['tasks']['processing'].append(str(task.pk))
                new_data = self.__add_solution(task, new_data)
            elif str(task.pk) in data['tasks']['processing']:
                new_data['tasks']['processing'].append(str(task.pk))
                new_data = self.__add_solution(task, new_data)
            elif str(task.pk) in data['tasks']['finished']:
                task.status = status_map['finished']
                task.save()
                try:
                    task.solution
                except ObjectDoesNotExist:
                    # TODO: notify admin with email
                    logger.exception(
                        "Solution was not found for the processing->finished task with id '%s'" % task.pk,
                        stack_info=True
                    )
                if task.progress.tasks_processing > 0:
                    task.progress.tasks_processing -= 1
                task.progress.tasks_finished += 1
                task.progress.save()
            elif str(task.pk) in data['tasks']['error']:
                task.status = status_map['error']
                if str(task.pk) in data['task errors']:
                    task.error = data['task errors'][str(task.pk)]
                else:
                    task.error = "The scheduler hasn't given error description"
                task.save()
                if task.progress.tasks_processing > 0:
                    task.progress.tasks_processing -= 1
                task.progress.tasks_error += 1
                task.progress.save()
            else:
                new_data['tasks']['processing'].append(str(task.pk))
                new_data = self.__add_solution(task, new_data)
        for task in all_tasks['error']:
            if str(task.pk) in data['tasks']['pending']:
                self.error = "The task '%s' with status 'ERROR' has become 'PENDING'" % task.pk
                return None
            elif str(task.pk) in data['tasks']['processing']:
                self.error = "The task '%s' with status 'ERROR' has become 'PROCESSING'" % task.pk
                return None
            elif str(task.pk) in data['tasks']['error']:
                self.error = "The task '%s' with status 'ERROR' has become 'ERROR'" % task.pk
                return None
            elif str(task.pk) in data['tasks']['finished']:
                self.error = "The task '%s' with status 'ERROR' has become 'FINISHED'" % task.pk
                return None
        for task in all_tasks['finished']:
            if str(task.pk) in data['tasks']['pending']:
                self.error = "The task '%s' with status 'FINISHED' has become 'PENDING'" % task.pk
                return None
            elif str(task.pk) in data['tasks']['processing']:
                self.error = "The task '%s' with status 'FINISHED' has become 'PROCESSING'" % task.pk
                return None
            elif str(task.pk) in data['tasks']['error']:
                self.error = "The task '%s' with status 'FINISHED' has become 'ERROR'" % task.pk
                return None
            elif str(task.pk) in data['tasks']['finished']:
                self.error = "The task '%s' with status 'FINISHED' has become 'FINISHED'" % task.pk
                return None
        for task in all_tasks['cancelled']:
            if str(task.pk) in data['tasks']['pending']:
                self.error = "The task '%s' with status 'CANCELLED' has become 'PENDING'" % task.pk
                return None
            elif str(task.pk) in data['tasks']['processing']:
                self.error = "The task '%s' with status 'CANCELLED' has become 'PROCESSING'" % task.pk
                return None
            elif str(task.pk) in data['tasks']['error']:
                self.error = "The task '%s' with status 'CANCELLED' has become 'ERROR'" % task.pk
                return None
            elif str(task.pk) in data['tasks']['finished']:
                self.error = "The task '%s' with status 'CANCELLED' has become 'FINISHED'" % task.pk
                return None
            elif str(task.pk) in data['tasks']['cancelled']:
                self.error = "The task '%s' with status 'CANCELLED' has become 'CANCELLED'" % task.pk
                return None

        if self.scheduler.type == SCHEDULER_TYPE[0][0]:
            for progress in SolvingProgress.objects.all():
                if progress.job.status == JOB_STATUS[1][0]:
                    new_data['job configurations'][progress.job.identifier] = \
                        json.loads(progress.configuration.decode('utf8'))
                    if progress.job.identifier in data['jobs']['error']:
                        change_job_status(progress.job, JOB_STATUS[4][0])
                        if progress.job.identifier in data['job errors']:
                            progress.error = data['job errors'][progress.job.identifier]
                        else:
                            progress.error = "The scheduler hasn't given an error description"
                        progress.save()
                    else:
                        new_data['jobs']['pending'].append(progress.job.identifier)
                elif progress.job.status == JOB_STATUS[2][0]:
                    if progress.job.identifier in data['jobs']['finished']:
                        try:
                            if len(ReportUnknown.objects.filter(
                                    parent=ReportComponent.objects.get(
                                        Q(parent=None, root=progress.job.reportroot) & ~Q(finish_date=None)
                                    )
                            )) > 0:
                                change_job_status(progress.job, JOB_STATUS[5][0])
                            else:
                                change_job_status(progress.job, JOB_STATUS[3][0])
                        except ObjectDoesNotExist:
                            change_job_status(progress.job, JOB_STATUS[5][0])
                    elif progress.job.identifier in data['jobs']['error']:
                        change_job_status(progress.job, JOB_STATUS[4][0])
                        if progress.job.identifier in data['job errors']:
                            progress.error = data['job errors'][progress.job.identifier]
                        else:
                            progress.error = "The scheduler hasn't given an error description"
                        progress.save()
                    else:
                        new_data['jobs']['processing'].append(progress.job.identifier)
                elif progress.job.status == JOB_STATUS[6][0]:
                    new_data['jobs']['cancelled'].append(progress.job.identifier)
        try:
            return json.dumps(new_data)
        except ValueError:
            self.error = "Can't dump json data"
            return None

    def __add_description(self, task, data):
        self.ccc = 0
        data['task descriptions'][str(task.pk)] = {
            'description': json.loads(task.description.decode('utf8'))
        }
        if task.progress.scheduler.type == SCHEDULER_TYPE[1][0]:
            try:
                operator = task.progress.job.reportroot.user
            except ObjectDoesNotExist:
                return data
            data['task descriptions'][str(task.pk)]['VerifierCloud user name'] = operator.scheduleruser.login
            data['task descriptions'][str(task.pk)]['VerifierCloud user password'] = operator.scheduleruser.password
        return data

    def __add_solution(self, task, data):
        self.ccc = 0
        try:
            solution = task.solution
        except ObjectDoesNotExist:
            return data
        data['task solutions'][str(task.pk)] = json.loads(solution.description.decode('utf8'))
        return data


# Case 3.2(3) DONE
class GetTaskData(object):
    def __init__(self, task_id):
        self.error = None
        try:
            self.task = Task.objects.get(pk=int(task_id))
        except ObjectDoesNotExist:
            self.error = 'The task was not found'
            return
        except ValueError:
            self.error = 'Incorrect task id (integer needed)'
            return
        if self.task.progress.job.status != JOB_STATUS[2][0]:
            self.error = "The job is not processing"
            return
        if self.task.status not in [TASK_STATUS[0][0], TASK_STATUS[1][0]]:
            self.error = 'The task status is wrong'


# Case 3.2(4) DONE
class SaveSolution(object):
    def __init__(self, task_id, archive, description):
        self.error = None
        try:
            self.task = Task.objects.get(pk=int(task_id))
        except ObjectDoesNotExist:
            self.error = 'The task was not found'
            return
        except ValueError:
            self.error = 'Incorrect task id (integer needed)'
            return
        if self.task.progress.job.status != JOB_STATUS[2][0]:
            self.error = "The job is not processing"
            return
        self.__create_solution(description, archive)

    def __create_solution(self, description, archive):
        try:
            self.task.solution.description = '{}'
            self.error = 'The task already has solution'
            return
        except ObjectDoesNotExist:
            pass
        Solution.objects.create(
            task=self.task, description=description.encode('utf8'),
            archive=archive, archname=archive.name
        )
        self.task.progress.solutions += 1
        self.task.progress.save()


# Case 3.2(5) DONE
class SetNodes(object):
    def __init__(self, node_data):
        self.error = None
        try:
            self.__read_node_data(node_data)
        except IndexError or KeyError:
            self.error = "Wrong nodes data format"
            NodesConfiguration.objects.all().delete()
        except Exception as e:
            logger.exception("SetNodes failed: %s" % e, stack_info=True)
            NodesConfiguration.objects.all().delete()
            self.error = "Unknown error"

    def __read_node_data(self, nodes_data):
        NodesConfiguration.objects.all().delete()
        for config in json.loads(nodes_data):
            nodes_conf = NodesConfiguration.objects.create(
                cpu=config['CPU model'], cores=config['CPU number'],
                ram=config['RAM memory'], memory=config['disk memory']
            )
            for hostname in config['nodes']:
                self.__create_node(nodes_conf, hostname, config['nodes'][hostname])

    def __create_node(self, conf, hostname, data):
        self.ccc = 0
        node = Node.objects.create(
            config=conf, hostname=hostname, status=data['status']
        )
        if 'workload' in data:
            node.workload = Workload.objects.create(
                cores=data['workload']['reserved CPU number'],
                ram=data['workload']['reserved RAM memory'],
                memory=data['workload']['reserved disk memory'],
                jobs=data['workload']['running verification jobs'],
                tasks=data['workload']['running verification tasks'],
                for_jobs=data['workload']['available for jobs'],
                for_tasks=data['workload']['available for tasks']
            )
            node.save()


# Case 3.2(6) DONE
class UpdateTools(object):
    def __init__(self, sch_type, tools_data):
        self.error = None
        try:
            self.scheduler = Scheduler.objects.get(type=sch_type)
        except ObjectDoesNotExist:
            self.error = 'Scheduler was not found'
            return
        try:
            self.__read_tools_data(tools_data)
        except ValueError or KeyError:
            self.error = "Wrong tools data format"
        except Exception as e:
            logger.exception(e, stack_info=True)
            self.error = "Unknown error"

    def __read_tools_data(self, data):
        VerificationTool.objects.filter(scheduler=self.scheduler).delete()
        for tool in json.loads(data):
            VerificationTool.objects.create(scheduler=self.scheduler, name=tool['tool'], version=tool['version'])


# Case 3.3(2) DONE
class SetSchedulersStatus(object):
    def __init__(self, statuses):
        self.error = None
        try:
            self.statuses = json.loads(statuses)
        except ValueError:
            self.error = "Incorrect format of statuses"
            return
        self.__update_statuses()

    def __update_statuses(self):
        sch_type_map = {}
        for sch_type in SCHEDULER_TYPE:
            sch_type_map[sch_type[1]] = sch_type[0]
        for sch_type in self.statuses:
            try:
                scheduler = Scheduler.objects.get(type=sch_type_map[sch_type])
            except ObjectDoesNotExist:
                self.error = "Scheduler was not found"
                return
            if self.statuses[sch_type] not in list(x[0] for x in SCHEDULER_STATUS):
                self.error = "Scheduler status is wrong"
                return
            if scheduler.status == self.statuses[sch_type]:
                continue
            if self.statuses[sch_type] == SCHEDULER_STATUS[2][0]:
                self.__finish_tasks(scheduler)
            scheduler.status = self.statuses[sch_type]
            scheduler.save()

    def __finish_tasks(self, scheduler):
        self.ccc = 0
        for progress in scheduler.solvingprogress_set.filter(job__status=JOB_STATUS[2][0], finish_date=None):
            for task in progress.task_set.filter(status__in=[TASK_STATUS[0][0], TASK_STATUS[1][0]]):
                if task.status == TASK_STATUS[0][0]:
                    progress.tasks_pending -= 1
                else:
                    progress.tasks_processing -= 1
                progress.tasks_error += 1
                task.error = "Task was finished with error due to scheduler is disconnected"
                task.save()
            if scheduler.type == SCHEDULER_TYPE[0][0]:
                progress.finish_date = now()
                progress.error = "Klever scheduler was disconnected"
                change_job_status(progress.job, JOB_STATUS[5][0])
            progress.save()


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


class NodesData(object):
    def __init__(self):
        self.conf_data = []
        self.total_data = {
            'cores': {0: 0, 1: 0},
            'ram': {0: 0, 1: 0},
            'memory': {0: 0, 1: 0},
            'jobs': 0,
            'tasks': 0
        }
        self.nodes = []
        self.__get_data()

    def __get_data(self):
        cnt = 0
        for conf in NodesConfiguration.objects.all():
            cnt += 1
            conf_data = {
                'id': conf.pk,
                'conf': {
                    'ram': int(conf.ram / 10**9),
                    'cores': conf.cores,
                    'memory': int(conf.memory / 10**9),
                    'num_of_nodes': len(conf.node_set.all())
                },
                'cnt': cnt,
                'cpu': conf.cpu,
                'cores': {0: 0, 1: 0},
                'ram': {0: 0, 1: 0},
                'memory': {0: 0, 1: 0},
                'jobs': 0,
                'tasks': 0
            }
            for node in conf.node_set.all():
                node_data = {
                    'conf_id': conf.pk,
                    'hostname': node.hostname,
                    'status': node.get_status_display(),
                    'cpu': conf.cpu,
                    'cores': '-',
                    'ram': '-',
                    'memory': '-',
                    'tasks': '-',
                    'jobs': '-',
                    'for_tasks': '-',
                    'for_jobs': '-'
                }
                if node.workload is not None:
                    conf_data['cores'][0] += node.workload.cores
                    conf_data['cores'][1] += conf.cores
                    conf_data['ram'][0] += node.workload.ram
                    conf_data['ram'][1] += conf.ram
                    conf_data['memory'][0] += node.workload.memory
                    conf_data['memory'][1] += conf.memory
                    node_data.update({
                        'cores': "%s/%s" % (node.workload.cores, conf.cores),
                        'ram': "%s/%s" % (int(node.workload.ram / 10**9),
                                          int(conf.ram / 10**9)),
                        'memory': "%s/%s" % (int(node.workload.memory / 10**9),
                                             int(conf.memory / 10**9)),
                        'tasks': node.workload.tasks,
                        'jobs': node.workload.jobs,
                        'for_jobs': node.workload.for_jobs,
                        'for_tasks': node.workload.for_tasks,
                    })
                self.nodes.append(node_data)
            self.total_data['cores'] = (self.total_data['cores'][0] + conf_data['cores'][0],
                                        self.total_data['cores'][1] + conf_data['cores'][1])
            self.total_data['ram'] = (self.total_data['ram'][0] + conf_data['ram'][0],
                                      self.total_data['ram'][1] + conf_data['ram'][1])
            self.total_data['memory'] = (self.total_data['memory'][0] + conf_data['memory'][0],
                                         self.total_data['memory'][1] + conf_data['memory'][1])
            conf_data['cores'] = "%s/%s" % (conf_data['cores'][0], conf_data['cores'][1])
            conf_data['ram'] = "%s/%s" % (int(conf_data['ram'][0] / 10**9),
                                          int(conf_data['ram'][1] / 10**9))
            conf_data['memory'] = "%s/%s" % (int(conf_data['memory'][0] / 10**9),
                                             int(conf_data['memory'][1] / 10**9))
            self.conf_data.append(conf_data)
        self.total_data['cores'] = "%s/%s" % (self.total_data['cores'][0], self.total_data['cores'][1])
        self.total_data['ram'] = "%s/%s" % (int(self.total_data['ram'][0] / 10**9),
                                            int(self.total_data['ram'][1] / 10**9))
        self.total_data['memory'] = "%s/%s" % (int(self.total_data['memory'][0] / 10**9),
                                               int(self.total_data['memory'][1] / 10**9))


# Case 3.4(5) DONE
class StartJobDecision(object):
    def __init__(self, user, job_id, data):
        self.error = None
        self.operator = user
        self.data = data
        self.job = self.__get_job(job_id)
        if self.error is not None:
            return
        self.job_scheduler = self.__get_scheduler()
        if self.error is not None:
            return
        self.klever_core_data = self.__get_klever_core_data()
        self.__check_schedulers()
        if self.error is not None:
            return
        self.progress = self.__create_solving_progress()
        if self.error is not None:
            return
        try:
            self.job.reportroot.delete()
        except ObjectDoesNotExist:
            pass
        ReportRoot.objects.create(user=self.operator, job=self.job)
        self.job.status = JOB_STATUS[1][0]
        self.job.save()

    def __get_klever_core_data(self):
        scheduler = SCHEDULER_TYPE[0][1]
        for sch in SCHEDULER_TYPE:
            if sch[0] == self.data[0][1]:
                scheduler = sch[1]
                break
        return {
            'identifier': self.job.identifier,
            'priority': self.data[0][0],
            'abstract task generation priority': self.data[0][2],
            'task scheduler': scheduler,
            'resource limits': {
                'memory size': int(self.data[2][0] * 10**9),
                'number of CPU cores': self.data[2][1],
                'disk memory size': int(self.data[2][2] * 10**9),
                'CPU model': self.data[2][3] if isinstance(self.data[2][3], str) and len(self.data[2][3]) > 0 else None,
                'CPU time': int(self.data[2][4] * 10**4 * 6) if self.data[2][4] is not None else None,
                'wall time': int(self.data[2][5] * 10**4 * 6) if self.data[2][5] is not None else None
            },
            'keep intermediate files': self.data[4][0],
            'upload input files of static verifiers': self.data[4][1],
            'upload other intermediate files': self.data[4][2],
            'allow local source directories use': self.data[4][3],
            'ignore another instances': self.data[4][4],
            'logging': {
                'formatters': [
                    {
                        'name': 'brief',
                        'value': self.data[3][1]
                    },
                    {
                        'name': 'detailed',
                        'value': self.data[3][3]
                    }
                ],
                'loggers': [
                    {
                        'name': 'default',
                        'handlers': [
                            {
                                'formatter': 'brief',
                                'level': self.data[3][0],
                                'name': 'console'
                            },
                            {
                                'formatter': 'detailed',
                                'level': self.data[3][2],
                                'name': 'file'
                            }
                        ]
                    }
                ]
            },
            'parallelism': {
                'Build': self.data[1][0],
                'Tasks generation': self.data[1][1]
            }
        }

    def __get_scheduler(self):
        try:
            return Scheduler.objects.get(type=self.data[0][1])
        except ObjectDoesNotExist:
            self.error = _('The scheduler was not found')
            return None

    def __get_job(self, job_id):
        try:
            job = Job.objects.get(pk=job_id)
        except ObjectDoesNotExist:
            self.error = _('The job was not found')
            return
        if not JobAccess(self.operator, job).can_decide():
            self.error = _("You don't have an access to start decision of this job")
            return
        return job

    def __create_solving_progress(self):
        try:
            self.job.solvingprogress.delete()
        except ObjectDoesNotExist:
            pass
        self.__save_configuration()
        return SolvingProgress.objects.create(
            job=self.job, priority=self.data[0][0],
            scheduler=self.job_scheduler,
            configuration=json.dumps(self.klever_core_data).encode('utf8')
        )

    def __save_configuration(self):
        m = BytesIO()
        m.write(json.dumps(self.klever_core_data, sort_keys=True, indent=4).encode('utf8'))
        m.seek(0)
        check_sum = file_checksum(m)
        try:
            db_file = File.objects.get(hash_sum=check_sum)
        except ObjectDoesNotExist:
            db_file = File()
            db_file.file.save('job-%s.conf' % self.job.identifier[:5], NewFile(m))
            db_file.hash_sum = check_sum
            db_file.save()
        RunHistory.objects.create(job=self.job, operator=self.operator, configuration=db_file, status=JOB_STATUS[1][0])

    def __check_schedulers(self):
        try:
            klever_sch = Scheduler.objects.get(type=SCHEDULER_TYPE[0][0])
        except ObjectDoesNotExist:
            self.error = _('Unknown error')
            return
        if klever_sch.status == SCHEDULER_STATUS[2][0]:
            self.error = _('The Klever scheduler is disconnected')
            return
        if self.job_scheduler.type == SCHEDULER_TYPE[1][0]:
            if self.job_scheduler.status == SCHEDULER_STATUS[2][0]:
                self.error = _('The VerifierCloud scheduler is disconnected')
                return
            try:
                self.operator.scheduleruser
            except ObjectDoesNotExist:
                self.error = _("You didn't specify credentials for VerifierCloud")
                return
