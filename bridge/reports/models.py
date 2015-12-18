from django.db import models
from django.contrib.auth.models import User
from bridge.vars import UNSAFE_VERDICTS, SAFE_VERDICTS
from jobs.models import File, Job

LOG_DIR = 'ReportLogs'


class AttrName(models.Model):
    name = models.CharField(max_length=63, unique=True)

    class Meta:
        db_table = 'attr_name'


class Attr(models.Model):
    name = models.ForeignKey(AttrName)
    value = models.CharField(max_length=255)

    class Meta:
        db_table = 'attr'


class ReportRoot(models.Model):
    user = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    job = models.OneToOneField(Job)

    class Meta:
        db_table = 'report_root'


class Report(models.Model):
    root = models.ForeignKey(ReportRoot)
    parent = models.ForeignKey('self', null=True, related_name='+')
    identifier = models.CharField(max_length=255, unique=True)
    attr = models.ManyToManyField(Attr)
    description = models.BinaryField(null=True)

    class Meta:
        db_table = 'report'


class ReportAttrOrder(models.Model):
    name = models.ForeignKey(AttrName)
    report = models.ForeignKey(Report, related_name='attrorder')

    class Meta:
        db_table = 'reports_attr_order'


class Computer(models.Model):
    description = models.TextField()

    class Meta:
        db_table = 'computer'


class Component(models.Model):
    name = models.CharField(max_length=15, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'component'


class Resource(models.Model):
    cpu_time = models.BigIntegerField()
    wall_time = models.BigIntegerField()
    memory = models.BigIntegerField()

    class Meta:
        db_table = 'resource'


class ReportComponent(Report):
    computer = models.ForeignKey(Computer)
    component = models.ForeignKey(Component, on_delete=models.PROTECT)
    resource = models.ForeignKey(Resource, null=True)
    start_date = models.DateTimeField()
    finish_date = models.DateTimeField(null=True)
    log = models.ForeignKey(File, null=True, on_delete=models.SET_NULL)
    data = models.BinaryField(null=True)

    class Meta:
        db_table = 'report_component'


class ReportUnsafe(Report):
    error_trace = models.BinaryField()
    verdict = models.CharField(max_length=1, choices=UNSAFE_VERDICTS, default='5')

    class Meta:
        db_table = 'report_unsafe'


class ETVFiles(models.Model):
    unsafe = models.ForeignKey(ReportUnsafe, related_name='files')
    file = models.ForeignKey(File)
    name = models.CharField(max_length=1024)

    class Meta:
        db_table = 'etv_files'


class ReportSafe(Report):
    proof = models.BinaryField()
    verdict = models.CharField(max_length=1, choices=SAFE_VERDICTS, default='4')

    class Meta:
        db_table = 'report_safe'


class ReportUnknown(Report):
    component = models.ForeignKey(Component, on_delete=models.PROTECT)
    problem_description = models.BinaryField()

    class Meta:
        db_table = 'report_unknown'


class ReportComponentLeaf(models.Model):
    report = models.ForeignKey(ReportComponent, related_name='leaves')
    safe = models.ForeignKey(ReportSafe, null=True, related_name='leaves')
    unsafe = models.ForeignKey(ReportUnsafe, null=True, related_name='leaves')
    unknown = models.ForeignKey(ReportUnknown, null=True, related_name='leaves')

    class Meta:
        db_table = 'cache_report_component_leaf'


class Verdict(models.Model):
    report = models.OneToOneField(ReportComponent)
    unsafe = models.PositiveIntegerField(default=0)
    unsafe_bug = models.PositiveIntegerField(default=0)
    unsafe_target_bug = models.PositiveIntegerField(default=0)
    unsafe_false_positive = models.PositiveIntegerField(default=0)
    unsafe_unknown = models.PositiveIntegerField(default=0)
    unsafe_unassociated = models.PositiveIntegerField(default=0)
    unsafe_inconclusive = models.PositiveIntegerField(default=0)
    safe = models.PositiveIntegerField(default=0)
    safe_missed_bug = models.PositiveIntegerField(default=0)
    safe_incorrect_proof = models.PositiveIntegerField(default=0)
    safe_unknown = models.PositiveIntegerField(default=0)
    safe_unassociated = models.PositiveIntegerField(default=0)
    safe_inconclusive = models.PositiveIntegerField(default=0)
    unknown = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "cache_report_verdict"


class ComponentResource(models.Model):
    report = models.ForeignKey(ReportComponent, related_name='resources_cache')
    component = models.ForeignKey(Component, null=True, on_delete=models.PROTECT)
    resource = models.ForeignKey(Resource)

    class Meta:
        db_table = 'cache_report_component_resource'


class ComponentUnknown(models.Model):
    report = models.ForeignKey(ReportComponent, related_name='unknowns_cache')
    component = models.ForeignKey(Component, on_delete=models.PROTECT)
    number = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'cache_report_component_unknown'
