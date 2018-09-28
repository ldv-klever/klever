#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import hashlib
import logging
import os
import shutil
import tempfile
import time
import zipfile

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.files import File
from django.db.models import Q
from django.http import HttpResponseBadRequest, JsonResponse, Http404
from django.template import loader
from django.template import Template, Context
from django.template.defaultfilters import filesizeformat
from django.test import Client, TestCase, override_settings
from django.utils.timezone import now, activate as activate_timezone
from django.utils.translation import ugettext_lazy as _, activate

from bridge.vars import UNKNOWN_ERROR, ERRORS, USER_ROLES

BLOCKER = {}
GROUP_BLOCKER = {}
CALL_STATISTIC = {}
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


def exec_time(func):
    def inner(*args, **kwargs):
        t1 = time.time()
        res = func(*args, **kwargs)
        print("CALL {}(): {:5.5f}".format(func.__name__, time.time() - t1))
        return res
    return inner


def file_checksum(f):
    md5 = hashlib.md5()
    while True:
        data = f.read(8 * 1024)
        if not data:
            break
        md5.update(data)
    f.seek(0)
    return md5.hexdigest()


def file_get_or_create(fp, filename, table, check_size=False):
    if check_size:
        file_size = fp.seek(0, os.SEEK_END)
        if file_size > settings.MAX_FILE_SIZE:
            raise ValueError(
                _('Please keep the file size under {0} (the current file size is {1})'.format(
                    filesizeformat(settings.MAX_FILE_SIZE),
                    filesizeformat(file_size)
                ))
            )
    fp.seek(0)
    check_sum = file_checksum(fp)
    try:
        return table.objects.get(hash_sum=check_sum), check_sum
    except ObjectDoesNotExist:
        db_file = table(hash_sum=check_sum)
        db_file.file.save(filename, File(fp), save=True)
        return db_file, check_sum


# archive - django.core.files.File object
# Example: archive = File(open(<path>, mode='rb'))
# Note: files from requests are already File objects
def extract_archive(archive):
    with tempfile.NamedTemporaryFile() as fp:
        for chunk in archive.chunks():
            fp.write(chunk)
        fp.seek(0)
        if os.path.splitext(archive.name)[-1] != '.zip':
            raise ValueError('Only zip archives are supported')
        with zipfile.ZipFile(fp, mode='r') as zfp:
            tmp_dir_name = tempfile.TemporaryDirectory()
            zfp.extractall(tmp_dir_name.name)
        return tmp_dir_name


def unique_id():
    return hashlib.md5(now().strftime("%Y%m%d%H%M%S%f%z").encode('utf8')).hexdigest()


def tests_logging_conf():
    tests_logging = settings.LOGGING.copy()
    cnt = 1
    for handler in tests_logging['handlers']:
        if 'filename' in tests_logging['handlers'][handler]:
            tests_logging['handlers'][handler]['filename'] = os.path.join(
                settings.MEDIA_ROOT, TESTS_DIR, 'log%s.log' % cnt)
            cnt += 1
    return tests_logging


def get_templated_text(template, **kwargs):
    return Template(template).render(Context(kwargs))


# Logging overriding does not work (does not override it for tests but override it after tests done)
# Maybe it's Django's bug (LOGGING=tests_logging_conf())
@override_settings(MEDIA_ROOT=os.path.join(settings.MEDIA_ROOT, TESTS_DIR))
class KleverTestCase(TestCase):
    def setUp(self):
        if not os.path.exists(os.path.join(settings.MEDIA_ROOT, TESTS_DIR)):
            os.makedirs(os.path.join(settings.MEDIA_ROOT, TESTS_DIR).encode("utf8"))
        self.client = Client()
        super(KleverTestCase, self).setUp()

    def tearDown(self):
        super(KleverTestCase, self).tearDown()
        try:
            shutil.rmtree(os.path.join(settings.MEDIA_ROOT, TESTS_DIR))
        except PermissionError:
            pass


def has_references(obj):
    relations = [f for f in getattr(obj, '_meta').get_fields()
                 if (f.one_to_many or f.one_to_one) and f.auto_created and not f.concrete]
    for link in list(rel.get_accessor_name() for rel in relations):
        if getattr(obj, link).count() > 0:
            return True
    return False


class ArchiveFileContent:
    def __init__(self, report, field_name, file_name):
        self._report = report
        self._field = field_name
        self._name = file_name
        self.content = self.__extract_file_content()

    def __extract_file_content(self):
        with getattr(self._report, '_meta').model.objects.get(id=self._report.id).__getattribute__(self._field) as fp:
            if os.path.splitext(fp.name)[-1] != '.zip':
                raise ValueError('Archive type is not supported')
            with zipfile.ZipFile(fp, 'r') as zfp:
                return zfp.read(self._name)


class OpenFiles:
    def __init__(self, *args, mode='rb', rel_path=None):
        self._files = {}
        self._mode = mode
        self._rel_path = rel_path
        self._paths = self.__check_files(*args)

    def __enter__(self):
        try:
            for p in self._paths:
                dict_key = p
                if isinstance(self._rel_path, str) and os.path.isdir(self._rel_path):
                    dict_key = os.path.relpath(dict_key, self._rel_path)
                dict_key = dict_key.replace('\\', '/')
                if dict_key not in self._files:
                    self._files[dict_key] = File(open(p, mode=self._mode))
        except Exception as e:
            self.__exit__(type(e), str(e), e.__traceback__)
        return self._files

    def __exit__(self, exc_type, exc_val, exc_tb):
        for fp in self._files.values():
            fp.close()

    def __check_files(self, *args):
        paths = set()
        for arg in args:
            if not isinstance(arg, str):
                raise ValueError('Unsupported argument: {0}'.format(arg))
            if not os.path.isfile(arg):
                raise FileNotFoundError("The file doesn't exist: {0}".format(arg))
            paths.add(arg)
        return paths


class RemoveFilesBeforeDelete:
    def __init__(self, obj):
        model_name = getattr(obj, '_meta').object_name
        if model_name == 'SolvingProgress':
            self.__remove_progress_files(obj)
        elif model_name == 'ReportRoot':
            self.__remove_reports_files(obj)
        elif model_name == 'Job':
            # Deleting of the job automatically send signals of deleting OneToOne fields
            # (ReportRoot and SolvingProgress), so we don't need to do here something
            pass
        elif model_name == 'Task':
            self.__remove_task_files(obj)

    def __remove_progress_files(self, progress):
        from service.models import Solution, Task
        for files in Solution.objects.filter(task__progress=progress).values_list('archive'):
            self.__remove(files)
        for files in Task.objects.filter(progress=progress).values_list('archive'):
            self.__remove(files)

    def __remove_reports_files(self, root):
        from reports.models import ReportSafe, ReportUnsafe, ReportUnknown, ReportComponent, CoverageArchive
        for files in ReportSafe.objects.filter(Q(root=root) & ~Q(proof=None)).values_list('proof'):
            self.__remove(files)
        for files in ReportUnsafe.objects.filter(root=root).values_list('error_trace'):
            self.__remove(files)
        for files in ReportUnknown.objects.filter(root=root).values_list('problem_description'):
            self.__remove(files)
        for files in ReportComponent.objects.filter(root=root).exclude(log='', data='', verifier_input='')\
                .values_list('log', 'verifier_input', 'data'):
            self.__remove(files)
        for files in CoverageArchive.objects.filter(report__root=root).values_list('archive'):
            self.__remove(files)

    def __remove_task_files(self, task):
        from service.models import Solution
        files = set()
        try:
            files.add(Solution.objects.get(task=task).archive.path)
        except ObjectDoesNotExist:
            pass
        files.add(task.archive.path)
        self.__remove(files)

    def __remove(self, files):
        self.__is_not_used()
        for f in files:
            if f:
                path = os.path.join(settings.MEDIA_ROOT, f)
                try:
                    os.remove(path)
                except OSError:
                    pass
                except Exception as e:
                    logger.exception(e)

    def __is_not_used(self):
        pass


class BridgeException(Exception):
    def __init__(self, message=None, code=None, response_type='html', back=None):
        self.response_type = response_type
        self.back = back
        if code is None and message is None:
            self.code = 500
            self.message = UNKNOWN_ERROR
        elif isinstance(code, int):
            self.code = code
            self.message = ERRORS.get(code, UNKNOWN_ERROR)
        else:
            self.code = None
            self.message = message

    def __str__(self):
        return str(self.message)


class BridgeErrorResponse(HttpResponseBadRequest):
    def __init__(self, response, *args, back=None, **kwargs):
        if isinstance(response, int):
            response = ERRORS.get(response, UNKNOWN_ERROR)
        super(BridgeErrorResponse, self).__init__(
            loader.get_template('error.html').render({'message': response, 'back': back}),
            *args, **kwargs
        )


class BridgeMiddlware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.user.extended.role != USER_ROLES[4][0]:
            activate(request.user.extended.language)
            activate_timezone(request.user.extended.timezone)
        response = self.get_response(request)
        return response

    def process_exception(self, request, exception):
        if isinstance(exception, BridgeException):
            if exception.response_type == 'json':
                return JsonResponse({'error': str(exception.message)})
            elif exception.response_type == 'html':
                return HttpResponseBadRequest(loader.get_template('error.html').render({
                    'user': request.user, 'message': exception.message, 'back': exception.back
                }))
        elif isinstance(exception, Http404):
            return
        logger.exception(exception)
        return HttpResponseBadRequest(loader.get_template('error.html').render({
            'user': request.user, 'message': str(UNKNOWN_ERROR)
        }))
