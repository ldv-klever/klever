import random
from time import sleep
from django.contrib.auth.models import User
from jobs.job_functions import create_job, update_job
from jobs.job_model import Job
from marks.models import UnsafeTag, SafeTag
from jobs.models import MarkSafeTag, MarkUnsafeTag


def clear_table(table):
    rows = table.objects.all()
    for row in rows:
        row.delete()


def populate_jobs(username):
    old_jobs = Job.objects.all()
    while len(old_jobs) > 0:
        for job in old_jobs:
            if len(job.children_set.all()) == 0:
                job.delete()
        old_jobs = Job.objects.all()

    kwargs = {
        'author': User.objects.get(username=username),
        'type': '0',
        'description': "A lot of text (description)!"
    }

    for i in range(10):
        kwargs['name'] = 'Title of the job %s' % str(i + 1)
        kwargs['pk'] = i + 1
        create_job(kwargs)
        sleep(0.1)

    # Filling parents
    for i in range(1, 11):
        pid = None
        if i in [1, 3, 5]:
            pass
        elif i in [2, 8]:
            pid = 6
        elif i in [6, 7, 10]:
            pid = 1
        elif i == 4:
            pid = 10
        elif i == 9:
            pid = 3
        if pid is not None:
            job = Job.objects.get(pk=i)
            update_kwargs = {
                'author': User.objects.get(username=username),
                'comment': 'Set parent',
                'name': job.name,
                'parent': Job.objects.get(pk=pid),
                'job': job,
                'description': job.jobhistory_set.get(version=1).description
            }
            update_job(update_kwargs)


def populate_tags():
    clear_table(SafeTag)
    clear_table(UnsafeTag)
    clear_table(MarkSafeTag)
    clear_table(MarkUnsafeTag)
    for i in range(5):
        newtag = SafeTag()
        newtag.tag = 'my:safe:tag:%s' % str(i + 1)
        newtag.save()
        newtag = UnsafeTag()
        newtag.tag = 'my:unsafe:tag:%s' % str(i + 1)
        newtag.save()
    for job in Job.objects.all():
        for st in SafeTag.objects.all():
            if random.randint(1, 10) < 4:
                mark_tag = MarkSafeTag()
                mark_tag.tag = st
                mark_tag.number = random.randint(0, 5)
                mark_tag.job = job
                mark_tag.save()
        for st in UnsafeTag.objects.all():
            if random.randint(1, 10) < 4:
                mark_tag = MarkUnsafeTag()
                mark_tag.tag = st
                mark_tag.number = random.randint(0, 5)
                mark_tag.job = job
                mark_tag.save()


def main_population(username):
    """
    To populate test data you need to:
    - register a new user with role Producer;
    - run the "shell" manage.py task;
    - import jobs.populate;
    - jobs.populate.main_population('username')

    :param username: login of the user that will become an author of created
    jobs.
    """
    populate_jobs(username)
    populate_tags()
