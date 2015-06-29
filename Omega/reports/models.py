from django.db import models
from django.utils.translation import ugettext as _
from django.contrib.auth.models import User
from jobs.job_model import Job


# Current differences from the original database schema:
# MEDIUMBLOB -> LONGBLOB
# TEXT, MEDIUMTEXT -> LONGTEXT
# TODO: __str__ is useful only for debugging. Do you need it everywhere?
# __str__ must return string.
# Storing files in the database is bad in 99% cases. Try to find another way.
# TODO: check if some ForeignKey fields can be OneToOneField.

class AttrName(models.Model):
    name = models.CharField(max_length=31)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'attr_name'


class Attr(models.Model):
    name = models.ForeignKey(AttrName)
    value = models.CharField(max_length=255)
    
    def __str__(self):
        return self.name.name

    class Meta:
        db_table = 'attr'


class Report(models.Model):
    parent = models.ForeignKey('self', blank=True, null=True, related_name='+')
    identifier = models.CharField(max_length=255, unique=True)
    creation_date = models.DateTimeField(auto_now=True)
    description = models.BinaryField(null=True)
    attr = models.ManyToManyField(Attr)

    def __str__(self):
        return self.identifier

    class Meta:
        db_table = 'report'


class Computer(models.Model):
    description = models.TextField()

    def __str__(self):
        return self.description

    class Meta:
        db_table = 'computer'


class Component(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'component'


class Resource(models.Model):
    cpu_time = models.BigIntegerField()
    wall_time = models.BigIntegerField()
    memory = models.BigIntegerField()

    def __str__(self):
        return str(self.pk)

    class Meta:
        db_table = 'resource'


class ReportRoot(Report):
    user = models.ForeignKey(User, blank=True, null=True,
                             on_delete=models.SET_NULL, related_name='+')

    # TODO: on_delete default is CASCADE. Is it OK?
    job = models.ForeignKey(Job, related_name='+')
    computer = models.ForeignKey(Computer, related_name='+')
    resource = models.ForeignKey(Resource, related_name='+')
    
    STATUS = (
        ('0', _('Not Solved')),
        ('1', _('Solving')),
        ('2', _('Stopped')),
        ('3', _('Solved')),
        ('4', _('Failed')),
    )
    status = models.CharField(max_length=1, choices=STATUS, default='0')
    start_date = models.DateTimeField()
    last_request_date = models.DateTimeField()
    finish_date = models.DateTimeField()
    log = models.BinaryField(null=True)

    def __str__(self):
        return self.identifier

    class Meta:
        db_table = 'report_root'


class ReportComponent(Report):
    computer = models.ForeignKey(Computer, related_name='+')
    resource = models.ForeignKey(Resource, related_name='+')
    component = models.ForeignKey(Component, related_name='+')
    log = models.BinaryField(null=True)
    data = models.BinaryField(null=True)

    def __str__(self):
        return self.identifier

    class Meta:
        db_table = 'report_component'


class ReportUnsafe(Report):
    error_trace = models.BinaryField()

    def __str__(self):
        return self.identifier

    class Meta:
        db_table = 'report_unsafe'


class ReportSafe(Report):
    proof = models.BinaryField()

    def __str__(self):
        return self.identifier

    class Meta:
        db_table = 'report_safe'


class ReportUnknown(Report):
    problem_description = models.BinaryField()

    def __str__(self):
        return self.identifier

    class Meta:
        db_table = 'report_unknown'
