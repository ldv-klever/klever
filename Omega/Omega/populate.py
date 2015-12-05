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
from Omega.vars import JOB_CLASSES, SCHEDULER_TYPE, USER_ROLES, JOB_ROLES
from Omega.settings import DEFAULT_LANGUAGE, BASE_DIR
from Omega.utils import print_err
from users.models import Extended
from jobs.utils import create_job
from jobs.models import Job, File
from marks.models import MarkUnsafeCompare, MarkUnsafeConvert
from marks.ConvertTrace import ConvertTrace
from marks.CompareTrace import CompareTrace
from service.models import Scheduler

JOB_SETTINGS_FILE = 'settings.json'


class Population(object):

    def __init__(self, user, manager=None, service=None):
        self.changes = {}
        self.user = user
        self.manager = self.__get_manager(manager)
        self.__population()
        self.__add_service_user(service)
        print('END:', self.changes)

    def __population(self):
        try:
            self.user.extended
        except ObjectDoesNotExist:
            self.__extend_user(self.user)
        self.__populate_functions()
        if len(Job.objects.filter(parent=None)) < 3:
            self.__populate_jobs()
        self.__populate_default_jobs()
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
            print('Creating manager')
            manager = User.objects.create(username=manager_username)
            self.changes['manager'] = {
                'username': manager.username,
                'password': self.__add_password(manager)
            }
            print('Changes:', self.changes)
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
            if any(x not in job_settings for x in ['name', 'type', 'description']):
                print_err('Default job settings must contain name, type and description')
                continue
            if job_settings['type'] not in list(x[0] for x in JOB_CLASSES):
                print_err('Default job type is wrong. See Omega.vars.JOB_CLASSES for choice ("0", "1" or "2")')
                continue
            if len(job_settings['name']) == 0:
                print_err('Default job name is required')
                continue
            try:
                parent = Job.objects.get(parent=None, type=job_settings['type'])
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
