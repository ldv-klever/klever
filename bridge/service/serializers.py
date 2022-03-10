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

import pika
import zipfile

from django.conf import settings
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers, exceptions, fields

from bridge.vars import DECISION_STATUS, PRIORITY, SCHEDULER_TYPE, SCHEDULER_STATUS, TASK_STATUS
from bridge.utils import logger, require_lock, RMQConnect
from bridge.serializers import TimeStampField, DynamicFieldsModelSerializer

from users.models import SchedulerUser
from jobs.models import Scheduler, Decision
from service.models import Task, Solution, VerificationTool, NodesConfiguration, Node, Workload

from users.utils import HumanizedValue
from jobs.serializers import decision_status_changed


def on_task_change(task_id, task_status, scheduler_type):
    with RMQConnect() as channel:
        channel.basic_publish(
            exchange='', routing_key=settings.RABBIT_MQ_QUEUE,
            properties=pika.BasicProperties(delivery_mode=2),
            body="task {} {} {}".format(task_id, task_status, scheduler_type)
        )


class VerificationToolSerializer(serializers.ModelSerializer):
    class Meta:
        model = VerificationTool
        exclude = ('scheduler',)


class SchedulerUserSerializer(serializers.ModelSerializer):
    user = fields.HiddenField(default=serializers.CurrentUserDefault())

    @require_lock(SchedulerUser)
    def create(self, validated_data):
        try:
            instance = SchedulerUser.objects.get(user=validated_data['user'])
            validated_data.pop('user')
            return self.update(instance, validated_data)
        except SchedulerUser.DoesNotExist:
            return super().create(validated_data)

    class Meta:
        model = SchedulerUser
        fields = ('user', 'login', 'password')


class UpdateToolsSerializer(serializers.Serializer):
    scheduler = serializers.SlugRelatedField(slug_field='type', queryset=Scheduler.objects)
    tools = VerificationToolSerializer(many=True)

    def create(self, validated_data):
        # Clear old verification tools
        VerificationTool.objects.all().delete()

        # Create new verification tools
        return VerificationTool.objects.bulk_create(list(VerificationTool(
            scheduler=validated_data['scheduler'], **tool
        ) for tool in validated_data['tools']))

    def to_representation(self, instance):
        return {}

    def update(self, instance, validated_data):
        raise NotImplementedError('Update() is not supported')


class TaskSerializer(DynamicFieldsModelSerializer):
    default_error_messages = {
        'status_change': 'Status change from "{old_status}" to "{new_status}" is not supported!'
    }
    # Not a job, but decision object!
    job = serializers.SlugRelatedField(
        slug_field='identifier', write_only=True,
        queryset=Decision.objects.select_related('scheduler')
    )

    def validate_job(self, instance):
        if instance.status == DECISION_STATUS[6][0]:
            raise serializers.ValidationError('The job is cancelling')
        if instance.status != DECISION_STATUS[2][0]:
            raise serializers.ValidationError('The job is not processing')
        if instance.scheduler.status == SCHEDULER_STATUS[2][0]:
            raise exceptions.ValidationError('The tasks scheduler is disconnected')
        return instance

    def validate_archive(self, archive):
        if not zipfile.is_zipfile(archive) or zipfile.ZipFile(archive).testzip():
            raise exceptions.ValidationError('The task file "%s" is not a ZIP file' % archive)
        return archive

    def validate_description(self, desc):
        if not isinstance(desc, dict):
            raise exceptions.ValidationError('Not a dictionary')
        if 'priority' not in desc:
            raise exceptions.ValidationError('Task priority was not set')
        if desc['priority'] not in set(pr[0] for pr in PRIORITY):
            raise exceptions.ValidationError('Unsupported task priority value')
        return desc

    def validate_status(self, new_status):
        if not self.instance:
            raise exceptions.APIException('The status can be provided only for changing the task')
        old_status = self.instance.status

        # Finished (with error or not) task can't be finished again
        if old_status not in {TASK_STATUS[0][0], TASK_STATUS[1][0]}:
            self.fail('status_change', old_status=old_status, new_status=new_status)

        # Status is changed already
        if old_status == new_status:
            self.fail('status_change', old_status=old_status, new_status=new_status)

        # Processing task can't become pending again
        if old_status == TASK_STATUS[1][0] and new_status == TASK_STATUS[0][0]:
            self.fail('status_change', old_status=old_status, new_status=new_status)

        if new_status == TASK_STATUS[2][0]:
            if not Solution.objects.filter(task=self.instance).exists():
                # logger.error("Task was finished without solutions")
                raise exceptions.ValidationError("Task can't be finished without solutions")
        return new_status

    def validate(self, attrs):
        if 'status' in attrs:
            if attrs['status'] != TASK_STATUS[3][0]:
                attrs.pop('error', None)
            elif 'error' not in attrs:
                attrs['error'] = "The scheduler hasn't given error description"

        if 'description' in attrs and 'decision' in attrs:
            # Validate task priority
            job_priority = attrs['decision'].priority
            task_priority = attrs['description']['priority']
            priority_list = list(pr[0] for pr in PRIORITY)
            if priority_list.index(job_priority) > priority_list.index(task_priority):
                raise exceptions.ValidationError({'priority': 'Task priority is too big'})
        return attrs

    def update_decision(self, decision, new_status, old_status=None):
        status_map = {
            TASK_STATUS[0][0]: 'tasks_pending',
            TASK_STATUS[1][0]: 'tasks_processing',
            TASK_STATUS[2][0]: 'tasks_finished',
            TASK_STATUS[3][0]: 'tasks_error',
            TASK_STATUS[4][0]: 'tasks_cancelled'
        }

        if old_status:
            # Decrement counter for old status
            decr_field = status_map[old_status]
            old_num = getattr(decision, decr_field)
            if old_num > 0:
                setattr(decision, decr_field, old_num - 1)
            else:
                logger.error('Something wrong with Decision: number of {} tasks is 0, '
                             'but there is at least one such task in the system'.format(old_status))
        else:
            # Task was created
            decision.tasks_total += 1

        # Increment counter for new status
        incr_field = status_map[new_status]
        new_num = getattr(decision, incr_field)
        setattr(decision, incr_field, new_num + 1)
        decision.save()

    def create(self, validated_data):
        validated_data['filename'] = validated_data['archive'].name[:256]
        validated_data['decision'] = validated_data.pop('job')
        instance = super().create(validated_data)
        self.update_decision(instance.decision, instance.status)
        on_task_change(instance.id, instance.status, instance.decision.scheduler.type)
        return instance

    def update(self, instance, validated_data):
        assert isinstance(instance, Task)
        if 'status' not in validated_data:
            raise exceptions.ValidationError({'status': 'Required'})

        if instance.decision.status != DECISION_STATUS[2][0]:
            raise serializers.ValidationError({'job': 'Is not processing'})

        old_status = instance.status
        instance = super().update(instance, validated_data)
        self.update_decision(instance.decision, instance.status, old_status=old_status)
        on_task_change(instance.id, instance.status, instance.decision.scheduler.type)
        return instance

    def to_representation(self, instance):
        if isinstance(instance, Task) and 'request' in self.context and self.context['request'].method != 'GET':
            return {'id': instance.id}
        return super().to_representation(instance)

    class Meta:
        model = Task
        exclude = ('decision', 'filename')
        extra_kwargs = {'archive': {'write_only': True}}


class SolutionSerializer(DynamicFieldsModelSerializer):
    def validate_archive(self, archive):
        if not zipfile.is_zipfile(archive) or zipfile.ZipFile(archive).testzip():
            raise exceptions.ValidationError('The task solution file "%s" is not a ZIP file' % archive)
        return archive

    def validate_description(self, desc):
        if not isinstance(desc, dict):
            raise exceptions.ValidationError('Not a dictionary')
        return desc

    def create(self, validated_data):
        # Set file name
        validated_data['filename'] = validated_data['archive'].name[:256]

        # Get and validate decision
        decision = Decision.objects.only('id', 'status').get(id=validated_data['task'].decision_id)
        if decision.status != DECISION_STATUS[2][0]:
            pass
            # raise exceptions.ValidationError({'job': 'The job is not processing'})
        validated_data['decision'] = decision

        # Create the solution and update decision
        instance = super().create(validated_data)
        decision.solutions += 1
        decision.save()
        return instance

    def update(self, instance, validated_data):
        raise NotImplementedError('The solution update is prohibited')

    def to_representation(self, instance):
        if isinstance(instance, Solution) and 'request' in self.context and self.context['request'].method != 'GET':
            return {'id': instance.id}
        return super().to_representation(instance)

    class Meta:
        model = Solution
        exclude = ('decision', 'filename')
        extra_kwargs = {'archive': {'write_only': True}}


class DecisionSerializer(serializers.ModelSerializer):
    tasks_started = fields.BooleanField(default=False, write_only=True)
    tasks_finished = fields.BooleanField(default=False, write_only=True)
    subjobs_started = fields.BooleanField(default=False, write_only=True)
    subjobs_finished = fields.BooleanField(default=False, write_only=True)

    start_ts = TimeStampField(read_only=True)
    finish_ts = TimeStampField(read_only=True)
    start_sj = TimeStampField(read_only=True)
    finish_sj = TimeStampField(read_only=True)
    start_date = TimeStampField(read_only=True)
    finish_date = TimeStampField(read_only=True)
    status = fields.CharField(read_only=True)

    def update(self, instance, validated_data):
        assert isinstance(instance, Decision)

        # Set current date
        current_date = now()
        if validated_data.pop('tasks_started', False) and not instance.start_ts:
            validated_data['start_ts'] = current_date
        if validated_data.pop('tasks_finished', False) and not instance.finish_ts:
            validated_data['finish_ts'] = current_date
        if validated_data.pop('subjobs_started', False) and not instance.start_sj:
            validated_data['start_sj'] = current_date
        if validated_data.pop('subjobs_finished', False) and not instance.finish_sj:
            validated_data['finish_sj'] = current_date

        # Both time and gag can't exist
        if 'expected_time_ts' in validated_data:
            validated_data['gag_text_ts'] = None
        elif 'gag_text_ts' in validated_data:
            validated_data['expected_time_ts'] = None

        # Both time and gag can't exist
        if 'expected_time_sj' in validated_data:
            validated_data['gag_text_sj'] = None
        elif 'gag_text_sj' in validated_data:
            validated_data['expected_time_sj'] = None

        return super().update(instance, validated_data)

    class Meta:
        model = Decision
        fields = (
            'total_sj', 'failed_sj', 'solved_sj', 'total_ts', 'failed_ts', 'solved_ts',
            'tasks_started', 'tasks_finished', 'subjobs_started', 'subjobs_finished',
            'expected_time_sj', 'gag_text_sj', 'expected_time_ts', 'gag_text_ts',
            'start_ts', 'finish_ts', 'start_sj', 'finish_sj', 'start_date', 'finish_date', 'status'
        )


class ProgressSerializerRO(serializers.ModelSerializer):
    total_ts = serializers.SerializerMethodField()
    total_sj = serializers.SerializerMethodField()
    progress_ts = serializers.SerializerMethodField()
    progress_sj = serializers.SerializerMethodField()
    start_date = serializers.SerializerMethodField()
    finish_date = serializers.SerializerMethodField()

    @cached_property
    def _user(self):
        if 'request' in self.root.context and self.root.context['request'].user.is_authenticated:
            return self.root.context['request'].user
        elif 'user' in self.root.context and self.root.context['user'].is_authenticated:
            return self.root.context['user']
        return None

    def get_total_ts(self, instance):
        default_value = _('Estimating the number') if instance.status == DECISION_STATUS[2][0] else None
        return instance.total_ts or default_value

    def get_total_sj(self, instance):
        if instance.total_sj is None and instance.start_sj is None:
            # Seems like the decision doesn't have subjobs
            return None
        default_value = _('Estimating the number') if instance.status == DECISION_STATUS[2][0] else None
        return instance.total_sj or default_value

    def __calculate_progress(self, total, solved, failed):
        if total is None or solved is None or failed is None:
            return None
        if total > failed:
            return "%s%%" % int(100 * solved / (total - failed))
        return "100%"

    def __get_expected_time(self, db_value, default_text):
        return HumanizedValue(
            db_value * 1000 if db_value else None, user=self._user,
            default=default_text or _('Estimating time')
        ).timedelta

    def get_progress_ts(self, instance):
        progress = self.__calculate_progress(instance.total_ts, instance.solved_ts, instance.failed_ts)
        if instance.status == DECISION_STATUS[2][0]:
            progress = progress or _('Estimating progress')
        if not progress:
            return None
        value = {
            'progress': progress,
            'start': HumanizedValue(instance.start_ts, user=self._user).date,
            'finish': HumanizedValue(instance.finish_ts, user=self._user).date,
        }
        if instance.status == DECISION_STATUS[2][0]:
            value['expected_time'] = self.__get_expected_time(instance.expected_time_ts, instance.gag_text_ts)
        return value

    def get_progress_sj(self, instance):
        if instance.total_sj is None and instance.start_sj is None:
            # Seems like the decision doesn't have subjobs
            return None
        progress = self.__calculate_progress(instance.total_sj, instance.solved_sj, instance.failed_sj)
        if instance.status == DECISION_STATUS[2][0]:
            progress = progress or _('Estimating progress')
        if not progress:
            return None
        value = {
            'progress': progress,
            'start': HumanizedValue(instance.start_sj, user=self._user).date,
            'finish': HumanizedValue(instance.finish_sj, user=self._user).date,
        }
        if instance.status == DECISION_STATUS[2][0]:
            value['expected_time'] = self.__get_expected_time(instance.expected_time_sj, instance.gag_text_sj)
        return value

    def get_start_date(self, instance):
        return HumanizedValue(instance.start_date, user=self._user).date

    def get_finish_date(self, instance):
        return HumanizedValue(instance.finish_date, user=self._user).date

    def to_representation(self, instance):
        assert isinstance(instance, Decision), 'Wrong serializer usage'
        # Do not return nulls
        return dict((k, v) for k, v in super().to_representation(instance).items() if v)

    class Meta:
        model = Decision
        fields = ('id', 'total_ts', 'total_sj', 'progress_ts', 'progress_sj', 'start_date', 'finish_date')


class SchedulerSerializer(serializers.ModelSerializer):
    decision_error = 'Klever scheduler was disconnected'
    task_error = 'Task was finished with error due to scheduler is disconnected'

    def finish_tasks(self, scheduler: Scheduler):
        decisions_qs = scheduler.decision_set.filter(
            status__in=[DECISION_STATUS[1][0], DECISION_STATUS[2][0], DECISION_STATUS[6][0]]
        )
        if scheduler.type == SCHEDULER_TYPE[0][0]:
            decisions_qs = decisions_qs.select_related('job')
        for decision in decisions_qs:
            decision.tasks_pending = decision.tasks_processing = 0
            # Pending or processing tasks
            tasks_updated = Task.objects.filter(
                status__in=[TASK_STATUS[0][0], TASK_STATUS[1][0]], decision=decision
            ).update(error=self.task_error)
            decision.tasks_error += tasks_updated
            if scheduler.type == SCHEDULER_TYPE[0][0]:
                if not decision.finish_date:
                    decision.finish_date = now()
                if not decision.error:
                    decision.error = self.decision_error
                decision.status = DECISION_STATUS[8][0]
                decision_status_changed(decision)
            decision.save()

    def create(self, validated_data):
        raise NotImplementedError('Scheduler creation is prohibited')

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        if instance.status == SCHEDULER_STATUS[2][0]:
            self.finish_tasks(instance)
        return instance

    class Meta:
        model = Scheduler
        fields = ('status',)


class WorkloadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workload
        exclude = ('node',)


class NodeSerializer(serializers.ModelSerializer):
    workload = WorkloadSerializer(required=False)

    def create(self, validated_data):
        workload = validated_data.pop('workload', None)
        instance = super().create(validated_data)
        if workload:
            Workload.objects.create(node=instance, **workload)
        return instance

    class Meta:
        model = Node
        exclude = ('config',)


class NodeConfSerializer(serializers.ModelSerializer):
    nodes = NodeSerializer(many=True)

    def create(self, validated_data):
        nodes = validated_data.pop('nodes', [])
        instance = super().create(validated_data)
        for node_data in nodes:
            workload = node_data.pop('workload', None)
            node = Node.objects.create(config=instance, **node_data)
            if workload:
                Workload.objects.create(node=node, **workload)
        return instance

    class Meta:
        model = NodesConfiguration
        fields = '__all__'
