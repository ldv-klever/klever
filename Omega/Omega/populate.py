from time import sleep
from jobs.utils import create_job, update_job
from jobs.models import Job
from reports.models import *
import hashlib
from marks.models import MarkDefaultFunctions, MarkUnsafeCompare,\
    MarkUnsafeConvert
from marks.ConvertTrace import DESCRIPTIONS
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _
from datetime import datetime
from users.models import Extended
from Omega.vars import JOB_CLASSES


COMPARE_FUNCTIONS = [
    [
        'default_compare',
        """
return 1
        """,
        """
Default comparing function.
Always returns 1.
        """,
    ],
    [
        'random_compare',
        """
import random
return random.random()
        """,
        """
Random comparing function.
Returns random number between 0 and 1.
        """,
    ],
]


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
        if len(COMPARE_FUNCTIONS) == 0:
            return _("Error: compare functions not found!")

        for func_name in DESCRIPTIONS:
            try:
                func = MarkUnsafeConvert.objects.get(name=func_name)
                if func.description != DESCRIPTIONS[func_name]:
                    func.description = DESCRIPTIONS[func_name]
                    func.save()
            except ObjectDoesNotExist:
                MarkUnsafeConvert.objects.create(
                    name=func_name, description=DESCRIPTIONS[func_name])

        default_compare = None
        for func_data in COMPARE_FUNCTIONS:
            hash_sum = hashlib.md5(
                (func_data[0] + func_data[1]).encode('utf8')).hexdigest()
            try:
                func = MarkUnsafeCompare.objects.get(
                    name=func_data[0], hash_sum=hash_sum)
                if func.description != func_data[2]:
                    func.description = func_data[2]
                    func.save()
            except ObjectDoesNotExist:
                func = MarkUnsafeCompare.objects.create(
                    name=func_data[0], body=func_data[1],
                    description=func_data[2]
                )
            if default_compare is None:
                default_compare = func
        def_funcs = MarkDefaultFunctions()
        def_funcs.compare = default_compare
        try:
            def_funcs.convert = MarkUnsafeConvert.objects.get(
                name='default_convert')
        except ObjectDoesNotExist:
            return _("Error: there are no convert functions")
        def_funcs.save()
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
