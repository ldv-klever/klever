from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models.signals import pre_delete, post_delete
from django.dispatch.dispatcher import receiver
from bridge.settings import FILES_AUTODELETE
from bridge.utils import has_references
from jobs.models import RunHistory, FileSystem, JobFile
from reports.models import ReportComponent, ReportUnsafe, ReportSafe, ReportUnknown
from marks.models import MarkUnsafe, ConvertedTraces, ErrorTraceConvertionCache


MODELS_WITH_FILE = {
    RunHistory: (JobFile, 'configuration'),
    FileSystem: (JobFile, 'file'),
    MarkUnsafe: (ConvertedTraces, 'error_trace'),
    ErrorTraceConvertionCache: (ConvertedTraces, 'converted')
}


class FilesToCheck(models.Model):
    instance_id = models.CharField(max_length=64, db_index=True)
    file_id = models.IntegerField()

    class Meta:
        db_table = 'tools_files_to_check'


def create_functions(m):

    @receiver(pre_delete, sender=m)
    def function_pre(**kwargs):
        instance = kwargs['instance']
        file_field = getattr(instance, MODELS_WITH_FILE[m][1])
        if file_field is not None:
            FilesToCheck.objects.create(instance_id='%s%s' % (type(instance), instance.pk), file_id=file_field.pk)

    @receiver(post_delete, sender=m)
    def function_post(**kwargs):
        instance = kwargs['instance']
        for fc in FilesToCheck.objects.filter(instance_id='%s%s' % (type(instance), instance.pk)):
            try:
                f = MODELS_WITH_FILE[m][0].objects.get(pk=fc.file_id)
                if not has_references(f):
                    f.delete()
            except ObjectDoesNotExist:
                pass
            fc.delete()

    return function_pre, function_post


if FILES_AUTODELETE:
    SIGNAL_FUNCTIONS = {}
    for model in MODELS_WITH_FILE:
        SIGNAL_FUNCTIONS[model] = create_functions(model)
