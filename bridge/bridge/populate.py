import os
import json
import hashlib
from time import sleep
from types import FunctionType
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.files import File as NewFile
from django.db.models import Q
from django.utils.translation import override
from django.utils.timezone import now
from bridge.vars import JOB_CLASSES, SCHEDULER_TYPE, USER_ROLES, JOB_ROLES, MARK_STATUS
from bridge.settings import DEFAULT_LANGUAGE, BASE_DIR
from bridge.utils import print_err
from users.models import Extended
from jobs.utils import create_job
from jobs.models import Job, File
from marks.models import MarkUnsafeCompare, MarkUnsafeConvert
from marks.ConvertTrace import ConvertTrace
from marks.CompareTrace import CompareTrace
from service.models import Scheduler

JOB_SETTINGS_FILE = 'settings.json'


class Population(object):

    def __init__(self, user=None, manager=None, service=None):
        self.changes = {}
        self.user = user
        self.manager = self.__get_manager(manager)
        self.__population()
        self.__add_service_user(service)

    def __population(self):
        if self.user is not None:
            try:
                self.user.extended
            except ObjectDoesNotExist:
                self.__extend_user(self.user)
        self.__populate_functions()
        if len(Job.objects.filter(parent=None)) < 3:
            self.__populate_jobs()
        self.__populate_default_jobs()
        self.__populate_unknown_marks()
        sch_crtd1 = Scheduler.objects.get_or_create(type=SCHEDULER_TYPE[0][0])[1]
        sch_crtd2 = Scheduler.objects.get_or_create(type=SCHEDULER_TYPE[1][0])[1]
        self.changes['schedulers'] = (sch_crtd1 or sch_crtd2)

    def __populate_functions(self):
        func_names = []
        for func_name in [x for x, y in ConvertTrace.__dict__.items()
                          if type(y) == FunctionType and not x.startswith('_')]:
            func_names.append(func_name)
            description = self.__correct_description(getattr(ConvertTrace, func_name).__doc__)
            func, crtd = MarkUnsafeConvert.objects.get_or_create(name=func_name)
            if crtd or description != func.description:
                self.changes['functions'] = True
                func.description = description
                func.save()
        MarkUnsafeConvert.objects.filter(~Q(name__in=func_names)).delete()
        func_names = []
        for func_name in [x for x, y in CompareTrace.__dict__.items()
                          if type(y) == FunctionType and not x.startswith('_')]:
            func_names.append(func_name)
            description = self.__correct_description(getattr(CompareTrace, func_name).__doc__)
            func, crtd = MarkUnsafeCompare.objects.get_or_create(name=func_name)
            if crtd or description != func.description:
                self.changes['functions'] = True
                func.description = description
                func.save()
        MarkUnsafeCompare.objects.filter(~Q(name__in=func_names)).delete()

    def __correct_description(self, descr):
        self.ccc = 0
        descr_strs = descr.split('\n')
        new_descr_strs = []
        for s in descr_strs:
            if len(s) > 0 and len(s.split()) > 0:
                new_descr_strs.append(s)
        return '\n'.join(new_descr_strs)

    def __extend_user(self, user, role=USER_ROLES[1][0]):
        self.ccc = 0
        try:
            user.extended.role = role
            user.extended.save()
        except ObjectDoesNotExist:
            Extended.objects.create(first_name='Firstname', last_name='Lastname', role=role, user=user)

    def __get_manager(self, manager_username):
        if manager_username is None:
            try:
                return Extended.objects.filter(role=USER_ROLES[2][0])[0].user
            except IndexError:
                return None
        try:
            manager = User.objects.get(username=manager_username)
        except ObjectDoesNotExist:
            manager = User.objects.create(username=manager_username)
            self.changes['manager'] = {
                'username': manager.username,
                'password': self.__add_password(manager)
            }
        self.__extend_user(manager, USER_ROLES[2][0])
        return manager

    def __add_service_user(self, service_username):
        if service_username is None:
            return
        try:
            self.__extend_user(User.objects.get(username=service_username), USER_ROLES[4][0])
        except ObjectDoesNotExist:
            service = User.objects.create(username=service_username)
            self.__extend_user(service, USER_ROLES[4][0])
            self.changes['service'] = {
                'username': service.username,
                'password': self.__add_password(service)
            }

    def __add_password(self, user):
        self.ccc = 0
        password = hashlib.md5(now().strftime("%Y%m%d%H%M%S%f%z").encode('utf8')).hexdigest()[:8]
        user.set_password(password)
        user.save()
        return password

    def __populate_jobs(self):
        if not isinstance(self.manager, User):
            return None
        args = {
            'author': self.manager,
            'global_role': JOB_ROLES[1][0],
        }
        if not isinstance(args['author'], User):
            return
        for i in range(len(JOB_CLASSES)):
            try:
                Job.objects.get(type=JOB_CLASSES[i][0], parent=None)
            except ObjectDoesNotExist:
                with override(DEFAULT_LANGUAGE):
                    args['name'] = JOB_CLASSES[i][1]
                    args['description'] = "<h3>%s</h3>" % JOB_CLASSES[i][1]
                    args['pk'] = i + 1
                    args['type'] = JOB_CLASSES[i][0]
                    create_job(args)
                    sleep(0.1)
                    self.changes['jobs'] = True

    def __populate_default_jobs(self):
        if not isinstance(self.manager, User):
            return None
        default_jobs_dir = os.path.join(BASE_DIR, 'jobs', 'presets')
        for jobdir in [os.path.join(default_jobs_dir, x) for x in os.listdir(default_jobs_dir)]:
            if not os.path.exists(os.path.join(jobdir, JOB_SETTINGS_FILE)):
                print_err('There is default job without settings file')
                continue
            conf = open(os.path.join(jobdir, JOB_SETTINGS_FILE), 'rb')
            try:
                job_settings = json.loads(''.join(conf.read().decode('utf8').split('\n')))
            except Exception as e:
                print_err(e)
                print_err('The default job was not created')
                continue
            if any(x not in job_settings for x in ['name', 'class', 'description']):
                print_err('Default job settings must contain name, class and description')
                continue
            if job_settings['class'] not in list(x[0] for x in JOB_CLASSES):
                print_err('Default job class is wrong. See bridge.vars.JOB_CLASSES for choice ("0", "1" or "2")')
                continue
            if len(job_settings['name']) == 0:
                print_err('Default job name is required')
                continue
            try:
                parent = Job.objects.get(parent=None, type=job_settings['class'])
            except ObjectDoesNotExist:
                print_err('Main jobs were not created')
                continue
            job = create_job({
                'author': self.manager,
                'global_role': '1',
                'name': job_settings['name'],
                'description': job_settings['description'],
                'parent': parent,
                'filedata': self.__get_filedata(jobdir)
            })
            if isinstance(job, Job):
                if 'default_jobs' not in self.changes:
                    self.changes['default_jobs'] = []
                self.changes['default_jobs'].append([job.name, job.identifier])
            sleep(0.1)

    def __get_filedata(self, d):
        self.cnt = 0
        self.dir_info = {d: None}

        def get_fdata(directory):
            fdata = []
            for f in [os.path.join(directory, x) for x in os.listdir(directory)]:
                parent_name, base_f = os.path.split(f)
                if base_f == JOB_SETTINGS_FILE:
                    continue
                self.cnt += 1
                if os.path.isfile(f):
                    fobj = open(f, 'rb')
                    check_sum = hashlib.md5(fobj.read()).hexdigest()
                    try:
                        File.objects.get(hash_sum=check_sum)
                    except ObjectDoesNotExist:
                        db_file = File()
                        db_file.file.save(base_f, NewFile(fobj))
                        db_file.hash_sum = check_sum
                        db_file.save()
                    fdata.append({
                        'id': self.cnt,
                        'parent': self.dir_info[parent_name] if parent_name in self.dir_info else None,
                        'hash_sum': check_sum,
                        'title': base_f,
                        'type': '1'
                    })
                elif os.path.isdir(f):
                    self.dir_info[f] = self.cnt
                    fdata.append({
                        'id': self.cnt,
                        'parent': self.dir_info[parent_name] if parent_name in self.dir_info else None,
                        'hash_sum': None,
                        'title': base_f,
                        'type': '0'
                    })
                    fdata += get_fdata(f)
            return fdata
        return get_fdata(d)

    def __populate_unknown_marks(self):
        if not isinstance(self.manager, User):
            return None
        from marks.models import MarkUnknown, MarkUnknownHistory, Component
        from marks.utils import ConnectMarkWithReports
        presets_dir = os.path.join(BASE_DIR, 'marks', 'presets')
        for component_dir in [os.path.join(presets_dir, x) for x in os.listdir(presets_dir)]:
            component = os.path.basename(component_dir)
            if not 0 < len(component) <= 15:
                print_err('Wrong component length: %s' % component)
            for mark_settings in [os.path.join(component_dir, x) for x in os.listdir(component_dir)]:
                fname = os.path.basename(mark_settings)
                f = open(mark_settings, 'r', encoding='utf8')
                try:
                    data = json.loads(''.join(f.read().split('\n')))
                except Exception as e:
                    print_err(e)
                    continue
                if not isinstance(data, dict) or any(x not in data for x in ['class', 'function', 'pattern']):
                    print_err('Wrong unknown mark data: %s' % fname)
                    continue
                if 'link' not in data:
                    data['link'] = ''
                if 'description' not in data:
                    data['description'] = ''
                if 'status' not in data:
                    data['status'] = MARK_STATUS[0][0]
                if 'is_modifiable' not in data:
                    data['is_modifiable'] = True
                if data['class'] not in list(x[0] for x in JOB_CLASSES) \
                        or data['status'] not in list(x[0] for x in MARK_STATUS) \
                        or len(data['function']) == 0 \
                        or not 0 < len(data['pattern']) <= 15 \
                        or not isinstance(data['is_modifiable'], bool):
                    print_err('Wrong unknown mark data: %s' % fname)
                    continue
                try:
                    MarkUnknown.objects.get(
                        type=data['class'],
                        component__name=component,
                        function=data['function'],
                        problem_pattern=data['pattern']
                    )
                    continue
                except ObjectDoesNotExist:
                    create_args = {
                        'identifier': hashlib.md5(now().strftime("%Y%m%d%H%M%S%f%z").encode('utf8')).hexdigest(),
                        'component': Component.objects.get_or_create(name=component)[0],
                        'type': data['class'],
                        'author': self.manager,
                        'status': data['status'],
                        'is_modifiable': data['is_modifiable'],
                        'function': data['function'],
                        'problem_pattern': data['pattern'],
                        'description': data['description']
                    }
                    if len(data['link']) > 0:
                        create_args['link'] = data['link']
                    try:
                        mark = MarkUnknown.objects.create(**create_args)
                    except Exception as e:
                        print_err(e)
                        continue
                    MarkUnknownHistory.objects.create(
                        mark=mark, version=mark.version, author=mark.author, status=mark.status,
                        function=mark.function, problem_pattern=mark.problem_pattern, link=mark.link,
                        change_date=mark.change_date, description=mark.description, comment=''
                    )
                    ConnectMarkWithReports(mark)
                    self.changes['marks'] = True


# Example argument: {'username': 'myname', 'password': '12345', 'last_name': 'Mylastname', 'first_name': 'Myfirstname'}
# last_name and first_name are not required; username and password are required (for admin password is not required)z
# Returns None if everything is OK, str (error text) in other cases.
def populate_users(admin=None, manager=None, service=None):
    if admin is not None:
        if not isinstance(admin, dict):
            return 'Wrong administrator format'
        if 'username' not in admin or not isinstance(admin['username'], str):
            return 'Administator username is required'
        if 'last_name' not in admin:
            admin['last_name'] = 'Lastname'
        if 'first_name' not in manager:
            admin['first_name'] = 'Firstname'
        try:
            user = User.objects.get(username=admin['username'])
            Extended.objects.create(
                last_name=admin['last_name'],
                first_name=admin['first_name'],
                role=USER_ROLES[1][0],
                user=user
            )
        except ObjectDoesNotExist:
            return 'Administrator with specified username does not exist'
    if manager is not None:
        if not isinstance(manager, dict):
            return 'Wrong manager format'
        if 'password' not in manager or not isinstance(manager['password'], str):
            return 'Manager password is required'
        if 'username' not in manager or not isinstance(manager['username'], str):
            return 'Manager username is required'
        if 'last_name' not in manager:
            manager['last_name'] = 'Lastname'
        if 'first_name' not in manager:
            manager['first_name'] = 'Firstname'
        try:
            User.objects.get(username=manager['username'])
            return 'Manager with specified username already exists'
        except ObjectDoesNotExist:
            newuser = User.objects.create(username=manager['username'])
            newuser.set_password(manager['password'])
            newuser.save()
            Extended.objects.create(
                last_name=manager['last_name'],
                first_name=manager['first_name'],
                role=USER_ROLES[2][0],
                user=newuser
            )
    if service is not None:
        if not isinstance(service, dict):
            return 'Wrong service format'
        if 'password' not in service or not isinstance(service['password'], str):
            return 'Service password is required'
        if 'username' not in service or not isinstance(service['username'], str):
            return 'Service username is required'
        if 'last_name' not in service:
            service['last_name'] = 'Lastname'
        if 'first_name' not in service:
            service['first_name'] = 'Firstname'
        try:
            User.objects.get(username=service['username'])
            return 'Service with specified username already exists'
        except ObjectDoesNotExist:
            newuser = User.objects.create(username=service['username'])
            newuser.set_password(service['password'])
            newuser.save()
            Extended.objects.create(
                last_name=service['last_name'],
                first_name=service['first_name'],
                role=USER_ROLES[4][0],
                user=newuser
            )
    return None
