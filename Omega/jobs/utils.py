import hashlib
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _, string_concat
from django.utils.timezone import now
from Omega.vars import USER_ROLES, JOB_ROLES, JOB_STATUS
from Omega.utils import print_err
from jobs.models import Job, JobHistory, FileSystem, File, UserRole
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
    'resource': _('Consumed resources'),
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
    'priority': _('Priority'),
    'start_date': _('Decision start date'),
    'finish_date': _('Decision finish date'),
    'solution_wall_time': _('Decision wall time'),
    'operator': _('Operator'),
    'tasks_pending': _('Pending tasks'),
    'tasks_processing': _('Processing tasks'),
    'tasks_finished': _('Finished tasks'),
    'tasks_error': _('Error tasks'),
    'tasks_cancelled': _('Cancelled tasks'),
    'tasks_total': _('Total tasks'),
    'progress': _('Progress of job decision'),
    'solutions': _('Number of task decisions')
}


class JobAccess(object):

    def __init__(self, user, job=None):
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

    def psi_access(self):
        if self.job is None:
            return False
        return self.__is_manager or self.__is_service

    def can_decide(self):
        if self.job is None or self.job.status in [JOB_STATUS[1][0], JOB_STATUS[2][0]]:
            return False
        # TODO: can author decide the job?
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
        return (self.job.status not in [JOB_STATUS[1][0], JOB_STATUS[2][0]]
                and (self.__is_author or self.__is_manager))

    def can_stop(self):
        if self.job is None:
            return False
        if self.job.status in [JOB_STATUS[1][0], JOB_STATUS[2][0]] \
                and (self.__is_operator or self.__is_manager):
            return True
        return False

    def can_delete(self):
        if self.job is None:
            return False
        if len(self.job.children.all()) > 0:
            return False
        if self.__is_manager and self.job.status == JOB_STATUS[3]:
            return True
        if self.job.status in [js[0] for js in JOB_STATUS[1:2]]:
            return False
        return self.__is_author or self.__is_manager

    def can_download(self):
        return not (self.job is None or self.job.status in [JOB_STATUS[2][0], JOB_STATUS[5][0], JOB_STATUS[6][0]])

    def __get_prop(self, user):
        if self.job is not None:
            try:
                first_version = self.job.versions.get(version=1)
                last_version = self.job.versions.get(
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
        for f in job.filesystem_set.all().order_by('name'):
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


class SaveFileData(object):

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
    job_author = job.job.versions.get(version=1).change_author

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

    time_encoded = now().strftime("%Y%m%d%H%M%S%f%z").encode('utf-8')
    newjob.identifier = hashlib.md5(time_encoded).hexdigest()
    newjob.save()

    new_version = create_version(newjob, kwargs)

    if 'filedata' in kwargs:
        db_fdata = SaveFileData(kwargs['filedata'], new_version)
        if db_fdata.err_message is not None:
            newjob.delete()
            return db_fdata.err_message
    if 'absolute_url' in kwargs:
        newjob_url = reverse('jobs:job', args=[newjob.pk])
        try:
            Notify(newjob, 0, {
                'absurl': kwargs['absolute_url'] + newjob_url
            })
        except Exception as e:
            print_err("Can't notify users: %s" % e)
    else:
        try:
            Notify(newjob, 0)
        except Exception as e:
            print_err("Can't notify users: %s" % e)
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
        db_fdata = SaveFileData(kwargs['filedata'], newversion)
        if db_fdata.err_message is not None:
            newversion.delete()
            kwargs['job'].version -= 1
            kwargs['job'].save()
            return db_fdata.err_message
    if 'absolute_url' in kwargs:
        try:
            Notify(kwargs['job'], 1, {'absurl': kwargs['absolute_url']})
        except Exception as e:
            print_err("Can't notify users: %s" % e)
    else:
        try:
            Notify(kwargs['job'], 1)
        except Exception as e:
            print_err("Can't notify users: %s" % e)
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
        try:
            Notify(job, 2)
        except Exception as e:
            print_err("Can't notify users: %s" % e)
        job.delete()
    clear_files()
    return 0


def delete_versions(job, versions):
    access_versions = []
    for v in versions:
        v = int(v)
        if v != 1 and v != job.version:
            access_versions.append(v)
    checked_versions = job.versions.filter(version__in=access_versions)
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


def get_user_time(user, milliseconds):
    accuracy = user.extended.accuracy
    converted = int(milliseconds)
    if user.extended.data_format == 'hum':
        converted = convert_time(converted, accuracy)
    return converted
