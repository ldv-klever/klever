import zipfile

from collections import OrderedDict

from django.utils.translation import ugettext_lazy as _
from django.utils.functional import cached_property
from django.utils.timezone import now

from rest_framework import serializers, exceptions, fields

from bridge.utils import logger
from bridge.vars import JOB_STATUS, DATAFORMAT, PRIORITY, SCHEDULER_TYPE, JOB_WEIGHT, SCHEDULER_STATUS, TASK_STATUS
from jobs.models import Job
from jobs.serializers import change_job_status
from service.models import Task, Solution, Decision, VerificationTool, Scheduler, NodesConfiguration, Node, Workload

from users.models import User, SchedulerUser
from users.utils import HumanizedValue
from service.utils import NotAnError


class VerificationToolSerializer(serializers.ModelSerializer):
    class Meta:
        model = VerificationTool
        exclude = ('scheduler',)


class SchedulerUserSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        # 'user' should be provided in save() method
        if 'user' not in validated_data:
            raise exceptions.ValidationError({'user': 'Required!'})
        elif not isinstance(validated_data['user'], User):
            raise exceptions.ValidationError({'user': 'Not a User instance!'})
        try:
            instance = SchedulerUser.objects.get(user=validated_data['user'])
            validated_data.pop('user')
            return self.update(instance, validated_data)
        except SchedulerUser.DoesNotExist:
            return super().create(validated_data)

    class Meta:
        model = SchedulerUser
        fields = ('login', 'password')


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


class TaskSerializer(serializers.ModelSerializer):
    default_error_messages = {
        'status_change': 'Status change from "{old_status}" to "{new_status}" is not supported!'
    }
    job = serializers.SlugRelatedField(
        slug_field='identifier', write_only=True, queryset=Job.objects.only('id', 'identifier', 'name')
    )

    def __init__(self, *args, **kwargs):
        super(TaskSerializer, self).__init__(*args, **kwargs)
        if self.context['request'].method == 'GET':
            fields_to_repr = self.context['request'].query_params.getlist('fields')
            if fields_to_repr:
                # Drop any fields that are not specified in the `fields` argument.
                allowed = set(fields_to_repr)
                existing = set(self.fields.keys())
                for field_name in existing - allowed:
                    self.fields.pop(field_name)

    def validate_job(self, instance):
        if instance.status == JOB_STATUS[6][0]:
            raise serializers.ValidationError('Is cancelling')
        if instance.status != JOB_STATUS[2][0]:
            raise serializers.ValidationError('Is not processing')
        return instance

    def validate_archive(self, archive):
        if not zipfile.is_zipfile(archive) or zipfile.ZipFile(archive).testzip():
            raise exceptions.ValidationError('The task archive "%s" is not a ZIP file' % archive)
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
            return new_status
        old_status = self.instance.status

        if old_status not in {TASK_STATUS[0][0], TASK_STATUS[1][0]}:
            # Finished (with error or not) task can't be finished again
            self.fail('status_change', old_status=old_status, new_status=new_status)
        if old_status == new_status:
            # If you don't want to change status, don't provide it
            self.fail('status_change', old_status=old_status, new_status=new_status)
        if old_status == TASK_STATUS[1][0] and new_status == TASK_STATUS[0][0]:
            # Processing task can't become pending again
            self.fail('status_change', old_status=old_status, new_status=new_status)
        if new_status == TASK_STATUS[2][0]:
            if not Solution.objects.filter(task=self.instance).exists():
                logger.error("Task was finished without solutions")
                # raise exceptions.ValidationError("Task can't be finished without solutions")
        return new_status

    def get_decision(self, job):
        try:
            decision = Decision.objects.select_related('scheduler').get(job=job)
        except Decision.DoesNotExist:
            raise exceptions.ValidationError({'job': 'The job was not started properly'})
        if decision.scheduler.status == SCHEDULER_STATUS[2][0]:
            raise exceptions.ValidationError({'scheduler': 'The tasks scheduler is disconnected'})
        return decision

    def update_decision(self, decision, new_status=None, old_status=None, error=None):
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

        if new_status:
            # Increment counter for new status
            incr_field = status_map[new_status]
            new_num = getattr(decision, incr_field)
            setattr(decision, incr_field, new_num + 1)

            # Set error for ERROR tasks
            if new_status == TASK_STATUS[3][0]:
                if not error:
                    error = "The scheduler hasn't given error description"
                if len(error) > 1024:
                    error = "Length of error for task with must be less than 1024 characters"
                decision.error = error

        decision.save()

    def compare_priority(self, job_priority, task_priority):
        priority_list = list(pr[0] for pr in PRIORITY)
        if priority_list.index(job_priority) > priority_list.index(task_priority):
            raise exceptions.ValidationError({'priority': 'Task priority is too big'})

    def create(self, validated_data):
        # Do not allow to fill error or status on creation
        validated_data.pop('error', None)
        validated_data.pop('status', None)

        # Set archive name
        validated_data['archname'] = validated_data['archive'].name[:256]

        # Get and validate decision
        decision = self.get_decision(validated_data.pop('job'))

        # Validate task priority
        self.compare_priority(decision.priority, validated_data['description']['priority'])
        validated_data['decision'] = decision

        # Create the task and update decision
        instance = super().create(validated_data)
        self.update_decision(decision, new_status=instance.status)
        return instance

    def update(self, instance, validated_data):
        assert isinstance(instance, Task)
        # Only status and error can be changed
        validated_data = dict((k, v) for k, v in validated_data.items() if k in {'status', 'error'})
        job = Job.objects.get(decision=instance.decision)
        if job.status != JOB_STATUS[2][0]:
            raise serializers.ValidationError({'job': 'Is not processing'})

        self.update_decision(
            instance.decision, new_status=validated_data.get('status'),
            old_status=instance.status, error=validated_data.get('error')
        )
        return super().update(instance, validated_data)

    class Meta:
        model = Task
        exclude = ('decision', 'archname')
        extra_kwargs = {'archive': {'write_only': True}}


class SolutionSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.context['request'].method == 'GET':
            fields_to_repr = self.context['request'].query_params.getlist('fields')
            if fields_to_repr:
                # Drop any fields that are not specified in the `fields` argument.
                allowed = set(fields_to_repr)
                existing = set(self.fields.keys())
                for field_name in existing - allowed:
                    self.fields.pop(field_name)

    def validate_archive(self, archive):
        if not zipfile.is_zipfile(archive) or zipfile.ZipFile(archive).testzip():
            raise exceptions.ValidationError('The task archive "%s" is not a ZIP file' % archive)
        return archive

    def validate_description(self, desc):
        if not isinstance(desc, dict):
            raise exceptions.ValidationError('Not a dictionary')
        return desc

    def get_decision(self, task):
        decision = Decision.objects.select_related('job').only('id', 'job__status').get(id=task.decision_id)
        if decision.job.status != JOB_STATUS[2][0]:
            raise exceptions.ValidationError({'job': 'The job is not processing'})
        return decision

    def create(self, validated_data):
        # Set archive name
        validated_data['archname'] = validated_data['archive'].name[:256]

        # Get and validate decision
        decision = self.get_decision(validated_data['task'])
        validated_data['decision'] = decision

        # Create the task and update decision
        instance = super().create(validated_data)
        decision.solutions += 1
        decision.save()
        return instance

    def update(self, instance, validated_data):
        raise NotImplementedError('The solution update is prohibited')

    class Meta:
        model = Solution
        exclude = ('decision', 'archname')
        extra_kwargs = {'archive': {'write_only': True}}


class DecisionSerializer(serializers.ModelSerializer):
    start_tasks_solution = fields.BooleanField(default=False, write_only=True)
    finish_tasks_solution = fields.BooleanField(default=False, write_only=True)
    start_subjobs_solution = fields.BooleanField(default=False, write_only=True)
    finish_subjobs_solution = fields.BooleanField(default=False, write_only=True)

    def update(self, instance, validated_data):
        assert isinstance(instance, Decision)

        # Set current date
        current_date = now()
        if validated_data.pop('start_tasks_solution', False) and not instance.start_ts:
            validated_data['start_ts'] = current_date
        if validated_data.pop('finish_tasks_solution', False) and not instance.finish_ts:
            validated_data['finish_ts'] = current_date
        if validated_data.pop('start_subjobs_solution', False) and not instance.start_sj:
            validated_data['start_sj'] = current_date
        if validated_data.pop('finish_subjobs_solution', False) and not instance.finish_sj:
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
            'total_sj', 'failed_sj', 'solved_sj',
            'total_ts', 'failed_ts', 'solved_ts',
            'start_tasks_solution', 'finish_tasks_solution',
            'start_subjobs_solution', 'finish_subjobs_solution',
            'expected_time_sj', 'gag_text_sj',
            'expected_time_ts', 'gag_text_ts'
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
        default_value = _('Estimating the number') if instance.job.status == JOB_STATUS[2][0] else None
        return instance.total_ts or default_value

    def get_total_sj(self, instance):
        if instance.total_sj is None and instance.start_sj is None:
            # Seems like the job doesn't have subjobs
            return None
        default_value = _('Estimating the number') if instance.job.status == JOB_STATUS[2][0] else None
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
        if instance.job.status == JOB_STATUS[2][0]:
            progress = progress or _('Estimating progress')
        if not progress:
            return None
        value = {
            'progress': progress,
            'start': HumanizedValue(instance.start_ts, user=self._user).date,
            'finish': HumanizedValue(instance.finish_ts, user=self._user).date,
        }
        if instance.job.status == JOB_STATUS[2][0]:
            value['expected_time'] = self.__get_expected_time(instance.expected_time_ts, instance.gag_text_ts)
        return value

    def get_progress_sj(self, instance):
        if instance.total_sj is None and instance.start_sj is None:
            # Seems like the job doesn't have subjobs
            return None
        progress = self.__calculate_progress(instance.total_sj, instance.solved_sj, instance.failed_sj)
        if instance.job.status == JOB_STATUS[2][0]:
            progress = progress or _('Estimating progress')
        if not progress:
            return None
        value = {
            'progress': progress,
            'start': HumanizedValue(instance.start_sj, user=self._user).date,
            'finish': HumanizedValue(instance.finish_sj, user=self._user).date,
        }
        if instance.job.status == JOB_STATUS[2][0]:
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
        fields = ('job', 'total_ts', 'total_sj', 'progress_ts', 'progress_sj', 'start_date', 'finish_date')


class SchedulerSerializer(serializers.ModelSerializer):
    decision_error = 'Klever scheduler was disconnected'
    task_error = 'Task was finished with error due to scheduler is disconnected'

    def finish_tasks(self, scheduler: Scheduler):
        for decision in scheduler.decision_set.filter(job__status=JOB_STATUS[2][0], finish_date=None):
            decision.tasks_pending = decision.tasks_processing = 0
            # Pending or processing tasks
            tasks = Task.objects.filter(
                status__in=[TASK_STATUS[0][0], TASK_STATUS[1][0]], decision=decision
            ).update(error=self.task_error)
            decision.tasks_error += len(tasks)
            if scheduler.type == SCHEDULER_TYPE[0][0]:
                decision.finish_date = now()
                decision.error = self.decision_error
                change_job_status(decision.job, JOB_STATUS[8][0])
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
