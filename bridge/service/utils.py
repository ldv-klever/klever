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

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.files import File as NewFile
from django.db.models import F
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from bridge.vars import JOB_STATUS, PRIORITY, SCHEDULER_STATUS, SCHEDULER_TYPE, TASK_STATUS
from bridge.utils import file_checksum, logger, BridgeException

from jobs.models import RunHistory, JobFile, FileSystem, Job
from reports.models import ReportRoot, ReportUnknown, ReportComponent, ComponentInstances
from service.models import Scheduler, SolvingProgress, Task, Solution, VerificationTool, Node, NodesConfiguration,\
    SchedulerUser, Workload, JobProgress

from jobs.utils import JobAccess, change_job_status, get_user_time


class ServiceError(Exception):
    pass


class NotAnError(Exception):
    pass


class ScheduleTask:
    def __init__(self, job_id, description, archive):
        try:
            self.progress = SolvingProgress.objects\
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
        SolvingProgress.objects.filter(id=self.progress.id)\
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
        if SolvingProgress.objects.filter(id__in=list(t.progress_id for t in self._tasks))\
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


class CancelTask:
    def __init__(self, task_id):
        try:
            self.task = Task.objects.get(id=task_id)
        except ObjectDoesNotExist:
            raise NotAnError("The task '%s' was not found" % task_id)
        if Job.objects.get(solvingprogress=self.task.progress).status != JOB_STATUS[2][0]:
            raise ServiceError('The job is not processing')

        progress = SolvingProgress.objects.get(id=self.task.progress_id)
        if self.task.status == TASK_STATUS[0][0]:
            if progress.tasks_pending > 0:
                progress.tasks_pending -= 1
        elif self.task.status == TASK_STATUS[1][0]:
            if progress.tasks_processing > 0:
                progress.tasks_processing -= 1
        else:
            raise ServiceError('The task status is wrong')
        progress.tasks_cancelled += 1
        progress.save()

        self.task.delete()


class FinishJobDecision:
    def __init__(self, inst, status, error=None):
        if isinstance(inst, SolvingProgress):
            self.progress = inst
            self.job = self.progress.job
        elif isinstance(inst, Job):
            self.job = inst
            try:
                self.progress = SolvingProgress.objects.get(job=self.job)
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
            self.progress.error = str(e)
            self.status = JOB_STATUS[5][0]
        if self.error is not None:
            if len(self.error) > 1024:
                logger.error("The job '%s' finished with large error: %s" % (self.job.identifier, self.error))
                self.error = "Length of error for job '%s' is large (1024 characters is maximum)" % self.job.identifier
                self.status = JOB_STATUS[8][0]
            self.progress.error = self.error
        self.progress.finish_date = now()
        self.progress.save()
        ComponentInstances.objects.filter(report__root__job=self.job, in_progress__gt=0).update(in_progress=0)
        change_job_status(self.job, self.status)

    def __remove_tasks(self):
        if self.progress.job.status == JOB_STATUS[1][0]:
            return
        elif self.progress.job.status != JOB_STATUS[2][0]:
            raise ServiceError('The job is not processing')
        elif self.progress.task_set.filter(status__in={TASK_STATUS[0][0], TASK_STATUS[0][1]}).count() > 0:
            raise ServiceError('There are unfinished tasks')
        elif self.progress.task_set.filter(status=TASK_STATUS[3][0], error=None).count() > 0:
            raise ServiceError('There are tasks finished with error and without error descriptions')
        elif self.progress.task_set.filter(status=TASK_STATUS[2][0], solution=None).count() > 0:
            raise ServiceError('There are finished tasks without solutions')
        self.progress.task_set.all().delete()

    def __get_status(self, status):
        if status not in set(x[0] for x in JOB_STATUS):
            raise ValueError('Unsupported status: %s' % status)
        if status == JOB_STATUS[3][0]:
            unfinished_reports = list(identifier for identifier, in ReportComponent.objects.filter(
                root=self.progress.job.reportroot, finish_date=None
            ).values_list('identifier'))
            if len(unfinished_reports) > 0:
                self.error = 'There are unfinished reports (%s): %s' % (len(unfinished_reports), unfinished_reports)
                logger.error(self.error)
                if len(self.error) > 1024:
                    self.error = 'There are unfinished reports (%s)' % len(unfinished_reports)
                return JOB_STATUS[5][0]
            try:
                core_r = ReportComponent.objects.get(parent=None, root=self.progress.job.reportroot)
            except ObjectDoesNotExist:
                self.error = "The job doesn't have Core report"
                return JOB_STATUS[5][0]
            if ReportUnknown.objects\
                    .filter(parent=core_r, component=core_r.component, root=self.progress.job.reportroot).count() > 0:
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
                core_r = ReportComponent.objects.get(parent=None, root=self.progress.job.reportroot)
            except ObjectDoesNotExist:
                pass
            else:
                if ReportComponent.objects.filter(root=self.progress.job.reportroot, finish_date=None).count() > 0 \
                        or ReportUnknown.objects.filter(parent=core_r, component=core_r.component,
                                                        root=self.progress.job.reportroot).count() == 0:
                    status = JOB_STATUS[5][0]
            if self.error is None:
                self.error = "The scheduler hasn't given an error description"
        return status

    def __check_progress(self):
        try:
            jp = JobProgress.objects.get(job=self.job)
        except ObjectDoesNotExist:
            return
        if jp.start_ts is not None:
            if any(x is None for x in [jp.solved_ts, jp.failed_ts, jp.total_ts, jp.start_ts, jp.finish_ts]):
                raise ServiceError("The job didn't got full tasks progress data")
            else:
                if jp.solved_ts + jp.failed_ts != jp.total_ts or jp.finish_ts is None:
                    raise ServiceError("Tasks solving progress is not finished")
        if jp.start_sj is not None:
            if any(x is None for x in [jp.solved_sj, jp.failed_sj, jp.total_sj, jp.start_sj, jp.finish_sj]):
                raise ServiceError("The job didn't got full subjobs progress data")
            else:
                if jp.solved_sj + jp.failed_sj != jp.total_sj or jp.finish_sj is None:
                    raise ServiceError("Subjobs solving progress is not finished")


class KleverCoreStartDecision:
    def __init__(self, job):
        try:
            progress = SolvingProgress.objects.get(job=job)
        except ObjectDoesNotExist:
            raise ValueError('job decision was not successfully started')
        if progress.start_date is not None:
            raise ValueError('the "start" report of Core was already uploaded')
        elif progress.finish_date is not None:
            raise ValueError('the job is not solving already')
        progress.start_date = now()
        progress.save()


class StopDecision:
    def __init__(self, job):
        if job.status not in [JOB_STATUS[1][0], JOB_STATUS[2][0]]:
            raise BridgeException(_("Only pending and processing jobs can be stopped"))
        try:
            self.progress = SolvingProgress.objects.get(job=job)
        except ObjectDoesNotExist:
            raise BridgeException(_('The job solving progress does not exist'))

        change_job_status(job, JOB_STATUS[6][0])
        self.__clear_tasks()

    def __clear_tasks(self):
        pending_num = self.progress.task_set.filter(status=TASK_STATUS[0][0]).count()
        processing_num = self.progress.task_set.filter(status=TASK_STATUS[1][0]).count()
        self.progress.tasks_processing = self.progress.tasks_pending = 0
        self.progress.tasks_cancelled += processing_num + pending_num
        self.progress.finish_date = now()
        self.progress.error = "The job was cancelled"
        self.progress.save()
        # If there are a lot of tasks that are not still deleted it could be too long
        # as there is request to DB for each task here (pre_delete signal)
        self.progress.task_set.all().delete()


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
            for progress in SolvingProgress.objects.filter(job__status=JOB_STATUS[1][0], fake=False)\
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
            for progress in SolvingProgress.objects.filter(job__status=JOB_STATUS[2][0], fake=False)\
                    .select_related('job'):
                if progress.job.identifier in data['jobs']['finished']:
                    FinishJobDecision(progress, JOB_STATUS[3][0])
                elif progress.job.identifier in data['jobs']['error']:
                    FinishJobDecision(progress, JOB_STATUS[4][0], data['job errors'].get(progress.job.identifier))
                else:
                    self._data['jobs']['processing'].append(progress.job.identifier)
                    self._data['jobs progress'][progress.job.identifier] = JobProgressData(progress.job).get()
            for progress in SolvingProgress.objects.filter(job__status=JOB_STATUS[6][0]).select_related('job'):
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
        self.__is_not_used()
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

    def __is_not_used(self):
        pass


class UpdateTools:
    def __init__(self, sch_type, tools_data):
        try:
            self.scheduler = Scheduler.objects.get(type=sch_type)
        except ObjectDoesNotExist:
            raise ServiceError('Scheduler was not found')
        try:
            self.__read_tools_data(tools_data)
        except ValueError or KeyError:
            raise ServiceError('Wrong tools data format')
        except Exception:
            raise ServiceError('Unknown error')

    def __read_tools_data(self, data):
        VerificationTool.objects.filter(scheduler=self.scheduler).delete()
        VerificationTool.objects.bulk_create(list(
            VerificationTool(scheduler=self.scheduler, name=tool['tool'], version=tool['version'])
            for tool in json.loads(data)
        ))


class SetSchedulersStatus:
    def __init__(self, statuses):
        try:
            self.statuses = json.loads(statuses)
        except ValueError:
            raise ServiceError('Incorrect format of statuses')
        self.__update_statuses()

    def __update_statuses(self):
        sch_type_map = {}
        for sch_type in SCHEDULER_TYPE:
            sch_type_map[sch_type[1]] = sch_type[0]
        for sch_type in self.statuses:
            try:
                scheduler = Scheduler.objects.get(type=sch_type_map[sch_type])
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
        self.__is_not_used()
        for progress in scheduler.solvingprogress_set.filter(job__status=JOB_STATUS[2][0], finish_date=None):
            pending_num = Task.objects.filter(status=TASK_STATUS[0][0], progress=progress)\
                .update(error='Task was finished with error due to scheduler is disconnected')
            processing_num = Task.objects.filter(status=TASK_STATUS[1][0], progress=progress)\
                .update(error='Task was finished with error due to scheduler is disconnected')
            progress.tasks_pending = progress.tasks_processing = 0
            progress.tasks_error += pending_num + processing_num
            if scheduler.type == SCHEDULER_TYPE[0][0]:
                progress.finish_date = now()
                progress.error = 'Klever scheduler was disconnected'
                change_job_status(progress.job, JOB_STATUS[8][0])
            progress.save()

    def __is_not_used(self):
        pass


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
                    'num_of_nodes': conf.node_set.count()
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


class StartJobDecision:
    def __init__(self, user, job_id, configuration, fake=False):
        self.operator = user
        self._fake = fake
        self.configuration = configuration
        self.job = self.__get_job(job_id)
        self.job_scheduler = self.__get_scheduler()

        self.__check_schedulers()
        self.progress = self.__create_solving_progress()
        try:
            ReportRoot.objects.get(job=self.job).delete()
        except ObjectDoesNotExist:
            pass
        ReportRoot.objects.create(user=self.operator, job=self.job)
        self.job.status = JOB_STATUS[1][0]
        self.job.weight = self.configuration.weight
        self.job.save()

    def __get_scheduler(self):
        try:
            return Scheduler.objects.get(type=self.configuration.scheduler)
        except ObjectDoesNotExist:
            raise BridgeException(_('The scheduler was not found'))

    def __get_job(self, job_id):
        try:
            job = Job.objects.get(pk=job_id)
        except ObjectDoesNotExist:
            raise BridgeException(_('The job was not found'))
        if not JobAccess(self.operator, job).can_decide():
            raise BridgeException(_("You don't have an access to start decision of this job"))
        return job

    def __create_solving_progress(self):
        try:
            self.job.solvingprogress.delete()
            self.job.jobprogress.delete()
        except ObjectDoesNotExist:
            pass
        return SolvingProgress.objects.create(
            job=self.job, priority=self.configuration.priority, scheduler=self.job_scheduler,
            fake=self._fake, configuration=self.__save_configuration()
        )

    def __save_configuration(self):
        m = BytesIO(self.configuration.as_json(self.job.identifier).encode('utf8'))
        check_sum = file_checksum(m)
        try:
            db_file = JobFile.objects.get(hash_sum=check_sum)
        except ObjectDoesNotExist:
            db_file = JobFile(hash_sum=check_sum)
            db_file.file.save('job-%s.conf' % self.job.identifier[:5], NewFile(m), save=True)
        RunHistory.objects.create(job=self.job, operator=self.operator, configuration=db_file, date=now())
        return db_file

    def __check_schedulers(self):
        try:
            klever_sch = Scheduler.objects.get(type=SCHEDULER_TYPE[0][0])
        except ObjectDoesNotExist:
            raise BridgeException()
        if klever_sch.status == SCHEDULER_STATUS[2][0]:
            raise BridgeException(_('The Klever scheduler is disconnected'))
        if self.job_scheduler.type == SCHEDULER_TYPE[1][0]:
            if self.job_scheduler.status == SCHEDULER_STATUS[2][0]:
                raise BridgeException(_('The VerifierCloud scheduler is disconnected'))
            try:
                self.operator.scheduleruser
            except ObjectDoesNotExist:
                raise BridgeException(_("You didn't specify credentials for VerifierCloud"))


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


class GetJobsProgresses:
    def __init__(self, user, jobs_ids):
        self._user = user
        self._s_progress = {}
        self._j_progress = {}
        self.__get_progresses(jobs_ids)
        self.data = self.__get_data(jobs_ids)

    def table_data(self):
        for j_id in self.data:
            for col in list(self.data[j_id]):
                if col.endswith('_ts'):
                    self.data[j_id]["tasks:%s" % col] = self.data[j_id].pop(col)
                elif col.endswith('_sj'):
                    self.data[j_id]["subjobs:%s" % col] = self.data[j_id].pop(col)
        return self.data

    def __get_progresses(self, jobs_ids):
        for j_id, status, start, finish in SolvingProgress.objects.filter(job_id__in=jobs_ids)\
                .values_list('job_id', 'job__status', 'start_date', 'finish_date'):
            if start is None:
                start = '-'
            if finish is None:
                finish = '-'
            self._s_progress[j_id] = (status, start, finish)
        for jp in JobProgress.objects.filter(job_id__in=jobs_ids):
            self._j_progress[jp.job_id] = jp

    def __get_data(self, jobs_ids):
        data = {}
        for j_id in jobs_ids:
            data[j_id] = self.__job_values(j_id)
        return data

    def __job_values(self, j_id):
        if j_id not in self._s_progress:
            # Not-solved jobs: JOB_STATUS[0][0]
            return {}

        job_status = self._s_progress[j_id][0]
        data = {
            'start_decision': self._s_progress[j_id][1],
            'finish_decision': self._s_progress[j_id][2]
        }
        # For pending jobs we need just start and finish decision dates. It will be '-' both.
        if job_status == JOB_STATUS[1][0]:
            return data

        has_sj = (j_id in self._j_progress and
                  (self._j_progress[j_id].start_sj is not None or self._j_progress[j_id].total_sj is not None))
        has_progress_ts = self.__has_progress(j_id, 'ts')
        has_progress_sj = (has_sj and self.__has_progress(j_id, 'sj'))

        # Add other data
        data.update({
            'total_ts': self.__get_int_attr(j_id, 'total_ts', _('Estimating the number')),
            'start_ts': self.__get_date_attr(j_id, 'start_ts', '-'),
            'finish_ts': self.__get_date_attr(j_id, 'finish_ts', '-'),
            'progress_ts': self.__progress(j_id, 'ts') if has_progress_ts else _('Estimating progress')
        })
        if has_sj:
            data.update({
                'total_sj': self.__get_int_attr(j_id, 'total_sj', _('Estimating the number')),
                'start_sj': self.__get_date_attr(j_id, 'start_sj', '-'),
                'finish_sj': self.__get_date_attr(j_id, 'finish_sj', '-'),
                'progress_sj': self.__progress(j_id, 'sj') if has_progress_sj else _('Estimating progress')
            })

        # Get expected time if job is solving
        if job_status == JOB_STATUS[2][0]:
            if j_id in self._j_progress and self._j_progress[j_id].expected_time_ts is not None:
                data['expected_time_ts'] = get_user_time(self._user, self._j_progress[j_id].expected_time_ts * 1000)
            elif j_id in self._j_progress and self._j_progress[j_id].gag_text_ts is not None:
                data['expected_time_ts'] = self._j_progress[j_id].gag_text_ts
            else:
                data['expected_time_ts'] = _('Estimating time')
            if has_sj:
                if self._j_progress[j_id].expected_time_sj is not None:
                    data['expected_time_sj'] = get_user_time(self._user, self._j_progress[j_id].expected_time_sj * 1000)
                elif self._j_progress[j_id].gag_text_sj is not None:
                    data['expected_time_sj'] = self._j_progress[j_id].gag_text_sj
                else:
                    data['expected_time_sj'] = _('Estimating time')
        else:
            # Do not show "Estimating progress" for finished jobs
            if not has_progress_ts:
                del data['progress_ts']
            if has_sj and not has_progress_sj:
                del data['progress_sj']
        return data

    def __get_int_attr(self, j_id, valname, defval):
        if j_id not in self._j_progress:
            return defval
        value = getattr(self._j_progress[j_id], valname)
        if value is None or value == 0:
            return defval
        return value

    def __get_date_attr(self, j_id, valname, defval):
        if j_id not in self._j_progress:
            return defval
        value = getattr(self._j_progress[j_id], valname)
        if value is None:
            return defval
        return value

    def __progress(self, j_id, progress_type):
        if progress_type not in {'sj', 'ts'}:
            return None
        total = getattr(self._j_progress[j_id], 'total_%s' % progress_type)
        solved = getattr(self._j_progress[j_id], 'solved_%s' % progress_type)
        failed = getattr(self._j_progress[j_id], 'failed_%s' % progress_type)
        if total > failed:
            return "%s%%" % int(100 * solved / (total - failed))
        else:
            return "100%"

    def __has_progress(self, j_id, progress_type):
        if progress_type not in {'sj', 'ts'} or j_id not in self._j_progress:
            return False
        args = list(x.format(progress_type) for x in ['total_{0}', 'solved_{0}', 'failed_{0}'])
        if all(getattr(self._j_progress[j_id], x) is not None for x in args):
            return True
        return False
