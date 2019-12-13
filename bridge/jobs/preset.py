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
import io
import os
import json
import uuid

from django.conf import settings
from django.core.files import File
from django.utils.functional import cached_property
from django.utils.timezone import now

from bridge.vars import USER_ROLES, JOB_ROLES
from bridge.utils import file_checksum

from users.models import User
from jobs.models import Job, JobHistory, PresetStatus

from jobs.utils import JSTreeConverter, get_unique_name
from jobs.serializers import JobFileSerializer

BASE_FILE = 'base.json'
TASKS_FILE = 'tasks.json'
JOB_FILE = 'job.json'


def get_presets_dir():
    presets = os.path.join(settings.BASE_DIR, 'jobs', 'presets')
    if os.path.isdir(presets):
        return presets
    with open(presets, mode='r', encoding='utf-8') as fp:
        presets_path = fp.read()
    return os.path.abspath(os.path.join(settings.BASE_DIR, 'jobs', presets_path))


class PresetFiles:
    def __init__(self, preset_uuid):
        self._preset_uuid = str(preset_uuid)
        self._presets_dir = get_presets_dir()

    def __iter__(self):
        # Get specific preset files
        job_directory = self.__find_directory(self._presets_data['jobs'])
        if not job_directory:
            raise ValueError('The preset job was not found')
        yield JOB_FILE, self.__save_file(os.path.join(job_directory, JOB_FILE))
        yield TASKS_FILE, self.__save_file(os.path.join(job_directory, TASKS_FILE))

        # Common presets files
        for name in self._presets_data['common directories and files']:
            path = os.path.join(self._presets_dir, name)
            if os.path.isdir(path):
                for dir_path, dir_names, file_names in os.walk(path):
                    for file_name in file_names:
                        file_path = os.path.join(dir_path, file_name)
                        rel_path = os.path.relpath(file_path, self._presets_dir)
                        yield rel_path.replace('\\', '/'), self.__save_file(file_path)
            elif os.path.isfile(path):
                yield name, self.__save_file(path)
            else:
                raise ValueError('Preset file/dir "{}" was not found'.format(name))

    @cached_property
    def _presets_data(self):
        with open(os.path.join(self._presets_dir, BASE_FILE), mode='r', encoding='utf-8') as fp:
            return json.load(fp)

    def __find_directory(self, jobs_list):
        for data in jobs_list:
            if 'uuid' in data and data['uuid'] == self._preset_uuid:
                directory = os.path.join(self._presets_dir, data['directory'])
                if not os.path.isdir(directory):
                    raise ValueError('The preset job directory does not exist')
                return directory
            elif 'children' in data:
                directory = self.__find_directory(data['children'])
                if directory:
                    return directory
        return None

    def __save_file(self, file_path):
        if not os.path.isfile(file_path):
            raise ValueError('File was not found: {}'.format(file_path))
        with open(file_path, mode='rb') as fp:
            serializer = JobFileSerializer(data={'file': File(fp, name=os.path.basename(file_path))})
            serializer.is_valid(raise_exception=True)
            instance = serializer.save()
        return instance


class PresetsProcessor:
    def __init__(self, user):
        self._user = user
        self._parents = []
        self._presets_dir = get_presets_dir()

    def get_jobs_tree(self):
        if settings.POPULATE_JUST_PRODUCTION_PRESETS:
            return self.__get_production_children(self._presets_data['jobs'])
        return self._presets_data['jobs']

    def __find_name(self, preset_uuid, jobs_list):
        for data in jobs_list:
            if 'uuid' in data and data['uuid'] == preset_uuid:
                return data['name']
            elif 'children' in data:
                self._parents.append({'name': data['name'], 'identifier': data['uuid']})
                name = self.__find_name(preset_uuid, data['children'])
                if name:
                    return name
                self._parents.pop()
        return None

    def __get_job_parent(self):
        # If preset job don't have parents, then new job will not have it
        if not self._parents:
            return None
        # Try to get last the closest parent from DB
        try:
            return Job.objects.get(identifier=self._parents[-1]['identifier'])
        except Job.DoesNotExist:
            pass
        # Get or create all parents branch
        prev_parent = None
        for parent_data in self._parents:
            new_job, created = Job.objects.get_or_create(identifier=parent_data['identifier'], defaults={
                'name': parent_data['name'], 'parent': prev_parent, 'author': self._user
            })
            if created:
                JobHistory.objects.create(
                    job=new_job, name=new_job.name, version=new_job.version,
                    change_author=new_job.author, change_date=now()
                )
            prev_parent = new_job
        return prev_parent

    def get_job_name_and_parent(self, preset_uuid):
        self._parents = []
        base_name = self.__find_name(str(preset_uuid), self._presets_data['jobs'])
        if not base_name:
            raise ValueError('The preset job with identifier "{}" was not found'.format(preset_uuid))
        return get_unique_name(base_name), self.__get_job_parent()

    @cached_property
    def _presets_data(self):
        with open(os.path.join(self._presets_dir, BASE_FILE), mode='r', encoding='utf-8') as fp:
            return json.load(fp)

    def __get_production_children(self, preset_tree):
        new_tree = []
        for job_data in preset_tree:
            if 'children' in job_data:
                new_children_list = self.__get_production_children(job_data['children'])
                if new_children_list:
                    job_data['children'] = new_children_list
                    new_tree.append(job_data)
            elif 'uuid' in job_data and job_data.get('production'):
                new_tree.append(job_data)
        return new_tree

    def initial_roles(self):
        users_qs = User.objects.exclude(role__in=[USER_ROLES[2][0], USER_ROLES[4][0]])
        available_users = list({'id': u.id, 'name': u.get_full_name()} for u in users_qs)
        available_users.sort(key=lambda x: x['name'])
        return {'user_roles': [], 'available_users': available_users, 'global_role': JOB_ROLES[0][0]}

    def get_form_data(self, preset_uuid):
        preset_files_hashsums = list((name, obj.hash_sum) for name, obj in PresetFiles(preset_uuid))
        return {
            'files': JSTreeConverter().make_tree(preset_files_hashsums),
            'roles': self.initial_roles()
        }

    def get_file_system_kwargs(self, preset_uuid):
        return list({'name': name, 'file_id': obj.id} for name, obj in PresetFiles(preset_uuid))


class PresetsChecker:
    def __init__(self):
        self._presets_dir = get_presets_dir()

    @cached_property
    def _presets_data(self):
        with open(os.path.join(self._presets_dir, BASE_FILE), mode='r', encoding='utf-8') as fp:
            return json.load(fp)

    def __get_check_sum(self, file_path):
        with open(file_path, mode='rb') as fp:
            return file_checksum(fp)

    def __files_checksums(self, job_directory):
        yield self.__get_check_sum(os.path.join(self._presets_dir, job_directory, JOB_FILE))
        yield self.__get_check_sum(os.path.join(self._presets_dir, job_directory, TASKS_FILE))

        # Common files
        for name in self._presets_data['common directories and files']:
            path = os.path.join(self._presets_dir, name)
            if os.path.isdir(path):
                for dir_path, dir_names, file_names in os.walk(path):
                    for file_name in file_names:
                        yield self.__get_check_sum(os.path.join(dir_path, file_name))
            elif os.path.isfile(path):
                yield self.__get_check_sum(path)
            else:
                raise ValueError('Preset file/dir "{}" was not found'.format(name))

    def __calculate_for_job(self, job_data):
        check_sums = []
        for check_sum in self.__files_checksums(job_data['directory']):
            check_sums.append(check_sum)
        fp = io.BytesIO(json.dumps(check_sums, ensure_ascii=False).encode('utf8'))
        job_hash_sum = file_checksum(fp)[:128]
        try:
            preset_obj = PresetStatus.objects.get(identifier=job_data['uuid'])
            if preset_obj.hash_sum != job_hash_sum:
                preset_obj.hash_sum = job_hash_sum
                preset_obj.save()
        except PresetStatus.DoesNotExist:
            PresetStatus.objects.create(identifier=uuid.UUID(job_data['uuid']), hash_sum=job_hash_sum)

    def __check_all(self, jobs_list):
        for data in jobs_list:
            if 'uuid' in data and 'directory' in data:
                if not settings.POPULATE_JUST_PRODUCTION_PRESETS or data.get('production'):
                    self.__calculate_for_job(data)
            elif 'children' in data:
                self.__check_all(data['children'])

    def calculate_hash_sums(self):
        self.__check_all(self._presets_data['jobs'])
