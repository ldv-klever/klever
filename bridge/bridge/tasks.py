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

import os
import time

from celery import shared_task

from django.conf import settings


@shared_task
def clear_old_django_cache(minutes):
    cache_dir = settings.CACHES['default']['LOCATION']
    for f in os.listdir(cache_dir):
        full_path = os.path.join(cache_dir, f)
        file_age = int(time.time() - os.stat(full_path).st_mtime) // 60
        if file_age > minutes:
            os.remove(full_path)
