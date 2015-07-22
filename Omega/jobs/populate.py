from jobs.job_model import Job, JobHistory, JobStatus
from marks.models import UnknownProblem, UnsafeTag, SafeTag
from jobs.models import ComponentMarkUnknownProblem,\
    ComponentUnknown, ComponentResource, Component, Verdict,\
    MarkSafeTag, MarkUnsafeTag
import string
import random


from django.contrib.auth.models import User


def clear_table(table):
    rows = table.objects.all()
    for row in rows:
        row.delete()


def populate_jobs(username):
    author = User.objects.get(username=username)
    identifiers = [''.join([random.choice(string.ascii_letters + string.digits) for n in range(32)]) for x in range(10)]
    jobtype = '0'
    names = ['Title of the job %s' % str(x) for x in range(1, 11)]
    configuration = "A lot of text (configuration)!"
    description = "A lot of text (description)!"
    for i in range(10):
        newjob = Job()
        newjob.pk = i + 1
        newjob.name = names[i]
        newjob.change_author = author
        newjob.description = description
        newjob.configuration = configuration
        newjob.type = jobtype
        newjob.identifier = identifiers[i]
        newjob.parent = None
        newjob.save()
    for i in range(1, 11):
        pid = None
        if i == 1:
            pass
        elif i == 2:
            pid = 6
        elif i == 3:
            pass
        elif i == 4:
            pid = 10
        elif i == 5:
            pass
        elif i == 6:
            pid = 1
        elif i == 7:
            pid = 1
        elif i == 8:
            pid = 6
        elif i == 9:
            pid = 3
        elif i == 10:
            pid = 1
        if pid:
            job = Job.objects.get(pk=i)
            par = Job.objects.get(pk=pid)
            job.parent = par
            job.save()
    for job in Job.objects.all():
        create_version(job)
        newstatus = JobStatus()
        newstatus.job = job
        newstatus.save()



def populate_problems():
    clear_table(UnknownProblem)
    problem_names = ['Problem %s' % str(x + 1) for x in range(15)]
    for i in range(15):
        problem = UnknownProblem()
        problem.name = problem_names[i]
        problem.pk = i + 1
        problem.save()


def populate_components():
    components = [
        'DSCV',
        'RCV',
        'DEG',
        'CIL',
        'Reporter',
    ]
    for i in range(5):
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
            fill = random.randint(1, 100)
            if fill < 30:
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

    cnt = 0
    jobs = Job.objects.all()
    components = Component.objects.all()
    problems = UnknownProblem.objects.all()
    for job in jobs:
        has_problem = random.randint(1, 10)
        if has_problem < 8:
            mark_prob = ComponentMarkUnknownProblem()
            cnt += 1
            mark_prob.pk = cnt
            mark_prob.job = job
            comp_id = random.randint(1, len(components)) - 1
            mark_prob.component = components[comp_id]

            has_unmark = random.randint(1, 10)
            if has_unmark < 4:
                mark_prob.problem = None
            else:
                probl_id = (comp_id + 1) * 3 - random.randint(0, 2) - 1
                if probl_id < len(problems):
                    mark_prob.problem = problems[probl_id]
            mark_prob.number = random.randint(1, 10)
            mark_prob.save()
    for job in jobs:
        has_problem = random.randint(1, 10)
        if has_problem < 8:
            mark_prob = ComponentMarkUnknownProblem()
            cnt += 1
            mark_prob.pk = cnt
            mark_prob.job = job
            comp_id = random.randint(1, len(components)) - 1
            mark_prob.component = components[comp_id]

            has_unmark = random.randint(1, 10)
            if has_unmark < 4:
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
        has_verdicts = random.randint(1, 10)
        if has_verdicts < 8:
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
    safe_tags = [
        'my:safe:tag:1',
        'my:safe:tag:2',
        'my:safe:tag:3',
        'my:safe:tag:4',
        'my:safe:tag:5',
    ]
    unsafe_tags = [
        'my:unsafe:tag:1',
        'my:unsafe:tag:2',
        'my:unsafe:tag:3',
        'my:unsafe:tag:4',
        'my:unsafe:tag:5',
    ]
    for i in range(5):
        newtag = SafeTag()
        newtag.tag = safe_tags[i]
        newtag.save()
    for i in range(5):
        newtag = UnsafeTag()
        newtag.tag = unsafe_tags[i]
        newtag.save()
    for job in Job.objects.all():
        for st in SafeTag.objects.all():
            has_tag = random.randint(1, 10)
            if has_tag < 3:
                mark_tag = MarkSafeTag()
                mark_tag.tag = st
                mark_tag.number = random.randint(0, 5)
                mark_tag.job = job
                mark_tag.save()
        for st in UnsafeTag.objects.all():
            has_tag = random.randint(1, 10)
            if has_tag < 3:
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

    Note that this works only on a fresh database.

    :param username: login of the user that will become an author of created jobs.
    """
    populate_jobs(username)
    populate_problems()
    populate_components()
    populate_resourses()
    populate_mark_probl()
    populate_verdict()
    populate_tags()


def update_job():
    old_job = Job.objects.get(pk=1)
    old_job.name = 'New name of the job 1'
    old_job.version += 1
    old_job.save()
    create_version(old_job)


def create_version(job, version=1):
    job_v = JobHistory()
    job_v.name = job.name
    job_v.job = job
    job_v.change_author = job.change_author
    job_v.change_date = job.change_date
    job_v.description = job.description
    job_v.configuration = job.configuration
    job_v.format = job.format
    job_v.version = job.version
    job_v.save()
