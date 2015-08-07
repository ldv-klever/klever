from django.db import models
from django.contrib.auth.models import User
from jobs.job_model import Job
from marks.models import UnknownProblem


class AttrName(models.Model):
    name = models.CharField(max_length=63)

    class Meta:
        db_table = 'attr_name'


class Attr(models.Model):
    name = models.ForeignKey(AttrName)
    value = models.CharField(max_length=255)

    class Meta:
        db_table = 'attr'


class ReportRoot(models.Model):
    user = models.ForeignKey(User, blank=True, null=True,
                             on_delete=models.SET_NULL, related_name='+')
    job = models.OneToOneField(Job)
    last_request_date = models.DateTimeField()

    class Meta:
        db_table = 'report_root'


class Report(models.Model):
    root = models.ForeignKey(ReportRoot)
    parent = models.ForeignKey('self', blank=True, null=True, related_name='+')
    identifier = models.CharField(max_length=255, unique=True)
    description = models.BinaryField(null=True)
    attr = models.ManyToManyField(Attr)

    class Meta:
        db_table = 'report'


class ReportAttr(models.Model):
    report = models.ForeignKey(Report)
    attr = models.ForeignKey(Attr)

    class Meta:
        db_table = 'cache_report_attr'


class Computer(models.Model):
    description = models.TextField()

    class Meta:
        db_table = 'computer'


class Component(models.Model):
    name = models.CharField(max_length=255)

    class Meta:
        db_table = 'component'


class Resource(models.Model):
    cpu_time = models.BigIntegerField()
    wall_time = models.BigIntegerField()
    memory = models.BigIntegerField()

    class Meta:
        db_table = 'resource'


class ReportComponent(Report):
    computer = models.ForeignKey(Computer, related_name='+')
    resource = models.ForeignKey(Resource, related_name='+', null=True)
    component = models.ForeignKey(Component, related_name='+')
    log = models.BinaryField(null=True)
    data = models.BinaryField(null=True)
    start_date = models.DateTimeField()
    finish_date = models.DateTimeField(null=True)

    class Meta:
        db_table = 'report_component'


class ReportUnsafe(Report):
    error_trace = models.BinaryField()
    error_trace_processed = models.BinaryField()

    class Meta:
        db_table = 'report_unsafe'


class ReportSafe(Report):
    proof = models.BinaryField()

    class Meta:
        db_table = 'report_safe'


class ReportUnknown(Report):
    problem_description = models.BinaryField()

    class Meta:
        db_table = 'report_unknown'


class ReportComponentLeaf(models.Model):
    report = models.ForeignKey(ReportComponent)
    safe = models.ForeignKey(ReportSafe, null=True, related_name='+')
    unsafe = models.ForeignKey(ReportUnsafe, null=True, related_name='+')
    unknown = models.ForeignKey(ReportUnknown, null=True, related_name='+')

    class Meta:
        db_table = 'cache_report_component_report_leaf'


class Verdict(models.Model):
    report = models.OneToOneField(ReportRoot)
    unsafe = models.IntegerField(default=0)
    unsafe_bug = models.IntegerField(default=0)
    unsafe_target_bug = models.IntegerField(default=0)
    unsafe_false_positive = models.IntegerField(default=0)
    unsafe_unknown = models.IntegerField(default=0)
    unsafe_unassociated = models.IntegerField(default=0)
    unsafe_inconclusive = models.IntegerField(default=0)
    safe = models.IntegerField(default=0)
    safe_missed_bug = models.IntegerField(default=0)
    safe_incorrect_proof = models.IntegerField(default=0)
    safe_unknown = models.IntegerField(default=0)
    safe_unassociated = models.IntegerField(default=0)
    safe_inconclusive = models.IntegerField(default=0)
    unknown = models.IntegerField(default=0)

    class Meta:
        db_table = "cache_job_verdict"


class ComponentUnknown(models.Model):
    report = models.ForeignKey(ReportRoot)
    component = models.ForeignKey(Component, related_name='+')
    number = models.IntegerField(default=0)

    class Meta:
        db_table = 'cache_job_component_unknown'


class ComponentMarkUnknownProblem(models.Model):
    report = models.ForeignKey(ReportRoot)
    component = models.ForeignKey(Component)
    problem = models.ForeignKey(UnknownProblem, null=True, blank=True,
                                on_delete=models.SET_NULL)
    number = models.IntegerField(default=0)

    class Meta:
        db_table = 'cache_job_component_mark_unknown_problem'


class ComponentResource(models.Model):
    report = models.ForeignKey(ReportRoot)
    component = models.ForeignKey(Component, null=True, blank=True,
                                  on_delete=models.SET_NULL)
    resource = models.ForeignKey(Resource)

    class Meta:
        db_table = 'cache_job_component_resource'
