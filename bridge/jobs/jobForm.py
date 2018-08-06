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

import json
import hashlib
from io import BytesIO

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.utils.timezone import pytz, now
from django.utils.translation import ugettext_lazy as _

from bridge.vars import JOB_ROLES, USER_ROLES, JOB_WEIGHT
from bridge.utils import BridgeException, file_get_or_create

from users.models import User
from jobs.models import Job, JobHistory, FileSystem, JobFile, UserRole

from jobs.utils import get_job_by_identifier, JobAccess


def role_info(job, user):
    roles_data = {'global': (job.global_role, job.get_global_role_display())}

    users = []
    user_roles_data = []
    users_roles = job.userrole_set.all().order_by('user__last_name')
    job_author = job.job.versions.get(version=1).change_author

    for ur in users_roles:
        u_id = ur.user_id
        if u_id == user.id:
            user_roles_data.append({
                'user': {'name': _('Your role for the job')},
                'role': {'val': ur.role, 'title': ur.get_role_display()}
            })
        else:
            user_roles_data.append({
                'user': {'id': u_id, 'name': ur.user.get_full_name()},
                'role': {'val': ur.role, 'title': ur.get_role_display()}
            })
        users.append(u_id)

    roles_data['user_roles'] = user_roles_data

    available_users = []
    for u in User.objects.filter(~Q(pk__in=users) & ~Q(pk=user.pk)).order_by('last_name'):
        if u != job_author:
            available_users.append({'id': u.pk, 'name': u.get_full_name()})
    roles_data['available_users'] = available_users
    return roles_data


class UserRolesForm:
    def __init__(self, user, job_version):
        self._user = user
        self._version = job_version

    def __user_roles(self):
        roles_data = {
            'user_roles': [], 'available_users': [],
            'global': (self._version.global_role, self._version.get_global_role_display()),
        }

        # Only author and manager can edit the job, so they can't change the role for each other
        users = [self._user.id, self._version.job.versions.order_by('version').first().change_author.id]

        for ur in self._version.userrole_set.exclude(user_id__in=users).order_by('user__last_name'):
            roles_data['user_roles'].append({
                'user': {'id': ur.user_id, 'name': ur.user.get_full_name()},
                'role': {'val': ur.role, 'title': ur.get_role_display()}
            })
            users.append(ur.user_id)

        for u in User.objects.exclude(id__in=users).order_by('last_name'):
            roles_data['available_users'].append({'id': u.id, 'name': u.get_full_name()})

        return roles_data

    def get_context(self):
        return {'job_roles': JOB_ROLES, 'roles': self.__user_roles()}

    def save(self, data):
        user_roles = dict((int(ur['user']), ur['role']) for ur in json.loads(data))
        user_roles_to_create = []
        for u in User.objects.filter(id__in=user_roles).only('id'):
            if user_roles[u.id] not in set(x[0] for x in JOB_ROLES):
                raise BridgeException()
            user_roles_to_create.append(UserRole(job=self._version, user=u, role=user_roles[u.id]))
        if len(user_roles_to_create) > 0:
            UserRole.objects.bulk_create(user_roles_to_create)


class JobForm:
    def __init__(self, user, job, action):
        self._user = user
        self._job = job
        self._copy = (action == 'copy')

    def get_context(self):
        data = {
            'job_id': self._job.id, 'name': self._job.name, 'parent': '',
            'description': self.job_version().description,
            'copy': self._copy, 'versions': []
        }

        # Get list of versions
        for j_version in self._job.versions.order_by('-version'):
            if self._job.version == j_version.version:
                title = _("Current version")
            else:
                job_time = j_version.change_date.astimezone(pytz.timezone(self._user.extended.timezone))
                title = '%s (%s): %s' % (
                    job_time.strftime("%d.%m.%Y %H:%M:%S"),
                    j_version.change_author.get_full_name(), j_version.comment)
            data['versions'].append({'version': j_version.version, 'title': title})

        if self._copy:
            data['parent'] = self._job.identifier
        else:
            if self._job.parent:
                data['parent'] = self._job.parent.identifier
        return data

    def job_version(self):
        return self._job.versions.get(version=self._job.version)

    def __is_parent_valid(self, parent):
        if self._copy:
            return True
        if self._job.parent == parent:
            return True
        while parent is not None:
            if parent.id == self._job.id:
                return False
            parent = parent.parent
        return True

    def __get_parent(self, identifier):
        parent = None
        if len(identifier) > 0:
            parent = get_job_by_identifier(identifier)
            if not self.__is_parent_valid(parent):
                raise BridgeException(_("The specified parent can't be set for this job"))
        elif self._user.extended.role != USER_ROLES[2][0]:
            raise BridgeException(_("The parent identifier is required for this job"))
        return parent

    def __check_name(self, name):
        if len(name) == 0:
            raise BridgeException(_('The job name is required'))
        try:
            job = Job.objects.get(name=name)
        except ObjectDoesNotExist:
            return name
        if not self._copy and job.id == self._job.id:
            return name
        raise BridgeException(_('The job name is already used'))

    def __create_version(self, data):
        new_version = JobHistory(
            job=self._job, version=self._job.version, change_author=self._user,
            comment=data.get('comment', ''), description=data.get('description', '')
        )
        if 'global_role' in data and data['global_role'] in set(x[0] for x in JOB_ROLES):
            new_version.global_role = data['global_role']
        new_version.save()

        if 'user_roles' in data:
            try:
                UserRolesForm(self._user, new_version).save(data['user_roles'])
            except Exception:
                new_version.delete()
                raise
        if 'file_data' in data:
            try:
                UploadFilesTree(new_version, data['file_data'])
            except Exception:
                new_version.delete()
                raise
        return new_version

    def __create_job(self, data):
        if 'identifier' in data and data['identifier'] is not None:
            if Job.objects.filter(identifier=data['identifier']).count() > 0:
                raise BridgeException(_('The job with specified identifier already exists'))
            identifier = data['identifier']
        else:
            identifier = hashlib.md5(now().strftime("%Y%m%d%H%M%S%f%z").encode('utf-8')).hexdigest()

        self._job = Job(
            identifier=identifier, name=self.__check_name(data.get('name', '')), change_date=now(),
            parent=self.__get_parent(data.get('parent', '')), safe_marks=settings.ENABLE_SAFE_MARKS
        )
        if 'weight' in data and data['weight'] in list(x[0] for x in JOB_WEIGHT):
            self._job.weight = data['weight']
        if 'safe marks' in data and isinstance(data['safe marks'], bool):
            self._job.safe_marks = data['safe marks']
        self._job.save()

        try:
            new_version = self.__create_version(data)
        except Exception:
            self._job.delete()
            raise
        self._job.change_author = new_version.change_author
        self._job.change_date = new_version.change_date
        self._job.save()

    def __update_job(self, data):
        if self._job.version != int(data.get('last_version', 0)):
            raise BridgeException(_("Your version is expired, please reload the page"))

        self._job.parent = self.__get_parent(data.get('parent', ''))
        self._job.name = self.__check_name(data.get('name', ''))
        self._job.version += 1

        new_version = self.__create_version(data)
        self._job.change_author = new_version.change_author
        self._job.change_date = new_version.change_date
        self._job.save()

    def save(self, data):
        if self._copy:
            if not JobAccess(self._user).can_create():
                raise BridgeException(_("You don't have an access to create new jobs"))
            self.__create_job(data)
        else:
            if not JobAccess(self._user, self._job).can_edit():
                raise BridgeException(_("You don't have an access to edit this job"))
            self.__update_job(data)
        return self._job


class LoadFilesTree:
    def __init__(self, job_id, version, opened=True):
        self._opened = opened
        self._tree = self.__files_tree(job_id, version)

    def __files_tree(self, job_id, version):
        self.__is_not_used()
        data = {}
        for fs in FileSystem.objects.filter(job__job_id=job_id, job__version=version):
            data[fs.id] = {
                'parent': fs.parent_id, 'name': fs.name,
                'f_id': fs.file_id, 'file': fs.file.hash_sum if fs.file else None
            }
        return data

    def __get_children(self, parent_id):
        children = []
        for n_id in self._tree:
            if self._tree[n_id]['parent'] == parent_id:
                children.append((
                    (self._tree[n_id]['file'] is not None, self._tree[n_id]['name']),
                    self.__get_node(n_id))
                )
        return list(x[1] for x in sorted(children))

    def __get_node(self, n_id):
        node = {'text': self._tree[n_id]['name'], 'type': 'folder'}
        if self._tree[n_id]['f_id']:
            node['data'] = {'hashsum': self._tree[n_id]['file']}
            node['id'] = '{0}__{1}'.format(n_id, self._tree[n_id]['f_id'])
            node['type'] = 'file'
        else:
            node['id'] = 'dir_{0}'.format(n_id)
            children = self.__get_children(n_id)
            if len(children) > 0:
                node['children'] = children
        return node

    def as_json(self):
        return {
            'state': {'opened': self._opened}, 'type': 'root',
            'text': 'Files', "children": self.__get_children(None)
        }

    def __is_not_used(self):
        pass


class UploadFilesTree:
    def __init__(self, job_version, tree_data):
        self._job_version = job_version
        self._tree = json.loads(tree_data)
        self._empty = None
        self._files = self.__get_files()
        self.__save_children(None, self._tree[0].get('children', []))

    def __get_children_files(self, children):
        hashsums = set()
        for data in children:
            if len(data['text']) == 0:
                raise ValueError("The file/folder name can't be empty")
            if data['type'] == 'file' and 'data' in data and 'hashsum' in data['data']:
                hashsums.add(data['data']['hashsum'])
            elif 'children' in data:
                hashsums |= self.__get_children_files(data['children'])
        return hashsums

    def __get_files(self):
        files = {}
        for f in JobFile.objects.filter(hash_sum__in=self.__get_children_files(self._tree)):
            files[f.hash_sum] = f.id
        return files

    def __save_fs_obj(self, parent_id, name, file_id):
        return FileSystem.objects.create(job=self._job_version, parent_id=parent_id, name=name, file_id=file_id).id

    def __save_children(self, parent_id, children):
        for child in children:
            file_id = None
            if child['type'] == 'file':
                if 'data' not in child or 'hashsum' not in child['data']:
                    if self._empty is None:
                        self._empty = file_get_or_create(BytesIO(), child['text'], JobFile, False)[0]
                    file_id = self._empty.id
                elif child['data']['hashsum'] in self._files:
                    file_id = self._files[child['data']['hashsum']]
                else:
                    raise ValueError('The file with hashsum %s was not uploaded before' % child['data']['hashsum'])
            new_id = self.__save_fs_obj(parent_id, child['text'], file_id)
            if child['type'] == 'folder':
                self.__save_children(new_id, child['children'])
