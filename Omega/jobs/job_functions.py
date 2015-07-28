# coding: utf-8

import os
import tarfile
import hashlib
from io import BytesIO
from datetime import datetime
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.files import File as NewFile
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _, string_concat
from Omega.vars import USER_ROLES, JOB_ROLES, JOB_STATUS, FORMAT
from jobs.models import FileSystem, File, UserRole
from jobs.job_model import Job, JobHistory, JobStatus


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
    'parent_id': string_concat(_('Parent'), '/', _('Identifier')),
    'role': _('Your role'),
}

DOWNLOAD_LOCKFILE = 'download.lock'


class JobAccess(object):

    def __init__(self, user, job=None):
        self.job = job
        self.__is_author = False
        self.__job_role = None
        self.__user_role = user.extended.role
        self.__get_prop(user)

    def can_view(self):
        if self.job is None:
            return False
        if self.__user_role == USER_ROLES[2][0] or self.__is_author or \
           self.__job_role != JOB_ROLES[0][0]:
            return True
        return False

    def can_create(self):
        return self.__user_role != USER_ROLES[0][0]

    def can_edit(self):
        if self.job is None:
            return False
        if self.__user_role == USER_ROLES[0][0]:
            return False
        try:
            status = self.job.jobstatus.status
        except ObjectDoesNotExist:
            return False
        if status == JOB_STATUS[0][0]:
            if self.__is_author or self.__user_role == USER_ROLES[2][0]:
                return True
        return False

    def can_delete(self):
        if self.job is None:
            return False
        if len(self.job.children_set.all()) == 0:
            if self.__user_role == USER_ROLES[2][0]:
                return True
            try:
                status = self.job.jobstatus.status
            except ObjectDoesNotExist:
                return False
            if status in [js[0] for js in JOB_STATUS[1:4]]:
                return False
            if self.__is_author:
                return True
        return False

    def __get_prop(self, user):
        if self.job is not None:
            first_version = self.job.jobhistory_set.filter(version=1)[0]
            self.__is_author = (first_version.change_author == user)
            job_versions = self.job.jobhistory_set.all().order_by(
                '-change_date')[0]
            last_v_role = job_versions.userrole_set.filter(user=user)
            if len(last_v_role) > 0:
                self.__job_role = last_v_role[0].role
            else:
                self.__job_role = self.job.global_role


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
                        return _("Saving folder failed")
                    try:
                        parent = FileSystem.objects.get(pk=parent_pk, file=None)
                    except ObjectDoesNotExist:
                        return _("Saving folder failed")
                    fs_elem.parent = parent
                if lvl_elem['type'] == '1':
                    try:
                        fs_elem.file = File.objects.get(
                            hash_sum=lvl_elem['hash_sum']
                        )
                    except ObjectDoesNotExist:
                        return _("The file was not uploaded")
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
                if not all(ord(c) < 128 for c in fd['title']):
                    title_size = len(fd['title'])
                    if title_size > 30:
                        fd['title'] = fd['title'][(title_size - 30):]
                if fd['type'] == '1' and fd['hash_sum'] is None:
                    return _("The file was not uploaded")
                names_of_lvl.append(fd['title'])
            for name in names_of_lvl:
                if names_of_lvl.count(name) != 1:
                    return _("You can't use the same names in one folder")
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


class ReadZipJob(object):

    def __init__(self, parent, user, zip_archive):
        self.costyl = 1
        self.parent = parent
        self.job_id = None
        self.user = user
        self.zip_file = zip_archive
        self.err_message = self.__create_job_from_tar()

    def __create_job_from_tar(self):
        inmemory = BytesIO(self.zip_file.read())
        jobzip_file = tarfile.open(fileobj=inmemory, mode='r')
        job_title = ''
        job_description = ''
        job_configuration = ''
        job_format = None
        file_data = []
        for f in jobzip_file.getmembers():
            file_name = f.name
            file_obj = jobzip_file.extractfile(f)
            if file_name == 'configuration':
                job_configuration = file_obj.read().decode('utf-8')
            elif file_name == 'description':
                job_description = file_obj.read().decode('utf-8')
            elif file_name == 'format':
                job_format = file_obj.read().decode('utf-8')
                if int(job_format) != FORMAT:
                    return _("Job format is not supported!")
            elif file_name == 'title':
                job_title = file_obj.read().decode('utf-8')
                if len(job_title) == 0:
                    return _("Job title is empty!")
            elif file_name.startswith('root/'):
                if f.isreg():
                    file_content = BytesIO(file_obj.read())
                    check_sum = hashlib.md5(file_content.read()).hexdigest()
                    file_in_db = File.objects.filter(hash_sum=check_sum)
                    if len(file_in_db) == 0:
                        db_file = File()
                        db_file.file.save(
                            os.path.basename(file_name),
                            NewFile(file_content)
                        )
                        db_file.hash_sum = check_sum
                        db_file.save()
                    file_data.append([file_name, check_sum])
                else:

                    file_data.append([file_name, None])
        if job_format is None:
            return _("Can't detect job format.")

        def create_filesystem(filedata):
            fulldata = {}
            for fd in filedata:
                dir_list = []
                dir_name = fd[0][len('root/'):]
                while len(dir_name) > 0:
                    (dir_name, d) = os.path.split(dir_name)
                    dir_list.insert(0, d)
                prev_parent = None
                for i in range(0, len(dir_list)):
                    fdid = '#'.join(dir_list[:(i + 1)])
                    curr_id = hashlib.md5(fdid.encode('utf-8')).hexdigest()
                    if curr_id not in fulldata:
                        fulldata[curr_id] = {
                            'title': dir_list[i],
                            'type': '0',
                            'id': curr_id,
                            'parent': prev_parent,
                            'hash_sum': None
                        }
                        if fd[1] is not None and i == len(dir_list) - 1:
                            fulldata[curr_id]['hash_sum'] = fd[1]
                            fulldata[curr_id]['type'] = '1'
                    prev_parent = curr_id
            return list(fulldata[x] for x in fulldata)

        job = create_job({
            'name': job_title,
            'author': self.user,
            'configuration': job_configuration,
            'description': job_description,
            'parent': self.parent,
            'filedata': create_filesystem(file_data)
        })
        if isinstance(job, Job):
            self.job_id = job.pk
            return None
        return _("One of the jobs was not saved!")


# For first lock: job = None, hash_sum = None, user != None;
#  if first_lock return True self.hash_sum =- hash_sum in lock file.
# After it create JobArchive with job != None, hash_sum != None
# and call create_tar(); then read tar archive from 'memory'.
class JobArchive(object):

    def __init__(self, job=None, hash_sum=None, user=None):
        self.costyl = 1
        self.lockfile = DOWNLOAD_LOCKFILE
        self.workdir = 'TARcreation'
        self.jobtar_name = ''
        self.job = job
        self.user = user
        self.hash_sum = hash_sum
        self.__prepare_workdir()
        self.memory = BytesIO()

    def first_lock(self):
        f = open(self.lockfile, 'r')
        line = f.readline()
        f.close()
        curr_time = (datetime.now() - datetime(2000, 1, 1)).total_seconds()
        if line == 'unlocked':
            self.__update_hash_sum()
            if self.hash_sum:
                f = open(self.lockfile, 'w')
                f.write('locked#' + str(curr_time) + '#' + self.hash_sum)
                f.close()
                return True
        elif line.startswith('locked#'):
            line_lock_time = float(line.split('#')[1])
            if (curr_time - line_lock_time) > 10:
                self.__update_hash_sum()
                if self.hash_sum:
                    f = open(self.lockfile, 'w')
                    f.write('locked#' + str(curr_time) + '#' + self.hash_sum)
                    f.close()
                    return True
        return False

    def create_tar(self):
        if self.job is None:
            return False

        if self.__second_lock():

            def __write_file_str(jobtar, file_name, file_content):
                file_content = file_content.encode('utf-8')
                t = tarfile.TarInfo(file_name)
                t.size = len(file_content)
                jobtar.addfile(t, BytesIO(file_content))

            self.jobtar_name = 'VJ__' + self.job.identifier + '.tar.gz'
            jobtar_obj = tarfile.open(fileobj=self.memory, mode='w:gz')
            __write_file_str(
                jobtar_obj, 'title', self.job.name
            )
            __write_file_str(
                jobtar_obj, 'configuration', self.job.configuration
            )
            __write_file_str(
                jobtar_obj, 'description', self.job.description
            )
            __write_file_str(
                jobtar_obj, 'format', str(self.job.format)
            )
            for f in self.__get_filedata():
                if f['src'] is None:
                    folder = tarfile.TarInfo(f['path'])
                    folder.type = tarfile.DIRTYPE
                    jobtar_obj.addfile(folder)
                else:
                    jobtar_obj.add(f['src'], f['path'])
            jobtar_obj.close()
            self.__unlock()
            return True
        return False

    def __prepare_workdir(self):
        self.workdir = os.path.join(settings.MEDIA_ROOT, self.workdir)
        if not os.path.isdir(self.workdir):
            os.mkdir(self.workdir)
        self.lockfile = os.path.join(self.workdir, self.lockfile)
        if not os.path.isfile(self.lockfile):
            f = open(self.lockfile, 'w')
            f.write('unlocked')
            f.close()

    def __update_hash_sum(self):
        if self.user:
            hash_data = (
                '%s%s' % (self.user.extended.pk, datetime.now().isoformat())
            ).encode('utf-8')
            self.hash_sum = hashlib.md5(hash_data).hexdigest()

    def __second_lock(self):
        f = open(self.lockfile, 'r')
        line = f.readline()
        f.close()
        line_data = line.split('#')
        if len(line_data) == 3 and line_data[0] == 'locked':
            if self.hash_sum == line_data[2]:
                f = open(self.lockfile, 'w')
                f.write('doublelocked')
                f.close()
                return True
        return False

    def __unlock(self):
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
        files_for_tar = []
        for f in files:
            if len(f.children_set.all()) == 0:
                src = None
                if f.file is not None:
                    src = os.path.join(settings.MEDIA_ROOT, f.file.file.name)
                file_path = f.name
                file_parent = f.parent
                while file_parent is not None:
                    file_path = file_parent.name + '/' + file_path
                    file_parent = file_parent.parent
                files_for_tar.append({
                    'path': 'root' + '/' + file_path,
                    'src': src
                })
        return files_for_tar


def convert_time(val, acc):
    new_time = int(val)
    time_format = "%%1.%df %%s" % int(acc)
    try_div = new_time / 1000
    if try_div < 1:
        return time_format % (new_time, _('ms'))
    new_time = try_div
    try_div = new_time / 60
    if try_div < 1:
        return time_format % (new_time, _('s'))
    new_time = try_div
    try_div = new_time / 60
    if try_div < 1:
        return time_format % (new_time, _('min'))
    return time_format % (try_div, _('h'))


def convert_memory(val, acc):
    new_mem = int(val)
    mem_format = "%%1.%df %%s" % int(acc)
    try_div = new_mem / 1024
    if try_div < 1:
        return mem_format % (new_mem, _('B'))
    new_mem = try_div
    try_div = new_mem / 1024
    if try_div < 1:
        return mem_format % (new_mem, _('KiB'))
    new_mem = try_div
    try_div = new_mem / 1024
    if try_div < 1:
        return mem_format % (new_mem, _('MiB'))
    return mem_format % (try_div, _('GiB'))


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
    return roles_data


def is_operator(user, job):
    last_version = job.jobhistory_set.get(version=job.version)
    user_role = last_version.userrole_set.filter(user=user)
    if len(user_role):
        if user_role[0].role in [JOB_ROLES[3][0], JOB_ROLES[4][0]]:
            return True
        return False
    if job.global_role in [JOB_ROLES[3][0], JOB_ROLES[4][0]]:
        return True
    return False


def create_version(job, comment=None):
    new_version = JobHistory()
    new_version.job = job
    new_version.name = job.name
    new_version.description = job.description
    if comment is not None:
        new_version.comment = comment
    new_version.configuration = job.configuration
    new_version.global_role = job.global_role
    new_version.type = job.type
    new_version.change_author = job.change_author
    new_version.change_date = job.change_date
    new_version.format = job.format
    new_version.version = job.version
    new_version.parent = job.parent
    new_version.save()
    return new_version


def create_job(kwargs):
    newjob = Job()
    if 'name' not in kwargs or \
            len(kwargs['name']) == 0 or 'author' not in kwargs:
        return _("Name and author are required")
    creation_comment = ''
    if 'parent' in kwargs:
        newjob.parent = kwargs['parent']
        newjob.type = kwargs['parent'].type
        newjob.format = kwargs['parent'].format
        creation_comment = "Make copy of %s" % kwargs['parent'].identifier
    elif 'type' in kwargs:
        newjob.type = kwargs['type']
    else:
        return _("Parent or job type are required")
    if 'pk' in kwargs:
        try:
            Job.objects.get(pk=int(kwargs['pk']))
        except ObjectDoesNotExist:
            newjob.pk = int(kwargs['pk'])
    newjob.name = kwargs['name']
    newjob.change_author = kwargs['author']
    if 'configuration' in kwargs:
        newjob.configuration = kwargs['configuration']
    if 'description' in kwargs:
        newjob.description = kwargs['description']
    if 'global_role' in kwargs and \
            kwargs['global_role'] in list(x[0] for x in JOB_ROLES):
        newjob.global_role = kwargs['global_role']
    time_encoded = datetime.now().strftime(
        "%Y%m%d%H%M%S%f%z"
    ).encode('utf-8')
    newjob.identifier = hashlib.md5(time_encoded).hexdigest()
    newjob.save()
    jobstatus = JobStatus()
    jobstatus.job = newjob
    jobstatus.save()
    new_version = create_version(newjob, creation_comment)
    if 'user_roles' in kwargs:
        for ur in kwargs['user_roles']:
            ur_user = User.objects.filter(pk=int(ur['user']))
            if len(ur_user):
                new_ur = UserRole()
                new_ur.job = new_version
                new_ur.user = ur_user[0]
                new_ur.role = ur['role']
                new_ur.save()
    if 'filedata' in kwargs:
        db_fdata = DBFileData(kwargs['filedata'], new_version)
        if db_fdata.err_message is not None:
            newjob.delete()
            return db_fdata.err_message
    return newjob


def update_job(kwargs):
    if any(x not in kwargs for x in ['author', 'comment']):
        return _('Author and comment are required')
    if len(kwargs['comment']) == 0:
        return _('Comment is required')
    kwargs['job'].change_author = kwargs['author']
    if 'name' in kwargs:
        kwargs['job'].name = kwargs['name']
    if 'parent' in kwargs:
        kwargs['job'].parent = kwargs['parent']
    if 'configuration' in kwargs:
        kwargs['job'].configuration = kwargs['configuration']
    if 'description' in kwargs:
        kwargs['job'].description = kwargs['description']
    if 'global_role' in kwargs and \
            kwargs['global_role'] in list(x[0] for x in JOB_ROLES):
        kwargs['job'].global_role = kwargs['global_role']
    kwargs['job'].version += 1
    kwargs['job'].save()
    newversion = create_version(kwargs['job'], kwargs['comment'])
    if 'user_roles' in kwargs:
        for ur in kwargs['user_roles']:
            ur_user = User.objects.filter(pk=int(ur['user']))
            if len(ur_user):
                new_ur = UserRole()
                new_ur.job = newversion
                new_ur.user = ur_user[0]
                new_ur.role = ur['role']
                new_ur.save()
    if 'filedata' in kwargs:
        db_fdata = DBFileData(kwargs['filedata'], newversion)
        if db_fdata.err_message is not None:
            newversion.delete()
            kwargs['job'].version -= 1
            kwargs['job'].save()
            return db_fdata.err_message
    return kwargs['job']


def remove_jobs_by_id(user, job_ids):
    jobs = []
    for job_id in job_ids:
        try:
            jobs.append(Job.objects.get(pk=job_id))
        except ObjectDoesNotExist:
            return 404
    for job in jobs:
        if not JobAccess(user, job).can_delete():
            return 400
    for job in jobs:
        job.delete()
    return 0


def check_new_parent(job, parent):
    if job.type != parent.type:
        return False
    if job.parent == parent:
        return True
    while parent is not None:
        if parent == job:
            return False
        parent = parent.parent
    return True
