#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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

from multiprocessing import Pool
from django.core.management.base import BaseCommand

from bridge.vars import JOB_UPLOAD_STATUS


def upload_archive_process(obj_id: int) -> str:
    import django
    django.setup()
    from jobs.models import UploadedJobArchive
    from jobs.Upload import JobArchiveUploader

    try:
        upload_obj = UploadedJobArchive.objects.get(id=obj_id)
    except UploadedJobArchive.DoesNotExist:
        return "Can't find uploaded archive"
    try:
        with JobArchiveUploader(upload_obj) as uploader:
            uploader.upload()
    except Exception as e:
        return str(e)
    return ""


class Command(BaseCommand):
    help = 'Upload pending job archives.'
    requires_migrations_checks = True

    def handle(self, *args, **options):
        from jobs.models import UploadedJobArchive
        ids = list(UploadedJobArchive.objects.filter(status=JOB_UPLOAD_STATUS[0][0]).values_list('id', flat=True))
        if len(ids) == 0:
            if options['verbosity'] >= 1:
                self.stdout.write("No archives to upload.")
            return
        pool = Pool(4)
        if options['verbosity'] >= 1:
            self.stdout.write("Starting uploading of {} archive(s).".format(len(ids)))
        res = pool.map(upload_archive_process, ids)

        if options['verbosity'] >= 1:
            assert len(ids) == len(res)
            for i in range(len(ids)):
                if res[i]:
                    self.stdout.write("Uploading archive with id={} failed: {}".format(ids[i], res[i]))
            self.stdout.write("Uploading finished.")
