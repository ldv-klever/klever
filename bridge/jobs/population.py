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
import uuid

from django.conf import settings
from django.utils.functional import cached_property

from bridge.utils import logger, BridgeException, file_get_or_create
from bridge.vars import JOB_ROLES

from jobs.models import JobFile, Job
from jobs.serializers import CreateJobSerializer

JOB_SETTINGS_FILE = 'settings.json'


class JobsPopulation:
    def __init__(self, user=None):
        self._user = user

    @cached_property
    def jobs_dir(self):
        presets = os.path.join(settings.BASE_DIR, 'jobs', 'presets')
        if os.path.isdir(presets):
            return presets
        with open(presets, mode='r', encoding='utf-8') as fp:
            presets_path = fp.read()
        return os.path.abspath(os.path.join(settings.BASE_DIR, 'jobs', presets_path))

    @cached_property
    def common_files(self):
        # Directory "specifications" and files "program fragmentation.json" and "verifier profiles.json"
        # should be added for all preset jobs.
        return [
            self.__get_dir(os.path.join(self.jobs_dir, 'specifications'), 'specifications'),
            self.__get_dir(os.path.join(self.jobs_dir, 'fragmentation sets'), 'fragmentation sets'),
            self.__get_file(os.path.join(self.jobs_dir, 'verifier profiles.json'), 'verifier profiles.json')
        ]

    def populate(self):
        created_jobs = 0
        for dirpath, dirnames, filenames in os.walk(self.jobs_dir):
            # Do not traverse within specific directories. Directory "specifications" should be placed within the root
            # preset jobs directory, directory "staging" can be placed anywhere.
            if os.path.basename(dirpath) == 'specifications' or os.path.basename(dirpath) == 'staging':
                dirnames[:] = []
                filenames[:] = []
                continue

            # Directories without preset job settings file serve to keep ones with that file and specific ones.
            job_settings_file = os.path.join(dirpath, JOB_SETTINGS_FILE)
            if not os.path.exists(job_settings_file):
                continue

            # Do not traverse within directories with preset job settings file.
            dirnames[:] = []

            data = self.__get_settings_data(job_settings_file)

            if settings.POPULATE_JUST_PRODUCTION_PRESETS and not data['production']:
                # Do not populate non-production jobs
                continue

            data.update({
                'global_role': JOB_ROLES[1][0], 'parent': None,
                'files': [{
                    'type': 'root', 'text': 'Root',
                    'children': self.common_files + self.__get_children(dirpath)
                }]
            })
            serializer = CreateJobSerializer(data=data, context={'author': self._user})
            if not serializer.is_valid(raise_exception=True):
                logger.error(serializer.errors)
                raise BridgeException('Job data validation failed')
            serializer.save()

            created_jobs += 1
        return created_jobs

    def __get_settings_data(self, filepath):
        data = {}

        # Parse settings
        with open(filepath, encoding='utf8') as fp:
            try:
                job_settings = json.load(fp)
            except Exception as e:
                logger.exception(e)
                raise BridgeException('Settings file is not valid JSON file')

        # Get unique name
        name = job_settings.get('name')
        if not isinstance(name, str) or len(name) == 0:
            raise BridgeException('Preset job name is required')
        job_name = name
        cnt = 1
        while True:
            try:
                Job.objects.get(name=job_name)
            except Job.DoesNotExist:
                break
            cnt += 1
            job_name = "%s #%s" % (name, cnt)
        data['name'] = job_name

        # Get description if specified
        description = job_settings.get('description')
        if isinstance(description, str):
            data['description'] = description

        # Get identifier if it is specified
        if 'identifier' in job_settings:
            try:
                data['identifier'] = uuid.UUID(job_settings['identifier'])
            except Exception as e:
                logger.exception(e)
                raise BridgeException('Job identifier has wrong format, uuid expected')

        # Is the job for production only?
        data['production'] = job_settings.get('production', False)
        return data

    def __get_file(self, path, fname):
        with open(path, mode='rb') as fp:
            db_file = file_get_or_create(fp, fname, JobFile, True)
        return {'type': 'file', 'text': fname, 'data': {'hashsum': db_file.hash_sum}}

    def __get_dir(self, path, fname):
        return {'type': 'folder', 'text': fname, 'children': self.__get_children(path)}

    def __get_children(self, root):
        children = []
        for fname in os.listdir(root):
            if fname == JOB_SETTINGS_FILE:
                continue
            path = os.path.join(root, fname)
            if os.path.isfile(path):
                children.append(self.__get_file(path, fname))
            elif os.path.isdir(path):
                children.append(self.__get_dir(path, fname))
        return children
