#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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

import os
import time
import shutil
import logging
import hashlib
import tempfile
import zipfile
from django.core.exceptions import ObjectDoesNotExist
from django.core.files import File
from django.db.models.base import ModelBase
from django.template.defaultfilters import filesizeformat
from django.test import Client, TestCase, override_settings
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from bridge.settings import MAX_FILE_SIZE, MEDIA_ROOT, LOGGING

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


def affected_models(model):
    curr_name = getattr(model, '_meta').object_name
    related_models = {curr_name}
    for rel in [f for f in getattr(model, '_meta').get_fields()
                if (f.one_to_one or f.one_to_many) and f.auto_created and not f.concrete]:
        rel_model_name = getattr(rel.field.model, '_meta').object_name
        if rel_model_name not in related_models and rel_model_name != curr_name:
            related_models.add(rel_model_name)
            related_models |= affected_models(rel.field.model)
    return related_models


def unparallel_group(groups):
    def unparallel_inner(f):
        block = set()
        for group in groups:
            if isinstance(group, ModelBase):
                block |= affected_models(group)
            else:
                block.add(str(group))

        def block_access():
            for g in block:
                if g not in GROUP_BLOCKER:
                    GROUP_BLOCKER[g] = 0
                if GROUP_BLOCKER[g] == 1:
                    return False
            return True

        def change_block(status):
            for g in block:
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
        return table.objects.get(hash_sum=check_sum), check_sum
    except ObjectDoesNotExist:
        db_file = table()
        db_file.file.save(filename, File(fp))
        db_file.hash_sum = check_sum
        db_file.save()
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
            os.makedirs(os.path.join(MEDIA_ROOT, TESTS_DIR).encode("utf8"))
        self.client = Client()
        super(KleverTestCase, self).setUp()

    def tearDown(self):
        super(KleverTestCase, self).tearDown()
        try:
            shutil.rmtree(os.path.join(MEDIA_ROOT, TESTS_DIR))
        except PermissionError:
            pass


def has_references(obj):
    relations = [f for f in getattr(obj, '_meta').get_fields()
                 if (f.one_to_many or f.one_to_one) and f.auto_created and not f.concrete]
    for link in list(rel.get_accessor_name() for rel in relations):
        if getattr(obj, link).count() > 0:
            return True
    return False


class ArchiveFileContent(object):
    def __init__(self, report, file_name):
        self._report = report
        self._name = file_name
        self.content = self.__extract_file_content()

    def __extract_file_content(self):
        with self._report.archive as fp:
            if os.path.splitext(fp.name)[-1] != '.zip':
                raise ValueError('Archive type is not supported')
            with zipfile.ZipFile(fp, 'r') as zfp:
                return zfp.read(self._name)


class RemoveFilesBeforeDelete:
    def __init__(self, obj):
        model_name = getattr(obj, '_meta').object_name
        if model_name == 'SolvingProgress':
            self.__remove_progress_files(obj)
        elif model_name == 'ReportRoot':
            self.__remove_reports_files(obj)
        elif model_name == 'Job':
            self.__remove_job_files(obj)
        elif model_name == 'ReportComponent':
            self.__remove_component_files(obj)
        elif model_name == 'Task':
            self.__remove_task_files(obj)

    def __remove_progress_files(self, progress):
        from service.models import Solution, Task
        for files in Solution.objects.filter(task__progress=progress).values_list('archive'):
            self.__remove(files)
        for files in Task.objects.filter(progress=progress).values_list('archive'):
            self.__remove(files)

    def __remove_reports_files(self, root):
        from reports.models import ReportSafe, ReportUnsafe, ReportUnknown, ReportComponent
        for files in ReportSafe.objects.filter(root=root).values_list('archive'):
            self.__remove(files)
        for files in ReportUnsafe.objects.filter(root=root).values_list('archive'):
            self.__remove(files)
        for files in ReportUnknown.objects.filter(root=root).values_list('archive'):
            self.__remove(files)
        for files in ReportComponent.objects.filter(root=root).values_list('archive', 'data'):
            self.__remove(files)

    def __remove_job_files(self, job):
        from service.models import SolvingProgress
        from reports.models import ReportRoot
        try:
            self.__remove_reports_files(ReportRoot.objects.get(job=job))
        except ObjectDoesNotExist:
            pass
        try:
            self.__remove_progress_files(SolvingProgress.objects.get(job=job))
        except ObjectDoesNotExist:
            pass

    def __remove_component_files(self, report):
        from reports.models import ReportComponent, ReportSafe, ReportUnsafe, ReportUnknown
        reports = set()
        parents = {report.parent_id}
        while len(parents) > 0:
            reports |= parents
            parents = set(rc['id'] for rc in ReportComponent.objects.filter(parent_id__in=parents).values('id'))
        for files in ReportUnsafe.objects.filter(parent_id__in=reports).values_list('archive'):
            self.__remove(files)
        for files in ReportSafe.objects.filter(parent_id__in=reports).values_list('archive'):
            self.__remove(files)
        for files in ReportUnknown.objects.filter(parent_id__in=reports).values_list('archive'):
            self.__remove(files)
        for files in ReportComponent.objects.filter(id__in=reports).values_list('archive', 'data'):
            self.__remove(files)

    def __remove_task_files(self, task):
        self.__is_not_used()
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
                path = os.path.join(MEDIA_ROOT, f)
                try:
                    os.remove(path)
                except OSError:
                    pass
                except Exception as e:
                    logger.exception(e)

    def __is_not_used(self):
        pass
