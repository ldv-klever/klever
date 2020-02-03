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

from celery import shared_task
from datetime import timedelta

from django.utils.timezone import now

from bridge import celery_app
from bridge.vars import JOB_UPLOAD_STATUS
from bridge.utils import BridgeException

from jobs.models import UploadedJobArchive
from jobs.Upload import JobArchiveUploader


@shared_task
def upload_job_archive(upload_id, parent_uuid):
    try:
        upload_obj = UploadedJobArchive.objects.get(id=upload_id)
    except UploadedJobArchive.DoesNotExist:
        raise BridgeException('Uploaded job archive with id "{}" was not found'.format(upload_id))
    with JobArchiveUploader(upload_obj, parent_uuid) as uploader:
        uploader.upload()


@shared_task
def clear_old_uploads(minutes):
    UploadedJobArchive.objects.exclude(finish_date=None).filter(
        finish_date__lt=now() - timedelta(minutes=int(minutes))
    ).delete()
