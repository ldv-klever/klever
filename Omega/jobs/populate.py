import pytz
import random
from time import sleep
from datetime import datetime
from jobs.job_functions import create_job, update_job
from jobs.models import MarkSafeTag, MarkUnsafeTag
from reports.models import *
from marks.models import UnsafeTag, SafeTag


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
    SafeTag.objects.all().delete()
    UnsafeTag.objects.all().delete()
    MarkSafeTag.objects.all().delete()
    MarkUnsafeTag.objects.all().delete()
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


def populate_root_report(username):
    ReportRoot.objects.all().delete()
    Component.objects.all().delete()

    components = ["DSCV", "RCV", "Reporter", "DEG"]
    for comp_name in components:
        component = Component()
        component.name = comp_name
        component.save()

    for job in Job.objects.all():
        root_report = ReportRoot()
        root_report.job = job
        root_report.user = User.objects.get(username=username)
        root_report.last_request_date = pytz.timezone('UTC').localize(datetime(
            2015, 7, 31, random.randint(10, 15), random.randint(5, 50), 17
        ))
        root_report.save()


def populate_verdicts():
    for report in ReportRoot.objects.all():
        verdict = Verdict()
        verdict.report = report
        verdict.unsafe = random.randint(0, 10)
        verdict.unsafe_bug = random.randint(0, 10)
        verdict.unsafe_target_bug = random.randint(0, 10)
        verdict.unsafe_false_positive = random.randint(0, 10)
        verdict.unsafe_unknown = random.randint(0, 10)
        verdict.unsafe_unassociated = random.randint(0, 10)
        verdict.unsafe_inconclusive = random.randint(0, 10)
        verdict.safe = random.randint(0, 10)
        verdict.safe_missed_bug = random.randint(0, 10)
        verdict.safe_incorrect_proof = random.randint(0, 10)
        verdict.safe_unknown = random.randint(0, 10)
        verdict.safe_unassociated = random.randint(0, 10)
        verdict.safe_inconclusive = random.randint(0, 10)
        verdict.unknown = random.randint(0, 10)
        verdict.save()


def populate_resources():
    for report in ReportRoot.objects.all():
        resource = Resource()
        resource.cpu_time = random.randint(0, 60000)
        resource.wall_time = random.randint(0, 60000)
        resource.memory = random.randint(0, 15000000)
        resource.save()
        comp_res = ComponentResource()
        comp_res.report = report
        comp_res.component = None
        comp_res.resource = resource
        comp_res.save()
        for component in Component.objects.all():
            resource = Resource()
            resource.cpu_time = random.randint(0, 6000)
            resource.wall_time = random.randint(0, 6000)
            resource.memory = random.randint(0, 1500000)
            resource.save()
            comp_res = ComponentResource()
            comp_res.report = report
            comp_res.component = component
            comp_res.resource = resource
            comp_res.save()


def populate_unknowns():
    UnknownProblem.objects.all().delete()

    for i in range(0, 15):
        marked_problem = UnknownProblem()
        marked_problem.name = "Problem %s" % str(i + 1)
        marked_problem.save()

    for report in ReportRoot.objects.all():
        for component in Component.objects.all():
            if random.randint(0, 10) > 6:
                total = ComponentUnknown()
                total.component = component
                total.number = random.randint(1, 15)
                total.report = report
                total.save()
                if random.randint(0, 10) > 4:
                    unmarked_unknown = ComponentMarkUnknownProblem()
                    unmarked_unknown.number = random.randint(1, 15)
                    unmarked_unknown.component = component
                    unmarked_unknown.problem = None
                    unmarked_unknown.report = report
                    unmarked_unknown.save()

                for problem in UnknownProblem.objects.all():
                    if random.randint(0, 10) > 6:
                        marked_unknown = ComponentMarkUnknownProblem()
                        marked_unknown.number = random.randint(1, 15)
                        marked_unknown.problem = problem
                        marked_unknown.component = component
                        marked_unknown.report = report
                        marked_unknown.save()


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
    populate_root_report(username)
    populate_verdicts()
    populate_resources()
    populate_unknowns()
    populate_tags()
