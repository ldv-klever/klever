from django.contrib.auth.models import User
from django.db.models import Q
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _, string_concat
from Omega.vars import USER_ROLES, JOB_ROLES, JOB_STATUS
from jobs.models import FileSystem, File
from django.conf import settings
import os
import re
import zipfile
from datetime import datetime
from io import BytesIO, StringIO
import hashlib


COLORS = {
    'red': '#C70646',
    'orange': '#D05A00',
    'purple': '#930BBD',
}

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
    'author': _('Author'),
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
    'resource': _('Resourses'),
    'resource:total': _('Total'),
    'tag': _('Tags'),
    'tag:safe': _('Safes'),
    'tag:unsafe': _('Unsafes'),
    'identifier': _('Identifier'),
    'format': _('Format'),
    'version': _('Version'),
    'type': _('Class'),
    'parent_title': string_concat(_('Parent'), '/', _('Title')),
    'parent_id': string_concat(_('Parent'), '/', _('Identifier')),
    'role': _('Your role'),
}


DOWNLOAD_LOCKFILE = 'download.lock'


class FileData(object):

    def __init__(self, job):
        self.filedata = []
        self.__get_filedata(job)
        self.__order_by_type()
        self.__order_by_lvl()

    def __get_filedata(self, job):
        for f in job.file_set.all().order_by('name'):
            file_info = {
                'title': f.name,
                'id': f.pk,
                'parent': None,
                'hash_sum': None,
                'type': 0
            }
            if f.parent:
                file_info['parent'] = f.parent_id
            if f.file:
                file_info['type'] = 1
                file_info['hash_sum'] = f.file.hash_sum
            self.filedata.append(file_info)

    def __order_by_type(self):
        newfilesdata = []
        for fd in self.filedata:
            if fd['type'] == 0:
                newfilesdata.append(fd)
        for fd in self.filedata:
            if fd['type'] == 1:
                newfilesdata.append(fd)
        self.filedata = newfilesdata

    def __order_by_lvl(self):
        lvl = 1
        ordered_filedata = []
        for fd in self.filedata:
            if fd['parent'] is None:
                fd['lvl'] = lvl
                ordered_filedata.append(fd)
        while len(ordered_filedata) < len(self.filedata):
            ordered_filedata = self.__insert_level(lvl, ordered_filedata)
            lvl += 1
            # maximum depth of folders: 1000
            if lvl > 1000:
                return ordered_filedata
        self.filedata = ordered_filedata

    def __insert_level(self, lvl, ordered_filedata):
        ordered_data = []
        for o_fd in ordered_filedata:
            ordered_data.append(o_fd)
            if o_fd['lvl'] == lvl:
                for f_fd in self.filedata:
                    if f_fd['parent'] == o_fd['id']:
                        f_fd['lvl'] = lvl + 1
                        ordered_data.append(f_fd)
        return ordered_data


class DBFileData(object):
    def __init__(self, filedata, job):
        self.filedata = filedata
        self.job = job
        self.filedata_by_lvl = []
        self.filedata_hash = {}
        self.err_message = self.__validate()
        if self.err_message is None:
            self.err_message = self.__save_file_data()

    def __save_file_data(self):
        for lvl in self.filedata_by_lvl:
            for lvl_elem in lvl:
                fs_elem = FileSystem()
                fs_elem.job = self.job
                if lvl_elem['parent']:
                    parent_pk = self.filedata_hash[lvl_elem['parent']].get(
                        'pk', None
                    )
                    if parent_pk is None:
                        return _("Parent was not saved")
                    try:
                        parent = FileSystem.objects.get(pk=parent_pk, file=None)
                    except ObjectDoesNotExist:
                        return _("Parent was not saved")
                    fs_elem.parent = parent
                if lvl_elem['type'] == '1':
                    try:
                        fs_elem.file = File.objects.get(
                            hash_sum=lvl_elem['hash_sum']
                        )
                    except ObjectDoesNotExist:
                        return _("The file was not found")
                fs_elem.name = lvl_elem['title']
                fs_elem.save()
                self.filedata_hash[lvl_elem['id']]['pk'] = fs_elem.pk
        return None

    def __validate(self):
        num_of_elements = 0
        element_of_lvl = []
        cnt = 0
        while num_of_elements < len(self.filedata):
            cnt += 1
            if cnt > 1000:
                return _("Unknown error")
            num_of_elements += len(element_of_lvl)
            element_of_lvl = self.__get_lower_level(element_of_lvl)
            if len(element_of_lvl):
                self.filedata_by_lvl.append(element_of_lvl)
        for lvl in self.filedata_by_lvl:
            names_of_lvl = []
            for fd in lvl:
                self.filedata_hash[fd['id']] = fd
                if len(fd['title']) == 0:
                    return _("You can't specify an empty name")
                if fd['type'] == '1' and fd['hash_sum'] is None:
                    return _("The file was not uploaded")
                names_of_lvl.append(fd['title'])
            for name in names_of_lvl:
                if names_of_lvl.count(name) != 1:
                    return _("You can't use the same name in one folder")
        return None

    def __get_lower_level(self, data):
        new_level = []
        if len(data):
            for d in data:
                for fd in self.filedata:
                    if fd['parent'] == d['id']:
                        if fd not in new_level:
                            new_level.append(fd)
        else:
            for fd in self.filedata:
                if fd['parent'] is None:
                    new_level.append(fd)
        return new_level


# For first lock: job = None, hash_sum = None, user != None;
#  if first_lock return True self.hash_sum =- hash_sum in lock file.
class JobArchive(object):
    def __init__(self, job=None, hash_sum=None, user=None):
        self.lockfile = DOWNLOAD_LOCKFILE
        self.workdir = 'ZIPcreation'
        self.jobzip_name = ''
        self.job = job
        self.user = user
        self.hash_sum = hash_sum
        self.__prepare_workdir()
        self.memory = BytesIO()
        self.err_code = 0

    def __prepare_workdir(self):
        self.workdir = os.path.join(settings.MEDIA_ROOT, self.workdir)
        if not os.path.isdir(self.workdir):
            os.mkdir(self.workdir)
        self.lockfile = os.path.join(self.workdir, self.lockfile)
        if not os.path.isfile(self.lockfile):
            f = open(self.lockfile, 'w')
            f.write('unlocked')
            f.close()

    def first_lock(self):
        f = open(self.lockfile, 'r')
        line = f.readline()
        f.close()
        curr_time = (datetime.now() - datetime(2000, 1, 1)).total_seconds()
        if line == 'unlocked':
            self.__update_hash_sum()
            if self.hash_sum:
                f = open(self.lockfile, 'w')
                print("Locking with hash: " + self.hash_sum)
                f.write('locked#' + str(curr_time) + '#' + self.hash_sum)
                f.close()
                return True
        elif line.startswith('locked#'):
            line_lock_time = float(line.split('#')[1])
            if (curr_time - line_lock_time) > 10:
                self.__update_hash_sum()
                if self.hash_sum:
                    f = open(self.lockfile, 'w')
                    print("Locking with hash: " + self.hash_sum)
                    f.write('locked#' + str(curr_time) + '#' + self.hash_sum)
                    f.close()
                    return True
        return False

    def __update_hash_sum(self):
        if self.user:
            hash_data = (
                '%s%s' % (self.user.extended.pk, datetime.now().isoformat())
            ).encode('utf-8')
            self.hash_sum = hashlib.md5(hash_data).hexdigest()

    def second_lock(self):
        f = open(self.lockfile, 'r')
        line = f.readline()
        f.close()
        line_data = line.split('#')
        if len(line_data) == 3 and line_data[0] == 'locked':
            if self.hash_sum == line_data[2]:
                f = open(self.lockfile, 'w')
                print("Double lock: " + self.hash_sum)
                f.write('doublelocked')
                f.close()
                return True
        return False

    def unlock(self):
        f = open(self.lockfile, 'r')
        status = f.readline()
        f.close()
        if status == 'unlocked':
            return
        f = open(self.lockfile, 'w')
        f.write('unlocked')
        f.close()

    def __get_filedata(self):
        job_version = self.job.jobhistory_set.get(version=self.job.version)
        files = job_version.file_set.all()
        files_for_zip = []
        for f in files:
            if f.file:
                file_path = f.name
                file_parent = f.parent
                while file_parent:
                    file_path = file_parent.name + '/' + file_path
                    file_parent = file_parent.parent
                files_for_zip.append({
                    'path': 'root' + '/' + file_path,
                    'src': os.path.join(settings.MEDIA_ROOT, f.file.file.name)
                })
        return files_for_zip

    def create_zip(self):
        if self.job is None:
            self.err_code = 404
            return
        if self.second_lock():
            self.jobzip_name = 'VJ__' + self.job.identifier + '.zip'
            files_for_zip = self.__get_filedata()
            job_zip_file = zipfile.ZipFile(self.memory, 'w')
            self.__write_file_str(
                job_zip_file, 'title', self.job.name
            )
            self.__write_file_str(
                job_zip_file, 'configuration', self.job.configuration
            )
            self.__write_file_str(
                job_zip_file, 'description', self.job.description
            )
            for f in files_for_zip:
                job_zip_file.write(f['src'], f['path'], zipfile.ZIP_DEFLATED)
            job_zip_file.close()
            self.unlock()
        else:
            self.err_code = 450

    def __write_file_str(self, jobzip, file_name, file_content):
        virt_file = StringIO()
        virt_file.write(file_content)
        jobzip.writestr(file_name, virt_file.getvalue(), zipfile.ZIP_DEFLATED)
        virt_file.close()


def convert_time(val, acc):
    new_time = int(val)
    time_format = "%%1.%df%%s" % int(acc)
    try_div = new_time / 1000
    if try_div < 1:
        return time_format % (new_time, _('__ms'))
    new_time = try_div
    try_div = new_time / 60
    if try_div < 1:
        return time_format % (new_time, _('__s'))
    new_time = try_div
    try_div = new_time / 60
    if try_div < 1:
        return time_format % (new_time, _('__m'))
    return time_format % (try_div, _('__h'))


def convert_memory(val, acc):
    new_mem = int(val)
    mem_format = "%%1.%df%%s" % int(acc)
    try_div = new_mem / 1024
    if try_div < 1:
        return mem_format % (new_mem, _('__b'))
    new_mem = try_div
    try_div = new_mem / 1024
    if try_div < 1:
        return mem_format % (new_mem, _('__Kb'))
    new_mem = try_div
    try_div = new_mem / 1024
    if try_div < 1:
        return mem_format % (new_mem, _('__Mb'))
    return mem_format % (try_div, _('__Gb'))


def verdict_info(job):
    try:
        verdicts = job.verdict
    except ObjectDoesNotExist:
        return None

    safes_data = []
    for s in SAFES:
        safe_name = 'safe:' + s
        color = None
        val = '-'
        if s == 'missed_bug':
            val = verdicts.safe_missed_bug
            color = COLORS['red']
        elif s == 'incorrect':
            val = verdicts.safe_incorrect_proof
            color = COLORS['orange']
        elif s == 'unknown':
            val = verdicts.safe_unknown
            color = COLORS['purple']
        elif s == 'inconclusive':
            val = verdicts.safe_inconclusive
            color = COLORS['red']
        elif s == 'unassociated':
            val = verdicts.safe_unassociated
        elif s == 'total':
            val = verdicts.safe
        safes_data.append({
            'title': TITLES[safe_name],
            'value': val,
            'color': color,
        })

    unsafes_data = []
    for s in UNSAFES:
        unsafe_name = 'unsafe:' + s
        color = None
        val = '-'
        if s == 'bug':
            val = verdicts.unsafe_bug
            color = COLORS['red']
        elif s == 'target_bug':
            val = verdicts.unsafe_target_bug
            color = COLORS['red']
        elif s == 'false_positive':
            val = verdicts.unsafe_false_positive
            color = COLORS['orange']
        elif s == 'unknown':
            val = verdicts.unsafe_unknown
            color = COLORS['purple']
        elif s == 'inconclusive':
            val = verdicts.unsafe_inconclusive
            color = COLORS['red']
        elif s == 'unassociated':
            val = verdicts.unsafe_unassociated
        elif s == 'total':
            val = verdicts.unsafe
        unsafes_data.append({
            'title': TITLES[unsafe_name],
            'value': val,
            'color': color,
        })
    return {
        'unsafes': unsafes_data,
        'safes': safes_data,
        'unknowns': verdicts.unknown
    }


def unknowns_info(job):
    unknowns_data = {}
    unkn_set = job.componentmarkunknownproblem_set.filter(~Q(problem=None))
    for cmup in unkn_set:
        if cmup.component.name not in unknowns_data:
            unknowns_data[cmup.component.name] = {}
        unknowns_data[cmup.component.name][cmup.problem.name] = cmup.number
    unkn_set = job.componentmarkunknownproblem_set.filter(problem=None)
    for cmup in unkn_set:
        if cmup.component.name not in unknowns_data:
            unknowns_data[cmup.component.name] = {}
        unknowns_data[cmup.component.name][_('Without marks')] = cmup.number
    unkn_set = job.componentunknown_set.all()
    for cmup in unkn_set:
        if cmup.component.name not in unknowns_data:
            unknowns_data[cmup.component.name] = {}
        unknowns_data[cmup.component.name][_('Total')] = cmup.number
    unknowns_sorted = []
    for comp in sorted(unknowns_data):
        problems_sorted = []
        for probl in unknowns_data[comp]:
            problems_sorted.append({
                'num': unknowns_data[comp][probl],
                'problem': probl,
            })
        unknowns_sorted.append({
            'component': comp,
            'problems': problems_sorted,
        })
    return unknowns_sorted


def resource_info(job, user):
    accuracy = user.extended.accuracy
    data_format = user.extended.data_format

    res_set = job.componentresource_set.filter(~Q(component=None))
    res_data = {}
    for cr in res_set:
        if cr.component.name not in res_data:
            res_data[cr.component.name] = {}
        wall = cr.wall_time
        cpu = cr.cpu_time
        mem = cr.memory
        if data_format == 'hum':
            wall = convert_time(wall, accuracy)
            cpu = convert_time(cpu, accuracy)
            mem = convert_memory(mem, accuracy)
        res_data[cr.component.name] = "%s %s %s" % (wall, cpu, mem)
    resource_data = [
        {'component': x, 'val': res_data[x]} for x in sorted(res_data)]
    res_total = job.componentresource_set.filter(component=None)
    if len(res_total):
        wall = res_total[0].wall_time
        cpu = res_total[0].cpu_time
        mem = res_total[0].memory
        if data_format == 'hum':
            wall = convert_time(wall, accuracy)
            cpu = convert_time(cpu, accuracy)
            mem = convert_memory(mem, accuracy)
        total_value = "%s %s %s" % (wall, cpu, mem)
        resource_data.append({
            'component': _('Total'),
            'val': total_value,
        })
    return resource_data


def role_info(job, user):
    roles_data = {'global': job.job.global_role}

    users = []
    user_roles_data = []
    users_roles = job.userrole_set.filter(~Q(user=user))
    job_author = job.job.jobhistory_set.get(version=1).change_author

    for ur in users_roles:
        title = ur.user.extended.last_name + ' ' + ur.user.extended.first_name
        u_id = ur.user_id
        user_roles_data.append({
            'user': {'id': u_id, 'name': title},
            'role': {'val': ur.role, 'title': ur.get_role_display()}
        })
        users.append(u_id)

    roles_data['user_roles'] = user_roles_data

    available_users = []
    for u in User.objects.filter(~Q(pk__in=users) & ~Q(pk=user.pk)):
        if u != job_author:
            available_users.append({
                'id': u.pk,
                'name': u.extended.last_name + ' ' + u.extended.first_name
            })
    roles_data['available_users'] = available_users

    available_roles = []
    for role in JOB_ROLES:
        available_roles.append({
            'value': role[0],
            'title': role[1],
        })
    roles_data['job_roles'] = available_roles
    return roles_data


def has_job_access(user, action='view', job=None):
    if action == 'view' and job:
        last_version = job.jobhistory_set.all().order_by('-change_date')[0]
        if user.extended.role == USER_ROLES[2][0]:
            return True
        job_first_ver = job.jobhistory_set.filter(version=1)
        if len(job_first_ver) and job_first_ver[0].change_author == user:
            return True
        user_role = last_version.userrole_set.filter(user=user)
        if len(user_role):
            if user_role[0].role == JOB_ROLES[0][0]:
                return False
            return True
        if job.global_role == JOB_ROLES[0][0]:
            return False
        return True
    elif action == 'create':
        return user.extended.role != USER_ROLES[0][0]
    elif action == 'edit' and job:
        if user.extended.role == USER_ROLES[0][0]:
            return False
        first_v = job.jobhistory_set.filter(version=1)
        if first_v:
            try:
                status = job.jobstatus.status
            except ObjectDoesNotExist:
                return False
            if status == JOB_STATUS[0][0]:
                if first_v[0].change_author == user:
                    return True
                if user.extended.role == USER_ROLES[2][0]:
                    return True
        return False
    elif action == 'remove' and job:
        notedit_status = [JOB_STATUS[1][0], JOB_STATUS[2][0], JOB_STATUS[3][0]]
        first_version = job.jobhistory_set.filter(version=1)
        if len(first_version) and len(job.children_set.all()) == 0:
            if user.extended.role == USER_ROLES[2][0]:
                return True
            try:
                status = job.jobstatus.status
            except ObjectDoesNotExist:
                return False
            if status in notedit_status:
                return False
            if first_version[0].change_author == user:
                return True
    return False
