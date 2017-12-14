#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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
from types import FunctionType

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.utils.translation import ungettext_lazy

from bridge.vars import SCHEDULER_TYPE, USER_ROLES, JOB_ROLES
from bridge.utils import file_get_or_create, unique_id, BridgeException

import marks.SafeUtils as SafeUtils
import marks.UnsafeUtils as UnsafeUtils
import marks.UnknownUtils as UnknownUtils

from users.models import Extended
from jobs.models import JobFile
from marks.models import MarkUnsafeCompare, MarkUnsafeConvert, ErrorTraceConvertionCache
from service.models import Scheduler

from jobs.utils import create_job
from marks.ConvertTrace import ConvertTrace
from marks.CompareTrace import CompareTrace, CONVERSION
from marks.tags import CreateTagsFromFile


JOB_SETTINGS_FILE = 'settings.json'


def extend_user(user, role=USER_ROLES[1][0]):
    try:
        user.extended.role = role
        user.extended.save()
    except ObjectDoesNotExist:
        Extended.objects.create(role=role, user=user)
        user.first_name = 'Firstname'
        user.last_name = 'Lastname'
        user.save()


class Population:
    def __init__(self, user=None, manager=None, service=None):
        self.changes = {'marks': {}}
        self.user = user
        if manager is None:
            self.manager = self.__get_manager(None, None)
            if service is not None:
                self.__add_service_user(service[0], service[1])
        else:
            self.manager = self.__get_manager(manager[0], manager[1])
            if service is not None and manager[0] != service[0]:
                self.__add_service_user(service[0], service[1])
        self.__population()

    def __population(self):
        if self.user is not None:
            try:
                Extended.objects.get(user=self.user)
            except ObjectDoesNotExist:
                extend_user(self.user)
        self.__populate_functions()
        self.__populate_jobs()
        self.__populate_unknown_marks()
        self.__populate_tags()
        self.__populate_unsafe_marks()
        if settings.ENABLE_SAFE_MARKS:
            self.__populate_safe_marks()
        sch_crtd1 = Scheduler.objects.get_or_create(type=SCHEDULER_TYPE[0][0])[1]
        sch_crtd2 = Scheduler.objects.get_or_create(type=SCHEDULER_TYPE[1][0])[1]
        self.changes['schedulers'] = (sch_crtd1 or sch_crtd2)

    def __populate_functions(self):
        conversions = {}
        for func_name in [x for x, y in ConvertTrace.__dict__.items()
                          if type(y) == FunctionType and not x.startswith('_')]:
            description = self.__correct_description(getattr(ConvertTrace, func_name).__doc__)
            func, crtd = MarkUnsafeConvert.objects.get_or_create(name=func_name)
            if crtd or description != func.description:
                self.changes['functions'] = True
                func.description = description
                func.save()
            conversions[func_name] = func
        MarkUnsafeConvert.objects.filter(~Q(name__in=list(conversions))).delete()

        comparisons = []
        for func_name in [x for x, y in CompareTrace.__dict__.items()
                          if type(y) == FunctionType and not x.startswith('_')]:
            comparisons.append(func_name)
            description = self.__correct_description(getattr(CompareTrace, func_name).__doc__)

            conversion = CONVERSION.get(func_name, func_name)
            if conversion not in conversions:
                raise BridgeException('Convert function "%s" for comparison "%s" does not exist' %
                                      (conversion, func_name))

            func, crtd = MarkUnsafeCompare.objects.get_or_create(name=func_name, convert=conversions[conversion])
            if crtd or description != func.description:
                self.changes['functions'] = True
                func.description = description
                func.save()
        MarkUnsafeCompare.objects.filter(~Q(name__in=comparisons)).delete()
        ErrorTraceConvertionCache.objects.all().delete()

    def __correct_description(self, descr):
        self.__is_not_used()
        descr_strs = descr.split('\n')
        new_descr_strs = []
        for s in descr_strs:
            if len(s) > 0 and len(s.split()) > 0:
                new_descr_strs.append(s)
        return '\n'.join(new_descr_strs)

    def __get_manager(self, manager_username, manager_password):
        if manager_username is None:
            try:
                return Extended.objects.filter(role=USER_ROLES[2][0])[0].user
            except IndexError:
                raise BridgeException('There are no managers in the system')
        try:
            manager = User.objects.get(username=manager_username)
        except ObjectDoesNotExist:
            manager = User.objects.create(username=manager_username, first_name='Firstname', last_name='Lastname')
            self.changes['manager'] = {
                'username': manager.username,
                'password': self.__add_password(manager, manager_password)
            }
        extend_user(manager, USER_ROLES[2][0])
        return manager

    def __add_service_user(self, service_username, service_password):
        if service_username is None:
            return
        try:
            extend_user(User.objects.get(username=service_username), USER_ROLES[4][0])
        except ObjectDoesNotExist:
            service = User.objects.create(username=service_username, first_name='Firstname', last_name='Lastname')
            extend_user(service, USER_ROLES[4][0])
            self.changes['service'] = {
                'username': service.username,
                'password': self.__add_password(service, service_password)
            }

    def __add_password(self, user, password):
        self.__is_not_used()
        if isinstance(password, str):
            password = password.strip()
        if not isinstance(password, str) or len(password) == 0:
            password = unique_id()[:8]
        user.set_password(password)
        user.save()
        return password

    def __populate_jobs(self):
        default_jobs_dir = os.path.join(settings.BASE_DIR, 'jobs', 'presets')
        for jobdir in [os.path.join(default_jobs_dir, x) for x in os.listdir(default_jobs_dir)]:
            if not os.path.exists(os.path.join(jobdir, JOB_SETTINGS_FILE)):
                raise BridgeException('There is default job without settings file (%s)' % jobdir)
            with open(os.path.join(jobdir, JOB_SETTINGS_FILE), encoding='utf8') as fp:
                try:
                    job_settings = json.load(fp)
                except Exception as e:
                    raise BridgeException('The default job settings file is wrong json: %s' % e)
            if any(x not in job_settings for x in ['name', 'description']):
                raise BridgeException(
                    'Default job settings must contain name and description. Job in "%s" has %s' % (
                        jobdir, str(list(job_settings))
                    )
                )
            if len(job_settings['name']) == 0:
                raise BridgeException('Default job name is required')
            job = create_job({
                'author': self.manager,
                'global_role': JOB_ROLES[1][0],
                'name': job_settings['name'],
                'description': job_settings['description'],
                'filedata': self.__get_filedata(jobdir)
            })
            if 'jobs' not in self.changes:
                self.changes['jobs'] = []
            self.changes['jobs'].append([job.name, job.identifier])

    def __get_filedata(self, d):
        self.cnt = 0
        self.dir_info = {d: None}

        def get_fdata(directory):
            fdata = []
            for f in [os.path.join(directory, x) for x in os.listdir(directory)]:
                parent_name, base_f = os.path.split(f)
                if base_f == JOB_SETTINGS_FILE:
                    continue
                self.cnt += 1
                if os.path.isfile(f):
                    with open(f, mode='rb') as fp:
                        check_sum = file_get_or_create(fp, base_f, JobFile, True)[1]
                    fdata.append({
                        'id': self.cnt,
                        'parent': self.dir_info[parent_name] if parent_name in self.dir_info else None,
                        'hash_sum': check_sum,
                        'title': base_f,
                        'type': '1'
                    })
                elif os.path.isdir(f):
                    self.dir_info[f] = self.cnt
                    fdata.append({
                        'id': self.cnt,
                        'parent': self.dir_info[parent_name] if parent_name in self.dir_info else None,
                        'hash_sum': None,
                        'title': base_f,
                        'type': '0'
                    })
                    fdata += get_fdata(f)
            return fdata
        return get_fdata(d)

    def __populate_unknown_marks(self):
        res = UnknownUtils.PopulateMarks(self.manager)
        if res.created > 0:
            self.changes['marks']['unknown'] = (res.created, res.total)

    def __populate_safe_marks(self):
        res = SafeUtils.PopulateMarks(self.manager)
        new_num = len(res.created)
        if new_num > 0:
            self.changes['marks']['safe'] = (new_num, res.total)

    def __populate_unsafe_marks(self):
        res = UnsafeUtils.PopulateMarks(self.manager)
        new_num = len(res.created)
        if new_num > 0:
            self.changes['marks']['unsafe'] = (new_num, res.total)

    def __populate_tags(self):
        self.changes['tags'] = []
        num_of_new = self.__create_tags('unsafe')
        if num_of_new > 0:
            self.changes['tags'].append(ungettext_lazy(
                '%(count)d new unsafe tag uploaded.', '%(count)d new unsafe tags uploaded.', num_of_new
            ) % {'count': num_of_new})
        num_of_new = self.__create_tags('safe')
        if num_of_new > 0:
            self.changes['tags'].append(ungettext_lazy(
                '%(count)d new safe tag uploaded.', '%(count)d new safe tags uploaded.', num_of_new
            ) % {'count': num_of_new})

    def __create_tags(self, tag_type):
        self.__is_not_used()
        preset_tags = os.path.join(settings.BASE_DIR, 'marks', 'tags_presets', "%s.json" % tag_type)
        if not os.path.isfile(preset_tags):
            return 0
        with open(preset_tags, mode='rb') as fp:
            try:
                res = CreateTagsFromFile(self.manager, fp, tag_type, True)
            except Exception as e:
                raise BridgeException("Error while creating tags: %s" % str(e))
            return res.number_of_created

    def __is_not_used(self):
        pass


# Example argument: {'username': 'myname', 'password': '12345', 'last_name': 'Mylastname', 'first_name': 'Myfirstname'}
# last_name and first_name are not required; username and password are required (for admin password is not required)z
# Returns None if everything is OK, str (error text) in other cases.
def populate_users(admin=None, manager=None, service=None):
    if admin is not None:
        if not isinstance(admin, dict):
            return 'Wrong administrator format'
        if 'username' not in admin or not isinstance(admin['username'], str):
            return 'Administator username is required'
        if 'last_name' not in admin:
            admin['last_name'] = 'Lastname'
        if 'first_name' not in manager:
            admin['first_name'] = 'Firstname'
        try:
            user = User.objects.get(username=admin['username'])
            user.first_name = admin['first_name']
            user.last_name = admin['last_name']
            user.save()
            Extended.objects.create(user=user, role=USER_ROLES[1][0])
        except ObjectDoesNotExist:
            return 'Administrator with specified username does not exist'
    if manager is not None:
        if not isinstance(manager, dict):
            return 'Wrong manager format'
        if 'password' not in manager or not isinstance(manager['password'], str):
            return 'Manager password is required'
        if 'username' not in manager or not isinstance(manager['username'], str):
            return 'Manager username is required'
        if 'last_name' not in manager:
            manager['last_name'] = 'Lastname'
        if 'first_name' not in manager:
            manager['first_name'] = 'Firstname'
        try:
            User.objects.get(username=manager['username'])
            return 'Manager with specified username already exists'
        except ObjectDoesNotExist:
            newuser = User(
                username=manager['username'], first_name=manager['first_name'], last_name=manager['last_name']
            )
            newuser.set_password(manager['password'])
            newuser.save()
            Extended.objects.create(user=newuser, role=USER_ROLES[2][0])
    if service is not None:
        if not isinstance(service, dict):
            return 'Wrong service format'
        if 'password' not in service or not isinstance(service['password'], str):
            return 'Service password is required'
        if 'username' not in service or not isinstance(service['username'], str):
            return 'Service username is required'
        if 'last_name' not in service:
            service['last_name'] = 'Lastname'
        if 'first_name' not in service:
            service['first_name'] = 'Firstname'
        try:
            User.objects.get(username=service['username'])
            return 'Service with specified username already exists'
        except ObjectDoesNotExist:
            newuser = User(
                username=service['username'], last_name=service['last_name'], first_name=service['first_name']
            )
            newuser.set_password(service['password'])
            newuser.save()
            Extended.objects.create(user=newuser, role=USER_ROLES[4][0])
    return None
