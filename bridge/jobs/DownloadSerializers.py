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
import uuid

from django.utils.translation import gettext_lazy as _

from rest_framework import exceptions, serializers, fields

from bridge.vars import MPTT_FIELDS, PRESET_JOB_TYPE
from bridge.utils import require_lock
from bridge.serializers import TimeStampField

from jobs.models import Job, JobFile, FileSystem, Decision, Scheduler
from reports.models import ReportSafe, ReportUnsafe, ReportUnknown, ReportComponent, Computer, ReportAttr, DecisionCache

from jobs.serializers import DecisionFilesField

ARCHIVE_FORMAT = 16


def validate_report_identifier(value, field_name='report_identifier'):
    if not isinstance(value, str):
        raise exceptions.ValidationError({field_name: 'Report identifier must be a string'})
    identifier_field = fields.CharField(min_length=1, max_length=255)
    try:
        identifier_field.run_validators(value)
    except exceptions.ValidationError as exc:
        raise exceptions.ValidationError(detail={field_name: exc.detail})


class DownloadJobSerializer(serializers.ModelSerializer):
    identifier = fields.UUIDField()
    name = fields.CharField(max_length=150)
    archive_format = fields.IntegerField(write_only=True)

    def validate_archive_format(self, value):
        if value != ARCHIVE_FORMAT:
            raise exceptions.ValidationError(_("The job archive format is not supported"))
        return value

    def validate(self, attrs):
        attrs.pop('archive_format')
        return attrs

    @require_lock(Job)
    def create(self, validated_data):
        try:
            return Job.objects.get(identifier=validated_data['identifier'])
        except Job.DoesNotExist:
            return super(DownloadJobSerializer, self).create(validated_data)

    def to_representation(self, instance):
        value = super().to_representation(instance)
        value['archive_format'] = ARCHIVE_FORMAT

        if isinstance(instance, Job):
            preset_info = {}
            presets_qs = instance.preset.get_ancestors(include_self=True)\
                .exclude(type=PRESET_JOB_TYPE[0][0]).values_list('identifier', 'type', 'name')
            for p_identifier, p_type, p_name in presets_qs:
                if p_type == PRESET_JOB_TYPE[2][0]:
                    preset_info['name'] = p_name
                else:
                    preset_info['identifier'] = str(p_identifier)
            value['preset_info'] = preset_info
        return value

    class Meta:
        model = Job
        fields = ('identifier', 'name', 'global_role', 'archive_format')


class DownloadDecisionSerializer(serializers.ModelSerializer):
    identifier = fields.UUIDField()
    configuration = serializers.SlugRelatedField(slug_field='hash_sum', queryset=JobFile.objects)
    scheduler = serializers.SlugRelatedField(slug_field='type', queryset=Scheduler.objects)
    start_date = TimeStampField()
    finish_date = TimeStampField(allow_null=True)
    start_sj = TimeStampField(allow_null=True)
    finish_sj = TimeStampField(allow_null=True)
    start_ts = TimeStampField(allow_null=True)
    finish_ts = TimeStampField(allow_null=True)
    files = DecisionFilesField(source='files.all')

    def validate_identifier(self, value):
        if Decision.objects.filter(identifier=value).exists():
            return uuid.uuid4()
        return value

    def create(self, validated_data):
        decision_files = validated_data.pop('files')['all']
        instance = super(DownloadDecisionSerializer, self).create(validated_data)
        FileSystem.objects.bulk_create(list(FileSystem(decision=instance, **fkwargs) for fkwargs in decision_files))
        return instance

    class Meta:
        model = Decision
        exclude = ('job', 'operator')


class DecisionCacheSerializer(serializers.ModelSerializer):
    class Meta:
        model = DecisionCache
        fields = '__all__'
        extra_kwargs = {'decision': {'read_only': True}}


class DownloadComputerSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        # Do not create the computer with the same identifier again
        return Computer.objects.get_or_create(identifier=validated_data['identifier'], defaults=validated_data)[0]

    class Meta:
        model = Computer
        exclude = ('id',)


class DownloadReportComponentSerializer(serializers.ModelSerializer):
    start_date = TimeStampField()
    finish_date = TimeStampField(allow_null=True)
    computer = DownloadComputerSerializer(read_only=True)
    original_sources = serializers.SlugRelatedField(slug_field='identifier', read_only=True)
    additional_sources = serializers.FileField(source='additional_sources.archive', allow_null=True, read_only=True)
    parent = serializers.SlugRelatedField(slug_field='identifier', read_only=True)

    class Meta:
        model = ReportComponent
        exclude = ('id', *MPTT_FIELDS)
        extra_kwargs = {
            'decision': {'read_only': True},
            'log': {'read_only': True},
            'verifier_files': {'read_only': True},
        }


class UploadReportComponentSerializer(serializers.ModelSerializer):
    start_date = TimeStampField()
    finish_date = TimeStampField(allow_null=True)

    class Meta:
        model = ReportComponent
        fields = ('cpu_time', 'wall_time', 'memory', 'component', 'verification', 'start_date', 'finish_date', 'data')


class DownloadReportSafeSerializer(serializers.ModelSerializer):
    parent = serializers.SlugRelatedField(slug_field='identifier', read_only=True)

    class Meta:
        model = ReportSafe
        exclude = ('id', *MPTT_FIELDS)
        extra_kwargs = {'decision': {'read_only': True}}


class UploadReportSafeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportSafe
        exclude = ('id', 'parent', 'identifier', 'decision', *MPTT_FIELDS)


class DownloadReportUnsafeSerializer(serializers.ModelSerializer):
    parent = serializers.SlugRelatedField(slug_field='identifier', read_only=True)

    class Meta:
        model = ReportUnsafe
        exclude = ('id', *MPTT_FIELDS)
        extra_kwargs = {'decision': {'read_only': True}, 'error_trace': {'read_only': True}}


class UploadReportUnsafeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportUnsafe
        exclude = ('id', 'identifier', 'parent', 'error_trace', 'decision', *MPTT_FIELDS)


class DownloadReportUnknownSerializer(serializers.ModelSerializer):
    parent = serializers.SlugRelatedField(slug_field='identifier', read_only=True)

    class Meta:
        model = ReportUnknown
        exclude = ('id', *MPTT_FIELDS)
        extra_kwargs = {'decision': {'read_only': True}, 'problem_description': {'read_only': True}}


class UploadReportUnknownSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportUnknown
        exclude = ('id', 'identifier', 'parent', 'decision', 'problem_description', *MPTT_FIELDS)


class DownloadReportAttrSerializer(serializers.ModelSerializer):
    data_file = fields.FileField(source='data.file', allow_null=True, read_only=True)

    def get_attr_data(self, instance):
        if not instance.data:
            return None
        arch_name = '{}_{}'.format(instance.pk, os.path.basename(instance.data.file.name))
        return os.path.join(ReportAttr.__name__, arch_name)

    class Meta:
        model = ReportAttr
        exclude = ('id', 'report', 'data')
