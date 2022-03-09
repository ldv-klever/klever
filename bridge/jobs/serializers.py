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
import os
import pika

from django.conf import settings
from django.db.models import Q
from django.db.models.query import QuerySet
from django.template.defaultfilters import filesizeformat
from django.urls import reverse
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers, exceptions, fields

from bridge.vars import DECISION_STATUS
from bridge.utils import logger, file_checksum, file_get_or_create, RMQConnect, BridgeException
from bridge.serializers import DynamicFieldsModelSerializer

from jobs.models import (
    PRESET_JOB_TYPE, Job, Decision, JobFile, FileSystem, UserRole, UploadedJobArchive, PresetJob, PresetFile,
    DefaultDecisionConfiguration
)
from reports.models import Report, AttrFile, AdditionalSources, CompareDecisionsInfo, DecisionCache
from service.models import Task

from jobs.configuration import get_default_configuration, GetConfiguration
from jobs.utils import JSTreeConverter, validate_scheduler, copy_files_with_replace

FILE_SEP = '/'
ARCHIVE_FORMAT = 13


def decision_status_changed(decision):
    if decision.status in {DECISION_STATUS[1][0], DECISION_STATUS[5][0], DECISION_STATUS[6][0]}:
        with RMQConnect() as channel:
            channel.basic_publish(
                exchange='', routing_key=settings.RABBIT_MQ_QUEUE, properties=pika.BasicProperties(delivery_mode=2),
                body="job {} {} {}".format(decision.identifier, decision.status, decision.scheduler.type)
            )


def create_default_decision(request, job, configuration):
    """
    Creates decision with provided configuration and files copied from preset job.
    If 'files' are provided in request.data then those files will be replaced.
    :param request:
    :param job:
    :param configuration:
    :return:
    """
    # Get scheduler
    scheduler = validate_scheduler(type=configuration['task scheduler'])

    # Save configuration
    conf_db = file_get_or_create(
        json.dumps(configuration, indent=2, sort_keys=True, ensure_ascii=False), 'configuration.json', JobFile
    )

    # Create decision
    decision = Decision.objects.create(
        title='', job=job, operator=request.user, scheduler=scheduler, configuration=conf_db,
        weight=configuration['weight'], priority=configuration['priority']
    )

    # Copy files for decision from preset job
    preset_job = job.preset.get_ancestors(include_self=True).filter(type=PRESET_JOB_TYPE[1][0]).first()
    preset_files_qs = PresetFile.objects.filter(preset=preset_job).values_list('file_id', 'name')
    copy_files_with_replace(request, decision.id, preset_files_qs)

    return decision


def validate_configuration(user, conf_str):
    validated_data = {}

    # Get configuration
    if conf_str:
        try:
            configuration = GetConfiguration(user_conf=json.loads(conf_str)).for_json()
        except Exception as e:
            logger.exception(e)
            raise exceptions.ValidationError({'configuration': _('The configuration has wrong format')})
    else:
        configuration = get_default_configuration(user).for_json()

    validated_data['priority'] = configuration['priority']
    validated_data['weight'] = configuration['weight']

    # Validate task scheduler
    try:
        validated_data['scheduler'] = validate_scheduler(type=configuration['task scheduler'])
    except BridgeException as e:
        raise exceptions.ValidationError({'scheduler': str(e)})

    # Save configuration file
    conf_db = file_get_or_create(
        json.dumps(configuration, indent=2, sort_keys=True, ensure_ascii=False), 'configuration.json', JobFile
    )
    validated_data['configuration_id'] = conf_db.id

    return validated_data


class DecisionFilesField(fields.Field):
    initial = []

    default_error_messages = {
        'wrong_format': _("The files tree has wrong format")
    }

    def to_internal_value(self, data):
        try:
            if isinstance(data, str):
                data = json.loads(data)
            return JSTreeConverter().parse_tree(data)
        except BridgeException as e:
            raise exceptions.ValidationError(str(e))
        except Exception as e:
            logger.exception(e)
            self.fail('wrong_format')

    def to_representation(self, value):
        # Get list of files [(<id>, <hash_sum>)]
        queryset = FileSystem.objects.all()
        if isinstance(value, Decision):
            queryset = queryset.filter(decision=value)
        elif isinstance(value, QuerySet):
            queryset = value
        else:
            # Internal value
            queryset = queryset.filter(id__in=list(x['file_id'] for x in value))
        return JSTreeConverter().make_tree(list(queryset.values_list('name', 'file__hash_sum')))


class JobFileSerializer(serializers.ModelSerializer):
    default_error_messages = {
        'wrong_json': _('The file is wrong JSON: {exc}'),
        'max_size': _('Please keep the file size under {max_size} (the current file size is {curr_size})')
    }

    def validate_file(self, fp):
        file_size = fp.seek(0, os.SEEK_END)
        if file_size > settings.MAX_FILE_SIZE:
            self.fail('max_size', max_size=filesizeformat(settings.MAX_FILE_SIZE),
                      curr_size=filesizeformat(file_size))

        if os.path.splitext(fp.name)[1] == '.json':
            fp.seek(0)
            try:
                json.loads(fp.read().decode('utf8'))
            except Exception as e:
                self.fail('wrong_json', exc=str(e))
        fp.seek(0)
        return fp

    def create(self, validated_data):
        validated_data['hash_sum'] = file_checksum(validated_data['file'])
        return JobFile.objects.get_or_create(hash_sum=validated_data['hash_sum'], defaults=validated_data)[0]

    def update(self, instance, validated_data):
        raise RuntimeError('Update files is not allowed')

    def to_representation(self, instance):
        if isinstance(instance, JobFile):
            return {'hashsum': instance.hash_sum}
        return super().to_representation(instance)

    class Meta:
        model = JobFile
        fields = ('file',)
        extra_kwargs = {'file': {'allow_empty_file': True}}


class UserRoleSerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()

    def get_title(self, instance):
        return instance.get_role_display()

    class Meta:
        model = UserRole
        fields = ('user', 'role', 'title')


class CreateJobSerializer(serializers.ModelSerializer):
    author = fields.HiddenField(default=serializers.CurrentUserDefault())
    user_roles = UserRoleSerializer(many=True, default=[])

    def create(self, validated_data):
        user_roles = validated_data.pop('user_roles')
        instance = super().create(validated_data)
        UserRole.objects.bulk_create(list(UserRole(job=instance, **rkwargs) for rkwargs in user_roles))
        return instance

    def update(self, instance, validated_data):
        raise RuntimeError('Update method is not supported for this serializer')

    def to_representation(self, instance):
        if isinstance(instance, self.Meta.model):
            return {'url': reverse('jobs:decision-create', args=[instance.pk])}
        return super(CreateJobSerializer, self).to_representation(instance)

    class Meta:
        model = Job
        fields = ('preset', 'name', 'global_role', 'user_roles', 'author')


class UpdateJobSerializer(serializers.ModelSerializer):
    user_roles = UserRoleSerializer(many=True, default=[])

    def create(self, validated_data):
        raise RuntimeError('Create method is not supported for this serializer')

    def update(self, instance, validated_data):
        user_roles = validated_data.pop('user_roles')
        instance = super().update(instance, validated_data)

        # Update user roles
        UserRole.objects.filter(job=instance).delete()
        UserRole.objects.bulk_create(list(UserRole(job=instance, **rkwargs) for rkwargs in user_roles))
        return instance

    def to_representation(self, instance):
        if isinstance(instance, self.Meta.model):
            return {'url': reverse('jobs:job', args=[instance.pk])}
        return super(UpdateJobSerializer, self).to_representation(instance)

    class Meta:
        model = Job
        fields = ('preset', 'name', 'global_role', 'user_roles')


class CreateDecisionSerializer(serializers.ModelSerializer):
    operator = fields.HiddenField(default=serializers.CurrentUserDefault())
    files = DecisionFilesField()
    configuration = fields.CharField(required=False)

    def validate(self, attrs):
        conf_data = validate_configuration(attrs['operator'], attrs.pop('configuration', None))
        attrs.update(conf_data)
        return attrs

    def create(self, validated_data):
        assert 'job_id' in validated_data, 'Wrong serializer usage'

        job_files = validated_data.pop('files')
        instance = super().create(validated_data)
        FileSystem.objects.bulk_create(list(FileSystem(decision=instance, **fkwargs) for fkwargs in job_files))
        decision_status_changed(instance)
        return instance

    def update(self, instance, validated_data):
        raise RuntimeError('Update method is not supported for this serializer')

    def to_representation(self, instance):
        if isinstance(instance, self.Meta.model):
            return {'url': reverse('jobs:decision', args=[instance.pk])}
        return super(CreateDecisionSerializer, self).to_representation(instance)

    class Meta:
        model = Decision
        fields = ('title', 'operator', 'files', 'configuration')


class RestartDecisionSerializer(serializers.ModelSerializer):
    operator = fields.HiddenField(default=serializers.CurrentUserDefault())
    configuration = fields.CharField()

    def __clear_related_objects(self, instance):
        Report.objects.filter(decision=instance).delete()
        AttrFile.objects.filter(decision=instance).delete()
        AdditionalSources.objects.filter(decision=instance).delete()
        CompareDecisionsInfo.objects.filter(Q(decision1=instance) | Q(decision2=instance)).delete()
        DecisionCache.objects.filter(decision=instance).delete()
        Task.objects.filter(decision=instance).delete()

    def validate(self, attrs):
        conf_data = validate_configuration(attrs['operator'], attrs.pop('configuration'))
        attrs.update(conf_data)

        attrs['status'] = DECISION_STATUS[1][0]
        attrs['start_date'] = now()

        int_fields = (
            'tasks_total', 'tasks_pending', 'tasks_processing', 'tasks_finished',
            'tasks_error', 'tasks_cancelled', 'solutions'
        )
        null_fields = (
            'error', 'finish_date', 'total_sj', 'failed_sj', 'solved_sj', 'expected_time_sj',
            'start_sj', 'finish_sj', 'gag_text_sj', 'total_ts', 'failed_ts', 'solved_ts', 'expected_time_ts',
            'start_ts', 'finish_ts', 'gag_text_ts'
        )
        for field_name in int_fields:
            attrs[field_name] = 0
        for field_name in null_fields:
            attrs[field_name] = None

        return attrs

    def create(self, validated_data):
        raise NotImplementedError('Create method is not supported for this serializer')

    def update(self, instance, validated_data):
        self.__clear_related_objects(instance)
        instance = super(RestartDecisionSerializer, self).update(instance, validated_data)
        decision_status_changed(instance)
        return instance

    def to_representation(self, instance):
        return {'url': reverse('jobs:decision', args=[instance.pk])}

    class Meta:
        model = Decision
        fields = ('operator', 'configuration')


class DecisionStatusSerializerRO(serializers.ModelSerializer):
    class Meta:
        model = Decision
        fields = ('status', 'identifier')


class UploadedJobArchiveSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        assert 'author' in validated_data, 'Wrong serializer usage'
        validated_data['name'] = validated_data['archive'].name
        return super(UploadedJobArchiveSerializer, self).create(validated_data)

    class Meta:
        model = UploadedJobArchive
        fields = ('archive',)


class PresetJobDirSerializer(DynamicFieldsModelSerializer):
    def create(self, validated_data):
        validated_data['type'] = PRESET_JOB_TYPE[2][0]
        validated_data['check_date'] = validated_data['parent'].check_date
        return super(PresetJobDirSerializer, self).create(validated_data)

    class Meta:
        model = PresetJob
        fields = ('parent', 'name')


class UpdateDecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Decision
        fields = ('title',)


class DefaultDecisionConfigurationSerializer(serializers.ModelSerializer):
    user = fields.HiddenField(default=serializers.CurrentUserDefault())
    configuration = fields.CharField()

    def validate(self, attrs):
        # Get configuration
        conf_str = attrs.pop('configuration')
        try:
            configuration = GetConfiguration(user_conf=json.loads(conf_str)).for_json()
        except Exception as e:
            logger.exception(e)
            raise exceptions.ValidationError({'configuration': _('The configuration has wrong format')})

        # Save configuration file
        conf_db = file_get_or_create(json.dumps(
            configuration, indent=2, sort_keys=True, ensure_ascii=False
        ), 'configuration.json', JobFile)
        attrs['file_id'] = conf_db.id

        return attrs

    def to_representation(self, instance):
        if isinstance(instance, self.Meta.model):
            return {'pk': instance.pk}
        return {}

    class Meta:
        model = DefaultDecisionConfiguration
        fields = ('user', 'configuration')
