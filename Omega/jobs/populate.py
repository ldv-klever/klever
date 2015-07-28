import random
from time import sleep
from django.contrib.auth.models import User
from jobs.job_functions import create_job, update_job
from jobs.job_model import Job
from marks.models import UnknownProblem, UnsafeTag, SafeTag
from jobs.models import ComponentMarkUnknownProblem,\
    ComponentUnknown, ComponentResource, Component, Verdict,\
    MarkSafeTag, MarkUnsafeTag


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
        'format': 1,
        'configuration': "A lot of text (configuration)!",
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
                'job': job
            }
            update_job(update_kwargs)


def populate_problems():
    clear_table(UnknownProblem)
    for i in range(15):
        problem = UnknownProblem()
        problem.name = 'Problem %s' % str(i + 1)
        problem.pk = i + 1
        problem.save()


def populate_components():
    clear_table(Component)
    components = ['DSCV', 'RCV', 'DEG', 'CIL', 'Reporter']
    for i in range(len(components)):
        component = Component()
        component.name = components[i]
        component.pk = i + 1
        component.save()


def populate_resourses():
    clear_table(ComponentResource)
    cnt = 0
    components = Component.objects.all()
    jobs = Job.objects.all()
    for job in jobs:
        for comp in components:
            if random.randint(1, 100) < 30:
                res = ComponentResource()
                cnt += 1
                res.pk = cnt
                res.component = comp
                res.job = job
                res.wall_time = random.randint(1, 10000)
                res.cpu_time = random.randint(1, 10000)
                res.memory = random.randint(100, 10**10)
                res.save()


def populate_mark_probl():
    clear_table(ComponentMarkUnknownProblem)
    clear_table(ComponentUnknown)

    jobs = Job.objects.all()
    components = Component.objects.all()
    problems = UnknownProblem.objects.all()
    for job in jobs:
        if random.randint(1, 10) < 8:
            mark_prob = ComponentMarkUnknownProblem()
            mark_prob.job = job
            comp_id = random.randint(1, len(components)) - 1
            mark_prob.component = components[comp_id]
            if random.randint(1, 10) < 4:
                mark_prob.problem = None
            else:
                probl_id = (comp_id + 1) * 3 - random.randint(0, 2) - 1
                if probl_id < len(problems):
                    mark_prob.problem = problems[probl_id]
            mark_prob.number = random.randint(1, 10)
            mark_prob.save()


def populate_verdict():
    clear_table(Verdict)
    cnt = 0
    for job in Job.objects.all():
        if random.randint(1, 10) < 8:
            verd = Verdict()
            cnt += 1
            verd.pk = cnt
            verd.job = job
            verd.unsafe = random.randint(0, 5)
            verd.unsafe_bug = random.randint(0, 5)
            verd.unsafe_target_bug = random.randint(0, 5)
            verd.unsafe_false_positive = random.randint(0, 5)
            verd.unsafe_unknown = random.randint(0, 5)
            verd.unsafe_unassociated = random.randint(0, 5)
            verd.unsafe_inconclusive = random.randint(0, 5)
            verd.safe = random.randint(0, 5)
            verd.safe_missed_bug = random.randint(0, 5)
            verd.safe_incorrect_proof = random.randint(0, 5)
            verd.safe_unknown = random.randint(0, 5)
            verd.safe_unassociated = random.randint(0, 5)
            verd.safe_inconclusive = random.randint(0, 5)
            verd.unknown = random.randint(0, 5)
            verd.save()


def populate_tags():
    clear_table(SafeTag)
    clear_table(UnsafeTag)
    clear_table(MarkSafeTag)
    clear_table(MarkUnsafeTag)
    for i in range(5):
        newtag = SafeTag()
        newtag.tag = 'my:safe:tag:%s' % str(i + 1),
        newtag.save()
        newtag = UnsafeTag()
        newtag.tag = 'my:unsafe:tag:%s' % str(i + 1),
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
    - import jobs;
    - jobs.populate.main_population('username')

    :param username: login of the user that will become an author of created
    jobs.
    """
    populate_jobs(username)
    populate_verdict()
    populate_problems()
    populate_components()
    populate_resourses()
    populate_mark_probl()
    populate_tags()
