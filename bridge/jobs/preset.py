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
import os
import json
import uuid

from django.conf import settings
from django.core.files import File
from django.utils.functional import cached_property
from django.utils.timezone import now

from bridge.vars import PRESET_JOB_TYPE

from jobs.models import PresetJob, PresetFile

from jobs.serializers import JobFileSerializer
from jobs.utils import JSTreeConverter

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


def get_preset_dir_list(preset_job):
    available_dirs = []
    if preset_job.type == PRESET_JOB_TYPE[1][0]:
        available_dirs.append({'id': preset_job.id, 'name': preset_job.name, 'selected': True})
        preset_qs = PresetJob.objects.filter(parent=preset_job).order_by('name').values_list('id', 'name')
        available_dirs.extend(list({'id': p_id, 'name': name} for p_id, name in preset_qs))
    else:
        available_dirs.append({'id': preset_job.parent_id, 'name': preset_job.parent.name})
        preset_qs = PresetJob.objects.filter(parent_id=preset_job.parent_id).order_by('name').values_list('id', 'name')
        for p_id, name in preset_qs:
            available_dirs.append({'id': p_id, 'name': name, 'selected': (p_id == preset_job.id)})
    return available_dirs


def preset_job_files_tree_json(preset_job):
    # Get preset files
    if preset_job.type == PRESET_JOB_TYPE[1][0]:
        preset_files_qs = PresetFile.objects.filter(preset=preset_job).values_list('name', 'file__hash_sum')
    else:
        # Get files from parent for custom preset job
        preset_files_qs = PresetFile.objects.filter(preset_id=preset_job.parent_id) \
            .values_list('name', 'file__hash_sum')
    preset_files_hashsums = list((name, hash_sum) for name, hash_sum in preset_files_qs)
    return json.dumps(JSTreeConverter().make_tree(preset_files_hashsums), ensure_ascii=False)


class PopulatePresets:
    def __init__(self):
        self._presets_dir = get_presets_dir()

    def populate(self):
        self.__populate_presets(self._presets_data['jobs'])

    @cached_property
    def _presets_data(self):
        with open(os.path.join(self._presets_dir, BASE_FILE), mode='r', encoding='utf-8') as fp:
            return json.load(fp)

    def __populate_presets(self, jobs_list, parent_id=None):
        for data in jobs_list:
            if settings.POPULATE_JUST_PRODUCTION_PRESETS and not data.get('production'):
                continue
            try:
                preset_job = PresetJob.objects.get(identifier=data['uuid'])
            except PresetJob.DoesNotExist:
                create_kwargs = {'identifier': uuid.UUID(data['uuid']), 'name': data['name'], 'parent_id': parent_id}
                if 'children' in data:
                    preset_job = self.__create_preset_dir(**create_kwargs)
                elif 'directory' in data:
                    preset_job = self.__create_preset_leaf(data['directory'], **create_kwargs)
                else:
                    continue
            else:
                if 'children' in data:
                    self.__update_preset_dir(preset_job, name=data['name'], parent_id=parent_id)
                elif 'directory' in data:
                    self.__update_preset_leaf(preset_job, data['directory'], name=data['name'], parent_id=parent_id)
            if 'children' in data:
                self.__populate_presets(data['children'], parent_id=preset_job.id)

    def __create_preset_dir(self, **kwargs):
        return PresetJob.objects.create(check_date=now(), type=PRESET_JOB_TYPE[0][0], **kwargs)

    def __create_preset_leaf(self, files_dir, **kwargs):
        preset_job = PresetJob.objects.create(check_date=now(), type=PRESET_JOB_TYPE[1][0], **kwargs)
        new_preset_files = []
        for file_name, file_obj in self._job_files(files_dir):
            new_preset_files.append(PresetFile(preset_id=preset_job.id, name=file_name, file_id=file_obj.id))
        PresetFile.objects.bulk_create(new_preset_files)
        return preset_job

    def __update_preset_dir(self, preset_job, **kwargs):
        changed = False

        # Check if any field of the preset job is changed (name or parent)
        for field, value in kwargs.items():
            if getattr(preset_job, field) != value:
                setattr(preset_job, field, value)
                changed = True

        if changed:
            preset_job.save()

    def __update_preset_leaf(self, preset_job, files_dir, **kwargs):
        changed = False

        # Check if any field of the preset job is changed (name or parent)
        for field, value in kwargs.items():
            if getattr(preset_job, field) != value:
                setattr(preset_job, field, value)
                changed = True

        # Get old preset job files
        old_files = dict(((pr_f.name, pr_f.file_id), pr_f.id) for pr_f in PresetFile.objects.filter(preset=preset_job))

        files_to_create = []  # Unsaved PresetFile instances
        new_files = set()  # Tuples (name, JobFile.id)

        # Collect preset job files if its directory is provided (JobFile instances are created)
        for file_name, file_obj in self._job_files(files_dir):
            new_files.add((file_name, file_obj.id))
            if (file_name, file_obj.id) in old_files:
                continue
            files_to_create.append(PresetFile(preset_id=preset_job.id, name=file_name, file_id=file_obj.id))

        # Get preset job files that were deleted (or changed)
        files_to_delete = list(old_files[file_identifier] for file_identifier in set(old_files) - new_files)

        # If there are any changes in preset files, than update check_date and save new files
        if files_to_delete or files_to_create:
            changed = True
            preset_job.check_date = now()
            if files_to_delete:
                PresetFile.objects.filter(id__in=files_to_delete).delete()
            if files_to_create:
                PresetFile.objects.bulk_create(files_to_create)

        if changed:
            preset_job.save()

    def _job_files(self, job_directory):
        # Get specific preset files
        yield JOB_FILE, self.__save_file(os.path.join(self._presets_dir, job_directory, JOB_FILE))
        yield TASKS_FILE, self.__save_file(os.path.join(self._presets_dir, job_directory, TASKS_FILE))

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

    def __save_file(self, file_path):
        if not os.path.isfile(file_path):
            raise ValueError('File was not found: {}'.format(file_path))
        with open(file_path, mode='rb') as fp:
            serializer = JobFileSerializer(data={'file': File(fp, name=os.path.basename(file_path))})
            serializer.is_valid(raise_exception=True)
            instance = serializer.save()
        return instance
