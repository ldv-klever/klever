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
import hashlib

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q, Case, When, IntegerField
from django.template import Template, Context
from django.utils.translation import ugettext_lazy as _, string_concat
from django.utils.timezone import now

from bridge.vars import JOB_STATUS, KLEVER_CORE_PARALLELISM, KLEVER_CORE_FORMATTERS,\
    USER_ROLES, JOB_ROLES, SCHEDULER_TYPE, PRIORITY, START_JOB_DEFAULT_MODES, SCHEDULER_STATUS, JOB_WEIGHT
from bridge.utils import logger, BridgeException
from users.notifications import Notify

from jobs.models import Job, JobHistory, FileSystem, UserRole, JobFile
from reports.models import CompareJobsInfo, ReportComponent
from service.models import SchedulerUser, Scheduler


READABLE = {'txt', 'json', 'xml', 'c', 'aspect', 'i', 'h', 'tmpl'}

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
    'parent_id': string_concat(_('Parent'), '/', _('Identifier')),
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


class JobAccess(object):

    def __init__(self, user, job=None):
        self.user = user
        self.job = job
        self.__is_author = False
        self.__job_role = None
        self.__user_role = user.extended.role
        self.__is_manager = (self.__user_role == USER_ROLES[2][0])
        self.__is_expert = (self.__user_role == USER_ROLES[3][0])
        self.__is_service = (self.__user_role == USER_ROLES[4][0])
        self.__is_operator = False
        try:
            if self.job is not None:
                self.__is_operator = (user == self.job.reportroot.user)
        except ObjectDoesNotExist:
            pass
        self.__get_prop(user)

    def klever_core_access(self):
        if self.job is None:
            return False
        return self.__is_manager or self.__is_service

    def can_decide(self):
        if self.job is None or self.job.status in [JOB_STATUS[1][0], JOB_STATUS[2][0]]:
            return False
        return self.__is_manager or self.__is_author or self.__job_role in [JOB_ROLES[3][0], JOB_ROLES[4][0]]

    def can_upload_reports(self):
        if self.job is None or self.job.status in [JOB_STATUS[1][0], JOB_STATUS[2][0]]:
            return False
        return self.__is_manager or self.__is_author or self.__job_role in [JOB_ROLES[3][0], JOB_ROLES[4][0]]

    def can_view(self):
        if self.job is None:
            return False
        return self.__is_manager or self.__is_author or self.__job_role != JOB_ROLES[0][0] or self.__is_expert

    def can_create(self):
        return self.__user_role not in [USER_ROLES[0][0], USER_ROLES[4][0]]

    def can_edit(self):
        if self.job is None:
            return False
        return self.job.status not in [JOB_STATUS[1][0], JOB_STATUS[2][0]] and (self.__is_author or self.__is_manager)

    def can_stop(self):
        if self.job is None:
            return False
        if self.job.status in [JOB_STATUS[1][0], JOB_STATUS[2][0]] and (self.__is_operator or self.__is_manager):
            return True
        return False

    def can_delete(self):
        if self.job is None:
            return False
        for ch in self.job.children.all():
            if not JobAccess(self.user, ch).can_delete():
                return False
        if self.__is_manager and self.job.status == JOB_STATUS[3]:
            return True
        if self.job.status in [JOB_STATUS[1][0], JOB_STATUS[2][0]]:
            return False
        return self.__is_author or self.__is_manager

    def can_download(self):
        return self.job is not None and self.job.status != JOB_STATUS[2][0]

    def can_collapse(self):
        if self.job is None:
            return False
        return self.job.status not in {JOB_STATUS[1][0], JOB_STATUS[2][0]} \
            and (self.__is_author or self.__is_manager) and self.job.weight == JOB_WEIGHT[0][0]

    def can_clear_verifications(self):
        if self.job is None or self.job.status in {JOB_STATUS[1][0], JOB_STATUS[2][0]}:
            return False
        if not (self.__is_author or self.__is_manager):
            return False
        try:
            return ReportComponent.objects.filter(root=self.job.reportroot, verification=True)\
                .exclude(verifier_input='').count() > 0
        except ObjectDoesNotExist:
            return False

    def can_dfc(self):
        return self.job is not None and self.job.status not in [JOB_STATUS[0][0], JOB_STATUS[1][0]]

    def __get_prop(self, user):
        if self.job is not None:
            try:
                first_version = self.job.versions.get(version=1)
                last_version = self.job.versions.get(version=self.job.version)
            except ObjectDoesNotExist:
                return
            self.__is_author = (first_version.change_author == user)
            last_v_role = last_version.userrole_set.filter(user=user)
            if len(last_v_role) > 0:
                self.__job_role = last_v_role[0].role
            else:
                self.__job_role = last_version.global_role


class FileData(object):

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
                'hash_sum': f.file.hash_sum if f.file is not None else None
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


class SaveFileData(object):

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


def convert_time(val, acc):
    def final_value(time, postfix):
        fpart_len = len(str(round(time)))
        if fpart_len > int(acc):
            tmp_div = 10**(fpart_len - int(acc))
            rounded_value = round(time/tmp_div) * tmp_div
        elif fpart_len == int(acc):
            rounded_value = round(time)
        else:
            rounded_value = round(time, int(acc) - fpart_len)
        return Template('{% load l10n %}{{ val }} {{ postfix }}').render(Context({
            'val': rounded_value, 'postfix': postfix
        }))

    new_time = int(val)
    try_div = new_time / 1000
    if try_div < 1:
        return final_value(new_time, _('ms'))
    new_time = try_div
    try_div = new_time / 60
    if try_div < 1:
        return final_value(new_time, _('s'))
    new_time = try_div
    try_div = new_time / 60
    if try_div < 1:
        return final_value(new_time, _('min'))
    return final_value(try_div, _('h'))


def convert_memory(val, acc):
    def final_value(memory, postfix):
        fpart_len = len(str(round(memory)))
        if fpart_len > int(acc):
            tmp_div = 10 ** (fpart_len - int(acc))
            rounded_value = round(memory / tmp_div) * tmp_div
        elif fpart_len == int(acc):
            rounded_value = round(memory)
        else:
            rounded_value = round(memory, int(acc) - fpart_len)
        return Template('{% load l10n %}{{ val }} {{ postfix }}').render(Context({
            'val': rounded_value, 'postfix': postfix
        }))

    new_mem = int(val)
    try_div = new_mem / 10**3
    if try_div < 1:
        return final_value(new_mem, _('B'))
    new_mem = try_div
    try_div = new_mem / 10**3
    if try_div < 1:
        return final_value(new_mem, _('KB'))
    new_mem = try_div
    try_div = new_mem / 10**3
    if try_div < 1:
        return final_value(new_mem, _('MB'))
    return final_value(try_div, _('GB'))


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


def create_version(job, kwargs):
    new_version = JobHistory(
        job=job, parent=job.parent, version=job.version, name=job.name,
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


def create_job(kwargs):
    if 'name' not in kwargs or len(kwargs['name']) == 0:
        logger.error('The job name was not got')
        raise BridgeException()
    if 'author' not in kwargs or not isinstance(kwargs['author'], User):
        logger.error('The job author was not got')
        raise BridgeException()
    newjob = Job(name=kwargs['name'], change_author=kwargs['author'], parent=kwargs.get('parent'))

    if 'identifier' in kwargs and kwargs['identifier'] is not None:
        newjob.identifier = kwargs['identifier']
    else:
        time_encoded = now().strftime("%Y%m%d%H%M%S%f%z").encode('utf-8')
        newjob.identifier = hashlib.md5(time_encoded).hexdigest()
    newjob.safe_marks = bool(kwargs.get('safe_marks', settings.ENABLE_SAFE_MARKS))
    newjob.save()

    new_version = create_version(newjob, kwargs)

    if 'filedata' in kwargs:
        try:
            SaveFileData(kwargs['filedata'], new_version)
        except Exception as e:
            logger.exception(e)
            newjob.delete()
            raise BridgeException()
    if 'absolute_url' in kwargs:
        # newjob_url = reverse('jobs:job', args=[newjob.pk])
        # Notify(newjob, 0, {'absurl': kwargs['absolute_url'] + newjob_url})
        pass
    else:
        # Notify(newjob, 0)
        pass
    return newjob


def update_job(kwargs):
    if 'job' not in kwargs or not isinstance(kwargs['job'], Job):
        raise ValueError('The job is required')
    if 'author' not in kwargs or not isinstance(kwargs['author'], User):
        raise ValueError('Change author is required')
    if 'comment' in kwargs:
        if len(kwargs['comment']) == 0:
            raise ValueError('Change comment is required')
    else:
        kwargs['comment'] = ''
    if 'parent' in kwargs:
        kwargs['job'].parent = kwargs['parent']
    if 'name' in kwargs and len(kwargs['name']) > 0:
        kwargs['job'].name = kwargs['name']
    kwargs['job'].change_author = kwargs['author']
    kwargs['job'].version += 1
    kwargs['job'].save()

    newversion = create_version(kwargs['job'], kwargs)

    if 'filedata' in kwargs:
        try:
            SaveFileData(kwargs['filedata'], newversion)
        except Exception as e:
            newversion.delete()
            kwargs['job'].version -= 1
            kwargs['job'].save()
            raise e
    if 'absolute_url' in kwargs:
        try:
            Notify(kwargs['job'], 1, {'absurl': kwargs['absolute_url']})
        except Exception as e:
            logger.exception("Can't notify users: %s" % e)
    else:
        try:
            Notify(kwargs['job'], 1)
        except Exception as e:
            logger.exception("Can't notify users: %s" % e)


def remove_jobs_by_id(user, job_ids):
    job_struct = {}
    all_jobs = {}
    for j in Job.objects.only('id', 'parent_id'):
        if j.parent_id not in job_struct:
            job_struct[j.parent_id] = set()
        job_struct[j.parent_id].add(j.id)
        all_jobs[j.id] = j

    def remove_job_with_children(j_id):
        j_id = int(j_id)
        if j_id not in all_jobs:
            return
        if j_id in job_struct:
            for ch_id in job_struct[j_id]:
                remove_job_with_children(ch_id)
            del job_struct[j_id]
        if not JobAccess(user, all_jobs[j_id]).can_delete():
            raise BridgeException(_("You don't have an access to delete one of the children"))
        try:
            Notify(all_jobs[j_id], 2)
        except Exception as e:
            logger.exception("Can't notify users: %s" % e)
        all_jobs[j_id].delete()
        del all_jobs[j_id]

    for job_id in job_ids:
        remove_job_with_children(job_id)


def delete_versions(job, versions):
    access_versions = []
    for v in versions:
        v = int(v)
        if v != 1 and v != job.version:
            access_versions.append(v)
    checked_versions = job.versions.filter(version__in=access_versions)
    num_of_deleted = len(checked_versions)
    checked_versions.delete()
    return num_of_deleted


def check_new_parent(job, parent):
    if job.parent == parent:
        return True
    while parent is not None:
        if parent == job:
            return False
        parent = parent.parent
    return True


def get_resource_data(data_format, accuracy, resource):
    if data_format == 'hum':
        wall = convert_time(resource.wall_time, accuracy)
        cpu = convert_time(resource.cpu_time, accuracy)
        mem = convert_memory(resource.memory, accuracy)
    else:
        wall = "%s %s" % (resource.wall_time, _('ms'))
        cpu = "%s %s" % (resource.cpu_time, _('ms'))
        mem = "%s %s" % (resource.memory, _('B'))
    return [wall, cpu, mem]


def get_user_time(user, milliseconds):
    if user.extended.data_format == 'hum':
        converted = convert_time(int(milliseconds), user.extended.accuracy)
    else:
        converted = "%s %s" % (int(milliseconds), _('ms'))
    return converted


def get_user_memory(user, bytes_val):
    if user.extended.data_format == 'hum':
        converted = convert_memory(int(bytes_val), user.extended.accuracy)
    else:
        converted = "%s %s" % (int(bytes_val), _('B'))
    return converted


class CompareFileSet(object):
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

        def get_files(job):
            files = []
            last_v = job.versions.order_by('-version').first()
            files_data = {}
            for f in last_v.filesystem_set.only('parent_id', 'name'):
                files_data[f.pk] = (f.parent_id, f.name)
            for f in last_v.filesystem_set.exclude(file=None).select_related('file')\
                    .only('name', 'parent_id', 'file__hash_sum'):
                f_name = f.name
                parent = f.parent_id
                while parent is not None:
                    f_name = files_data[parent][1] + '/' + f_name
                    parent = files_data[parent][0]
                files.append([f_name, f.file.hash_sum])
            return files

        files1 = get_files(self.j1)
        files2 = get_files(self.j2)
        for f1 in files1:
            if f1[0] not in list(x[0] for x in files2):
                ext = os.path.splitext(f1[0])[1]
                if len(ext) > 0 and ext[1:] in READABLE:
                    self.data['unmatched1'].insert(0, [f1[0], f1[1]])
                else:
                    self.data['unmatched1'].append([f1[0]])
            else:
                for f2 in files2:
                    if f2[0] == f1[0]:
                        ext = os.path.splitext(f1[0])[1]
                        if f2[1] == f1[1]:
                            if len(ext) > 0 and ext[1:] in READABLE:
                                self.data['same'].insert(0, [f1[0], f1[1]])
                            else:
                                self.data['same'].append([f1[0]])
                        else:
                            if len(ext) > 0 and ext[1:] in READABLE:
                                self.data['diff'].insert(0, [f1[0], f1[1], f2[1]])
                            else:
                                self.data['diff'].append([f1[0]])
                        break
        for f2 in files2:
            if f2[0] not in list(x[0] for x in files1):
                ext = os.path.splitext(f2[0])[1]
                if len(ext) > 0 and ext[1:] in READABLE:
                    self.data['unmatched2'].insert(0, [f2[0], f2[1]])
                else:
                    self.data['unmatched2'].append([f2[0]])


class GetFilesComparison(object):
    def __init__(self, user, job1, job2):
        self.user = user
        self.job1 = job1
        self.job2 = job2
        self.data = self.__get_info()

    def __get_info(self):
        try:
            info = CompareJobsInfo.objects.get(user=self.user, root1=self.job1.reportroot, root2=self.job2.reportroot)
        except ObjectDoesNotExist:
            raise BridgeException(_('The comparison cache was not found'))
        return json.loads(info.files_diff)


def change_job_status(job, status):
    if not isinstance(job, Job) or status not in set(x[0] for x in JOB_STATUS):
        return
    job.status = status
    job.save()
    try:
        run_data = job.runhistory_set.latest('date')
        run_data.status = status
        run_data.save()
    except ObjectDoesNotExist:
        pass


def get_default_configurations():
    configurations = []
    for conf in settings.DEF_KLEVER_CORE_MODES:
        mode = next(iter(conf))
        configurations.append([
            mode,
            START_JOB_DEFAULT_MODES[mode] if mode in START_JOB_DEFAULT_MODES else mode
        ])
    return configurations


class GetConfiguration(object):
    def __init__(self, conf_name=None, file_conf=None, user_conf=None):
        self.configuration = None
        if conf_name is not None:
            self.__get_default_conf(conf_name)
        elif file_conf is not None:
            self.__get_file_conf(file_conf)
        elif user_conf is not None:
            self.__get_user_conf(user_conf)
        if not self.__check_conf():
            logger.error("The configuration didn't pass checks")
            self.configuration = None

    def __get_default_conf(self, name):
        if name is None:
            name = settings.DEF_KLEVER_CORE_MODE
        conf_template = None
        for conf in settings.DEF_KLEVER_CORE_MODES:
            mode = next(iter(conf))
            if mode == name:
                conf_template = conf[mode]
        if conf_template is None:
            return
        try:
            self.configuration = [
                list(conf_template[0]),
                list(settings.KLEVER_CORE_PARALLELISM_PACKS[conf_template[1]]),
                list(conf_template[2]),
                [
                    conf_template[3][0],
                    settings.KLEVER_CORE_LOG_FORMATTERS[conf_template[3][1]],
                    conf_template[3][2],
                    settings.KLEVER_CORE_LOG_FORMATTERS[conf_template[3][3]],
                ],
                list(conf_template[4:])
            ]
        except Exception as e:
            logger.exception("Wrong default configuration format: %s" % e, stack_info=True)

    def __get_file_conf(self, filedata):
        scheduler = None
        for sch in SCHEDULER_TYPE:
            if sch[1] == filedata['task scheduler']:
                scheduler = sch[0]
                break
        if scheduler is None:
            logger.error('Scheduler %s is not supported' % filedata['task scheduler'], stack_info=True)
            return

        cpu_time = filedata['resource limits']['CPU time']
        if isinstance(cpu_time, int):
            cpu_time = float("%0.3f" % (filedata['resource limits']['CPU time'] / 60))
        wall_time = filedata['resource limits']['wall time']
        if isinstance(wall_time, int):
            wall_time = float("%0.3f" % (filedata['resource limits']['wall time'] / 60))

        try:
            formatters = {}
            for f in filedata['logging']['formatters']:
                formatters[f['name']] = f['value']
            loggers = {}
            for l in filedata['logging']['loggers']:
                # TODO: what to do with other loggers?
                if l['name'] == 'default':
                    for l_h in l['handlers']:
                        loggers[l_h['name']] = {
                            'formatter': formatters[l_h['formatter']],
                            'level': l_h['level']
                        }
            logging = [
                loggers['console']['level'],
                loggers['console']['formatter'],
                loggers['file']['level'],
                loggers['file']['formatter']
            ]
        except Exception as e:
            logger.exception("Wrong logging format: %s" % e)
            return

        try:
            self.configuration = [
                [filedata['priority'], scheduler, filedata['max solving tasks per sub-job']],
                [
                    filedata['parallelism']['Sub-jobs processing'],
                    filedata['parallelism']['Build'],
                    filedata['parallelism']['Tasks generation'],
                    filedata['parallelism']['Results processing']
                ],
                [
                    filedata['resource limits']['memory size'] / 10**9,
                    filedata['resource limits']['number of CPU cores'],
                    filedata['resource limits']['disk memory size'] / 10**9,
                    filedata['resource limits']['CPU model'],
                    cpu_time, wall_time
                ],
                logging,
                [
                    filedata['keep intermediate files'],
                    filedata['upload input files of static verifiers'],
                    filedata['upload other intermediate files'],
                    filedata['allow local source directories use'],
                    filedata['ignore other instances'],
                    filedata['ignore failed sub-jobs'],
                    filedata['collect total code coverage'],
                    filedata['generate makefiles'],
                    filedata['weight']
                ]
            ]
        except Exception as e:
            logger.exception("Wrong core configuration format: %s" % e, stack_info=True)

    def __get_user_conf(self, conf):
        def int_or_float(val):
            m = re.match('^\s*(\d+),(\d+)\s*$', val)
            if m is not None:
                val = '%s.%s' % (m.group(1), m.group(2))
            try:
                return int(val)
            except ValueError:
                return float(val)

        try:
            conf[1] = [int_or_float(conf[1][i]) for i in range(4)]
            if len(conf[2][3]) == 0:
                conf[2][3] = None
            conf[2][0] = float(conf[2][0])
            conf[2][1] = int(conf[2][1])
            conf[2][2] = float(conf[2][2])
            if conf[2][4] is not None:
                conf[2][4] = float(conf[2][4])
            if conf[2][5] is not None:
                conf[2][5] = float(conf[2][5])
        except Exception as e:
            logger.exception("Wrong user configuration format: %s" % e, stack_info=True)
            return
        self.configuration = conf

    def __check_conf(self):
        if not isinstance(self.configuration, list) or len(self.configuration) != 5:
            return False
        if not isinstance(self.configuration[0], list) or len(self.configuration[0]) != 3:
            return False
        if not isinstance(self.configuration[1], list) or len(self.configuration[1]) != 4:
            return False
        if not isinstance(self.configuration[2], list) or len(self.configuration[2]) != 6:
            return False
        if not isinstance(self.configuration[3], list) or len(self.configuration[3]) != 4:
            return False
        if not isinstance(self.configuration[4], list) or len(self.configuration[4]) != 9:
            return False
        if self.configuration[0][0] not in set(x[0] for x in PRIORITY):
            return False
        if self.configuration[0][1] not in set(x[0] for x in SCHEDULER_TYPE):
            return False
        if not isinstance(self.configuration[0][2], int) or \
                (isinstance(self.configuration[0][2], int) and self.configuration[0][2] < 1):
            return False
        for i in range(4):
            if not isinstance(self.configuration[1][i], (float, int)):
                return False
        if not isinstance(self.configuration[2][0], (float, int)):
            return False
        if not isinstance(self.configuration[2][1], int):
            return False
        if not isinstance(self.configuration[2][2], (float, int)):
            return False
        if not isinstance(self.configuration[2][3], str) and self.configuration[2][3] is not None:
            return False
        if not isinstance(self.configuration[2][4], (float, int)) and self.configuration[2][4] is not None:
            return False
        if not isinstance(self.configuration[2][5], (float, int)) and self.configuration[2][5] is not None:
            return False
        if self.configuration[3][0] not in settings.LOGGING_LEVELS:
            return False
        if self.configuration[3][2] not in settings.LOGGING_LEVELS:
            return False
        if not isinstance(self.configuration[3][1], str) or not isinstance(self.configuration[3][3], str):
            return False
        if any(not isinstance(x, bool) for x in self.configuration[4][:-1]):
            return False
        if self.configuration[4][-1] not in set(w[0] for w in JOB_WEIGHT):
            return False
        return True


class StartDecisionData:
    def __init__(self, user, data):
        self.default = data
        self.job_sch_err = None
        self.schedulers = self.__get_schedulers()
        self.priorities = list(reversed(PRIORITY))
        self.logging_levels = settings.LOGGING_LEVELS
        self.parallelism = KLEVER_CORE_PARALLELISM
        self.formatters = KLEVER_CORE_FORMATTERS
        self.job_weight = JOB_WEIGHT

        self.need_auth = False
        try:
            SchedulerUser.objects.get(user=user)
        except ObjectDoesNotExist:
            self.need_auth = True

    def __get_schedulers(self):
        schedulers = []
        try:
            klever_sch = Scheduler.objects.get(type=SCHEDULER_TYPE[0][0])
        except ObjectDoesNotExist:
            raise BridgeException(_('Population has to be done first'))
        try:
            cloud_sch = Scheduler.objects.get(type=SCHEDULER_TYPE[1][0])
        except ObjectDoesNotExist:
            raise BridgeException(_('Population has to be done first'))
        if klever_sch.status == SCHEDULER_STATUS[1][0]:
            self.job_sch_err = _("The Klever scheduler is ailing")
        elif klever_sch.status == SCHEDULER_STATUS[2][0]:
            raise BridgeException(_('The Klever scheduler is disconnected'))
        schedulers.append([
            klever_sch.type,
            string_concat(klever_sch.get_type_display(), ' (', klever_sch.get_status_display(), ')')
        ])
        if cloud_sch.status != SCHEDULER_STATUS[2][0]:
            schedulers.append([
                cloud_sch.type,
                string_concat(cloud_sch.get_type_display(), ' (', cloud_sch.get_status_display(), ')')
            ])
        elif self.default[0][1] == SCHEDULER_TYPE[1][0]:
            raise BridgeException(_('The scheduler for tasks is disconnected'))
        return schedulers
