from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models.signals import pre_delete, post_delete
from django.dispatch.dispatcher import receiver
from bridge.settings import FILES_AUTODELETE
from bridge.utils import has_references
from jobs.models import File, RunHistory, FileSystem
from reports.models import ReportComponent, ReportFiles, ReportUnsafe, ETVFiles, ReportSafe, ReportUnknown
from marks.models import MarkUnsafe


MODELS_WITH_FILE = {
    RunHistory: ['configuration'],
    FileSystem: ['file'],
    ReportComponent: ['log', 'data'],
    ReportFiles: ['file'],
    ReportUnsafe: ['error_trace'],
    ETVFiles: ['file'],
    ReportSafe: ['proof'],
    ReportUnknown: ['problem_description'],
    MarkUnsafe: ['error_trace']
}


class FilesToCheck(models.Model):
    instance_id = models.CharField(max_length=64)
    file_id = models.IntegerField()

    class Meta:
        db_table = 'tools_files_to_check'


def create_functions(m):

    @receiver(pre_delete, sender=m)
    def function_pre(**kwargs):
        instance = kwargs['instance']
        for field in MODELS_WITH_FILE[m]:
            file_field = getattr(instance, field)
            if file_field is not None:
                FilesToCheck.objects.create(instance_id='%s%s' % (type(instance), instance.pk), file_id=file_field.pk)

    @receiver(post_delete, sender=m)
    def function_post(**kwargs):
        instance = kwargs['instance']
        checked = []
        for fc in FilesToCheck.objects.filter(instance_id='%s%s' % (type(instance), instance.pk)):
            checked.append(fc.pk)
            try:
                f = File.objects.get(pk=fc.file_id)
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
