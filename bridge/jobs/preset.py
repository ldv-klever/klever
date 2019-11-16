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
import json

from django.conf import settings
from django.core.files import File
from django.utils.functional import cached_property
from django.utils.timezone import now

from bridge.vars import USER_ROLES, JOB_ROLES

from users.models import User
from jobs.models import Job, JobHistory

from jobs.utils import JSTreeConverter, get_unique_name
from jobs.serializers import JobFileSerializer


def get_presets_dir():
    presets = os.path.join(settings.BASE_DIR, 'jobs', 'presets')
    if os.path.isdir(presets):
        return presets
    with open(presets, mode='r', encoding='utf-8') as fp:
        presets_path = fp.read()
    return os.path.abspath(os.path.join(settings.BASE_DIR, 'jobs', presets_path))


class PresetsProcessor:
    base_file = 'base.json'
    tasks_file = 'tasks.json'
    job_file = 'job.json'

    def __init__(self, user):
        self._user = user
        self._parent = None
        self._presets_dir = get_presets_dir()

    def get_jobs_tree(self):
        if settings.POPULATE_JUST_PRODUCTION_PRESETS:
            return self.__get_production_tree(self._presets_data['jobs'])
        return self._presets_data['jobs']

    def __get_fake_job(self, name, identifier):
        try:
            return Job.objects.get(identifier=identifier)
        except Job.DoesNotExist:
            new_job = Job.objects.create(name=name, parent=self._parent, identifier=identifier, author=self._user)
        JobHistory.objects.create(
            job=new_job, name=new_job.name, version=new_job.version, change_author=new_job.author, change_date=now()
        )
        return new_job

    def __find_name(self, preset_uuid, jobs_list):
        for data in jobs_list:
            if 'uuid' in data and data['uuid'] == preset_uuid:
                return data['name']
            elif 'children' in data:
                self._parent = self.__get_fake_job(data['name'], data['uuid'])
                name = self.__find_name(preset_uuid, data['children'])
                if name:
                    return name
                self._parent = self._parent.parent
        return None

    def get_job_name_and_parent(self, preset_uuid):
        self._parent = None
        preset_uuid = str(preset_uuid)
        base_name = self.__find_name(preset_uuid, self._presets_data['jobs'])
        parent = str(self._parent.identifier) if self._parent else ''
        return get_unique_name(base_name), parent

    @cached_property
    def _presets_data(self):
        with open(os.path.join(self._presets_dir, self.base_file), mode='r', encoding='utf-8') as fp:
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

    def __get_production_tree(self, data):
        return self.__get_production_children(data)

    def __initial_roles(self):
        users_qs = User.objects.exclude(role__in=[USER_ROLES[2][0], USER_ROLES[4][0]])
        available_users = list({'id': u.id, 'name': u.get_full_name()} for u in users_qs)
        available_users.sort(key=lambda x: x['name'])
        return {'user_roles': [], 'available_users': available_users, 'global_role': JOB_ROLES[0][0]}

    def __collect_main_files(self, preset_uuid):
        preset_uuid = str(preset_uuid)

        def find_directory(jobs_list):
            for data in jobs_list:
                if 'uuid' in data and data['uuid'] == preset_uuid:
                    return data['directory']
                elif 'children' in data:
                    directory = find_directory(data['children'])
                    if directory:
                        return directory
            return None

        job_directory = find_directory(self._presets_data['jobs'])
        if not job_directory:
            raise ValueError('The preset job was not found')
        return [
            (self.job_file, self.__save_file(os.path.join(self._presets_dir, job_directory, self.job_file))),
            (self.tasks_file, self.__save_file(os.path.join(self._presets_dir, job_directory, self.tasks_file)))
        ]

    def __collect_common_files(self):
        common_files = []
        for name in self._presets_data['common directories and files']:
            path = os.path.join(self._presets_dir, name)
            if os.path.isdir(path):
                for dir_path, dir_names, file_names in os.walk(path):
                    for file_name in file_names:
                        file_path = os.path.join(dir_path, file_name)
                        rel_path = os.path.relpath(file_path, self._presets_dir)
                        common_files.append((rel_path.replace('\\', '/'), self.__save_file(file_path)))
            elif os.path.isfile(path):
                common_files.append((name, self.__save_file(path)))
            else:
                raise ValueError('Preset file/dir "{}" was not found'.format(name))
        return common_files

    def get_form_data(self, preset_uuid):
        files_list = self.__collect_main_files(preset_uuid) + self.__collect_common_files()

        return {
            'files': JSTreeConverter().make_tree(files_list),
            'roles': self.__initial_roles()
        }

    def __save_file(self, file_path):
        if not os.path.isfile(file_path):
            raise ValueError('File was not found: {}'.format(file_path))
        with open(file_path, mode='rb') as fp:
            serializer = JobFileSerializer(data={'file': File(fp, name=os.path.basename(file_path))})
            serializer.is_valid(raise_exception=True)
            instance = serializer.save()
        return instance.hash_sum
