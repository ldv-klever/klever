import os
import time
import hashlib
from django.core.exceptions import ObjectDoesNotExist
from django.core.files import File as NewFile
from django.template.defaultfilters import filesizeformat
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from bridge.settings import DEBUG, MAX_FILE_SIZE
from jobs.models import File

BLOCKER = {}
GROUP_BLOCKER = {}


def print_err(message):
    if DEBUG:
        print(message)


def print_exec_time(f):
    def wrapper(*args, **kwargs):
        start = now()
        res = f(*args, **kwargs)
        print_err('%s: %s' % (f.__name__, now() - start))
        return res
    return wrapper


def unparallel(f):

    def wait_other(*args, **kwargs):
        if f.__name__ not in BLOCKER:
            BLOCKER[f.__name__] = 0
        while BLOCKER[f.__name__] == 1:
            time.sleep(0.1)
        BLOCKER[f.__name__] = 1
        res = f(*args, **kwargs)
        BLOCKER[f.__name__] = 0
        return res
    return wait_other


def unparallel_group(groups):
    def unparallel_inner(f):

        def block_access():
            for g in groups:
                if g not in GROUP_BLOCKER:
                    GROUP_BLOCKER[g] = 0
                if GROUP_BLOCKER[g] == 1:
                    return False
            return True

        def change_block(status):
            for g in groups:
                GROUP_BLOCKER[g] = status

        def wait(*args, **kwargs):
            while not block_access():
                time.sleep(0.1)
            change_block(1)
            res = f(*args, **kwargs)
            change_block(0)
            return res

        return wait

    return unparallel_inner


def file_checksum(f, block_size=2**20):
    md5 = hashlib.md5()
    while True:
        data = f.read(block_size)
        if not data:
            break
        md5.update(data)
    f.seek(0)
    return md5.hexdigest()


def file_get_or_create(fp, filename):
    check_sum = file_checksum(fp)
    file_size = fp.seek(0, os.SEEK_END)
    if file_size > MAX_FILE_SIZE:
        raise ValueError(
            _('Please keep the file size under {0} (the current file size is {1})'.format(
                filesizeformat(MAX_FILE_SIZE),
                filesizeformat(file_size)
            ))
        )
    try:
        return File.objects.get(hash_sum=check_sum), check_sum
    except ObjectDoesNotExist:
        db_file = File()
        db_file.file.save(filename, NewFile(fp))
        db_file.hash_sum = check_sum
        db_file.save()
        return db_file, check_sum
