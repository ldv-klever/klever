import os
import time
import shutil
import logging
import hashlib
import tarfile
import tempfile
from io import BytesIO
from django.core.exceptions import ObjectDoesNotExist
from django.core.files import File as NewFile
from django.template.defaultfilters import filesizeformat
from django.test import Client, TestCase, override_settings
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from bridge.settings import MAX_FILE_SIZE, MEDIA_ROOT, LOGGING
from jobs.models import File

BLOCKER = {}
GROUP_BLOCKER = {}
TESTS_DIR = 'Tests'

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
    with tempfile.NamedTemporaryFile() as fp:
        for chunk in archive.chunks():
            fp.write(chunk)
        fp.seek(0)
        with tarfile.open(fileobj=fp, mode='r:gz') as tar:
            tmp_dir_name = tempfile.TemporaryDirectory()
            tar.extractall(tmp_dir_name.name)
    return tmp_dir_name


def unique_id():
    return hashlib.md5(now().strftime("%Y%m%d%H%M%S%f%z").encode('utf8')).hexdigest()


def tests_logging_conf():
    tests_logging = LOGGING.copy()
    cnt = 1
    for handler in tests_logging['handlers']:
        if 'filename' in tests_logging['handlers'][handler]:
            tests_logging['handlers'][handler]['filename'] = os.path.join(MEDIA_ROOT, TESTS_DIR, 'log%s.log' % cnt)
            cnt += 1
    return tests_logging


# Logging overriding does not work (does not override it for tests but override it after tests done)
# Maybe it's Django's bug (LOGGING=tests_logging_conf())
@override_settings(MEDIA_ROOT=os.path.join(MEDIA_ROOT, TESTS_DIR))
class KleverTestCase(TestCase):
    def setUp(self):
        if not os.path.exists(os.path.join(MEDIA_ROOT, TESTS_DIR)):
            os.makedirs(os.path.join(MEDIA_ROOT, TESTS_DIR))
        self.client = Client()
        super(KleverTestCase, self).setUp()

    def tearDown(self):
        super(KleverTestCase, self).tearDown()
        try:
            shutil.rmtree(os.path.join(MEDIA_ROOT, TESTS_DIR))
        except PermissionError:
            pass


# TODO: remove if it is not used
def compress_file(file_pointer, file_name=None):
    if file_name is None:
        file_name = file_pointer.name
    tar_p = BytesIO()
    with tarfile.open(fileobj=tar_p, mode='w:gz') as arch:
        t = tarfile.TarInfo(file_name)
        file_pointer.seek(0, 2)
        t.size = file_pointer.tell()
        file_pointer.seek(0)
        arch.addfile(t, file_pointer)
    tar_p.flush()
    tar_p.seek(0)
    return tar_p


# Only extracting component log content uses max_size. If you add another usage, change error messages according to it.
class ArchiveFileContent(object):
    def __init__(self, file_model, file_name=None, max_size=None):
        self._file = file_model
        self._max_size = max_size
        self._name = file_name
        self.error = None
        try:
            self.content = self.__extract_file_content()
        except Exception as e:
            logger.exception("Error while extracting file from archive: %s" % e)
            self.error = 'Unknown error'

    def __extract_file_content(self):
        with self._file.file as fp:
            with tarfile.open(fileobj=fp, mode='r:gz') as arch:
                for f in arch.getmembers():
                    if f.isreg():
                        if self._name is not None and f.name != self._name:
                            continue
                        if self._max_size is not None:
                            fp.seek(0, 2)
                            if fp.tell() > self._max_size:
                                self.error = _('The component log is huge and can not be showed but you can download it')
                                return None
                            fp.seek(0)
                        self._name = f.name
                        return arch.extractfile(f).read().decode('utf8')
        self.error = _('Needed file was not found')
        return None
