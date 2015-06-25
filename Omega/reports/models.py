from django.db import models
from django.utils.translation import ugettext as _

class AttrName(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=31)

    def __str__(self):
        return self.id

class Attr(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.ForeignKey('AttrName', blank=False, null=False, on_delete=models.CASCADE, db_column='name_id')
    value = models.CharField(max_length=255, null=True)
    
    def __str__(self):
        return self.id

class Report(models.Model):
    id = models.AutoField(primary_key=True)
    parent = models.ForeignKey('Report', blank=True, null=True, on_delete=models.CASCADE, db_column='parent_id')
    identifier = models.CharField(max_length=255)
    creation_date = models.DateTimeField()
    description = models.BinaryField(null=True) # -> LongBlob only?
    attr = models.ManyToManyField('Attr') # specify table?

    def __str__(self):
        return self.id

class Computer(models.Model):
    id = models.AutoField(primary_key=True)
    description = models.TextField(null=True) # -> LONGTEXT only?

    def __str__(self):
        return self.id

class Component(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.id

class Resource(models.Model):
    id = models.AutoField(primary_key=True)
    cpu_time = models.BigIntegerField()
    wall_time = models.BigIntegerField()
    memory = models.BigIntegerField()
    
    def __str__(self):
        return self.id

class ReportRoot(Report):
    # PK/FK?
    # TODO: user = models.ForeignKey('User', blank=True, null=True, on_delete=models.SET_NULL, db_column='user_id')
    # TODO: job_id
    computer = models.ForeignKey('Computer', blank=False, null=False, on_delete=models.CASCADE, db_column='computer_id')
    resource = models.ForeignKey('Resource', blank=False, null=False, on_delete=models.CASCADE, db_column='resource_id')
    
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
    log = models.BinaryField(null=True) # -> LongBlob only?

    def __str__(self):
        return self.id

class ReportComponent(Report):
    # PK/FK?
    computer = models.ForeignKey('Computer', blank=False, null=False, on_delete=models.CASCADE, db_column='computer_id')
    resource = models.ForeignKey('Resource', blank=False, null=False, on_delete=models.CASCADE, db_column='resource_id')
    component = models.ForeignKey('Component', blank=False, null=False, on_delete=models.CASCADE, db_column='component_id')
    log = models.BinaryField(null=True) # -> LongBlob only?
    data = models.BinaryField(null=True) # -> LongBlob only?

    def __str__(self):
        return self.id

class ReportUnsafe(Report):
    # PK/FK?
    error_trace = models.BinaryField() # -> LongBlob only?

    def __str__(self):
        return self.id

class ReportSafe(Report):
    # PK/FK?
    proof = models.BinaryField() # -> LongBlob only?

    def __str__(self):
        return self.id
        
class ReportUnknown(Report):
    # PK/FK?
    problem_description = models.BinaryField() # -> LongBlob only?

    def __str__(self):
        return self.id
