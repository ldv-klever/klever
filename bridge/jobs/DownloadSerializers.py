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

from django.utils.translation import ugettext_lazy as _

from rest_framework import exceptions, serializers, fields

from bridge.vars import MPTT_FIELDS
from bridge.serializers import TimeStampField

from jobs.models import Job, RunHistory, JobFile, JobHistory
from reports.models import ReportSafe, ReportUnsafe, ReportUnknown, ReportComponent, Computer, ReportAttr
from service.models import Scheduler, Decision

from jobs.serializers import create_job_version, JobFilesField
from jobs.utils import get_unique_name

ARCHIVE_FORMAT = 14


class RunHistorySerializer(serializers.ModelSerializer):
    date = TimeStampField()
    configuration = serializers.SlugRelatedField(slug_field='hash_sum', queryset=JobFile.objects)

    class Meta:
        model = RunHistory
        exclude = ('id', 'job', 'operator')


class DownloadDecisionSerializer(serializers.ModelSerializer):
    scheduler = serializers.SlugRelatedField(slug_field='type', queryset=Scheduler.objects)
    start_date = TimeStampField(allow_null=True)
    finish_date = TimeStampField(allow_null=True)
    start_sj = TimeStampField(allow_null=True)
    finish_sj = TimeStampField(allow_null=True)
    start_ts = TimeStampField(allow_null=True)
    finish_ts = TimeStampField(allow_null=True)

    class Meta:
        model = Decision
        exclude = ('id', 'job', 'configuration', 'fake')


class DownloadJobSerializer(serializers.ModelSerializer):
    identifier = fields.UUIDField()
    name = fields.CharField(max_length=150)
    archive_format = fields.IntegerField(write_only=True)
    run_history = RunHistorySerializer(many=True)
    decision = DownloadDecisionSerializer(allow_null=True)

    def validate_identifier(self, value):
        if Job.objects.filter(identifier=value).exists():
            return uuid.uuid4()
        return value

    def validate_name(self, value):
        if Job.objects.filter(name=value).exists():
            return get_unique_name(value)
        return value

    def validate_archive_format(self, value):
        if value != ARCHIVE_FORMAT:
            raise exceptions.ValidationError(_("The job archive format is not supported"))
        return value

    def validate(self, attrs):
        attrs.pop('archive_format')
        return attrs

    def create(self, validated_data):
        # Run history and decision must be created outside with configuration file and job instance
        validated_data.pop('run_history')
        validated_data.pop('decision')

        return super().create(validated_data)

    def to_representation(self, instance):
        value = super().to_representation(instance)
        value['archive_format'] = ARCHIVE_FORMAT
        return value

    class Meta:
        model = Job
        exclude = ('id', 'author', 'creation_date', 'preset_uuid', 'parent', *MPTT_FIELDS)


class DownloadJobVersionSerializer(serializers.ModelSerializer):
    change_date = TimeStampField()
    files = JobFilesField(source='files.all')

    def create(self, validated_data):
        job = validated_data.pop('job')
        job_files = validated_data.pop('files')['all']
        return create_job_version(job, job_files, [], **validated_data)

    class Meta:
        model = JobHistory
        exclude = ('id', 'job', 'change_author')


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
        exclude = ('id', 'root', *MPTT_FIELDS)


class DownloadReportSafeSerializer(serializers.ModelSerializer):
    parent = serializers.SlugRelatedField(slug_field='identifier', read_only=True)

    class Meta:
        model = ReportSafe
        exclude = ('id', 'root', *MPTT_FIELDS)


class DownloadReportUnsafeSerializer(serializers.ModelSerializer):
    parent = serializers.SlugRelatedField(slug_field='identifier', read_only=True)

    class Meta:
        model = ReportUnsafe
        exclude = ('id', 'root', 'trace_id', *MPTT_FIELDS)


class DownloadReportUnknownSerializer(serializers.ModelSerializer):
    parent = serializers.SlugRelatedField(slug_field='identifier', read_only=True)

    class Meta:
        model = ReportUnknown
        exclude = ('id', 'root', *MPTT_FIELDS)


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
