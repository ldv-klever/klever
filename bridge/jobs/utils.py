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
import json
import os
import re
from collections import OrderedDict
from datetime import datetime

from django.db.models import Q
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _

from bridge.vars import (
    DECISION_STATUS, USER_ROLES, JOB_ROLES, SUBJOB_NAME, DECISION_WEIGHT, SCHEDULER_TYPE, SCHEDULER_STATUS
)
from bridge.utils import file_get_or_create, logger, BridgeException

from users.models import User
from jobs.models import PRESET_JOB_TYPE, Job, JobFile, FileSystem, UserRole, PresetJob, Scheduler
from reports.models import ReportComponent
from service.models import Decision

# List of available types of 'safe' column class.
SAFES = [
    'missed_bug',
    'incorrect',
    'unknown',
    'inconclusive',
    'unassociated',
    'total'
]

# List of available types of 'unsafe' column class.
UNSAFES = [
    'bug',
    'target_bug',
    'false_positive',
    'unknown',
    'inconclusive',
    'unassociated',
    'total'
]


def months_choices():
    months = []
    for i in range(1, 13):
        months.append((i, datetime(2016, i, 1).strftime('%B')))
    return months


def years_choices():
    curr_year = datetime.now().year
    return list(range(curr_year - 3, curr_year + 1))


def is_readable(filename):
    ext = os.path.splitext(filename)[1]
    return len(ext) > 0 and ext[1:] in {'txt', 'json', 'xml', 'c', 'aspect', 'i', 'h', 'tmpl'}


def get_unique_job_name(preset_job: PresetJob):
    names_in_use = Job.objects.filter(preset=preset_job).values_list('name', flat=True)
    numbers = list(int(num) for j_name in names_in_use for num in re.findall(r'#(\d+)', j_name))
    if numbers:
        new_num = max(numbers) + 1
    else:
        new_num = 1
    return '#{}'.format(new_num)


def get_unique_decision_name(job: Job):
    names_in_use = Decision.objects.filter(job=job).values_list('title', flat=True)
    numbers = list(int(num) for j_name in names_in_use for num in re.findall(r'#(\d+)', j_name))
    if numbers:
        new_num = max(numbers) + 1
    else:
        new_num = 1
    return '#{}'.format(new_num)


def is_preset_changed(job):
    preset_job = job.preset.get_ancestors(ascending=True, include_self=True)\
        .filter(type=PRESET_JOB_TYPE[1][0]).only('check_date').first()
    if preset_job:
        return bool(preset_job.check_date > job.creation_date)
    # Something went wrong
    return True


def jobs_with_view_access(user: User, queryset):
    """Filter queryset by view job access"""
    if user.is_manager or user.is_expert:
        return set(queryset.values_list('id', flat=True))
    custom_access_ids = set(UserRole.objects.filter(user=user)
                            .exclude(role=JOB_ROLES[0][0]).values_list('job_id', flat=True))
    return set(queryset.filter(
        Q(author=user) | ~Q(global_role=JOB_ROLES[0][0]) | Q(id__in=custom_access_ids)
    ).values_list('id', flat=True))


def decisions_with_view_access(user: User, queryset):
    """Filter decisions queryset by view decision access"""
    queryset = queryset.exclude(status=DECISION_STATUS[0][0])
    if user.is_manager or user.is_expert:
        return set(queryset.values_list('id', flat=True))
    custom_access_ids = set(UserRole.objects.filter(user=user)
                            .exclude(role=JOB_ROLES[0][0]).values_list('job_id', flat=True))
    return set(queryset.filter(
        Q(job__author=user) | ~Q(job__global_role=JOB_ROLES[0][0]) | Q(job_id__in=custom_access_ids)
    ).values_list('id', flat=True))


def get_core_link(decision):
    if decision.weight == DECISION_WEIGHT[1][0]:
        return None
    core = ReportComponent.objects.filter(parent=None, decision=decision).only('identifier').first()
    if not core:
        return None
    return reverse('reports:component', args=[decision.identifier, core.identifier])


def get_roles_form_data(job=None):
    global_role = JOB_ROLES[0][0]

    users_qs = User.objects.exclude(role__in=[USER_ROLES[2][0], USER_ROLES[4][0]])\
        .order_by('first_name', 'last_name', 'username')
    available_users = OrderedDict((u.id, u.get_full_name()) for u in users_qs)

    user_roles = []
    if job:
        global_role = job.global_role
        # Exclude job author
        available_users.pop(job.author_id, None)
        for ur in UserRole.objects.filter(job=job):
            # Either user is manager, author or service of the job if he is not in all_users dict
            user_name = available_users.pop(ur.user_id, None)
            if user_name:
                user_roles.append({'user': ur.user_id, 'name': user_name, 'role': ur.role})
    return {
        'user_roles': user_roles, 'global_role': global_role,
        'available_users': list({'id': u_id, 'name': u_name} for u_id, u_name in available_users.items())
    }


def copy_files_with_replace(request, decision_id, files_qs):
    new_job_files = []
    files_to_replace = {}

    # Upload provided files first
    if request.data.get('files'):
        if isinstance(request.data['files'], str):
            try:
                files_map = json.loads(request.data['files'])
            except Exception as e:
                logger.error("Can't decode files data: {}".format(request.data['files']))
                raise BridgeException("Can't decode files data: {}".format(e))
        elif isinstance(request.data['files'], dict):
            files_map = request.data['files']
        else:
            raise BridgeException('Wrong files data: "{}" ({})'
                                  .format(request.data['files'], type(request.data['files'])))
        for fname, fkey in files_map.items():
            if fkey in request.FILES:
                files_to_replace[fname] = request.FILES[fkey]
                new_file = file_get_or_create(files_to_replace[fname], fname, JobFile)
                new_job_files.append(FileSystem(decision_id=decision_id, file_id=new_file.id, name=fname))

    # Copy other files
    for f_id, f_name in files_qs:
        if f_name in files_to_replace:
            continue
        new_job_files.append(FileSystem(decision_id=decision_id, file_id=f_id, name=f_name))
    FileSystem.objects.bulk_create(new_job_files)


def validate_scheduler(**kwargs):
    try:
        scheduler = Scheduler.objects.get(**kwargs)
    except Scheduler.DoesNotExist:
        raise BridgeException(_('The task scheduler was not found'))
    if scheduler.type == SCHEDULER_TYPE[1][0]:
        if scheduler.status == SCHEDULER_STATUS[2][0]:
            raise BridgeException(_('The VerifierCloud scheduler is disconnected'))
    else:
        try:
            klever_sch = Scheduler.objects.get(type=SCHEDULER_TYPE[0][0])
        except Scheduler.DoesNotExist:
            raise BridgeException(_("Schedulers weren't populated"))
        if klever_sch.status == SCHEDULER_STATUS[2][0]:
            raise BridgeException(_('The Klever scheduler is disconnected'))
    return scheduler


class JobAccess:
    def __init__(self, user, job: Job):
        self.user = user
        self.job = job
        self.is_author = (self.job.author == user)

    @cached_property
    def _job_role(self):
        if self.job is None:
            return None
        user_role_obj = UserRole.objects.filter(job=self.job, user=self.user).first()
        return user_role_obj.role if user_role_obj else self.job.global_role

    @cached_property
    def _is_finished(self):
        for decision in Decision.objects.filter(job=self.job).only('status'):
            if not decision.is_finished:
                # The job has unfinished decision
                return False
        return True

    @cached_property
    def is_operator(self):
        return self._job_role in {JOB_ROLES[3][0], JOB_ROLES[4][0]}

    @cached_property
    def can_decide(self):
        return self.user.is_manager or self.user.is_expert or self.is_author or self.is_operator

    @cached_property
    def can_view(self):
        return self.user.is_manager or self.user.is_expert or self.is_author or self._job_role != JOB_ROLES[0][0]

    @cached_property
    def can_edit(self):
        return self.is_author or self.user.is_manager

    @cached_property
    def can_download(self):
        return self.can_view and self._is_finished

    @cached_property
    def can_delete(self):
        return (self.user.is_manager or self.is_author) and self._is_finished


class DecisionAccess:
    def __init__(self, user, decision):
        self.user = user
        self.decision = decision
        self.job_access = JobAccess(user, job=decision.job if decision else None)

    @cached_property
    def can_view(self):
        # User can't view hidden decisions
        return self.job_access.can_view and self.decision.status != DECISION_STATUS[0][0]

    @cached_property
    def can_stop(self):
        return self.decision.status in {DECISION_STATUS[1][0], DECISION_STATUS[2][0]} and \
               (self.decision.operator == self.user or self.user.is_manager)

    @cached_property
    def can_copy(self):
        return self.job_access.can_decide

    @cached_property
    def can_restart(self):
        return (self.user.is_manager or self.job_access.is_author or self.job_access.is_operator) \
               and self.decision.is_finished

    @cached_property
    def can_download(self):
        return self.job_access.can_view and self.decision.is_finished

    @cached_property
    def can_delete(self):
        # Only job author and manager can remove the finished decision
        return (self.job_access.is_author or self.user.is_manager) and self.decision.is_finished

    @cached_property
    def can_rename(self):
        return self.decision.operator == self.user or self.user.is_manager

    @cached_property
    def can_collapse(self):
        if not self.decision.is_finished or self.decision.is_lightweight or \
                not (self.job_access.is_author or self.user.is_manager):
            return False
        return not ReportComponent.objects.filter(decision=self.decision, component=SUBJOB_NAME).exists()

    @cached_property
    def _has_verifier_files(self):
        return ReportComponent.objects.filter(decision=self.decision, verification=True)\
            .exclude(verifier_files='').exists()

    @cached_property
    def can_clear_verifier_files(self):
        return self.decision.is_finished and (self.job_access.is_author or self.user.is_manager) and \
               self._has_verifier_files

    @cached_property
    def can_download_verifier_files(self):
        return self.decision.is_finished and self.job_access.can_view and self._has_verifier_files


class DecisionProgressData:
    def __init__(self, request, decision):
        self._request = request
        self._decision = decision

    @cached_property
    def progress(self):
        from service.serializers import ProgressSerializerRO

        return ProgressSerializerRO(instance=self._decision, context={'request': self._request}).data

    @cached_property
    def core_link(self):
        if self._decision.weight == DECISION_WEIGHT[1][0]:
            return None
        core = ReportComponent.objects.filter(parent=None, decision=self._decision).only('identifier').first()
        if not core:
            return None
        return reverse('reports:component', args=[self._decision.identifier, core.identifier])


class CompareFileSet:
    def __init__(self, decision1, decision2):
        self.d1 = decision1
        self.d2 = decision2
        self.data = {
            'same': [],
            'diff': [],
            'unmatched1': [],
            'unmatched2': []
        }
        self.__get_comparison()

    def __get_comparison(self):
        files1 = dict(FileSystem.objects.filter(decision=self.d1)
                      .order_by('name').values_list('name', 'file__hash_sum'))
        files2 = dict(FileSystem.objects.filter(decision=self.d2)
                      .order_by('name').values_list('name', 'file__hash_sum'))

        for name, f1_hash in files1.items():
            readable = is_readable(name)
            file_type = 'unmatched1'
            href = None

            if name in files2:
                if f1_hash == files2[name]:
                    file_type = 'same'
                    if readable:
                        href = reverse('jobs:file-content', args=[f1_hash])
                else:
                    file_type = 'diff'
                    if readable:
                        href = reverse('jobs:files-diff', args=[f1_hash, files2[name]])
            elif readable:
                href = reverse('jobs:file-content', args=[f1_hash])

            self.data[file_type].append({'name': name, 'href': href})

        for f2_name in set(files2) - set(files1):
            self.data['unmatched2'].append({
                'name': f2_name,
                'href': reverse('jobs:file-content', args=[files2[f2_name]]) if is_readable(f2_name) else None
            })


class JSTreeConverter:
    file_sep = '/'

    def make_tree(self, files_list):
        """
        Creates tree of files from list for jstree visualization.
        :param files_list: list of pairs (<file path>, <file hash sum>)
        :return: tree of files
        """
        # Create tree
        files_tree = [{'type': 'root', 'text': 'Files', 'children': []}]
        for name, hash_sum in files_list:
            path = name.split(self.file_sep)
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

    def parse_tree(self, tree_data):
        """
        Converts tree of files to list of kwargs for saving FileSystem object
        :param tree_data: jstree object
        :return: list of objects {"file_id": <JobFile object id>, "name": <file path in job files tree>}
        """
        assert isinstance(tree_data, list) and len(tree_data) == 1
        files_list = self.__get_children_data(tree_data[0])

        # Get files ids and check that there is a file for each provided hash_sum
        hash_sums = set(fdata['hash_sum'] for fdata in files_list if 'hash_sum' in fdata)
        db_files = dict(JobFile.objects.filter(hash_sum__in=hash_sums).values_list('hash_sum', 'id'))
        if hash_sums - set(db_files):
            raise BridgeException(_('There are not uploaded files'))

        # Set file for each file data instead of hash_sum
        for file_data in files_list:
            if 'hash_sum' in file_data:
                file_data['file_id'] = db_files[file_data['hash_sum']]
                file_data.pop('hash_sum')
            else:
                file_data['file_id'] = self._empty_file

        return files_list

    @cached_property
    def _empty_file(self):
        db_file = file_get_or_create(io.BytesIO(), 'empty', JobFile, False)
        return db_file.id

    def __sort_children(self, obj):
        if not obj.get('children'):
            return
        obj['children'].sort(key=lambda x: (x['type'] == 'file', x['text']))
        for child in obj['children']:
            self.__sort_children(child)

    def __get_children_data(self, obj_p, prefix=None):
        assert isinstance(obj_p, dict)
        if not obj_p['text']:
            raise BridgeException(_("The file/directory name can't be empty"))
        files = []
        name = ((prefix + self.file_sep) if prefix else '') + obj_p['text']
        if obj_p['type'] == 'file':
            file_data = {'name': name}
            if 'data' in obj_p and 'hashsum' in obj_p['data']:
                file_data['hash_sum'] = obj_p['data']['hashsum']
            files.append(file_data)
        elif 'children' in obj_p:
            for child in obj_p['children']:
                files.extend(self.__get_children_data(child, prefix=(name if obj_p['type'] != 'root' else None)))
        return files
