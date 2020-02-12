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
from django.db.models.query import QuerySet
from django.template.defaultfilters import filesizeformat
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers, exceptions, fields

from bridge.vars import DECISION_STATUS
from bridge.utils import logger, file_checksum, RMQConnect, BridgeException
from bridge.serializers import DynamicFieldsModelSerializer

from jobs.models import PRESET_JOB_TYPE, Job, JobFile, FileSystem, UserRole, UploadedJobArchive, PresetJob
from service.models import Decision

from jobs.utils import JSTreeConverter

FILE_SEP = '/'
ARCHIVE_FORMAT = 13


def decision_status_changed(decision):
    if decision.status in {DECISION_STATUS[1][0], DECISION_STATUS[5][0], DECISION_STATUS[6][0]}:
        with RMQConnect() as channel:
            channel.basic_publish(
                exchange='', routing_key=settings.RABBIT_MQ_QUEUE, properties=pika.BasicProperties(delivery_mode=2),
                body="job {} {} {}".format(decision.identifier, decision.status, decision.scheduler.type)
            )


class JobFilesField(fields.Field):
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
        if isinstance(value, Job):
            queryset = queryset.filter(job=value)
        elif isinstance(value, QuerySet):
            queryset = value
        else:
            # Internal value
            queryset = queryset.filter(id__in=list(x['file_id'] for x in value))
        return JSTreeConverter().make_tree(list(queryset.values_list('name', 'file__hash_sum')))


class JobFileSerializer(serializers.ModelSerializer):
    default_error_messages = {
        'wrong_json': _('The file is wrong json: {exc}'),
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
    files = JobFilesField()
    user_roles = UserRoleSerializer(many=True, default=[])

    def create(self, validated_data):
        job_files = validated_data.pop('files')
        user_roles = validated_data.pop('user_roles')
        instance = super().create(validated_data)

        # Save job files and user roles
        FileSystem.objects.bulk_create(list(FileSystem(job=instance, **fkwargs) for fkwargs in job_files))
        UserRole.objects.bulk_create(list(UserRole(job=instance, **rkwargs) for rkwargs in user_roles))
        return instance

    def update(self, instance, validated_data):
        raise RuntimeError('Update method is not supported for this serializer')

    def to_representation(self, instance):
        if isinstance(instance, self.Meta.model):
            return {
                'job': reverse('jobs:job', args=[instance.pk]),
                'start': reverse('jobs:prepare-decision', args=[instance.pk]),
                'faststart': reverse('jobs:api-decide', args=[instance.pk]),
            }
        return super(CreateJobSerializer, self).to_representation(instance)

    class Meta:
        model = Job
        fields = ('preset', 'name', 'global_role', 'author', 'files', 'user_roles')


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
            return {
                'job': reverse('jobs:job', args=[instance.pk])
            }
        return super(UpdateJobSerializer, self).to_representation(instance)

    class Meta:
        model = Job
        fields = ('preset', 'name', 'global_role', 'user_roles')


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
