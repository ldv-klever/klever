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
from datetime import datetime

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count, Case, When, IntegerField, F, BooleanField
from django.urls import reverse
from django.utils.text import format_lazy
from django.utils.translation import ugettext_lazy as _
from django.utils.timezone import pytz
from django.utils.functional import cached_property

from bridge.vars import (
    JOB_STATUS, USER_ROLES, JOB_ROLES, JOB_WEIGHT, SAFE_VERDICTS, UNSAFE_VERDICTS, ASSOCIATION_TYPE, SUBJOB_NAME
)
from bridge.utils import BridgeException, file_get_or_create

from users.models import User
from jobs.models import Job, JobHistory, FileSystem, UserRole, JobFile
from reports.models import ReportComponent, ReportSafe, ReportUnsafe, ReportUnknown, ReportAttr
from marks.models import MarkSafeReport, MarkSafeTag, MarkUnsafeReport, MarkUnsafeTag, MarkUnknownReport

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
    'format': _('Format'),
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


def get_job_parents(user, job):
    parent_set = []
    next_parent = job.parent
    while next_parent is not None:
        parent_set.append(next_parent)
        next_parent = next_parent.parent
    parent_set.reverse()
    parents = []
    for parent in parent_set:
        if JobAccess(user, parent).can_view():
            job_id = parent.pk
        else:
            job_id = None
        parents.append({'pk': job_id, 'name': parent.name})
    return parents


def get_job_children(user, job):
    children = []
    for child in job.children.order_by('name'):
        if JobAccess(user, child).can_view():
            children.append({'pk': child.pk, 'name': child.name})
    return children


class JobAccess:
    def __init__(self, user, job=None):
        self.user = user
        self.job = job
        self._is_author = (self.job is not None and self.job.author == user)
        self._is_manager = (self.user.role == USER_ROLES[2][0])
        self._is_expert = (self.user.role == USER_ROLES[3][0])
        self._is_service = (self.user.role == USER_ROLES[4][0])

    @cached_property
    def _job_role(self):
        if self.job is None:
            return None
        last_version = self.job.versions.get(version=self.job.version)
        last_v_role = last_version.userrole_set.filter(user=self.user).first()
        return last_v_role.role if last_v_role else last_version.global_role

    @cached_property
    def _is_operator(self):
        if self.job is None:
            return False
        try:
            return self.user == self.job.reportroot.user
        except ObjectDoesNotExist:
            pass
        return False

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

    def klever_core_access(self):
        return self.job is not None and (self._is_manager or self._is_service)

    def can_decide(self):
        return self._is_finished and (self._is_manager or self._is_author or
                                      self._job_role in {JOB_ROLES[3][0], JOB_ROLES[4][0]})

    def can_upload_reports(self):
        return self.can_decide()

    def can_view(self):
        if self.job is None:
            return False
        return self._is_manager or self._is_author or self._is_expert or self._job_role != JOB_ROLES[0][0]

    def can_create(self):
        return self.user.role not in {USER_ROLES[0][0], USER_ROLES[4][0]}

    def can_edit(self):
        return self._is_finished and (self._is_author or self._is_manager)

    def can_stop(self):
        return self.job is not None and self.job.status in {JOB_STATUS[1][0], JOB_STATUS[2][0]} \
               and (self._is_operator or self._is_manager)

    def can_download(self):
        return self._is_finished and self.can_view()

    def can_delete(self):
        if self.job is None:
            return False
        for job in self.job.get_descendants(include_self=True):
            is_finished = job.status not in {JOB_STATUS[1][0], JOB_STATUS[2][0], JOB_STATUS[6][0]}
            if not is_finished or not self._is_manager and job.author != self.user:
                return False
        return True

    def can_collapse(self):
        return self._is_finished and (self._is_author or self._is_manager) \
               and self.job.weight == JOB_WEIGHT[0][0] \
               and ReportComponent.objects.filter(component=SUBJOB_NAME).count() == 0

    def can_clear_verifications(self):
        queryset = ReportComponent.objects\
            .filter(root=self.job.reportroot, verification=True).exclude(verifier_input='')
        return self._is_finished and (self._is_author or self._is_manager) and queryset.count()

    def can_dfc(self):
        return self.job is not None and self.job.status not in {
            JOB_STATUS[0][0], JOB_STATUS[1][0], JOB_STATUS[2][0], JOB_STATUS[6][0]
        }


def get_job_by_identifier(identifier):
    found_jobs = Job.objects.filter(identifier__startswith=identifier)
    if len(found_jobs) == 0:
        raise BridgeException(_('The job with specified identifier was not found'))
    elif len(found_jobs) > 1:
        raise BridgeException(_('Several jobs match the specified identifier, '
                              'please increase the length of the job identifier'))
    return found_jobs[0]


class FileData:
    def __init__(self, job):
        self.filedata = []
        self.__get_filedata(job)
        self.__order_by_lvl()

    def __get_filedata(self, job):
        for f in job.filesystem_set\
                .annotate(is_file=Case(When(file=None, then=0), default=1, output_field=IntegerField()))\
                .order_by('is_file', 'name').select_related('file'):
            self.filedata.append({
                'id': f.pk,
                'title': f.name,
                'parent': f.parent_id,
                'type': f.is_file,
                'hash_sum': f.file.hash_sum if f.is_file else None
            })

    def __order_by_lvl(self):
        ordered_data = []
        first_lvl = []
        other_data = []
        for fd in self.filedata:
            if fd['parent'] is None:
                first_lvl.append(fd)
            else:
                other_data.append(fd)

        def __get_all_children(file_info):
            children = []
            if file_info['type'] == 1:
                return children
            for fi in other_data:
                if fi['parent'] == file_info['id']:
                    children.append(fi)
                    children.extend(__get_all_children(fi))
            return children

        for fd in first_lvl:
            ordered_data.append(fd)
            ordered_data.extend(__get_all_children(fd))
        self.filedata = ordered_data


class SaveFileData:
    def __init__(self, filedata, job):
        self.filedata = filedata
        self.job = job
        self.filedata_by_lvl = []
        self.__check_data()
        self._files = self.__get_files()
        self.__save_file_data()

    def __save_file_data(self):
        saved_files = {}
        for lvl in self.filedata_by_lvl:
            for lvl_elem in lvl:
                fs_elem = FileSystem(job=self.job)
                if lvl_elem['parent']:
                    fs_elem.parent = saved_files[lvl_elem['parent']]
                if lvl_elem['type'] == '1':
                    if lvl_elem['hash_sum'] not in self._files:
                        raise ValueError('The file was not uploaded before')
                    fs_elem.file = self._files[lvl_elem['hash_sum']]
                if not all(ord(c) < 128 for c in lvl_elem['title']):
                    t_size = len(lvl_elem['title'])
                    if t_size > 30:
                        lvl_elem['title'] = lvl_elem['title'][(t_size - 30):]
                fs_elem.name = lvl_elem['title']
                fs_elem.save()
                saved_files[lvl_elem['id']] = fs_elem
        return None

    def __check_data(self):
        num_of_elements = 0
        element_of_lvl = []
        cnt = 0
        while num_of_elements < len(self.filedata):
            cnt += 1
            if cnt > 1000:
                raise ValueError('The file is too deep, maybe there is a loop in the files tree')
            num_of_elements += len(element_of_lvl)
            element_of_lvl = self.__get_lower_level(element_of_lvl)
            if len(element_of_lvl):
                self.filedata_by_lvl.append(element_of_lvl)
        for lvl in self.filedata_by_lvl:
            names_with_parents = set()
            for fd in lvl:
                if len(fd['title']) == 0:
                    raise ValueError("The file/folder name can't be empty")
                if not all(ord(c) < 128 for c in fd['title']):
                    title_size = len(fd['title'])
                    if title_size > 30:
                        fd['title'] = fd['title'][(title_size - 30):]
                if fd['type'] == '1' and fd['hash_sum'] is None:
                    raise ValueError('The file was not uploaded before')
                if fd['parent'] is not None:
                    rel_path = "%s/%s" % (fd['parent'], fd['title'])
                else:
                    rel_path = fd['title']
                if rel_path in names_with_parents:
                    raise ValueError("The same names in one folder found")
                names_with_parents.add(rel_path)

    def __get_lower_level(self, data):
        if len(data) == 0:
            return list(fd for fd in self.filedata if fd['parent'] is None)
        parents = set(fd['id'] for fd in data)
        return list(fd for fd in self.filedata if fd['parent'] in parents)

    def __get_files(self):
        files_data = {}
        hash_sums = set(fd['hash_sum'] for fd in self.filedata if fd['hash_sum'] is not None)
        for f in JobFile.objects.filter(hash_sum__in=list(hash_sums)):
            files_data[f.hash_sum] = f
        return files_data


class ReplaceJobFile:
    def __init__(self, job_id, name, file):
        try:
            self._job = Job.objects.get(id=job_id)
        except ObjectDoesNotExist:
            raise BridgeException(_('The job was not found'))

        self._file_to_replace = self.__get_file(name)
        self.__replace_file(file)

    def __get_file(self, name):
        path = name.split('/')

        filetree = {}
        for fs in FileSystem.objects.filter(job__job=self._job, job__version=self._job.version):
            filetree[fs.id] = {'parent': fs.parent_id, 'name': fs.name, 'file': fs.file}

        for f_id in filetree:
            if filetree[f_id]['name'] == path[-1]:
                parent = filetree[f_id]['parent']
                parents_branch = list(reversed(path))[1:]
                if len(parents_branch) > 0:
                    for n in parents_branch:
                        if parent is not None and filetree[parent]['name'] == n:
                            parent = filetree[parent]['parent']
                        else:
                            break
                    else:
                        return f_id
                else:
                    return f_id
        raise ValueError("The file wasn't found")

    def __replace_file(self, fp):
        if self._file_to_replace is None:
            raise ValueError("The file wasn't found")

        fp.seek(0)
        db_file = file_get_or_create(fp, fp.name, JobFile, True)
        fs = FileSystem.objects.get(id=self._file_to_replace)
        fs.file = db_file
        fs.save()


def create_version(job, kwargs):
    new_version = JobHistory(
        job=job, version=job.version,
        change_author=job.change_author, change_date=job.change_date,
        comment=kwargs.get('comment', ''), description=kwargs.get('description', '')
    )
    if 'global_role' in kwargs and kwargs['global_role'] in set(x[0] for x in JOB_ROLES):
        new_version.global_role = kwargs['global_role']
    new_version.save()
    if 'user_roles' in kwargs:
        user_roles = dict((int(ur['user']), ur['role']) for ur in kwargs['user_roles'])
        user_roles_to_create = []
        for u in User.objects.filter(id__in=list(user_roles)).only('id'):
            user_roles_to_create.append(UserRole(job=new_version, user=u, role=user_roles[u.id]))
        if len(user_roles_to_create) > 0:
            UserRole.objects.bulk_create(user_roles_to_create)
    return new_version


class JobVersionsData:
    def __init__(self, job, user):
        self._job = job
        self._user = user
        self.first_version = None
        self.last_version = None
        self.versions = self.__get_versions()

    def __get_versions(self):
        versions = []
        for j in self._job.versions.order_by('-version'):
            if self.first_version is None:
                self.first_version = j
            if j.version == self._job.version:
                self.last_version = j

            title = j.change_date.astimezone(pytz.timezone(self._user.timezone)).strftime("%d.%m.%Y %H:%M:%S")
            if j.change_author:
                title += ' ({0})'.format(j.change_author.get_full_name())
            if j.comment:
                title += ': %s' % j.comment
            versions.append({'version': j.version, 'title': title})
        return versions


def delete_versions(job, versions):
    versions = list(int(v) for v in versions)
    if any(v in {1, job.version} for v in versions):
        raise BridgeException(_("You don't have an access to remove one of the selected version"))
    checked_versions = job.versions.filter(version__in=versions)
    checked_versions.delete()


def check_new_parent(job, parent):
    if job.parent == parent:
        return True
    while parent is not None:
        if parent == job:
            return False
        parent = parent.parent
    return True


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
                      .filesystem_set.order_by('name').values_list('name', 'file__hash_sum'))
        files2 = dict(self.j2.versions.order_by('-version').first()
                      .filesystem_set.order_by('name').values_list('name', 'file__hash_sum'))

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


class GetJobDecisionResults:
    no_mark = 'Without marks'
    total = 'Total'

    def __init__(self, job):
        self.job = job
        try:
            self.start_date = self.job.decision.start_date
            self.finish_date = self.job.decision.finish_date
        except ObjectDoesNotExist:
            raise BridgeException('The job was not solved')
        try:
            self._report = ReportComponent.objects.get(root__job=self.job, parent=None)
        except ObjectDoesNotExist:
            raise BridgeException('The job was not solved')

        self.verdicts = self.__get_verdicts()
        self.resources = self.__get_resources()

        self.safes = self.__get_safes()
        self.unsafes = self.__get_unsafes()
        self.unknowns = self.__get_unknowns()

    def __get_verdicts(self):
        data = {'safes': {}, 'unsafes': {}, 'unknowns': {}}

        # Obtaining safes information
        total_safes = 0
        confirmed_safes = 0
        for verdict, total, confirmed in ReportSafe.objects.filter(root=self._report.root).values('verdict')\
                .annotate(total=Count('id'), confirmed=Count(Case(When(has_confirmed=True, then=1))))\
                .values_list('verdict', 'total', 'confirmed'):
            data['safes'][verdict] = [confirmed, total]
            confirmed_safes += confirmed
            total_safes += total
        data['safes']['total'] = [confirmed_safes, total_safes]

        # Obtaining unsafes information
        total_unsafes = 0
        confirmed_unsafes = 0
        for verdict, total, confirmed in ReportUnsafe.objects.filter(root=self._report.root).values('verdict')\
                .annotate(total=Count('id'), confirmed=Count(Case(When(has_confirmed=True, then=1))))\
                .values_list('verdict', 'total', 'confirmed'):
            data['unsafes'][verdict] = [confirmed, total]
            confirmed_unsafes += confirmed
            total_unsafes += total
        data['unsafes']['total'] = [confirmed_unsafes, total_unsafes]

        # Marked/Unmarked unknowns
        unconfirmed = Case(When(markreport_set__type=ASSOCIATION_TYPE[2][0], then=True),
                           default=False, output_field=BooleanField())
        queryset = ReportUnknown.objects.filter(root=self._report.root)\
            .values('component_id', 'markreport_set__problem_id')\
            .annotate(number=Count('id', distinct=True), unconfirmed=unconfirmed)\
            .values_list('component__name', 'markreport_set__problem__name', 'number', 'unconfirmed')
        for c_name, p_name, number, unconfirmed in queryset:
            if p_name is None or unconfirmed:
                p_name = self.no_mark
            if c_name not in data['unknowns']:
                data['unknowns'][c_name] = {}
            if p_name not in data['unknowns'][c_name]:
                data['unknowns'][c_name][p_name] = 0
            data['unknowns'][c_name][p_name] += number

        # Total unknowns for each component
        for component, number in ReportUnknown.objects.filter(root=self._report.root) \
                .values('component_id').annotate(number=Count('id')).values_list('component__name', 'number'):
            if component not in data['unknowns']:
                data['unknowns'][component] = {}
            data['unknowns'][component][self.total] = number
        return data

    def __get_resources(self):
        res_total = self._report.resources_cache.filter(component=None).first()
        if res_total is None:
            return None
        return {'CPU time': res_total.cpu_time, 'memory': res_total.memory}

    def __get_safes(self):
        marks = {}
        reports = {}

        for mr in MarkSafeReport.objects.filter(report__root=self.job.reportroot).select_related('mark'):
            if mr.report_id not in reports:
                reports[mr.report_id] = {'attrs': [], 'marks': []}
            reports[mr.report_id]['marks'].append(mr.mark.identifier)
            if mr.mark.identifier not in marks:
                marks[mr.mark.identifier] = {
                    'verdict': mr.mark.verdict, 'status': mr.mark.status,
                    'description': mr.mark.description, 'tags': []
                }

        for s_id, in ReportSafe.objects.filter(root=self.job.reportroot, verdict=SAFE_VERDICTS[4][0]).values_list('id'):
            reports[s_id] = {'attrs': [], 'marks': []}

        for r_id, aname, aval in ReportAttr.objects.filter(report_id__in=reports) \
                .order_by('attr__name__name').values_list('report_id', 'attr__name__name', 'attr__value'):
            reports[r_id]['attrs'].append([aname, aval])

        for identifier, tag in MarkSafeTag.objects\
                .filter(mark_version__mark__identifier__in=marks,
                        mark_version__version=F('mark_version__mark__version'))\
                .order_by('tag__tag').values_list('mark_version__mark__identifier', 'tag__tag'):
            marks[identifier]['tags'].append(tag)
        report_data = []
        for r_id in sorted(reports):
            report_data.append(reports[r_id])
        return {'reports': report_data, 'marks': marks}

    def __get_unsafes(self):
        marks = {}
        reports = {}

        for mr in MarkUnsafeReport.objects.filter(report__root=self.job.reportroot).select_related('mark'):
            if mr.report_id not in reports:
                reports[mr.report_id] = {'attrs': [], 'marks': {}}
            reports[mr.report_id]['marks'][mr.mark.identifier] = mr.result
            if mr.mark.identifier not in marks:
                marks[mr.mark.identifier] = {
                    'verdict': mr.mark.verdict, 'status': mr.mark.status,
                    'description': mr.mark.description, 'tags': []
                }

        for u_id, in ReportUnsafe.objects.filter(root=self.job.reportroot, verdict=UNSAFE_VERDICTS[5][0])\
                .values_list('id'):
            reports[u_id] = {'attrs': [], 'marks': {}}

        for r_id, aname, aval in ReportAttr.objects.filter(report_id__in=reports)\
                .order_by('attr__name__name').values_list('report_id', 'attr__name__name', 'attr__value'):
            reports[r_id]['attrs'].append([aname, aval])

        for identifier, tag in MarkUnsafeTag.objects\
                .filter(mark_version__mark__identifier__in=marks,
                        mark_version__version=F('mark_version__mark__version'))\
                .order_by('tag__tag').values_list('mark_version__mark__identifier', 'tag__tag'):
            marks[identifier]['tags'].append(tag)
        report_data = []
        for r_id in sorted(reports):
            report_data.append(reports[r_id])
        return {'reports': report_data, 'marks': marks}

    def __get_unknowns(self):
        marks = {}
        reports = {}

        for mr in MarkUnknownReport.objects.filter(report__root=self.job.reportroot)\
                .select_related('mark', 'mark__component'):
            if mr.report_id not in reports:
                reports[mr.report_id] = {'attrs': [], 'marks': []}
            reports[mr.report_id]['marks'].append(mr.mark.identifier)
            if mr.mark.identifier not in marks:
                marks[mr.mark.identifier] = {
                    'component': mr.mark.component.name, 'function': mr.mark.function, 'is_regexp': mr.mark.is_regexp,
                    'status': mr.mark.status, 'description': mr.mark.description
                }

        for f_id, in ReportUnknown.objects.filter(root=self.job.reportroot).exclude(id__in=reports).values_list('id'):
            reports[f_id] = {'attrs': [], 'marks': []}

        for r_id, aname, aval in ReportAttr.objects.filter(report_id__in=reports) \
                .order_by('attr__name__name').values_list('report_id', 'attr__name__name', 'attr__value'):
            reports[r_id]['attrs'].append([aname, aval])

        report_data = []
        for r_id in sorted(reports):
            report_data.append(reports[r_id])
        return {'reports': report_data, 'marks': marks}


class ReadJobFile:
    def __init__(self, hash_sum):
        try:
            self._file = JobFile.objects.get(hash_sum=hash_sum)
        except ObjectDoesNotExist:
            raise BridgeException(_('The file was not found'))

    def read(self):
        return self._file.file.read()

    def lines(self):
        return self._file.file.read().decode('utf8').split('\n')
