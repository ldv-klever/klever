import hashlib
from time import sleep
from datetime import datetime
from types import FunctionType
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.utils.translation import override
from Omega.vars import JOB_CLASSES
from Omega.settings import LANGUAGE_CODE
from users.models import Extended
from jobs.utils import create_job
from jobs.models import Job
from marks.models import MarkUnsafeCompare, MarkUnsafeConvert
from marks.ConvertTrace import ConvertTrace
from marks.CompareTrace import CompareTrace


def populate_jobs(user):
    old_jobs = Job.objects.all()
    while len(old_jobs) > 0:
        for job in old_jobs:
            if len(job.children.all()) == 0:
                job.delete()
        old_jobs = Job.objects.all()

    args = {
        'author': user,
        'global_role': '1',
    }
    for i in range(len(JOB_CLASSES)):
        with override(LANGUAGE_CODE):
            args['name'] = JOB_CLASSES[i][1]
            args['description'] = "<h3>%s</h3>" % JOB_CLASSES[i][1]
        args['pk'] = i + 1
        args['type'] = JOB_CLASSES[i][0]
        create_job(args)
        sleep(0.1)


class Population(object):

    def __init__(self, user, username=None):
        self.user = user
        self.jobs_updated = False
        self.functions_updated = False
        self.manager_password = None
        self.manager_username = username
        self.__population()
        self.something_changed = (self.functions_updated or
                                  self.manager_password is not None
                                  or self.jobs_updated)

    def __population(self):
        try:
            self.user.extended
        except ObjectDoesNotExist:
            self.__extend_user(self.user)
        manager = self.__get_manager()
        self.__populate_functions()
        if len(Job.objects.all()) == 0 and isinstance(manager, User):
            self.jobs_updated = True
            populate_jobs(manager)

    def __populate_functions(self):
        func_names = []
        for func_name in [x for x, y in ConvertTrace.__dict__.items()
                          if type(y) == FunctionType and not x.startswith('_')]:
            func_names.append(func_name)
            description = self.__correct_description(
                getattr(ConvertTrace, func_name).__doc__)
            func, crtd = MarkUnsafeConvert.objects.get_or_create(name=func_name)
            if crtd or description != func.description:
                if isinstance(description, str):
                    self.functions_updated = True
                    func.description = description
                    func.save()
        MarkUnsafeConvert.objects.filter(~Q(name__in=func_names)).delete()
        func_names = []
        for func_name in [x for x, y in CompareTrace.__dict__.items()
                          if type(y) == FunctionType and not x.startswith('_')]:
            func_names.append(func_name)
            description = self.__correct_description(
                getattr(CompareTrace, func_name).__doc__
            )
            func, crtd = MarkUnsafeCompare.objects.get_or_create(name=func_name)
            if crtd or description != func.description:
                if isinstance(description, str):
                    self.functions_updated = True
                    func.description = description
                    func.save()
        MarkUnsafeCompare.objects.filter(~Q(name__in=func_names)).delete()

    def __extend_user(self, user, role='1'):
        try:
            user.extended.role = role
            user.extended.save()
            return
        except ObjectDoesNotExist:
            pass
        self.user = self.user
        extended = Extended()
        extended.first_name = 'Firstname'
        extended.last_name = 'Lastname'
        extended.role = role
        extended.user = user
        extended.save()

    def __get_manager(self):
        if self.manager_username is None:
            return None
        try:
            manager = User.objects.get(username=self.manager_username)
            self.__extend_user(manager, '2')
            return manager
        except ObjectDoesNotExist:
            pass
        manager = User()
        manager.username = self.manager_username
        manager.save()
        time_encoded = datetime.now().strftime("%Y%m%d%H%M%S%f%z")\
            .encode('utf8')
        password = hashlib.md5(time_encoded).hexdigest()[:8]
        manager.set_password(password)
        manager.save()
        self.__extend_user(manager, '2')
        self.manager_password = password
        return manager

    def __correct_description(self, descr):
        self.ccc = 0
        descr_strs = descr.split('\n')
        new_descr_strs = []
        for s in descr_strs:
            if len(s) > 0 and len(s.split()) > 0:
                new_descr_strs.append(s)
        return '\n'.join(new_descr_strs)
