from django.contrib import admin
from jobs.models import File, FileSystem
from jobs.job_model import JobStatus

# Register your models here.
admin.site.register(File)
admin.site.register(FileSystem)
admin.site.register(JobStatus)