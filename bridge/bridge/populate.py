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
import re
import json
from types import FunctionType

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.db import transaction
from django.db.models import Q
from django.utils.translation import override, ungettext_lazy, ugettext_lazy as _
from django.utils.timezone import now

from bridge.vars import JOB_CLASSES, SCHEDULER_TYPE, USER_ROLES, JOB_ROLES, MARK_STATUS, MARK_TYPE, SAFE_VERDICTS
from bridge.settings import DEFAULT_LANGUAGE, BASE_DIR
from bridge.utils import file_get_or_create, unique_id, BridgeException

from users.models import Extended
from jobs.utils import create_job
from jobs.models import Job, JobFile
from reports.models import TaskStatistic
from marks.ConvertTrace import ConvertTrace
from marks.CompareTrace import CompareTrace
from marks.models import MarkUnknown, MarkUnknownHistory, Component, MarkUnsafeCompare, MarkUnsafeConvert,\
    ErrorTraceConvertionCache, MarkSafeTag, MarkSafeHistory, MarkSafeAttr, MarkSafe
from marks.utils import ConnectMarkWithReports
from marks.tags import CreateTagsFromFile
from reports.models import AttrName, Attr
from service.models import Scheduler

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


class Population(object):
    def __init__(self, user=None, manager=None, service=None):
        self.changes = {}
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
        TaskStatistic.objects.get_or_create()
        if self.user is not None:
            try:
                Extended.objects.get(user=self.user)
            except ObjectDoesNotExist:
                extend_user(self.user)
        self.__populate_functions()
        if len(Job.objects.filter(parent=None)) < len(JOB_CLASSES):
            self.__populate_jobs()
        self.__populate_default_jobs()
        self.__populate_unknown_marks()
        self.__populate_tags()
        sch_crtd1 = Scheduler.objects.get_or_create(type=SCHEDULER_TYPE[0][0])[1]
        sch_crtd2 = Scheduler.objects.get_or_create(type=SCHEDULER_TYPE[1][0])[1]
        self.changes['schedulers'] = (sch_crtd1 or sch_crtd2)

    def __populate_functions(self):
        func_names = []
        for func_name in [x for x, y in ConvertTrace.__dict__.items()
                          if type(y) == FunctionType and not x.startswith('_')]:
            func_names.append(func_name)
            description = self.__correct_description(getattr(ConvertTrace, func_name).__doc__)
            func, crtd = MarkUnsafeConvert.objects.get_or_create(name=func_name)
            if crtd or description != func.description:
                self.changes['functions'] = True
                func.description = description
                func.save()
        MarkUnsafeConvert.objects.filter(~Q(name__in=func_names)).delete()
        func_names = []
        for func_name in [x for x, y in CompareTrace.__dict__.items()
                          if type(y) == FunctionType and not x.startswith('_')]:
            func_names.append(func_name)
            description = self.__correct_description(getattr(CompareTrace, func_name).__doc__)
            func, crtd = MarkUnsafeCompare.objects.get_or_create(name=func_name)
            if crtd or description != func.description:
                self.changes['functions'] = True
                func.description = description
                func.save()
        MarkUnsafeCompare.objects.filter(~Q(name__in=func_names)).delete()
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
        args = {
            'author': self.manager,
            'global_role': JOB_ROLES[1][0],
        }
        for i in range(len(JOB_CLASSES)):
            try:
                Job.objects.get(type=JOB_CLASSES[i][0], parent=None)
            except ObjectDoesNotExist:
                with override(DEFAULT_LANGUAGE):
                    args['name'] = JOB_CLASSES[i][1]
                    args['description'] = "<h3>%s</h3>" % JOB_CLASSES[i][1]
                    args['type'] = JOB_CLASSES[i][0]
                    create_job(args)
                    self.changes['jobs'] = True

    def __populate_default_jobs(self):
        default_jobs_dir = os.path.join(BASE_DIR, 'jobs', 'presets')
        for jobdir in [os.path.join(default_jobs_dir, x) for x in os.listdir(default_jobs_dir)]:
            if not os.path.exists(os.path.join(jobdir, JOB_SETTINGS_FILE)):
                raise BridgeException('There is default job without settings file (%s)' % jobdir)
            with open(os.path.join(jobdir, JOB_SETTINGS_FILE), encoding='utf8') as fp:
                try:
                    job_settings = json.load(fp)
                except Exception as e:
                    raise BridgeException('The default job settings file is wrong json: %s' % e)
            if any(x not in job_settings for x in ['name', 'class', 'description']):
                raise BridgeException(
                    'Default job settings must contain name, class and description. Job in "%s" has %s' % (
                        jobdir, str(list(job_settings))
                    )
                )
            if job_settings['class'] not in list(x[0] for x in JOB_CLASSES):
                raise BridgeException(
                    'Default job class is wrong: %s. See bridge.vars.JOB_CLASSES for choice.' % job_settings['class']
                )
            if len(job_settings['name']) == 0:
                raise BridgeException('Default job name is required')
            try:
                parent = Job.objects.get(parent=None, type=job_settings['class'])
            except ObjectDoesNotExist:
                raise BridgeException(
                    "Main jobs were not created (can't find main job with class %s)" % job_settings['class']
                )
            job = create_job({
                'author': self.manager,
                'global_role': '1',
                'name': job_settings['name'],
                'description': job_settings['description'],
                'parent': parent,
                'filedata': self.__get_filedata(jobdir)
            })
            if 'default_jobs' not in self.changes:
                self.changes['default_jobs'] = []
            self.changes['default_jobs'].append([job.name, job.identifier])

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
        presets_dir = os.path.join(BASE_DIR, 'marks', 'presets', 'unknowns')
        for component_dir in [os.path.join(presets_dir, x) for x in os.listdir(presets_dir)]:
            component = os.path.basename(component_dir)
            if not 0 < len(component) <= 15:
                raise ValueError('Wrong component length: "%s". 1-15 is allowed.' % component)
            for mark_settings in [os.path.join(component_dir, x) for x in os.listdir(component_dir)]:
                data = None
                with open(mark_settings, encoding='utf8') as fp:
                    try:
                        data = json.load(fp)
                    except Exception as e:
                        fp.seek(0)
                        try:
                            path_to_json = os.path.abspath(os.path.join(component_dir, fp.read()))
                            with open(path_to_json, encoding='utf8') as fp2:
                                data = json.load(fp2)
                        except Exception:
                            raise BridgeException("Can't parse json data of unknown mark: %s (\"%s\")" % (
                                e, os.path.relpath(mark_settings, presets_dir)
                            ))
                if not isinstance(data, dict) or any(x not in data for x in ['function', 'pattern']):
                    raise BridgeException('Wrong unknown mark data format: %s' % mark_settings)
                try:
                    re.compile(data['function'])
                except re.error:
                    raise ValueError('Wrong regular expression: "%s"' % data['function'])
                if 'link' not in data:
                    data['link'] = ''
                if 'description' not in data:
                    data['description'] = ''
                if 'status' not in data:
                    data['status'] = MARK_STATUS[0][0]
                if 'is_modifiable' not in data:
                    data['is_modifiable'] = True
                if data['status'] not in list(x[0] for x in MARK_STATUS) or len(data['function']) == 0 \
                        or not 0 < len(data['pattern']) <= 15 or not isinstance(data['is_modifiable'], bool):
                    raise BridgeException('Wrong unknown mark data: %s' % mark_settings)
                try:
                    MarkUnknown.objects.get(component__name=component, problem_pattern=data['pattern'])
                except ObjectDoesNotExist:
                    mark = MarkUnknown.objects.create(
                        identifier=unique_id(), component=Component.objects.get_or_create(name=component)[0],
                        author=self.manager, status=data['status'], is_modifiable=data['is_modifiable'],
                        function=data['function'], problem_pattern=data['pattern'], description=data['description'],
                        type=MARK_TYPE[1][0], link=data['link'] if len(data['link']) > 0 else None
                    )
                    MarkUnknownHistory.objects.create(
                        mark=mark, version=mark.version, author=mark.author, status=mark.status,
                        function=mark.function, problem_pattern=mark.problem_pattern, link=mark.link,
                        change_date=mark.change_date, description=mark.description, comment=''
                    )
                    ConnectMarkWithReports(mark)
                    self.changes['marks'] = True
                except MultipleObjectsReturned:
                    raise Exception('There are similar unknown marks in the system')

    def __populate_safe_marks(self):
        pass

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
        self.ccc = 0
        preset_tags = os.path.join(BASE_DIR, 'marks', 'tags_presets', "%s.json" % tag_type)
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


def populate_safe_marks():
    from marks.models import MarkSafe
    manager = User.objects.filter(extended__role=USER_ROLES[2][0]).first()
    if not manager:
        return
    MarkSafe.objects.filter(versions=None).delete()
    res = PopulateSafeMarks(manager)
    print('Number of created safe marks: %s/%s' % (len(res.created), res.total))


class PopulateSafeMarks:
    def __init__(self, manager):
        self.total = 0
        self._author = manager
        self._dbtags = {}
        self._tagnames = {}
        self._marktags = {}
        self._markattrs = {}
        self.__current_tags()
        self._marks = self.__get_data()
        self.__get_attrnames()
        self.__get_attrs()
        self.created = self.__create_marks()
        self.__create_related()
        self.__connect_new_marks()

    def __current_tags(self):
        from marks.models import SafeTag
        for t_id, parent_id, t_name in SafeTag.objects.values_list('id', 'parent_id', 'tag'):
            self._dbtags[t_id] = parent_id
            self._tagnames[t_name] = t_id

    def __get_tags(self, tags_data):
        tags = set()
        for t in tags_data:
            if t not in self._tagnames:
                raise BridgeException(_('Corrupted preset safe mark: not enough tags in the system'))
            t_id = self._tagnames[t]
            tags.add(t_id)
            while self._dbtags[t_id] is not None:
                t_id = self._dbtags[t_id]
                tags.add(t_id)
        return tags

    def __get_attrnames(self):
        attrnames = {}
        for a in AttrName.objects.all():
            attrnames[a.name] = a.id
        for mid in self._markattrs:
            for a in self._markattrs[mid]:
                if a['attr'] in attrnames:
                    a['attr'] = attrnames[a['attr']]
                else:
                    a['attr'] = AttrName.objects.create(name=a['attr']).id

    def __get_attrs(self):
        attrs_in_db = {}
        for a in Attr.objects.all():
            attrs_in_db[(a.name_id, a.value)] = a.id
        attrs_to_create = []
        for mid in self._markattrs:
            for a in self._markattrs[mid]:
                if (a['attr'], a['value']) not in attrs_in_db:
                    attrs_to_create.append(Attr(name_id=a['attr'], value=a['value']))
        if len(attrs_to_create) > 0:
            Attr.objects.bulk_create(attrs_to_create)
            self.__get_attrs()
        else:
            for mid in self._markattrs:
                for a in self._markattrs[mid]:
                    a['attr'] = attrs_in_db[(a['attr'], a['value'])]
                    del a['value']

    def __create_marks(self):
        marks_in_db = {}
        for ma in MarkSafeAttr.objects.values('mark_id', 'attr_id', 'is_compare'):
            if ma['mark_id'] not in marks_in_db:
                marks_in_db[ma['mark_id']] = set()
            marks_in_db[ma['mark_id']].add((ma['attr_id'], ma['is_compare']))
        marks_to_create = []
        for mark in self._marks:
            attr_set = set((a['attr'], a['is_compare']) for a in self._markattrs[mark.identifier])
            if any(attr_set == marks_in_db[x] for x in marks_in_db):
                del self._markattrs[mark.identifier]
                del self._marktags[mark.identifier]
                continue
            marks_to_create.append(mark)
        MarkSafe.objects.bulk_create(marks_to_create)

        created_marks = {}
        marks_versions = []
        for mark in MarkSafe.objects.filter(versions=None):
            created_marks[mark.identifier] = mark
            marks_versions.append(MarkSafeHistory(
                mark=mark, verdict=mark.verdict, status=mark.status, description=mark.description,
                version=mark.version, author=mark.author, change_date=now(), comment=''
            ))
        MarkSafeHistory.objects.bulk_create(marks_versions)
        return created_marks

    def __create_related(self):
        versions = {}
        for mh in MarkSafeHistory.objects.filter(mark__in=self.created.values()).select_related('mark'):
            versions[mh.mark.identifier] = mh.id

        new_tags = []
        for mid in self._marktags:
            for tid in self._marktags[mid]:
                new_tags.append(MarkSafeTag(tag_id=tid, mark_version_id=versions[mid]))
        MarkSafeTag.objects.bulk_create(new_tags)
        new_attrs = []
        for mid in self._markattrs:
            for a in self._markattrs[mid]:
                new_attrs.append(MarkSafeAttr(mark_id=versions[mid], attr_id=a['attr'], is_compare=a['is_compare']))
        MarkSafeAttr.objects.bulk_create(new_attrs)

    def __connect_new_marks(self):
        # TODO: optimisations
        for mark in self.created.values():
            ConnectMarkWithReports(mark)

    def __get_data(self):
        presets_dir = os.path.join(BASE_DIR, 'marks', 'presets', 'safes')
        new_marks = []
        for mark_settings in [os.path.join(presets_dir, x) for x in os.listdir(presets_dir)]:
            with open(mark_settings, encoding='utf8') as fp:
                data = json.load(fp)
            if not isinstance(data, dict):
                raise BridgeException(_('Corrupted preset safe mark: wrong format'))
            if any(x not in data for x in ['status', 'verdict', 'is_modifiable', 'description', 'attrs', 'tags']):
                raise BridgeException(_('Corrupted preset safe mark: not enough data'))
            if not isinstance(data['attrs'], list) or not isinstance(data['tags'], list):
                raise BridgeException(_('Corrupted preset safe mark: attributes or tags is ot a list'))
            if any(not isinstance(x, dict) for x in data['attrs']):
                raise BridgeException(_('Corrupted preset safe mark: one of attributes has wrong format'))
            if any(x not in y for x in ['attr', 'value', 'is_compare'] for y in data['attrs']):
                raise BridgeException(_('Corrupted preset safe mark: one of attributes does not have enough data'))
            if data['status'] not in list(x[0] for x in MARK_STATUS):
                raise BridgeException(_('Corrupted preset safe mark: wrong mark status'))
            if data['verdict'] not in list(x[0] for x in SAFE_VERDICTS):
                raise BridgeException(_('Corrupted preset safe mark: wrong mark verdict'))
            if not isinstance(data['description'], str):
                raise BridgeException(_('Corrupted preset safe mark: wrong description'))
            if not isinstance(data['is_modifiable'], bool):
                raise BridgeException(_('Corrupted preset safe mark: is_modifiable must be bool'))
            identifier = unique_id()
            new_marks.append(MarkSafe(
                identifier=identifier, author=self._author, verdict=data['verdict'], status=data['status'],
                is_modifiable=data['is_modifiable'], description=data['description'], type=MARK_TYPE[1][0]
            ))
            self._marktags[identifier] = self.__get_tags(data['tags'])
            self._markattrs[identifier] = data['attrs']
            self.total += 1
        return new_marks
