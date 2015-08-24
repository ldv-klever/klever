# coding: utf-8

import os
import json
import tarfile
import hashlib
from io import BytesIO
from datetime import datetime
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.core.files import File as NewFile
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _, string_concat,\
    override
from Omega.vars import USER_ROLES, JOB_CLASSES, JOB_ROLES, JOB_STATUS, FORMAT
from jobs.models import Job, JobHistory, FileSystem, File, UserRole,\
    JOBFILE_DIR
from users.notifications import Notify


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
        self.__is_manager = (self.__user_role == USER_ROLES[2][0])
        self.__is_expert = (self.__user_role == USER_ROLES[3][0])
        self.__get_prop(user)

    def can_download_for_deciding(self):
        if self.job is None:
            return False
        if self.__is_manager or self.__is_author:
            return True
        if self.__job_role in [JOB_ROLES[3][0], JOB_ROLES[4][0]]:
            return True
        return False

    def can_view(self):
        if self.job is None:
            return False
        if self.__is_manager or self.__is_author or \
           self.__job_role != JOB_ROLES[0][0] or self.__is_expert:
            return True
        return False

    def can_create(self):
        return self.__user_role != USER_ROLES[0][0]

    def can_edit(self):
        if self.job is None:
            return False
        if self.job.status not in [JOB_STATUS[1][0], JOB_STATUS[2][0]] and \
                (self.__is_author or self.__is_manager):
            return True
        return False

    def can_delete(self):
        if self.job is None:
            return False
        if len(self.job.children_set.all()) > 0:
            return False
        if self.__is_manager:
            return True
        if self.job.status in [js[0] for js in JOB_STATUS[1:3]]:
            return False
        if self.__is_author:
            return True
        return False

    def __get_prop(self, user):
        if self.job is not None:
            try:
                first_version = self.job.jobhistory_set.get(version=1)
                last_version = self.job.jobhistory_set.get(
                    version=self.job.version)
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
                if not all(ord(c) < 128 for c in lvl_elem['title']):
                    t_size = len(lvl_elem['title'])
                    if t_size > 30:
                        lvl_elem['title'] = lvl_elem['title'][(t_size - 30):]
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
            names_with_parents = []
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
                if [fd['title'], fd['parent']] in names_with_parents:
                    return _("You can't use the same names in one folder")
                names_of_lvl.append(fd['title'])
                names_with_parents.append([fd['title'], fd['parent']])
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
        self.parent = parent
        self.job_id = None
        self.user = user
        self.zip_file = zip_archive
        self.err_message = self.__create_job_from_tar()

    def __create_job_from_tar(self):
        inmemory = BytesIO(self.zip_file.read())
        jobzip_file = tarfile.open(fileobj=inmemory, mode='r')
        job_format = None
        job_type = None
        files_map = {}
        files_in_db = {}
        versions_data = {}
        for f in jobzip_file.getmembers():
            file_name = f.name
            file_obj = jobzip_file.extractfile(f)
            if file_name == 'format':
                job_format = int(file_obj.read().decode('utf-8'))
                if job_format != FORMAT:
                    return _("The job format is not supported")
            elif file_name == 'type':
                job_type = file_obj.read().decode('utf-8')
                if job_type != self.parent.type:
                    return _("The job class does not equal to the parent class")
            elif file_name == 'filedata':
                files_map = json.loads(file_obj.read().decode('utf-8'))
            elif file_name.startswith(JOBFILE_DIR):
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
                    files_in_db[file_name] = check_sum
            elif file_name.startswith('version-'):
                version_id = int(file_name.replace('version-', ''))
                versions_data[version_id] = json.loads(
                    file_obj.read().decode('utf-8'))

        for f_id in files_map:
            if files_map[f_id] in files_in_db:
                files_map[f_id] = files_in_db[files_map[f_id]]
            else:
                return _("The job archive is corrupted")
        if job_format is None:
            return _("Couldn't find the job format")
        if job_type is None:
            return _("Couldn't find the job class")

        version_list = list(versions_data[v] for v in sorted(versions_data))
        for i in range(0, len(version_list)):
            filedata = []
            for file in version_list[i]['filedata']:
                fdata_elem = {
                    'title': file['name'],
                    'id': file['pk'],
                    'type': '0',
                    'parent': file['parent'],
                    'hash_sum': None
                }
                if file['file'] is not None:
                    if str(file['file']) in files_map:
                        fdata_elem['type'] = '1'
                        fdata_elem['hash_sum'] = files_map[str(file['file'])]
                    else:
                        return _("The job archive is corrupted")
                filedata.append(fdata_elem)
            version_list[i]['filedata'] = filedata
        job = create_job({
            'name': version_list[0]['name'],
            'author': self.user,
            'description': version_list[0]['description'],
            'parent': self.parent,
            'type': self.parent.type,
            'global_role': version_list[0]['global_role'],
            'filedata': version_list[0]['filedata'],
            'comment': version_list[0]['comment']
        })
        if not isinstance(job, Job):
            return job
        for version_data in version_list[1:]:
            updated_job = update_job({
                'job': job,
                'name': version_data['name'],
                'author': self.user,
                'description': version_data['description'],
                'parent': self.parent,
                'type': self.parent.type,
                'filedata': version_data['filedata'],
                'global_role': version_data['global_role'],
                'comment': version_data['comment']
            })
            if not isinstance(updated_job, Job):
                job.delete()
                return updated_job
        self.job_id = job.pk
        return None


# For first lock: job = None, hash_sum = None, user != None;
#  if first_lock return True self.hash_sum =- hash_sum in lock file.
# After it create JobArchive with job != None, hash_sum != None
# and call create_tar(); then read tar archive from 'memory'.
class JobArchive(object):

    def __init__(self, job=None, hash_sum=None, user=None, full=True):
        self.lockfile = DOWNLOAD_LOCKFILE
        self.full = full
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
            if self.full:
                self.__full_tar()
            else:
                self.__normal_tar()
            self.__unlock()
            return True
        return False

    def __normal_tar(self):
        last_version = self.job.jobhistory_set.get(version=self.job.version)

        def write_file_str(jobtar, file_name, file_content):
            file_content = file_content.encode('utf-8')
            t = tarfile.TarInfo(file_name)
            t.size = len(file_content)
            jobtar.addfile(t, BytesIO(file_content))

        files_for_tar = []
        for f in last_version.file_set.all():
            if len(f.children_set.all()) == 0:
                src = None
                if f.file is not None:
                    src = os.path.join(
                        settings.MEDIA_ROOT, f.file.file.name)
                file_path = f.name
                file_parent = f.parent
                while file_parent is not None:
                    file_path = file_parent.name + '/' + file_path
                    file_parent = file_parent.parent
                files_for_tar.append({
                    'path': 'root' + '/' + file_path,
                    'src': src
                })

        self.jobtar_name = 'VJ__' + self.job.identifier + '.tar.gz'
        jobtar_obj = tarfile.open(fileobj=self.memory, mode='w:gz')
        write_file_str(jobtar_obj, 'format', str(self.job.format))
        for job_class in JOB_CLASSES:
            if job_class[0] == self.job.type:
                with override('en'):
                    write_file_str(jobtar_obj, 'class', job_class[1])
                break
        for f in files_for_tar:
            if f['src'] is None:
                folder = tarfile.TarInfo(f['path'])
                folder.type = tarfile.DIRTYPE
                jobtar_obj.addfile(folder)
            else:
                jobtar_obj.add(f['src'], f['path'])
        jobtar_obj.close()

    def __full_tar(self):

        def write_file_str(jobtar, file_name, file_content):
            file_content = file_content.encode('utf-8')
            t = tarfile.TarInfo(file_name)
            t.size = len(file_content)
            jobtar.addfile(t, BytesIO(file_content))

        files_in_tar = {}
        self.jobtar_name = 'VJ__' + self.job.identifier + '.tar.gz'
        jobtar_obj = tarfile.open(fileobj=self.memory, mode='w:gz')
        for jobversion in self.job.jobhistory_set.all():
            filedata = []
            for f in jobversion.file_set.all():
                filedata_element = {
                    'pk': f.pk,
                    'parent': f.parent_id,
                    'name': f.name,
                    'file': None
                }
                if f.file is not None:
                    filedata_element['file'] = f.file.pk
                    if f.file.pk not in files_in_tar:
                        files_in_tar[f.file.pk] = f.file.file.name
                        jobtar_obj.add(
                            os.path.join(settings.MEDIA_ROOT, f.file.file.name),
                            f.file.file.name)
                filedata.append(filedata_element)
            version_data = {
                'filedata': filedata,
                'description': jobversion.description,
                'name': jobversion.name,
                'global_role': jobversion.global_role,
                'comment': jobversion.comment,
            }
            write_file_str(jobtar_obj, 'version-%s' % jobversion.version,
                           json.dumps(version_data))

        write_file_str(jobtar_obj, 'format', str(self.job.format))
        write_file_str(jobtar_obj, 'type', str(self.job.type))
        write_file_str(jobtar_obj, 'filedata', json.dumps(files_in_tar))
        jobtar_obj.close()

    def __prepare_workdir(self):
        self.lockfile = os.path.join(settings.MEDIA_ROOT, self.lockfile)
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


def role_info(job, user):
    roles_data = {'global': job.global_role}

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


def create_version(job, kwargs):
    new_version = JobHistory()
    new_version.job = job
    new_version.parent = job.parent
    new_version.version = job.version
    new_version.change_author = job.change_author
    new_version.change_date = job.change_date
    new_version.name = job.name
    if 'comment' in kwargs:
        new_version.comment = kwargs['comment']
    if 'global_role' in kwargs and \
            kwargs['global_role'] in list(x[0] for x in JOB_ROLES):
        new_version.global_role = kwargs['global_role']
    if 'description' in kwargs:
        new_version.description = kwargs['description']
    new_version.save()
    if 'user_roles' in kwargs:
        for ur in kwargs['user_roles']:
            try:
                ur_user = User.objects.get(pk=int(ur['user']))
            except ObjectDoesNotExist:
                continue
            new_ur = UserRole()
            new_ur.job = new_version
            new_ur.user = ur_user
            new_ur.role = ur['role']
            new_ur.save()
    return new_version


def create_job(kwargs):
    newjob = Job()
    if 'name' not in kwargs or len(kwargs['name']) == 0:
        return _("Job title is required")
    if 'author' not in kwargs or not isinstance(kwargs['author'], User):
        return _("Job author is required")
    newjob.name = kwargs['name']
    newjob.change_author = kwargs['author']
    if 'parent' in kwargs:
        newjob.parent = kwargs['parent']
        newjob.type = kwargs['parent'].type
        kwargs['comment'] = "Make copy of %s" % kwargs['parent'].identifier
    elif 'type' in kwargs:
        newjob.type = kwargs['type']
    else:
        return _("The parent or the job class are required")
    if 'pk' in kwargs:
        try:
            Job.objects.get(pk=int(kwargs['pk']))
        except ObjectDoesNotExist:
            newjob.pk = int(kwargs['pk'])

    time_encoded = datetime.now().strftime(
        "%Y%m%d%H%M%S%f%z"
    ).encode('utf-8')
    newjob.identifier = hashlib.md5(time_encoded).hexdigest()
    newjob.save()

    new_version = create_version(newjob, kwargs)

    if 'filedata' in kwargs:
        db_fdata = DBFileData(kwargs['filedata'], new_version)
        if db_fdata.err_message is not None:
            newjob.delete()
            return db_fdata.err_message
    if 'absolute_url' in kwargs:
        newjob_url = reverse('jobs:job', args=[newjob.pk])
        Notify(newjob, 0, {
            'absurl': kwargs['absolute_url'] + newjob_url
        })
    else:
        Notify(newjob, 0)
    return newjob


def update_job(kwargs):
    if 'job' not in kwargs or not isinstance(kwargs['job'], Job):
        return _("Unknown error")
    if 'author' not in kwargs or not isinstance(kwargs['author'], User):
        return _("Change author is required")
    if 'comment' not in kwargs or len(kwargs['comment']) == 0:
        return _("Change comment is required")
    if 'parent' in kwargs:
        kwargs['job'].parent = kwargs['parent']
    if 'name' in kwargs and len(kwargs['name']) > 0:
        kwargs['job'].name = kwargs['name']
    kwargs['job'].change_author = kwargs['author']
    kwargs['job'].version += 1
    kwargs['job'].save()

    newversion = create_version(kwargs['job'], kwargs)

    if 'filedata' in kwargs:
        db_fdata = DBFileData(kwargs['filedata'], newversion)
        if db_fdata.err_message is not None:
            newversion.delete()
            kwargs['job'].version -= 1
            kwargs['job'].save()
            return db_fdata.err_message
    if 'absolute_url' in kwargs:
        Notify(kwargs['job'], 1, {'absurl': kwargs['absolute_url']})
    else:
        Notify(kwargs['job'], 1)
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
        Notify(job, 2)
        job.delete()
    clear_files()
    return 0


def delete_versions(job, versions):
    access_versions = []
    for v in versions:
        v = int(v)
        if v != 1 and v != job.version:
            access_versions.append(v)
    checked_versions = job.jobhistory_set.filter(version__in=access_versions)
    num_of_deleted = len(checked_versions)
    checked_versions.delete()
    clear_files()
    return num_of_deleted


def clear_files():
    for file in File.objects.all():
        if len(file.filesystem_set.all()) == 0:
            file.delete()


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


def get_resource_data(user, resource):
    accuracy = user.extended.accuracy
    cpu = resource.cpu_time
    wall = resource.wall_time
    mem = resource.memory
    if user.extended.data_format == 'hum':
        wall = convert_time(wall, accuracy)
        cpu = convert_time(cpu, accuracy)
        mem = convert_memory(mem, accuracy)
    return [wall, cpu, mem]
