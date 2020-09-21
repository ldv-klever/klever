from django.contrib import admin
from mptt.admin import MPTTModelAdmin
from reports.models import Report

admin.site.register(Report, MPTTModelAdmin)
