import os
import time
import logging
import hashlib
import tarfile
import tempfile
from django.core.exceptions import ObjectDoesNotExist
from django.core.files import File as NewFile
from django.template.defaultfilters import filesizeformat
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from bridge.settings import MAX_FILE_SIZE
from jobs.models import File

BLOCKER = {}
GROUP_BLOCKER = {}

logger = logging.getLogger('bridge')


class InfoFilter(object):
    def __init__(self, level):
        self.__level = level

    def filter(self, log_record):
        return log_record.levelno == self.__level


for h in logger.handlers:
    if h.name == 'other':
        h.addFilter(InfoFilter(logging.INFO))


def print_exec_time(f):
    def wrapper(*args, **kwargs):
        start = now()
        res = f(*args, **kwargs)
        logger.info('%s: %s' % (f.__name__, now() - start))
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


def file_get_or_create(fp, filename, check_size=False):
    if check_size:
        file_size = fp.seek(0, os.SEEK_END)
        if file_size > MAX_FILE_SIZE:
            raise ValueError(
                _('Please keep the file size under {0} (the current file size is {1})'.format(
                    filesizeformat(MAX_FILE_SIZE),
                    filesizeformat(file_size)
                ))
            )
    fp.seek(0)
    check_sum = file_checksum(fp)
    try:
        return File.objects.get(hash_sum=check_sum), check_sum
    except ObjectDoesNotExist:
        db_file = File()
        db_file.file.save(filename, NewFile(fp))
        db_file.hash_sum = check_sum
        db_file.save()
        return db_file, check_sum


# archive - django.core.files.File object
# Example: archive = File(open(<path>, mode='rb'))
# Note: files from requests are already File objects
def extract_tar_temp(archive):
    fp = tempfile.NamedTemporaryFile()
    for chunk in archive.chunks():
        fp.write(chunk)
    fp.seek(0)
    tar = tarfile.open(fileobj=fp, mode='r:gz')
    tmp_dir_name = tempfile.TemporaryDirectory()
    tar.extractall(tmp_dir_name.name)
    return tmp_dir_name
