import os
from Omega.settings import MEDIA_ROOT
from Omega.utils import print_err


def clear_job_files():
    from jobs.models import File, JOBFILE_DIR
    files_in_the_system = []
    for f in File.objects.all():
        if len(f.etvfiles_set.all()) == 0 \
                and len(f.reportcomponent_set.all()) == 0 \
                and len(f.filesystem_set.all()) == 0:
            f.delete()
        else:
            file_path = os.path.abspath(os.path.join(MEDIA_ROOT, f.file.name))
            files_in_the_system.append(file_path)
            if not(os.path.isfile(file_path) and os.path.exists(file_path)):
                print_err('Deleted from DB (file not exists): %s' % f.file.name)
                f.delete()
    files_directory = os.path.join(MEDIA_ROOT, JOBFILE_DIR)
    for f in [os.path.abspath(os.path.join(files_directory, x)) for x in os.listdir(files_directory)]:
        if f not in files_in_the_system:
            os.remove(f)


def clear_service_files():
    from service.models import FILE_DIR, Solution, Task
    files_in_the_system = []
    for s in Solution.objects.all():
        files_in_the_system.append(os.path.abspath(os.path.join(MEDIA_ROOT, s.archive.name)))
    for s in Task.objects.all():
        files_in_the_system.append(os.path.abspath(os.path.join(MEDIA_ROOT, s.archive.name)))
    files_directory = os.path.join(MEDIA_ROOT, FILE_DIR)
    for f in [os.path.abspath(os.path.join(files_directory, x)) for x in os.listdir(files_directory)]:
        if f not in files_in_the_system:
            os.remove(f)


def clear_resorces():
    from reports.models import Resource
    for r in Resource.objects.all():
        if len(r.reportcomponent_set.all()) == 0 and len(r.componentresource_set.all()) == 0:
            r.delete()


def clear_computers():
    from reports.models import Computer
    for c in Computer.objects.all():
        if len(c.reportcomponent_set.all()) == 0:
            c.delete()
