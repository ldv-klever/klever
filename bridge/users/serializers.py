from django.utils.translation import ugettext_lazy as _
from django.urls import reverse

from rest_framework import serializers, exceptions

from users.models import User
from jobs.models import JobHistory
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
        if JobAccess(self.context['request'].user, instance.job).can_view():
            value['href'] = reverse('jobs:job', args=[instance.job_id])
        if len(value['comment']) > 50:
            value['display_comment'] = value['comment'][:47] + '...'
        return value

    class Meta:
        model = JobHistory
        depth = 1
        fields = ('version', 'change_date', 'comment', 'job.name')
