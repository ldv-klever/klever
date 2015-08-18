from time import sleep
from jobs.utils import create_job
from jobs.models import Job
from reports.models import *
import hashlib
from marks.models import MarkDefaultFunctions, MarkUnsafeCompare,\
    MarkUnsafeConvert
from django.core.exceptions import ObjectDoesNotExist
from datetime import datetime
from users.models import Extended
from Omega.vars import JOB_CLASSES
from marks.ConvertTrace import ConvertTrace
from marks.CompareTrace import CompareTrace
from types import FunctionType


DEFAULT_FUNCTIONS = ['default_compare', 'default_convert']


def populate_jobs(user):
    old_jobs = Job.objects.all()
    while len(old_jobs) > 0:
        for job in old_jobs:
            if len(job.children_set.all()) == 0:
                job.delete()
        old_jobs = Job.objects.all()

    kwargs = {
        'author': user,
        'type': '0',
        'description': "A lot of text (description)!",
        'global_role': '1',
    }

    for i in range(len(JOB_CLASSES)):
        kwargs['name'] = 'Title of the job %s' % str(i + 1)
        kwargs['pk'] = i + 1
        kwargs['type'] = JOB_CLASSES[i][0]
        create_job(kwargs)
        sleep(0.1)


class Population(object):

    def __init__(self, user):
        self.user = user

    def full_population(self):
        try:
            self.user.extended
        except ObjectDoesNotExist:
            self.__extend_user(self.user)
        manager, password = self.__create_manager()
        self.populate_functions()
        populate_jobs(manager)
        return manager.username, password

    def populate_functions(self):
        self.user = self.user
        MarkUnsafeConvert.objects.all().delete()
        def_funcs = MarkDefaultFunctions()
        for func_name in [x for x, y in ConvertTrace.__dict__.items()
                          if type(y) == FunctionType and not x.startswith('_')]:
            description = getattr(ConvertTrace, func_name).__doc__
            func = MarkUnsafeConvert.objects.get_or_create(name=func_name)[0]
            if isinstance(description, str):
                func.description = description
                func.save()
            if func_name in DEFAULT_FUNCTIONS:
                def_funcs.convert = func

        for func_name in [x for x, y in CompareTrace.__dict__.items()
                          if type(y) == FunctionType and not x.startswith('_')]:
            description = getattr(CompareTrace, func_name).__doc__
            func = MarkUnsafeCompare.objects.get_or_create(name=func_name)[0]
            if isinstance(description, str):
                func.description = description
                func.save()
            if func_name in DEFAULT_FUNCTIONS:
                def_funcs.compare = func

        try:
            def_funcs.save()
        except ValueError:
            pass
        return None

    def __extend_user(self, user, role='1'):
        self.user = self.user
        extended = Extended()
        extended.first_name = 'Firstname'
        extended.last_name = 'Lastname'
        extended.role = role
        extended.user = user
        extended.save()

    def __create_manager(self):
        User.objects.filter(username='manager').delete()
        manager = User()
        manager.username = 'manager'
        manager.save()
        time_encoded = datetime.now().strftime("%Y%m%d%H%M%S%f%z")\
            .encode('utf8')
        password = hashlib.md5(time_encoded).hexdigest()
        manager.set_password(password)
        manager.save()
        self.__extend_user(manager, '2')
        return manager, password
