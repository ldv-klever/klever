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

import io
import os
from datetime import datetime

from django.db.models import F
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.text import format_lazy
from django.utils.translation import ugettext_lazy as _

from bridge.vars import JOB_STATUS, USER_ROLES, JOB_ROLES, JOB_WEIGHT, SUBJOB_NAME
from bridge.utils import file_get_or_create, BridgeException

from jobs.models import Job, JobHistory, JobFile, FileSystem, UserRole, RunHistory
from reports.models import ReportRoot, ReportComponent
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

# Dictionary of titles of static columns
TITLES = {
    'name': _('Title'),
    'author': _('Last change author'),
    'date': _('Last change date'),
    'status': _('Decision status'),

    'safe': _('Safes'),
    'safe:missed_bug': _('Missed target bugs'),
    'safe:incorrect': _('Incorrect proof'),
    'safe:unknown': _('Unknown'),
    'safe:inconclusive': _('Incompatible marks'),
    'safe:unassociated': _('Without marks'),
    'safe:total': _('Total'),

    'unsafe': _('Unsafes'),
    'unsafe:bug': _('Bugs'),
    'unsafe:target_bug': _('Target bugs'),
    'unsafe:false_positive': _('False positives'),
    'unsafe:unknown': _('Unknown'),
    'unsafe:inconclusive': _('Incompatible marks'),
    'unsafe:unassociated': _('Without marks'),
    'unsafe:total': _('Total'),

    'problem': _('Unknowns'),
    'problem:total': _('Total'),

    'resource': _('Consumed resources'),
    'resource:total': _('Total'),
    'tag': _('Tags'),
    'tag:safe': _('Safes'),
    'tag:unsafe': _('Unsafes'),
    'identifier': _('Identifier'),
    'version': _('Version'),
    'parent_id': format_lazy('{0}/{1}', _('Parent'), _('Identifier')),
    'role': _('Your role'),
    'priority': _('Priority'),
    'start_date': _('Decision start date'),
    'finish_date': _('Decision finish date'),
    'solution_wall_time': _('Decision wall time'),
    'operator': _('Operator'),

    'tasks': _('Verification tasks'),
    'tasks:pending': _('Pending'),
    'tasks:processing': _('Processing'),
    'tasks:finished': _('Finished'),
    'tasks:error': _('Error'),
    'tasks:cancelled': _('Cancelled'),
    'tasks:total': _('Total'),
    'tasks:solutions': _('Number of decisions'),
    'tasks:total_ts': _('Total to be solved'),
    'tasks:start_ts': _('Start solution date'),
    'tasks:finish_ts': _('Finish solution date'),
    'tasks:progress_ts': _('Solution progress'),
    'tasks:expected_time_ts': _('Expected solution time'),

    'subjobs': _('Subjobs'),
    'subjobs:total_sj': _('Total to be solved'),
    'subjobs:start_sj': _('Start solution date'),
    'subjobs:finish_sj': _('Finish solution date'),
    'subjobs:progress_sj': _('Solution progress'),
    'subjobs:expected_time_sj': _('Expected solution time'),
}


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


def get_unique_name(base_name):
    names_in_use = set(Job.objects.filter(name__startswith=base_name).values_list('name', flat=True))
    cnt = 1
    while True:
        new_name = "{} #{}".format(base_name, cnt)
        if new_name not in names_in_use:
            return new_name
        cnt += 1


class JobAccess:
    def __init__(self, user, job=None):
        self.user = user
        self.job = job
        self._is_author = (self.job is not None and self.job.author == user)
        self._is_manager = (self.user.role == USER_ROLES[2][0])
        self._is_expert = (self.user.role == USER_ROLES[3][0])
        self._is_service = (self.user.role == USER_ROLES[4][0])

    @cached_property
    def _root(self):
        if self.job is None:
            return False
        return ReportRoot.objects.filter(job=self.job).select_related('user').first()

    @cached_property
    def _job_role(self):
        if self.job is None:
            return None
        last_version = self.job.versions.get(version=self.job.version)
        last_v_role = last_version.userrole_set.filter(user=self.user).first()
        return last_v_role.role if last_v_role else last_version.global_role

    @cached_property
    def _is_operator(self):
        return self._root and self._root.user == self.user

    @cached_property
    def _is_finished(self):
        return self.job is not None and self.job.status not in {JOB_STATUS[1][0], JOB_STATUS[2][0], JOB_STATUS[6][0]}

    def can_view_jobs(self, queryset):
        """Filter queryset by view job access"""

        all_jobs_qs = queryset.values_list('id', flat=True)
        if self._is_manager or self._is_expert:
            return set(all_jobs_qs)

        author_of_qs = queryset.filter(author=self.user).values_list('pk', flat=True)
        with_custom_qs = UserRole.objects\
            .filter(user=self.user, job_version__version=F('job_version__job__version'))\
            .exclude(role=JOB_ROLES[0][0]).values_list('job_version__job_id', flat=True)
        no_global_qs = JobHistory.objects\
            .filter(version=F('job__version'), global_role=JOB_ROLES[0][0])\
            .values_list('job_id', flat=True)

        return set(all_jobs_qs) - (set(no_global_qs) - set(with_custom_qs) - set(author_of_qs))

    def can_download_jobs(self, queryset):
        """Check if all jobs in queryset can be downloaded"""
        unfinished_statues = {JOB_STATUS[1][0], JOB_STATUS[2][0], JOB_STATUS[6][0]}
        if any(job.status in unfinished_statues for job in queryset):
            return False
        jobs_ids = self.can_view_jobs(queryset)
        return len(jobs_ids) == len(queryset)

    @cached_property
    def can_decide(self):
        return self._is_finished and (self._is_manager or self._is_author or
                                      self._job_role in {JOB_ROLES[3][0], JOB_ROLES[4][0]})

    @cached_property
    def can_decide_last(self):
        return self.can_decide and RunHistory.objects.filter(job=self.job).exists()

    @cached_property
    def can_view(self):
        if self.job is None:
            return False
        return self._is_manager or self._is_author or self._is_expert or self._job_role != JOB_ROLES[0][0]

    @cached_property
    def can_create(self):
        return self.user.role not in {USER_ROLES[0][0], USER_ROLES[4][0]}

    @cached_property
    def can_edit(self):
        return self._is_finished and (self._is_author or self._is_manager)

    @cached_property
    def can_stop(self):
        return self.job is not None and self.job.status in {JOB_STATUS[1][0], JOB_STATUS[2][0]} \
               and (self._is_operator or self._is_manager)

    @cached_property
    def can_download(self):
        return self._is_finished and self.can_view

    @cached_property
    def can_delete(self):
        if self.job is None:
            return False
        for job in self.job.get_descendants(include_self=True):
            is_finished = job.status not in {JOB_STATUS[1][0], JOB_STATUS[2][0], JOB_STATUS[6][0]}
            if not is_finished or not self._is_manager and job.author != self.user:
                return False
        return True

    @cached_property
    def can_collapse(self):
        if not self._is_finished or not (self._is_author or self._is_manager):
            return False
        if self.job.weight != JOB_WEIGHT[0][0]:
            return False
        return not ReportComponent.objects.filter(root__job=self.job, component=SUBJOB_NAME).exists()

    @cached_property
    def _has_verifier_files(self):
        if not self._root:
            return False
        return ReportComponent.objects.filter(root=self._root, verification=True).exclude(verifier_files='').exists()

    @cached_property
    def can_clear_verifier_files(self):
        return self._is_finished and (self._is_author or self._is_manager) and self._has_verifier_files

    @cached_property
    def can_download_verifier_files(self):
        return self._is_finished and self._has_verifier_files


class JobDecisionData:
    def __init__(self, request, job):
        self._request = request
        self.job = job
        self._decision = self.__get_decision()

    @cached_property
    def status_color(self):
        if self.job.status == JOB_STATUS[0][0]:
            return 'grey'
        if self.job.status == JOB_STATUS[1][0]:
            return 'pink'
        if self.job.status == JOB_STATUS[2][0]:
            return 'purple'
        if self.job.status == JOB_STATUS[3][0]:
            return 'green'
        if self.job.status in {JOB_STATUS[4][0], JOB_STATUS[5][0], JOB_STATUS[8][0]}:
            return 'red'
        if self.job.status == JOB_STATUS[6][0]:
            return 'yellow'
        if self.job.status == JOB_STATUS[7][0]:
            return 'orange'
        return 'violet'

    @cached_property
    def progress(self):
        from service.serializers import ProgressSerializerRO

        if not self._decision:
            return None
        return ProgressSerializerRO(instance=self._decision, context={'request': self._request}).data

    @cached_property
    def core_link(self):
        if self.job.weight == JOB_WEIGHT[1][0]:
            return None
        core = ReportComponent.objects.filter(parent=None, root__job=self.job).only('id').first()
        if not core:
            return None
        return reverse('reports:component', args=[core.id])

    @cached_property
    def error(self):
        if not self._decision:
            return None
        return self._decision.error

    def __get_decision(self):
        return Decision.objects.filter(job=self.job).first()


class CompareFileSet:
    def __init__(self, job1, job2):
        self.j1 = job1
        self.j2 = job2
        self.data = {
            'same': [],
            'diff': [],
            'unmatched1': [],
            'unmatched2': []
        }
        self.__get_comparison()

    def __get_comparison(self):
        files1 = dict(self.j1.versions.order_by('-version').first()
                      .files.order_by('name').values_list('name', 'file__hash_sum'))
        files2 = dict(self.j2.versions.order_by('-version').first()
                      .files.order_by('name').values_list('name', 'file__hash_sum'))

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


class CompareJobVersions:
    def __init__(self, v1, v2):
        self.v1 = v1
        self.v2 = v2
        self.files_map = {}
        self.roles = self.__user_roles()
        self.paths, self.files = self.__compare_files()

    def __user_roles(self):
        set1 = set(uid for uid, in UserRole.objects.filter(job_version=self.v1).values_list('user_id'))
        set2 = set(uid for uid, in UserRole.objects.filter(job_version=self.v2).values_list('user_id'))
        if set1 != set2:
            return [
                UserRole.objects.filter(job_version=self.v1).order_by('user__last_name').select_related('user'),
                UserRole.objects.filter(job_version=self.v2).order_by('user__last_name').select_related('user')
            ]
        return None

    def __get_files(self, version):
        files = {}
        for f in FileSystem.objects.filter(job_version=version).select_related('file'):
            files[f.name] = {'hashsum': f.file.hash_sum, 'name': os.path.basename(f.name)}
        return files

    def __compare_files(self):
        files1 = self.__get_files(self.v1)
        files2 = self.__get_files(self.v2)
        changed_files = []
        changed_paths = []
        for fp1 in list(files1):
            if fp1 in files2:
                if files1[fp1]['hashsum'] != files2[fp1]['hashsum']:
                    # The file was changed
                    changed_files.append([is_readable(fp1), fp1, files1[fp1]['hashsum'], files2[fp1]['hashsum']])

                # Files are not changed deleted here too
                del files2[fp1]
            else:
                for fp2 in list(files2):
                    if files2[fp2]['hashsum'] == files1[fp1]['hashsum']:
                        # The file was moved
                        changed_paths.append([files1[fp1]['hashsum'], files2[fp2]['hashsum'], fp1, fp2])
                        del files2[fp2]
                        break
                else:
                    # The file was deleted
                    changed_paths.append([files1[fp1]['hashsum'], None, fp1, None])

        # files2 contains now only created files (or moved+changed at the same time)
        for fp2 in list(files2):
            changed_paths.append([None, files2[fp2]['hashsum'], None, fp2])
        return changed_paths, changed_files


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
        obj['children'].sort(key=lambda x: (x['type'] is 'file', x['text']))
        for child in obj['children']:
            self.__sort_children(child)

    def __get_children_data(self, obj_p, prefix=None):
        assert isinstance(obj_p, dict)
        if not obj_p['text']:
            raise BridgeException(_("The file/folder name can't be empty"))
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
