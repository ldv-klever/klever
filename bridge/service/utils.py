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

import json
from wsgiref.util import FileWrapper

from django.db.models import F
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from bridge.vars import JOB_STATUS, SCHEDULER_STATUS, SCHEDULER_TYPE, TASK_STATUS
from bridge.utils import file_get_or_create, logger, BridgeException

from users.models import SchedulerUser
from jobs.models import RunHistory, JobFile, FileSystem
from reports.models import ReportRoot, ReportUnknown, ReportComponent
from service.models import Scheduler, Decision, Task, Solution, Node, NodesConfiguration, Workload

from jobs.serializers import change_job_status
from service.serializers import SchedulerUserSerializer


class ServiceError(Exception):
    pass


class FinishJobDecision:
    def __init__(self, job, status, error=None):
        self.job = job
        try:
            self.decision = Decision.objects.get(job=self.job)
        except Decision.DoesNotExist:
            logger.exception('The job does not have solving progress')
            change_job_status(self.job, JOB_STATUS[5][0])
            return
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
            except ReportComponent.DoesNotExist:
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
            except ReportComponent.DoesNotExist:
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


class CancelDecision:
    def __init__(self, job):
        if job.status not in {JOB_STATUS[1][0], JOB_STATUS[2][0]}:
            raise BridgeException(_("Only pending and processing jobs can be stopped"))
        try:
            self.decision = Decision.objects.get(job=job)
        except Decision.DoesNotExist:
            raise BridgeException(_('The job decision does not exist'))

        change_job_status(job, JOB_STATUS[6][0])
        self.__clear_tasks()

    def __clear_tasks(self):
        in_progress_num = self.decision.tasks.filter(status__in=[TASK_STATUS[0][0], TASK_STATUS[1][0]]).count()
        self.decision.tasks_processing = self.decision.tasks_pending = 0
        self.decision.tasks_cancelled += in_progress_num
        self.decision.finish_date = now()
        self.decision.save()
        # If there are a lot of tasks that are not still deleted it could be too long
        # as there is request to DB for each task here (pre_delete signal)
        self.decision.tasks.all().delete()


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
                conf_data['cpu_number'][0] += workload.reserved_cpu_number
                conf_data['cpu_number'][1] += conf.cpu_number
                conf_data['ram_memory'][0] += workload.reserved_ram_memory
                conf_data['ram_memory'][1] += conf.ram_memory
                conf_data['disk_memory'][0] += workload.reserved_disk_memory
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
        except Scheduler.DoesNotExist:
            raise BridgeException(_('The task scheduler was not found'))
        if scheduler.type == SCHEDULER_TYPE[1][0]:
            if scheduler.status == SCHEDULER_STATUS[2][0]:
                raise BridgeException(_('The VerifierCloud scheduler is disconnected'))
        else:
            try:
                klever_sch = Scheduler.objects.get(type=SCHEDULER_TYPE[0][0])
            except Scheduler.DoesNotExist:
                raise BridgeException(_("Schedulers weren't populated"))
            if klever_sch.status == SCHEDULER_STATUS[2][0]:
                raise BridgeException(_('The Klever scheduler is disconnected'))
        return scheduler

    def __create_decision(self):
        ReportRoot.objects.filter(job=self._job).delete()
        ReportRoot.objects.create(user=self.operator, job=self._job)
        Decision.objects.filter(job=self._job).delete()
        conf_db = file_get_or_create(
            json.dumps(self.configuration, indent=2, sort_keys=True, ensure_ascii=False),
            'job-{}.json'.format(self._job.identifier), JobFile
        )
        Decision.objects.create(
            job=self._job, fake=self._fake, scheduler=self._scheduler,
            priority=self.configuration['priority'], configuration=conf_db
        )
        RunHistory.objects.create(job=self._job, operator=self.operator, configuration=conf_db, date=now())


class TaskArchiveGenerator(FileWrapper):
    def __init__(self, task: Task):
        self._task = task
        self.size = len(self._task.archive)
        self.name = self._task.filename
        super().__init__(self._task.archive, 8192)


class SolutionArchiveGenerator(FileWrapper):
    def __init__(self, solution: Solution):
        self._solution = solution
        self.size = len(self._solution.archive)
        self.name = self._solution.filename
        super().__init__(self._solution.archive, 8192)


class ReadJobConfiguration:
    tasks_file = 'tasks.json'

    def __init__(self, job):
        self.job = job
        self.data = {}
        self.__read_conf()
        self.__read_tasks()

    def __read_conf(self):
        decision = Decision.objects.select_related('configuration', 'scheduler').get(job=self.job)
        with decision.configuration.file as fp:
            self.data['configuration'] = json.loads(fp.read().decode('utf8'))
        if decision.scheduler.type == SCHEDULER_TYPE[1][0]:
            sch_user = SchedulerUser.objects.filter(user__roots__job=self.job).first()
            self.data['user'] = SchedulerUserSerializer(instance=sch_user).data if sch_user else None

    def __read_tasks(self):
        fs_obj = FileSystem.objects.filter(
            job_version__job=self.job, job_version__version=F('job_version__job__version'), name=self.tasks_file
        ).select_related('file').first()
        if fs_obj:
            with fs_obj.file.file as fp:
                self.data['tasks'] = json.loads(fp.read().decode('utf8'))
