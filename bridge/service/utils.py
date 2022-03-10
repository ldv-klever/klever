#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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

from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from bridge.vars import DECISION_STATUS, SCHEDULER_TYPE, TASK_STATUS
from bridge.utils import logger, BridgeException

from users.models import SchedulerUser
from jobs.models import FileSystem
from reports.models import ReportUnknown, ReportComponent
from service.models import Task, Solution, Node, NodesConfiguration, Workload

from jobs.serializers import decision_status_changed
from service.serializers import SchedulerUserSerializer


def cancel_decision(decision):
    if decision.status not in {DECISION_STATUS[1][0], DECISION_STATUS[2][0]}:
        raise BridgeException(_("Only pending and processing decisions can be stopped"))
    decision.tasks_processing = decision.tasks_pending = 0
    decision.tasks_cancelled += decision.tasks.filter(
        status__in=[TASK_STATUS[0][0], TASK_STATUS[1][0]]
    ).count()
    decision.finish_date = now()
    decision.status = DECISION_STATUS[6][0]
    decision.save()


class ServiceError(Exception):
    pass


class FinishDecision:
    def __init__(self, decision, status, error=None):
        self.decision = decision
        self.error = error
        self.status = self.__get_status(status)
        try:
            self.__remove_tasks()
        except ServiceError as e:
            logger.exception(e)
            self.decision.error = str(e)
            self.status = DECISION_STATUS[5][0]
        if self.error is not None:
            if len(self.error) > 1024:
                logger.error("The decision '{}' finished with large error: {}"
                             .format(self.decision.identifier, self.error))
                self.error = "Length of error for decision '{}' is large (1024 characters is maximum)"\
                    .format(self.decision.identifier)
                self.status = DECISION_STATUS[8][0]
            self.decision.error = self.error

        self.decision.status = self.status
        self.decision.finish_date = now()
        self.decision.save()
        decision_status_changed(self.decision)

    def __remove_tasks(self):
        if self.decision.status == DECISION_STATUS[1][0]:
            return
        elif self.decision.status != DECISION_STATUS[2][0]:
            raise ServiceError('The decision is not processing')
        elif self.decision.tasks.filter(status__in={TASK_STATUS[0][0], TASK_STATUS[0][1]}).count() > 0:
            raise ServiceError('There are unfinished tasks')
        elif self.decision.tasks.filter(status=TASK_STATUS[3][0], error=None).count() > 0:
            raise ServiceError('There are tasks finished with error and without error descriptions')
        elif self.decision.tasks.filter(status=TASK_STATUS[2][0], solution=None).count() > 0:
            raise ServiceError('There are finished tasks without solutions')
        self.decision.tasks.all().delete()

    def __get_status(self, status):
        if status not in set(x[0] for x in DECISION_STATUS):
            raise ValueError('Unsupported status: %s' % status)
        if status == DECISION_STATUS[3][0]:
            if self.decision.status != DECISION_STATUS[2][0]:
                self.error = "Only processing decisions can be finished"
                return DECISION_STATUS[5][0]
            unfinished_reports = list(ReportComponent.objects.filter(decision=self.decision, finish_date=None)
                                      .values_list('identifier', flat=True))
            if len(unfinished_reports) > 0:
                self.error = 'There are unfinished reports ({}): {}'.format(len(unfinished_reports), unfinished_reports)
                logger.error(self.error)
                if len(self.error) > 1024:
                    self.error = 'There are unfinished reports ({})'.format(len(unfinished_reports))
                return DECISION_STATUS[5][0]

            try:
                core_r = ReportComponent.objects.get(parent=None, decision=self.decision)
            except ReportComponent.DoesNotExist:
                self.error = "The decision doesn't have Core report"
                return DECISION_STATUS[5][0]
            if ReportUnknown.objects.filter(parent=core_r, component=core_r.component, decision=self.decision).exists():
                return DECISION_STATUS[4][0]

            try:
                self.__check_progress()
            except ServiceError as e:
                self.error = str(e)
                return DECISION_STATUS[5][0]
            except Exception as e:
                logger.exception(e)
                self.error = 'Unknown error while checking progress'
                return DECISION_STATUS[5][0]
        elif status == DECISION_STATUS[4][0]:
            try:
                core_r = ReportComponent.objects.get(parent=None, decision=self.decision)
            except ReportComponent.DoesNotExist:
                pass
            else:
                unfinished_components = ReportComponent.objects.filter(decision=self.decision, finish_date=None)
                core_unknowns = ReportUnknown.objects.filter(
                    parent=core_r, component=core_r.component, decision=self.decision
                )
                if unfinished_components.exists() or not core_unknowns.exists():
                    status = DECISION_STATUS[5][0]
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
                raise ServiceError("The decision didn't got full tasks progress data")
            elif self.decision.solved_ts + self.decision.failed_ts != self.decision.total_ts:
                raise ServiceError("Tasks solving progress is incorrect")
        if self.decision.start_sj is not None:
            sj_progress = [
                self.decision.solved_sj, self.decision.failed_sj, self.decision.total_sj, self.decision.finish_sj
            ]
            if any(x is None for x in sj_progress):
                raise ServiceError("The decision didn't got full subjobs progress data")
            elif self.decision.solved_sj + self.decision.failed_sj != self.decision.total_sj:
                raise ServiceError("Subjobs solving progress is not finished")


class ReadDecisionConfiguration:
    tasks_file = 'tasks.json'

    def __init__(self, decision):
        self.decision = decision
        self.data = {}
        self.__read_conf()
        self.__read_tasks()

    def __read_conf(self):
        with self.decision.configuration.file as fp:
            self.data['configuration'] = json.loads(fp.read().decode('utf8'))
        if self.decision.scheduler.type == SCHEDULER_TYPE[1][0]:
            sch_user = SchedulerUser.objects.filter(user__decisions=self.decision).first()
            self.data['user'] = SchedulerUserSerializer(instance=sch_user).data if sch_user else None

    def __read_tasks(self):
        fs_obj = FileSystem.objects.filter(
            decision_id=self.decision.id, name=self.tasks_file
        ).select_related('file').first()
        if fs_obj:
            with fs_obj.file.file as fp:
                self.data['tasks'] = json.loads(fp.read().decode('utf8'))


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
