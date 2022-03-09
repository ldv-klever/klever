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

from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.urls import reverse

from rest_framework import serializers, exceptions

from bridge.serializers import DynamicFieldsModelSerializer

from users.models import User, DataView, PreferableView
from jobs.utils import JobAccess


class ManageUserSerializer(serializers.ModelSerializer):
    def __set_password(self, instance, password):
        if password:
            instance.set_password(password)
            instance.save()
        return instance

    def create(self, validated_data):
        validated_data.update({'first_name': '', 'last_name': '', 'email': ''})
        password = validated_data.pop('password')
        instance = super().create(validated_data)
        return self.__set_password(instance, password)

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        instance = super().update(instance, validated_data)
        return self.__set_password(instance, password)

    class Meta:
        model = User
        fields = ('username', 'password', 'role', 'is_staff', 'is_superuser')


class JobsChangesSerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        if not isinstance(instance, JobHistory):
            raise exceptions.APIException('Wrong serializer usage')
        value = super().to_representation(instance)
        if JobAccess(self.context['request'].user, instance.job).can_view:
            value['href'] = reverse('jobs:job', args=[instance.job_id])
        if len(value['comment']) > 50:
            value['display_comment'] = value['comment'][:47] + '...'
        return value

    class Meta:
        # model = JobHistory
        depth = 1
        fields = ('version', 'change_date', 'comment', 'job.name')


class DataViewSerializer(DynamicFieldsModelSerializer):
    default_error_messages = {
        'wrong_name': _('Please choose another view name')
    }

    def validate_name(self, value):
        if value == str(_('Default')):
            self.fail('wrong_name')
        return value

    @cached_property
    def user(self):
        return self.context['request'].user if 'request' in self.context else None

    def validate(self, attrs):
        if 'name' in attrs and 'type' in attrs:
            if self.user.views.filter(name=attrs['name'], type=attrs['type']).exists():
                self.fail('wrong_name')
        attrs['author'] = self.user
        return attrs

    def to_representation(self, instance):
        if 'request' in self.context and self.context['request'].method != 'GET' and isinstance(instance, DataView):
            return {'id': instance.id, 'name': instance.name}
        return super().to_representation(instance)

    def update(self, instance, validated_data):
        assert isinstance(instance, DataView)
        if 'shared' in validated_data and validated_data['shared'] != instance.shared and instance.shared:
            # Remove preferable view for users if view has become hidden
            PreferableView.objects.filter(view=instance).exclude(user=self.user).delete()
        return super().update(instance, validated_data)

    class Meta:
        model = DataView
        exclude = ('author',)
