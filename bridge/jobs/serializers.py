import json
import os
import pika

from io import BytesIO

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.template.defaultfilters import filesizeformat
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers, exceptions, fields

from bridge.vars import USER_ROLES, JOB_ROLES, MPTT_FIELDS, FORMAT, JOB_STATUS
from bridge.utils import file_get_or_create, logger, file_checksum, RMQConnect
from bridge.serializers import TimeStampField

from users.models import User
from jobs.models import Job, JobHistory, JobFile, FileSystem, UserRole, RunHistory
from jobs.utils import JobAccess

FILE_SEP = '/'


def create_job_version(job, files, roles, **kwargs):
    """
    Creates job version (JobHistory) without any checks.
    :param job: Job instance
    :param files: list of dictionaries like {"name": <str>, "file_id": <existing file pk>}
    :param roles: list of dictionaries like {"user_id": <existing user pk>, "role": JOB_ROLES[<i>][0]}
    :param kwargs: JobHistory fields
    :return:
    """
    kwargs.setdefault('name', job.name)
    kwargs.setdefault('version', job.version)
    kwargs.setdefault('change_date', now())

    # Create job version
    job_version = JobHistory.objects.create(job=job, **kwargs)

    # Create job version files
    FileSystem.objects.bulk_create(list(FileSystem(job_version=job_version, **fkwargs) for fkwargs in files))

    # Create job version roles
    UserRole.objects.bulk_create(list(UserRole(job_version=job_version, **rkwargs) for rkwargs in roles))
    return job_version


class ReadOnlyMixin:
    def create(self, validated_data):
        raise RuntimeError('The serializer is for data representation only')

    def update(self, instance, validated_data):
        raise RuntimeError('The serializer is for data representation only')


class JobFilesField(fields.Field):
    initial = []

    default_error_messages = {
        'wrong_format': _("The files tree has wrong format"),
        'name_empty': _("The file/folder name can't be empty"),
        'not_uploaded': _('The file with hashsum "{hash_sum}" was not uploaded before'),
    }

    @cached_property
    def empty_file(self):
        db_file = file_get_or_create(BytesIO(), 'empty', JobFile, False)
        return db_file.id

    def __get_children_data(self, obj_p, prefix=None):
        if not isinstance(obj_p, dict):
            self.fail('wrong_format')

        files = []
        name = ((prefix + FILE_SEP) if prefix else '') + obj_p['text']
        if obj_p['type'] == 'file':
            file_data = {'name': name}
            if 'data' in obj_p and 'hashsum' in obj_p['data']:
                file_data['hash_sum'] = obj_p['data']['hashsum']
            files.append(file_data)
        elif 'children' in obj_p:
            for child in obj_p['children']:
                files.extend(self.__get_children_data(child, prefix=(name if obj_p['type'] != 'root' else None)))
        return files

    def to_internal_value(self, data):
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception as e:
                logger.exception(e)
                self.fail('wrong_format')

        if not isinstance(data, list) or len(data) != 1:
            self.fail('wrong_format')

        files_list = self.__get_children_data(data[0])

        # Get files ids and check that there is a file for each provided hash_sum
        hash_sums = set(fdata['hash_sum'] for fdata in files_list if 'hash_sum' in fdata)
        db_files = dict(JobFile.objects.filter(hash_sum__in=hash_sums).values_list('hash_sum', 'id'))
        if hash_sums - set(db_files):
            self.fail('not_uploaded')

        # Set file for each file data instead of hash_sum
        for file_data in files_list:
            if 'hash_sum' in file_data:
                file_data['file_id'] = db_files[file_data['hash_sum']]
                file_data.pop('hash_sum')
            else:
                file_data['file_id'] = self.empty_file

        return files_list

    def __sort_children(self, obj):
        if not obj.get('children'):
            return
        obj['children'].sort(key=lambda x: (x['type'] is 'file', x['text']))
        for child in obj['children']:
            self.__sort_children(child)

    def to_representation(self, value):
        # Get list of files [(<id>, <hash_sum>)]
        queryset = FileSystem.objects.all()
        if isinstance(value, JobHistory):
            queryset = queryset.filter(job_version=value)
        else:
            # Internal value
            queryset = queryset.filter(id__in=list(x['file_id'] for x in value))
        files_list = list(queryset.values_list('name', 'file__hash_sum'))

        # Create tree
        files_tree = [{'type': 'root', 'text': 'Files', 'children': []}]
        for name, hash_sum in files_list:
            path = name.split(FILE_SEP)
            obj_p = files_tree[0]['children']
            for dir_name in path[:-1]:
                for child in obj_p:
                    if isinstance(child, dict) and child['type'] == 'folder' and child['text'] == dir_name:
                        obj_p = child['children']
                        break
                else:
                    # Directory
                    new_p = []
                    obj_p.append({'text': dir_name, 'type': 'folder', 'children': new_p})
                    obj_p = new_p
            # File
            obj_p.append({'text': path[-1], 'type': 'file', 'data': {'hashsum': hash_sum}})

        # Sort files and folders by name and put folders before files
        self.__sort_children(files_tree[0])

        return files_tree


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
        try:
            return JobFile.objects.get(hash_sum=validated_data['hash_sum'])
        except JobFile.DoesNotExist:
            return super().create(validated_data)

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
    def to_representation(self, instance):
        value = super().to_representation(instance)
        value['title'] = dict(JOB_ROLES)[value['role']]
        return value

    class Meta:
        model = UserRole
        fields = ('user', 'role')


class JobVersionSerializer(serializers.ModelSerializer):
    def get_value(self, dictionary):
        return dictionary

    class Meta:
        model = JobHistory
        fields = ('comment', 'name', 'description', 'global_role')


class CreateJobSerializer(serializers.ModelSerializer):
    parent = serializers.SlugRelatedField(slug_field='identifier', allow_null=True, queryset=Job.objects.all())
    job_version = JobVersionSerializer()
    files = JobFilesField()
    user_roles = UserRoleSerializer(many=True, default=[])

    def validate_version(self, version):
        if self.instance and self.instance.version != version:
            raise exceptions.ValidationError(_("Your version is expired, please reload the page"))
        return version

    @cached_property
    def author(self):
        if 'author' in self.context:
            return self.context['author']
        if 'request' in self.context:
            return self.context['request'].user
        return None

    def create(self, validated_data):
        job_files = validated_data.pop('files')
        version_data = validated_data.pop('job_version')
        user_roles = validated_data.pop('user_roles')
        validated_data.pop('version', None)  # Use default version on job create
        validated_data['author'] = self.author
        instance = super().create(validated_data)

        # Create job version with files and roles
        create_job_version(instance, job_files, user_roles, change_author=self.author, **version_data)
        return instance

    def update(self, instance, validated_data):
        assert isinstance(instance, Job)
        job_files = validated_data.pop('files')
        version_data = validated_data.pop('job_version')
        user_roles = validated_data.pop('user_roles')
        validated_data['version'] = instance.version + 1
        instance = super().update(instance, validated_data)

        # Create job version with files and roles
        create_job_version(instance, job_files, user_roles, change_author=self.author, **version_data)
        return instance

    def to_representation(self, instance):
        if isinstance(instance, self.Meta.model):
            return {'url': reverse('jobs:job', args=[instance.pk])}
        return {'url': reverse('jobs:job', args=[instance['id']])}

    class Meta:
        model = Job
        exclude = ('status', 'author', *MPTT_FIELDS)


class UploadJobSerializer(serializers.ModelSerializer):
    def validate_format(self, value):
        if value != FORMAT:
            raise exceptions.ValidationError(_("The job format is not supported"))
        return value

    class Meta:
        model = Job
        exclude = ('author', *MPTT_FIELDS)
        extra_kwargs = {'parent': {'write_only': True}}


class UploadJobVersionSerializer(serializers.ModelSerializer):
    change_date = TimeStampField()
    files = JobFilesField()
    user_roles = UserRoleSerializer(many=True, default=[])

    class Meta:
        model = JobHistory
        exclude = ('job', 'change_author')


class JVrolesSerializerRO(serializers.ModelSerializer):
    user_roles = serializers.ListField(child=UserRoleSerializer(), source='userrole_set.all')
    available_users = serializers.SerializerMethodField()

    def get_available_users(self, instance):
        users_qs = User.objects.exclude(role__in=[USER_ROLES[2][0], USER_ROLES[4][0]])

        # Return all users in the system except service and manager users, exclude the job author also
        users = dict((u.id, u.get_full_name()) for u in users_qs)
        users.pop(instance.job.author_id, None)
        return users

    def to_representation(self, instance):
        data = super().to_representation(instance)

        # Add user full "name" for each user with specified role
        user_roles = []
        for ur in data['user_roles']:
            # Either user is manager, author or service of the job if he is not in all_users dict
            ur['name'] = data['available_users'].pop(ur['user'], None)
            if ur['name']:
                user_roles.append(ur)
        data['user_roles'] = user_roles

        # Available users for specifying the role; sorted by user full name
        data['available_users'] = list({'id': u_id, 'name': u_name} for u_id, u_name in data['available_users'].items())
        data['available_users'].sort(key=lambda x: x['name'])

        return data

    class Meta:
        model = JobHistory
        fields = ('user_roles', 'available_users', 'global_role')
        read_only = ('global_role',)


class JVlistSerializerRO(ReadOnlyMixin, serializers.ModelSerializer):
    title = serializers.SerializerMethodField()

    def get_title(self, instance):
        if instance.job.version == instance.version:
            return _("Current version")
        title = serializers.DateTimeField(format="%d.%m.%Y %H:%M:%S").to_representation(instance.change_date)
        if instance.change_author:
            title += ' ({0})'.format(instance.change_author.get_full_name())
        if instance.comment:
            title += ': {0}'.format(instance.comment)
        return title

    class Meta:
        model = JobHistory
        fields = ('version', 'title')


class JobFormSerializerRO(ReadOnlyMixin, serializers.ModelSerializer):
    parent = serializers.SerializerMethodField()
    versions = JVlistSerializerRO(many=True)

    def get_parent(self, instance):
        return str(instance.parent.identifier) if instance.parent else ''

    class Meta:
        model = Job
        fields = ('id', 'name', 'parent', 'versions', 'version')


class JVformSerializerRO(serializers.ModelSerializer):
    files = JobFilesField(source='*')
    roles = JVrolesSerializerRO(source='*')

    class Meta:
        model = JobHistory
        fields = ('name', 'description', 'files', 'roles')


class JobStatusSerializer(serializers.ModelSerializer):
    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        try:
            run_data = instance.runhistory_set.latest('date')
            run_data.status = instance.status
            run_data.save()
        except ObjectDoesNotExist:
            pass

        if instance.status in {JOB_STATUS[1][0], JOB_STATUS[5][0], JOB_STATUS[6][0]}:
            with RMQConnect() as channel:
                channel.basic_publish(
                    exchange='', routing_key=settings.RABBIT_MQ['name'],
                    properties=pika.BasicProperties(delivery_mode=2),
                    body="job {}: {}".format(instance.identifier, instance.status)
                )
        return instance

    class Meta:
        model = Job
        fields = ('status',)


class DuplicateJobSerializer(serializers.ModelSerializer):
    name = fields.CharField(max_length=150, required=False)

    def validate_name(self, name):
        if name and Job.objects.filter(name=name).count():
            raise exceptions.ValidationError('The job name is used already.')
        return name

    def __get_new_name(self, parent_name):
        cnt = 1
        while True:
            name = "{} #COPY-{}".format(parent_name, cnt)
            if Job.objects.filter(name=name).count():
                return name
            cnt += 1

    @cached_property
    def author(self):
        if 'author' in self.context:
            return self.context['author']
        if 'request' in self.context:
            return self.context['request'].user
        return None

    def create(self, validated_data):
        parent_version = validated_data['parent'].versions.order_by('-version').first()
        if not validated_data.get('name'):
            validated_data['name'] = self.__get_new_name(validated_data['parent'])
        instance = super().create(validated_data)

        job_files = FileSystem.objects.filter(job_version=parent_version).values('file_id', 'name')
        user_roles = UserRole.objects.filter(job_version=parent_version).values('user_id', 'role')

        # Create job version with parent files and user roles
        create_job_version(
            instance, job_files, user_roles, change_author=self.author,
            description=parent_version.description,
            global_role=parent_version.global_role
        )

        return instance

    def update(self, instance, validated_data):
        assert isinstance(instance, Job)
        last_version = instance.versions.order_by('-version').first()
        instance.version += 1

        job_files = FileSystem.objects.filter(job_version=last_version).values('file_id', 'name')
        user_roles = UserRole.objects.filter(job_version=last_version).values('user_id', 'role')

        # Copy job version with its files and user roles
        create_job_version(
            instance, job_files, user_roles, change_author=self.author,
            description=last_version.description,
            global_role=last_version.global_role
        )

        instance.save()
        return instance

    def to_representation(self, instance):
        return {'id': instance.pk, 'identifier': str(instance.identifier)}

    class Meta:
        model = Job
        fields = ('parent', 'name')


class RunHistorySerializer(serializers.ModelSerializer):
    date = TimeStampField()

    class Meta:
        model = RunHistory
        exclude = ('job', 'configuration')


def change_job_status(job, status):
    serializer = JobStatusSerializer(instance=job, data={'status': status})
    serializer.is_valid(raise_exception=True)
    return serializer.save()


def get_view_job_data(user, job: Job):
    # Get parents list
    parents = []
    parents_qs = job.get_ancestors()
    with_access = JobAccess(user).can_view_jobs(parents_qs)
    for parent in parents_qs:
        parents.append({
            'name': parent.name,
            'pk': parent.pk if parent.pk in with_access else None
        })

    # Get children list
    children = []
    children_qs = job.get_children()
    with_access = JobAccess(user).can_view_jobs(children_qs)
    for child in children_qs:
        if child.pk in with_access:
            children.append({'pk': child.pk, 'name': child.name})

    # Versions queryset
    versions_qs = job.versions.all()

    return {
        'author': job.author, 'parents': parents, 'children': children, 'last_version': versions_qs[0],
        'versions': JVlistSerializerRO(instance=versions_qs, many=True).data,
        'files': json.dumps(JobFilesField().to_representation(versions_qs[0])),
        'run_history': RunHistory.objects.filter(job=job).order_by('-date').select_related('operator'),
        'user_roles': versions_qs[0].userrole_set.select_related('user').order_by(
            'user__first_name', 'user__last_name', 'user__username'
        )
    }
