from django.db import models
from django.contrib.auth.models import User
from jobs.job_model import Job


class AttrName(models.Model):
    name = models.CharField(max_length=31)

    class Meta:
        db_table = 'attr_name'


class Attr(models.Model):
    name = models.ForeignKey(AttrName)
    value = models.CharField(max_length=255)

    class Meta:
        db_table = 'attr'


class Report(models.Model):
    parent = models.ForeignKey('self', blank=True, null=True, related_name='+')
    identifier = models.CharField(max_length=255, unique=True)
    description = models.BinaryField(null=True)
    attr = models.ManyToManyField(Attr)

    class Meta:
        db_table = 'report'


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
    resource = models.ForeignKey(Resource, related_name='+')
    component = models.ForeignKey(Component, related_name='+')
    log = models.BinaryField(null=True)
    data = models.BinaryField(null=True)
    start_date = models.DateTimeField()
    finish_date = models.DateTimeField()

    class Meta:
        db_table = 'report_component'


class ReportRoot(ReportComponent):
    user = models.ForeignKey(User, blank=True, null=True,
                             on_delete=models.SET_NULL, related_name='+')
    job = models.OneToOneField(Job)
    last_request_date = models.DateTimeField()

    class Meta:
        db_table = 'report_root'


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


class ReportAttr(models.Model):
    report = models.ForeignKey(Report)
    attr = models.ForeignKey(Attr)

    class Meta:
        db_table = 'cache_report_attr'


class ReportComponentLeaf(models.Model):
    report = models.ForeignKey(ReportComponent)
    leaf_id = models.IntegerField()  # Should only be leafs (safe, unsafe, unknown) ids.

    class Meta:
        db_table = 'cache_report_component_report_leaf'

