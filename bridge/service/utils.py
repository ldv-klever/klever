#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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

import os
import json
import zipfile
from io import BytesIO
from wsgiref.util import FileWrapper

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.files import File as NewFile
from django.db.models import F
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from bridge.vars import JOB_STATUS, PRIORITY, SCHEDULER_STATUS, SCHEDULER_TYPE, TASK_STATUS
from bridge.utils import file_get_or_create, logger, BridgeException

from users.models import SchedulerUser
from jobs.models import RunHistory, JobFile, FileSystem, Job
from reports.models import ReportRoot, ReportUnknown, ReportComponent
from service.models import Scheduler, Decision, Task, Solution, VerificationTool, Node, NodesConfiguration, Workload

from users.utils import HumanizedValue
from jobs.utils import JobAccess
from jobs.serializers import change_job_status


class ServiceError(Exception):
    pass


class NotAnError(Exception):
    pass


class ScheduleTask:
    def __init__(self, job_id, description, archive):
        try:
            self.progress = Decision.objects\
                .annotate(job_status=F('job__status'), sch_status=F('scheduler__status'))\
                .get(job_id=job_id)
        except ObjectDoesNotExist:
            raise ServiceError('Solving progress of the job was not found')
        if self.progress.job.status == JOB_STATUS[6][0]:
            # Do not process cancelling jobs
            raise NotAnError('The job is cancelling')
        self.description = description
        try:
            priority = json.loads(self.description)['priority']
        except Exception:
            raise ServiceError('Wrong description format')
        if priority not in set(x[0] for x in PRIORITY):
            raise ServiceError('Wrong priority')
        if self.progress.job_status != JOB_STATUS[2][0]:
            raise ServiceError('The job is not processing')
        if self.progress.sch_status == SCHEDULER_STATUS[2][0]:
            raise ServiceError('The scheduler for tasks is disconnected')
        if compare_priority(self.progress.priority, priority):
            raise ServiceError('Priority of the task is too big')
        try:
            self.__check_archive(archive)
        except Exception as e:
            logger.info(str(e))
            raise NotAnError('ZIP error')
        self.task_id = self.__create_task(archive)

    def __create_task(self, archive):
        task = Task.objects.create(
            progress=self.progress, archname=archive.name,
            archive=archive, description=self.description.encode('utf8')
        )
        Decision.objects.filter(id=self.progress.id)\
            .update(tasks_total=F('tasks_total') + 1, tasks_pending=F('tasks_pending') + 1)
        return task.id

    def __check_archive(self, arch):
        self.__is_not_used()
        if not zipfile.is_zipfile(arch) or zipfile.ZipFile(arch).testzip():
            raise ValueError('The task archive "%s" is not a ZIP file' % arch)

    def __is_not_used(self):
        pass


class GetTasksStatuses:
    def __init__(self, tasks_ids):
        self._task_ids = list(int(x) for x in json.loads(tasks_ids))
        self._tasks = self.__get_tasks()
        self.__check_jobs()
        self.statuses = self.__get_statuses()

    def __get_tasks(self):
        tasks = Task.objects.filter(id__in=self._task_ids)
        if tasks.count() != len(set(self._task_ids)):
            raise NotAnError('One of the tasks was not found')
        return tasks

    def __check_jobs(self):
        if Decision.objects.filter(id__in=list(t.progress_id for t in self._tasks))\
                .exclude(job__status=JOB_STATUS[2][0]).count() > 0:
            raise ServiceError('One of the jobs is not processing')

    def __get_statuses(self):
        res = {'pending': [], 'processing': [], 'finished': [], 'error': []}
        for t in self._tasks:
            res[t.status.lower()].append(str(t.id))
        return json.dumps(res, ensure_ascii=False)


class GetSolution:
    def __init__(self, task_id):
        try:
            self.task = Task.objects.get(id=task_id)
        except ObjectDoesNotExist:
            raise NotAnError("The task '%s' was not found" % task_id)
        if Job.objects.get(solvingprogress=self.task.progress).status != JOB_STATUS[2][0]:
            raise ServiceError('The job is not processing')
        if self.task.status == TASK_STATUS[3][0]:
            if self.task.error is None:
                raise ServiceError("The task was finished with error but doesn't have its description")
        elif self.task.status == TASK_STATUS[2][0]:
            try:
                self.solution = Solution.objects.get(task=self.task)
            except ObjectDoesNotExist:
                raise ServiceError("The solution of the finished task doesn't exist")
        else:
            raise ServiceError('The task is not finished')


class RemoveTask:
    def __init__(self, task_id):
        try:
            self.task = Task.objects.get(id=task_id)
        except ObjectDoesNotExist:
            raise NotAnError("The task '%s' was not found" % task_id)
        if Job.objects.get(solvingprogress=self.task.progress).status != JOB_STATUS[2][0]:
            raise ServiceError('The job is not processing')
        if self.task.status == TASK_STATUS[3][0]:
            if self.task.error is None:
                raise ServiceError("The task was finished with error but doesn't have its description")
        elif self.task.status == TASK_STATUS[2][0]:
            try:
                Solution.objects.get(task=self.task)
            except ObjectDoesNotExist:
                raise ServiceError("The solution of the finished task doesn't exist")
        else:
            raise ServiceError('The task is not finished')
        self.task.delete()


class FinishJobDecision:
    def __init__(self, inst, status, error=None):
        if isinstance(inst, Decision):
            self.decision = inst
            self.job = self.decision.job
        elif isinstance(inst, Job):
            self.job = inst
            try:
                self.decision = Decision.objects.get(job=self.job)
            except ObjectDoesNotExist:
                logger.exception('The job does not have solving progress')
                change_job_status(self.job, JOB_STATUS[5][0])
                return
        else:
            raise ValueError('Unsupported argument: %s' % type(inst))
        self.error = error
        self.status = self.__get_status(status)
        try:
            self.__remove_tasks()
        except ServiceError as e:
            logger.exception(e)
            self.decision.error = str(e)
            self.status = JOB_STATUS[5][0]
        if self.error is not None:
            if len(self.error) > 1024:
                logger.error("The job '%s' finished with large error: %s" % (self.job.identifier, self.error))
                self.error = "Length of error for job '%s' is large (1024 characters is maximum)" % self.job.identifier
                self.status = JOB_STATUS[8][0]
            self.decision.error = self.error
        self.decision.finish_date = now()
        self.decision.save()
        change_job_status(self.job, self.status)

    def __remove_tasks(self):
        if self.job.status == JOB_STATUS[1][0]:
            return
        elif self.job.status != JOB_STATUS[2][0]:
            raise ServiceError('The job is not processing')
        elif self.decision.tasks.filter(status__in={TASK_STATUS[0][0], TASK_STATUS[0][1]}).count() > 0:
            raise ServiceError('There are unfinished tasks')
        elif self.decision.tasks.filter(status=TASK_STATUS[3][0], error=None).count() > 0:
            raise ServiceError('There are tasks finished with error and without error descriptions')
        elif self.decision.tasks.filter(status=TASK_STATUS[2][0], solution=None).count() > 0:
            raise ServiceError('There are finished tasks without solutions')
        self.decision.tasks.all().delete()

    def __get_status(self, status):
        if status not in set(x[0] for x in JOB_STATUS):
            raise ValueError('Unsupported status: %s' % status)
        if status == JOB_STATUS[3][0]:
            if self.job.status != JOB_STATUS[2][0]:
                self.error = "Only processing jobs can be finished"
                return JOB_STATUS[5][0]
            unfinished_reports = list(ReportComponent.objects.filter(root__job=self.job, finish_date=None)
                                      .values_list('identifier', flat=True))
            if len(unfinished_reports) > 0:
                self.error = 'There are unfinished reports (%s): %s' % (len(unfinished_reports), unfinished_reports)
                logger.error(self.error)
                if len(self.error) > 1024:
                    self.error = 'There are unfinished reports (%s)' % len(unfinished_reports)
                return JOB_STATUS[5][0]

            try:
                core_r = ReportComponent.objects.get(parent=None, root__job=self.job)
            except ObjectDoesNotExist:
                self.error = "The job doesn't have Core report"
                return JOB_STATUS[5][0]
            if ReportUnknown.objects.filter(parent=core_r, component=core_r.component, root__job=self.job).exists():
                return JOB_STATUS[4][0]

            try:
                self.__check_progress()
            except ServiceError as e:
                self.error = str(e)
                return JOB_STATUS[5][0]
            except Exception as e:
                logger.exception(e)
                self.error = 'Unknown error while checking progress'
                return JOB_STATUS[5][0]
        elif status == JOB_STATUS[4][0]:
            try:
                core_r = ReportComponent.objects.get(parent=None, root__job=self.job)
            except ObjectDoesNotExist:
                pass
            else:
                unfinished_components = ReportComponent.objects.filter(root__job=self.job, finish_date=None)
                core_unknowns = ReportUnknown.objects.filter(
                    parent=core_r, component=core_r.component, root__job=self.job
                )
                if unfinished_components.exists() or not core_unknowns.exists():
                    status = JOB_STATUS[5][0]
            if self.error is None:
                self.error = "The scheduler hasn't given an error description"
        return status

    def __check_progress(self):
        if self.decision.start_ts is not None:
            tasks_progress = [
                self.decision.solved_ts, self.decision.failed_ts, self.decision.total_ts,
                self.decision.start_ts, self.decision.finish_ts
            ]
            if any(x is None for x in tasks_progress):
                raise ServiceError("The job didn't got full tasks progress data")
            elif self.decision.solved_ts + self.decision.failed_ts != self.decision.total_ts:
                raise ServiceError("Tasks solving progress is incorrect")
        if self.decision.start_sj is not None:
            sj_progress = [
                self.decision.solved_sj, self.decision.failed_sj, self.decision.total_sj, self.decision.finish_sj
            ]
            if any(x is None for x in sj_progress):
                raise ServiceError("The job didn't got full subjobs progress data")
            elif self.decision.solved_sj + self.decision.failed_sj != self.decision.total_sj:
                raise ServiceError("Subjobs solving progress is not finished")


class StopDecision:
    def __init__(self, job):
        if job.status not in {JOB_STATUS[1][0], JOB_STATUS[2][0]}:
            raise BridgeException(_("Only pending and processing jobs can be stopped"))
        try:
            self.decision = Decision.objects.get(job=job)
        except ObjectDoesNotExist:
            raise BridgeException(_('The job decision does not exist'))

        change_job_status(job, JOB_STATUS[6][0])
        self.__clear_tasks()

    def __clear_tasks(self):
        in_progress_num = self.decision.tasks.filter(status__in=[TASK_STATUS[0][0], TASK_STATUS[1][0]]).count()
        self.decision.tasks_processing = self.decision.tasks_pending = 0
        self.decision.tasks_cancelled += in_progress_num
        self.decision.finish_date = now()
        self.decision.error = "The job was cancelled"
        self.decision.save()
        # If there are a lot of tasks that are not still deleted it could be too long
        # as there is request to DB for each task here (pre_delete signal)
        self.decision.tasks.all().delete()


class GetTasks:
    def __init__(self, sch_type, tasks):
        try:
            self._scheduler = Scheduler.objects.get(type=sch_type)
        except ObjectDoesNotExist:
            raise ServiceError('The scheduler was not found')
        self._operators = {}
        self._progresses = {}
        self._tasks_statuses = {}
        self._solution_req = set()
        self._data = {
            'jobs': {'pending': [], 'processing': [], 'error': [], 'finished': [], 'cancelled': []},
            'tasks': {'pending': [], 'processing': [], 'error': [], 'finished': []},
            'task errors': {},
            'task descriptions': {},
            'task solutions': {},
            'job errors': {},
            'job configurations': {},
            'jobs progress': {}
        }
        self.__get_tasks(tasks)
        try:
            self.newtasks = json.dumps(self._data, ensure_ascii=False, sort_keys=True, indent=4)
        except ValueError:
            raise ServiceError("Can't dump json")

    def __get_tasks(self, tasks):
        data = json.loads(tasks)
        if 'jobs' not in data:
            data['jobs'] = {'error': [], 'finished': []}
        if 'tasks' not in data:
            data['tasks'] = {'pending': [], 'processing': [], 'error': [], 'finished': []}
        for x in ['error', 'finished', 'cancelled']:
            if x not in data['jobs']:
                data['jobs'][x] = []
        for x in ['pending', 'processing', 'error', 'finished']:
            if x not in data['tasks']:
                data['tasks'][x] = []
        if 'task errors' not in data:
            data['task errors'] = {}
        if 'job errors' not in data:
            data['job errors'] = {}

        # Finish job decisions and add pending/processing/cancelled jobs
        if self._scheduler.type == SCHEDULER_TYPE[0][0]:
            for progress in Decision.objects.filter(job__status=JOB_STATUS[1][0], fake=False)\
                    .select_related('job'):
                if progress.job.identifier in data['jobs']['finished']:
                    FinishJobDecision(progress, JOB_STATUS[5][0], "The job can't be finished as it is still pending")
                elif progress.job.identifier in data['jobs']['error']:
                    FinishJobDecision(progress, JOB_STATUS[4][0], data['job errors'].get(progress.job.identifier))
                else:
                    with progress.configuration.file as fp:
                        self._data['job configurations'][progress.job.identifier] = json.loads(fp.read().decode('utf8'))
                    self._data['job configurations'][progress.job.identifier]['task resource limits'] = \
                        self.__get_tasks_limits(progress.job_id)
                    self._data['jobs']['pending'].append(progress.job.identifier)
            for progress in Decision.objects.filter(job__status=JOB_STATUS[2][0], fake=False)\
                    .select_related('job'):
                if progress.job.identifier in data['jobs']['finished']:
                    FinishJobDecision(progress, JOB_STATUS[3][0])
                elif progress.job.identifier in data['jobs']['error']:
                    FinishJobDecision(progress, JOB_STATUS[4][0], data['job errors'].get(progress.job.identifier))
                else:
                    self._data['jobs']['processing'].append(progress.job.identifier)
                    self._data['jobs progress'][progress.job.identifier] = JobProgressData(progress.job).get()
            for progress in Decision.objects.filter(job__status=JOB_STATUS[6][0]).select_related('job'):
                if progress.job.identifier in data['jobs']['cancelled']:
                    change_job_status(progress.job, JOB_STATUS[7][0])
                else:
                    self._data['jobs']['cancelled'].append(progress.job.identifier)

        # Everything with tasks
        all_tasks = dict((x[0].lower(), []) for x in TASK_STATUS)
        for task in Task.objects.filter(progress__scheduler=self._scheduler, progress__job__status=JOB_STATUS[2][0])\
                .annotate(sol=F('solution__id')).order_by('id'):
            all_tasks[task.status.lower()].append(task)

        for old_status in ['error', 'finished']:
            for task in all_tasks[old_status]:
                for new_status in ['pending', 'processing', 'error', 'finished']:
                    if str(task.pk) in data['tasks'][new_status]:
                        raise ServiceError("The task '%s' with status '%s' has become '%s'" % (
                            task.id, old_status.upper(), new_status.upper()
                        ))
        for task in all_tasks['processing']:
            if str(task.id) in data['tasks']['pending']:
                raise ServiceError("The task '%s' with status 'PROCESSING' has become 'PENDING'" % task.id)

        for task in all_tasks['pending']:
            if str(task.id) in data['tasks']['pending']:
                self._data['tasks']['pending'].append(str(task.id))
                self._solution_req.add(task.id)
                self.__add_description(task)
            elif str(task.id) in data['tasks']['processing']:
                self.__change_status(task, 'pending', 'processing')
                self._data['tasks']['processing'].append(str(task.id))
                self._solution_req.add(task.id)
                self.__add_description(task)
            elif str(task.id) in data['tasks']['finished']:
                self.__change_status(task, 'pending', 'finished')
                if task.sol is None:
                    # TODO: email notification
                    logger.error('There are finished tasks without solutions', stack_info=True)
            elif str(task.id) in data['tasks']['error']:
                if str(task.id) in data['task errors']:
                    if len(data['task errors'][str(task.id)]) > 1024:
                        task.error = "Length of error for task with id '%s' must be less than 1024 characters" % task.id
                    else:
                        task.error = data['task errors'][str(task.id)]
                else:
                    task.error = "The scheduler hasn't given error description"
                task.save()
                self.__change_status(task, 'pending', 'error')
            else:
                self._data['tasks']['pending'].append(str(task.id))
                self._solution_req.add(task.id)
                self.__add_description(task)
        for task in all_tasks['processing']:
            if str(task.id) in data['tasks']['processing']:
                self._data['tasks']['processing'].append(str(task.id))
                self._solution_req.add(task.id)
            elif str(task.id) in data['tasks']['finished']:
                self.__change_status(task, 'processing', 'finished')
                if task.sol is None:
                    # TODO: email notification
                    logger.error('There are finished tasks without solutions', stack_info=True)
            elif str(task.id) in data['tasks']['error']:
                if str(task.id) in data['task errors']:
                    if len(data['task errors'][str(task.id)]) > 1024:
                        task.error = "Length of error for task with id '%s' must be less than 1024 characters" % task.id
                    else:
                        task.error = data['task errors'][str(task.id)]
                else:
                    task.error = "The scheduler hasn't given error description"
                task.save()
                self.__change_status(task, 'processing', 'error')
            else:
                self._data['tasks']['processing'].append(str(task.id))
                self._solution_req.add(task.id)
        # There are no cancelled tasks because when the task is cancelled it is deleted,
        # and there are no changes of status to cancelled in get_jobs_and_tasks_status()
        self.__finish_with_tasks()

    def __add_description(self, task):
        task_id = str(task.id)
        self._data['task descriptions'][task_id] = {'description': json.loads(task.description.decode('utf8'))}
        if self._scheduler.type == SCHEDULER_TYPE[1][0]:
            if task.progress_id in self._operators:
                self._data['task descriptions'][task_id]['VerifierCloud user name'] = \
                    self._operators[task.progress_id][0]
                self._data['task descriptions'][task_id]['VerifierCloud user password'] = \
                    self._operators[task.progress_id][1]
            else:
                try:
                    root = ReportRoot.objects.get(job__solvingprogress=task.progress)
                    sch_user = SchedulerUser.objects.get(user=root.user)
                except ObjectDoesNotExist:
                    return
                else:
                    self._operators[task.progress_id] = (sch_user.login, sch_user.password)
                    self._data['task descriptions'][task_id]['VerifierCloud user name'] = sch_user.login
                    self._data['task descriptions'][task_id]['VerifierCloud user password'] = sch_user.password

    def __change_status(self, task, old, new):
        old = old.upper()
        new = new.upper()
        fields = {
            TASK_STATUS[0][0]: 'tasks_pending',
            TASK_STATUS[1][0]: 'tasks_processing',
            TASK_STATUS[2][0]: 'tasks_finished',
            TASK_STATUS[3][0]: 'tasks_error',
            TASK_STATUS[4][0]: 'tasks_cancelled'
        }
        if task.progress_id not in self._progresses:
            self._progresses[task.progress_id] = SolvingProgress.objects.get(id=task.progress_id)
        old_num = getattr(self._progresses[task.progress_id], fields[old])
        if old_num <= 0:
            logger.error('Something wrong with SolvingProgress cache: '
                         'number of %s tasks is 0, but there is at least one such task in the system' % old)
        else:
            setattr(self._progresses[task.progress_id], fields[old], old_num - 1)
        new_num = getattr(self._progresses[task.progress_id], fields[new])
        setattr(self._progresses[task.progress_id], fields[new], new_num + 1)

        if new not in self._tasks_statuses:
            self._tasks_statuses[new] = set()
        self._tasks_statuses[new].add(task.id)

    def __finish_with_tasks(self):
        for status in self._tasks_statuses:
            Task.objects.filter(id__in=self._tasks_statuses[status]).update(status=status)
        for progress_id in self._progresses:
            self._progresses[progress_id].save()
        for solution in Solution.objects.filter(task_id__in=self._solution_req):
            self._data['task solutions'][str(solution.task_id)] = json.loads(solution.description.decode('utf8'))

    def __get_tasks_limits(self, job_id):
        self.__is_not_used()
        try:
            tasks = FileSystem.objects.get(
                job__job_id=job_id, job__version=F('job__job__version'), name='tasks.json', parent=None
            )
        except ObjectDoesNotExist:
            logger.error("The tasks.json file doesn't exists")
            return {}
        try:
            with open(os.path.join(settings.MEDIA_ROOT, tasks.file.file.name), mode='r', encoding='utf8') as fp:
                return json.load(fp)
        except Exception as e:
            logger.exception(e)
            return {}

    def __is_not_used(self):
        pass


class GetTaskData:
    def __init__(self, task_id):
        try:
            self.task = Task.objects.get(id=task_id)
        except ObjectDoesNotExist:
            raise NotAnError('The task %s was not found' % task_id)
        if Job.objects.get(solvingprogress=self.task.progress).status != JOB_STATUS[2][0]:
            raise ServiceError('The job is not processing')
        if self.task.status not in {TASK_STATUS[0][0], TASK_STATUS[1][0]}:
            raise ServiceError('The task status is wrong')


class SaveSolution:
    def __init__(self, task_id, archive, description):
        try:
            self.task = Task.objects.get(id=task_id)
        except ObjectDoesNotExist:
            raise NotAnError('The task %s was not found' % task_id)
        if not Job.objects.filter(solvingprogress=self.task.progress_id, status=JOB_STATUS[2][0]).exists():
            raise ServiceError('The job is not processing')
        try:
            self.__check_archive(archive)
        except Exception as e:
            logger.info(str(e))
            raise NotAnError('ZIP error')
        self.__create_solution(description, archive)

    def __create_solution(self, description, archive):
        try:
            Solution.objects.get(task=self.task)
            raise ServiceError('The task already has solution')
        except ObjectDoesNotExist:
            pass
        Solution.objects.create(task=self.task, description=description.encode('utf8'),
                                archive=archive, archname=archive.name)

        progress = SolvingProgress.objects.get(id=self.task.progress_id)
        progress.solutions += 1
        progress.save()

    def __check_archive(self, arch):
        self.__is_not_used()
        if not zipfile.is_zipfile(arch) or zipfile.ZipFile(arch).testzip():
            raise ValueError('The task archive "%s" is not a ZIP file' % arch)

    def __is_not_used(self):
        pass


class SetNodes:
    def __init__(self, node_data):
        try:
            self.__read_node_data(node_data)
        except IndexError or KeyError:
            NodesConfiguration.objects.all().delete()
            raise ServiceError('Wrong nodes data format')
        except Exception:
            NodesConfiguration.objects.all().delete()
            raise ServiceError('Unknown error')

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
        workload = None
        if 'workload' in data:
            workload = Workload.objects.create(
                cores=data['workload']['reserved CPU number'],
                ram=data['workload']['reserved RAM memory'],
                memory=data['workload']['reserved disk memory'],
                jobs=data['workload']['running verification jobs'],
                tasks=data['workload']['running verification tasks'],
                for_jobs=data['workload']['available for jobs'],
                for_tasks=data['workload']['available for tasks']
            )
        Node.objects.create(config=conf, hostname=hostname, status=data['status'], workload=workload)


class SetSchedulersStatus:
    task_error = 'Task was finished with error due to scheduler is disconnected'
    decision_error = 'Klever scheduler was disconnected'

    def __init__(self, statuses):
        try:
            self.statuses = json.loads(statuses)
        except ValueError:
            raise ServiceError('Incorrect format of statuses')
        self.__update_statuses()

    def __update_statuses(self):
        for sch_type in self.statuses:
            try:
                scheduler = Scheduler.objects.get(type=sch_type)
            except ObjectDoesNotExist:
                raise ServiceError('Scheduler was not found')
            if self.statuses[sch_type] not in list(x[0] for x in SCHEDULER_STATUS):
                raise ServiceError('Scheduler status is wrong')
            if scheduler.status == self.statuses[sch_type]:
                continue
            if self.statuses[sch_type] == SCHEDULER_STATUS[2][0]:
                self.__finish_tasks(scheduler)
            scheduler.status = self.statuses[sch_type]
            scheduler.save()

    def __finish_tasks(self, scheduler):
        for progress in scheduler.solvingprogress_set.filter(job__status=JOB_STATUS[2][0], finish_date=None):
            progress.tasks_pending = progress.tasks_processing = 0
            # Pending or processing tasks
            progress.tasks_error += Task.objects.filter(
                status__in=[TASK_STATUS[0][0], TASK_STATUS[1][0]], progress=progress
            ).update(error=self.task_error)
            if scheduler.type == SCHEDULER_TYPE[0][0]:
                progress.finish_date = now()
                progress.error = self.decision_error
                change_job_status(progress.job, JOB_STATUS[8][0])
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


class NodesData:
    def __init__(self):
        self.nodes = Node.objects.select_related('workload', 'config')
        self.configs = []
        self.totals = {
            'cpu_number': [0, 0],
            'ram_memory': [0, 0],
            'disk_memory': [0, 0],
            'jobs': 0, 'tasks': 0
        }
        self.__get_data()

    def __get_data(self):
        cnt = 0
        for conf in NodesConfiguration.objects.all():
            cnt += 1
            conf_nodes = list(node for node in self.nodes if node.config_id == conf.id)
            conf_data = {
                'cnt': cnt,
                'obj': conf,
                'id': conf.id,
                'nodes_number': len(conf_nodes),
                'cpu_number': [0, 0],
                'ram_memory': [0, 0],
                'disk_memory': [0, 0],
                'jobs': 0, 'tasks': 0
            }
            for node in conf_nodes:
                try:
                    workload = node.workload
                except Workload.DoesNotExist:
                    continue
                conf_data['cpu_number'][0] += workload.cpu_number
                conf_data['cpu_number'][1] += conf.cpu_number
                conf_data['ram_memory'][0] += workload.ram_memory
                conf_data['ram_memory'][1] += conf.ram_memory
                conf_data['disk_memory'][0] += workload.disk_memory
                conf_data['disk_memory'][1] += conf.disk_memory
                conf_data['jobs'] += workload.running_verification_jobs
                conf_data['tasks'] += workload.running_verification_tasks

            self.totals['cpu_number'][0] += conf_data['cpu_number'][0]
            self.totals['cpu_number'][1] += conf_data['cpu_number'][1]
            self.totals['ram_memory'][0] += conf_data['ram_memory'][0]
            self.totals['ram_memory'][1] += conf_data['ram_memory'][1]
            self.totals['disk_memory'][0] += conf_data['disk_memory'][0]
            self.totals['disk_memory'][1] += conf_data['disk_memory'][1]
            self.totals['jobs'] += conf_data['jobs']
            self.totals['tasks'] += conf_data['tasks']
            self.configs.append(conf_data)


class StartJobDecision:
    def __init__(self, user, job, configuration, fake=False):
        self.operator = user
        self._job = job
        self.configuration = configuration
        self._fake = fake

        self._scheduler = self.__get_scheduler()
        self.__create_decision()

        # The job will be saved in change_job_status()
        self._job.weight = self.configuration['weight']
        change_job_status(self._job, JOB_STATUS[1][0])

    def __get_scheduler(self):
        try:
            scheduler = Scheduler.objects.get(type=self.configuration['task scheduler'])
        except ObjectDoesNotExist:
            raise BridgeException(_('The task scheduler was not found'))
        if scheduler.type == SCHEDULER_TYPE[1][0]:
            if scheduler.status == SCHEDULER_STATUS[2][0]:
                raise BridgeException(_('The VerifierCloud scheduler is disconnected'))
        else:
            try:
                klever_sch = Scheduler.objects.get(type=SCHEDULER_TYPE[0][0])
            except ObjectDoesNotExist:
                raise BridgeException(_("Schedulers weren't populated"))
            if klever_sch.status == SCHEDULER_STATUS[2][0]:
                raise BridgeException(_('The Klever scheduler is disconnected'))
        return scheduler

    def __create_decision(self):
        ReportRoot.objects.filter(job=self._job).delete()
        ReportRoot.objects.create(user=self.operator, job=self._job)
        Decision.objects.filter(job=self._job).delete()
        conf = self.__save_configuration()
        Decision.objects.create(
            job=self._job, fake=self._fake, scheduler=self._scheduler,
            priority=self.configuration['priority'], configuration=conf
        )
        RunHistory.objects.create(job=self._job, operator=self.operator, configuration=conf, date=now())

    def __save_configuration(self):
        self.configuration['identifier'] = str(self._job.identifier)
        db_file = file_get_or_create(
            json.dumps(self.configuration, indent=2, sort_keys=True, ensure_ascii=False),
            'job-{}.json'.format(self._job.identifier), JobFile)
        return db_file


class JobProgressData:
    data_map = {
        'total subjobs to be solved': 'total_sj',
        'failed subjobs': 'failed_sj',
        'solved subjobs': 'solved_sj',
        'total tasks to be generated': 'total_ts',
        'failed tasks': 'failed_ts',
        'solved tasks': 'solved_ts'
    }
    dates_map = {
        'start tasks solution': 'start_ts',
        'finish tasks solution': 'finish_ts',
        'start subjobs solution': 'start_sj',
        'finish subjobs solution': 'finish_sj'
    }
    int_or_text = {
        'expected time for solving subjobs': ['expected_time_sj', 'gag_text_sj'],
        'expected time for solving tasks': ['expected_time_ts', 'gag_text_ts']
    }

    def __init__(self, job):
        self._job = job

    def update(self, data):
        data = json.loads(data)
        if not isinstance(data, dict) or any(x not in set(self.data_map) | set(self.dates_map) | set(self.int_or_text)
                                             for x in data):
            raise ServiceError('Wrong format of data')
        try:
            progress = JobProgress.objects.get(job=self._job)
        except ObjectDoesNotExist:
            progress = JobProgress(job=self._job)
        for dkey in self.data_map:
            if dkey in data:
                setattr(progress, self.data_map[dkey], data[dkey])
        for dkey in self.dates_map:
            if dkey in data and data[dkey] and getattr(progress, self.dates_map[dkey]) is None:
                setattr(progress, self.dates_map[dkey], now())
        for dkey in (k for k in self.int_or_text if k in data):
            if isinstance(data[dkey], int):
                setattr(progress, self.int_or_text[dkey][0], data[dkey])
                setattr(progress, self.int_or_text[dkey][1], None)
            else:
                setattr(progress, self.int_or_text[dkey][0], None)
                setattr(progress, self.int_or_text[dkey][1], str(data[dkey]))
        progress.save()

    def get(self):
        data = {}
        try:
            progress = JobProgress.objects.get(job=self._job)
        except ObjectDoesNotExist:
            return {}
        else:
            for dkey in self.data_map:
                value = getattr(progress, self.data_map[dkey])
                if value is not None:
                    data[dkey] = value
            for dkey in self.dates_map:
                data[dkey] = (getattr(progress, self.dates_map[dkey]) is not None)
        return data


class TaskArchiveGenerator(FileWrapper):
    def __init__(self, task: Task):
        self._task = task
        self.size = len(self._task.archive)
        self.name = self._task.archname
        super().__init__(self._task.archive, 8192)


class SolutionArchiveGenerator(FileWrapper):
    def __init__(self, solution: Solution):
        self._solution = solution
        self.size = len(self._solution.archive)
        self.name = self._solution.archname
        super().__init__(self._solution.archive, 8192)
