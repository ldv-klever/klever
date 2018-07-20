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
import re
import hashlib
from datetime import datetime

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count, Case, When, IntegerField
from django.utils.translation import ugettext_lazy as _, string_concat
from django.utils.timezone import now, pytz

from bridge.vars import JOB_STATUS, KLEVER_CORE_PARALLELISM, KLEVER_CORE_FORMATTERS, USER_ROLES, JOB_ROLES,\
    SCHEDULER_TYPE, PRIORITY, START_JOB_DEFAULT_MODES, SCHEDULER_STATUS, JOB_WEIGHT, SAFE_VERDICTS, UNSAFE_VERDICTS
from bridge.utils import logger, BridgeException, file_get_or_create, get_templated_text
from users.notifications import Notify

from jobs.models import Job, JobHistory, FileSystem, UserRole, JobFile
from reports.models import ReportComponent, ReportSafe, ReportUnsafe, ReportUnknown, ReportAttr
from service.models import SchedulerUser, Scheduler
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
    for child in job.children.order_by('change_date'):
        if JobAccess(user, child).can_view():
            children.append({'pk': child.pk, 'name': child.name})
    return children


class JobAccess:

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
        if self.job is None or self.job.status in [JOB_STATUS[1][0], JOB_STATUS[2][0], JOB_STATUS[6][0]]:
            return False
        return self.__is_manager or self.__is_author or self.__job_role in [JOB_ROLES[3][0], JOB_ROLES[4][0]]

    def can_upload_reports(self):
        if self.job is None or self.job.status in [JOB_STATUS[1][0], JOB_STATUS[2][0], JOB_STATUS[6][0]]:
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
        return self.job.status not in [JOB_STATUS[1][0], JOB_STATUS[2][0], JOB_STATUS[6][0]] \
            and (self.__is_author or self.__is_manager)

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
        return self.job.status not in {JOB_STATUS[1][0], JOB_STATUS[2][0], JOB_STATUS[6][0]} \
            and (self.__is_author or self.__is_manager) and self.job.weight == JOB_WEIGHT[0][0]

    def can_clear_verifications(self):
        if self.job is None or self.job.status in {JOB_STATUS[1][0], JOB_STATUS[2][0], JOB_STATUS[6][0]}:
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


def get_job_by_identifier(identifier):
    found_jobs = Job.objects.filter(identifier__startswith=identifier)
    if len(found_jobs) == 0:
        raise BridgeException(_('The job with specified identifier was not found'))
    elif len(found_jobs) > 1:
        raise BridgeException(_('Several jobs match the specified identifier, '
                              'please increase the length of the job identifier'))
    return found_jobs[0]


def get_job_by_name_or_id(name_or_id):
    try:
        return Job.objects.get(name=name_or_id)
    except ObjectDoesNotExist:
        found_jobs = Job.objects.filter(identifier__startswith=name_or_id)
        if len(found_jobs) == 0:
            raise BridgeException(_('The job with specified identifier or name was not found'))
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
        db_file = file_get_or_create(fp, fp.name, JobFile, True)[0]
        fs = FileSystem.objects.get(id=self._file_to_replace)
        fs.file = db_file
        fs.save()


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
        return get_templated_text('{% load l10n %}{{ val }} {{ postfix }}', val=rounded_value, postfix=postfix)

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
        return get_templated_text('{% load l10n %}{{ val }} {{ postfix }}', val=rounded_value, postfix=postfix)

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


def create_job(kwargs):
    if 'name' not in kwargs or len(kwargs['name']) == 0:
        logger.error('The job name was not got')
        raise BridgeException()
    try:
        Job.objects.get(name=kwargs['name'])
    except ObjectDoesNotExist:
        pass
    else:
        raise BridgeException(_('The job name is already used'))

    if 'author' not in kwargs or not isinstance(kwargs['author'], User):
        logger.error('The job author was not got')
        raise BridgeException()
    newjob = Job(name=kwargs['name'], change_date=now(), change_author=kwargs['author'], parent=kwargs.get('parent'))

    if 'identifier' in kwargs and kwargs['identifier'] is not None:
        if Job.objects.filter(identifier=kwargs['identifier']).count() > 0:
            # This exception will be occurred only on jobs population (if for preset jobs identifier would be set)
            # or jobs uploading
            raise BridgeException(_('The job with specified identifier already exists'))
        newjob.identifier = kwargs['identifier']
    else:
        time_encoded = now().strftime("%Y%m%d%H%M%S%f%z").encode('utf-8')
        newjob.identifier = hashlib.md5(time_encoded).hexdigest()
    newjob.safe_marks = bool(kwargs.get('safe marks', settings.ENABLE_SAFE_MARKS))
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
    if 'comment' not in kwargs:
        kwargs['comment'] = ''
    if 'parent' in kwargs:
        kwargs['job'].parent = kwargs['parent']
    if 'name' in kwargs and len(kwargs['name']) > 0:
        try:
            job = Job.objects.get(name=kwargs['name'])
        except ObjectDoesNotExist:
            pass
        else:
            if job.id != kwargs['job'].id:
                raise BridgeException(_('The job name is already used'))
        kwargs['job'].name = kwargs['name']
    kwargs['job'].change_author = kwargs['author']
    kwargs['job'].change_date = now()
    kwargs['job'].version += 1
    kwargs['job'].save()

    newversion = create_version(kwargs['job'], kwargs)

    if 'filedata' in kwargs:
        try:
            SaveFileData(kwargs['filedata'], newversion)
        except Exception:
            newversion.delete()
            kwargs['job'].version -= 1
            kwargs['job'].save()
            raise
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


def copy_job_version(user, job):
    last_version = JobHistory.objects.get(job=job, version=job.version)
    job.version += 1

    new_version = JobHistory.objects.create(
        job=job, parent=job.parent, version=job.version, change_author=user, comment='',
        description=last_version.description, global_role=last_version.global_role
    )

    roles = []
    for ur in UserRole.objects.filter(job=last_version):
        roles.append(UserRole(job=new_version, user=ur.user, role=ur.role))
    UserRole.objects.bulk_create(roles)

    try:
        fdata = FileData(last_version).filedata
        for i in range(len(fdata)):
            fdata[i]['type'] = str(fdata[i]['type'])
        SaveFileData(fdata, new_version)
    except Exception:
        new_version.delete()
        raise
    job.change_date = new_version.change_date
    job.change_author = user
    job.save()


def save_job_copy(user, job_id, name=None):
    try:
        job = Job.objects.get(id=job_id)
    except ObjectDoesNotExist:
        raise BridgeException(_('The job was not found'))

    last_version = JobHistory.objects.get(job=job, version=job.version)

    if isinstance(name, str) and len(name) > 0:
        job_name = name
        try:
            Job.objects.get(name=job_name)
        except ObjectDoesNotExist:
            pass
        else:
            raise BridgeException('The job name is used already.')
    else:
        cnt = 1
        while True:
            job_name = "%s #COPY-%s" % (job.name, cnt)
            try:
                Job.objects.get(name=job_name)
            except ObjectDoesNotExist:
                break
            cnt += 1

    newjob = Job.objects.create(
        identifier=hashlib.md5(now().strftime("%Y%m%d%H%M%S%f%z").encode('utf-8')).hexdigest(),
        name=job_name, change_date=now(), change_author=user, parent=job, type=job.type, safe_marks=job.safe_marks
    )

    new_version = JobHistory.objects.create(
        job=newjob, parent=newjob.parent, version=newjob.version,
        change_author=user, change_date=newjob.change_date, comment='',
        description=last_version.description, global_role=last_version.global_role
    )

    roles = []
    for ur in UserRole.objects.filter(job=last_version):
        roles.append(UserRole(job=new_version, user=ur.user, role=ur.role))
    UserRole.objects.bulk_create(roles)

    try:
        fdata = FileData(last_version).filedata
        for i in range(len(fdata)):
            fdata[i]['type'] = str(fdata[i]['type'])
        SaveFileData(fdata, new_version)
    except Exception:
        new_version.delete()
        job.version -= 1
        job.save()
        raise
    return newjob


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
        if j_id in list(job_struct):
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

            title = j.change_date.astimezone(pytz.timezone(self._user.extended.timezone)).strftime("%d.%m.%Y %H:%M:%S")
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
                if is_readable(f1[0]):
                    self.data['unmatched1'].insert(0, [f1[0], f1[1]])
                else:
                    self.data['unmatched1'].append([f1[0]])
            else:
                for f2 in files2:
                    if f2[0] == f1[0]:
                        is_rdb = is_readable(f1[0])
                        if f2[1] == f1[1]:
                            if is_rdb:
                                self.data['same'].insert(0, [f1[0], f1[1]])
                            else:
                                self.data['same'].append([f1[0]])
                        else:
                            if is_rdb:
                                self.data['diff'].insert(0, [f1[0], f1[1], f2[1]])
                            else:
                                self.data['diff'].append([f1[0]])
                        break
        for f2 in files2:
            if f2[0] not in list(x[0] for x in files1):
                if is_readable(f2[0]):
                    self.data['unmatched2'].insert(0, [f2[0], f2[1]])
                else:
                    self.data['unmatched2'].append([f2[0]])


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
                    filedata['resource limits']['CPU model']
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
        if not isinstance(self.configuration[2], list) or len(self.configuration[2]) != 4:
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


class CompareJobVersions:
    def __init__(self, v1, v2):
        self.v1 = v1
        self.v2 = v2
        self.files_map = {}
        self.roles = self.__user_roles()
        self.paths, self.files = self.__compare_files()

    def __user_roles(self):
        set1 = set(uid for uid, in UserRole.objects.filter(job=self.v1).values_list('user_id'))
        set2 = set(uid for uid, in UserRole.objects.filter(job=self.v2).values_list('user_id'))
        if set1 != set2:
            return [
                UserRole.objects.filter(job=self.v1).order_by('user__last_name').select_related('user'),
                UserRole.objects.filter(job=self.v2).order_by('user__last_name').select_related('user')
            ]
        return None

    def __get_files(self, version):
        self.__is_not_used()
        tree = {}
        for f in FileSystem.objects.filter(job=version).order_by('id').select_related('file'):
            tree[f.id] = {'parent': f.parent_id, 'name': f.name, 'hashsum': f.file.hash_sum if f.file else None}
        files = {}
        for f_id in tree:
            if tree[f_id]['hashsum'] is None:
                continue
            parent = tree[f_id]['parent']
            path_list = [tree[f_id]['name']]
            while parent is not None:
                path_list.insert(0, tree[parent]['name'])
                parent = tree[parent]['parent']
            files['/'.join(path_list)] = {'hashsum': tree[f_id]['hashsum'], 'name': tree[f_id]['name']}
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

    def __is_not_used(self):
        pass


class GetJobDecisionResults:
    def __init__(self, job):
        self.job = job
        try:
            self.start_date = self.job.solvingprogress.start_date
            self.finish_date = self.job.solvingprogress.finish_date
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
        for verdict, confirmed, total in self._report.leaves.exclude(safe=None).values('safe__verdict').annotate(
                total=Count('id'), confirmed=Count(Case(When(safe__has_confirmed=True, then=1)))
        ).values_list('safe__verdict', 'confirmed', 'total'):
            data['safes'][verdict] = [confirmed, total]
            confirmed_safes += confirmed
            total_safes += total
        data['safes']['total'] = [confirmed_safes, total_safes]

        # Obtaining unsafes information
        total_unsafes = 0
        confirmed_unsafes = 0
        for verdict, confirmed, total in self._report.leaves.exclude(unsafe=None).values('unsafe__verdict').annotate(
                total=Count('id'), confirmed=Count(Case(When(unsafe__has_confirmed=True, then=1)))
        ).values_list('unsafe__verdict', 'confirmed', 'total'):
            data['unsafes'][verdict] = [confirmed, total]
            confirmed_unsafes += confirmed
            total_unsafes += total
        data['unsafes']['total'] = [confirmed_unsafes, total_unsafes]

        # Obtaining unknowns information
        for cmup in self._report.mark_unknowns_cache.select_related('component', 'problem'):
            if cmup.component.name not in data['unknowns']:
                data['unknowns'][cmup.component.name] = {}
            data['unknowns'][cmup.component.name][cmup.problem.name if cmup.problem else 'Without marks'] = cmup.number
        for cmup in self._report.unknowns_cache.select_related('component'):
            if cmup.component.name not in data['unknowns']:
                data['unknowns'][cmup.component.name] = {}
            data['unknowns'][cmup.component.name]['Total'] = cmup.number

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

        for identifier, tag in MarkSafeTag.objects.filter(mark_version__mark__identifier__in=marks) \
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
            if u_id not in reports:
                reports[u_id] = {'attrs': [], 'marks': {}}

        for r_id, aname, aval in ReportAttr.objects.filter(report_id__in=reports)\
                .order_by('attr__name__name').values_list('report_id', 'attr__name__name', 'attr__value'):
            reports[r_id]['attrs'].append([aname, aval])

        for identifier, tag in MarkUnsafeTag.objects.filter(mark_version__mark__identifier__in=marks)\
                .order_by('tag__tag').values_list('mark_version__mark__identifier', 'tag__tag'):
            marks[identifier]['tags'].append(tag)
        report_data = []
        for r_id in sorted(reports):
            report_data.append(reports[r_id])
        return {'reports': report_data, 'marks': marks}

    def __get_unknowns(self):
        marks = {}
        reports = {}

        for mr in MarkUnknownReport.objects.filter(report__root=self.job.reportroot).select_related('mark'):
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
