from django.contrib import admin
from marks.models import MarkDefaultFunctions, MarkUnsafeReport,\
    MarkUnsafeConvert

# Register your models here.
admin.site.register(MarkDefaultFunctions)
admin.site.register(MarkUnsafeConvert)
admin.site.register(MarkUnsafeReport)