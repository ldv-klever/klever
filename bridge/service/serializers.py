from collections import OrderedDict

from django.utils.translation import ugettext_lazy as _
from django.utils.functional import cached_property

from rest_framework import serializers

from bridge.vars import JOB_STATUS, DATAFORMAT
from jobs.models import Job
from service.models import Task, Solution, Decision, VerificationTool, Scheduler

from users.utils import HumanizedValue
from service.utils import NotAnError


class VerificationToolSerializer(serializers.ModelSerializer):
    class Meta:
        model = VerificationTool
        exclude = ('scheduler',)


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
    job = serializers.SlugRelatedField(slug_field='identifier', write_only=True, queryset=Job.objects.all())
    # progress = serializers.PrimaryKeyRelatedField()

    def validate_job(self, instance):
        if instance.status == JOB_STATUS[6][0]:
            raise serializers.ValidationError('Is cancelling')
        if instance.status != JOB_STATUS[2][0]:
            raise serializers.ValidationError('Is not processing')
        return instance

    def validate_priority(self, priority):
        return priority

    def validate_progress(self, instance):
        pass

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        errors = OrderedDict()
        value['progress'] = 1
        return value

    class Meta:
        model = Task
        exclude = ('decision',)


class DecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Decision
        fields = '__all__'


# Read only
class ProgressSerializer(serializers.ModelSerializer):
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
        return dict((k, v) for k, v in super().to_representation(instance) if v)

    class Meta:
        model = Decision
        fields = ('job', 'total_ts', 'total_sj', 'progress_ts', 'progress_sj', 'start_date', 'finish_date')
