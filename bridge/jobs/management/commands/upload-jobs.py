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

from django.core.management.base import BaseCommand

from bridge.vars import JOB_UPLOAD_STATUS
from jobs.models import UploadedJobArchive
from jobs.Upload import JobArchiveUploader


class Command(BaseCommand):
    help = 'Upload pending job archives.'
    requires_migrations_checks = True

    def handle(self, *args, **options):
        upload_objects_qs = UploadedJobArchive.objects.filter(status=JOB_UPLOAD_STATUS[0][0])
        if len(upload_objects_qs) == 0:
            if options['verbosity'] >= 1:
                self.stdout.write("No archives to upload.")
            return

        if options['verbosity'] >= 1:
            self.stdout.write("Starting uploading of {} archive(s).".format(len(upload_objects_qs)))

        for upload_obj in upload_objects_qs:
            if options['verbosity'] >= 1:
                self.stdout.write("Starting uploading of archive {}.".format(upload_obj.name))
            try:
                with JobArchiveUploader(upload_obj) as uploader:
                    uploader.upload()
            except Exception as e:
                self.stderr.write("Uploading archive with id={} ({}) failed: {}".format(
                    upload_obj.id, upload_obj.name, str(e))
                )
        if options['verbosity'] >= 1:
            self.stdout.write("Uploading finished.")
