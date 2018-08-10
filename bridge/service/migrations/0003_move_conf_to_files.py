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

from __future__ import unicode_literals

import hashlib
from io import BytesIO

from django.core.files import File
from django.db import migrations


def file_checksum(f):
    md5 = hashlib.md5()
    while True:
        data = f.read(8 * 1024)
        if not data:
            break
        md5.update(data)
    f.seek(0)
    return md5.hexdigest()


def move_configuration_to_files(apps, schema_editor):
    JobFile = apps.get_model("jobs", "JobFile")

    files = {}
    for f in JobFile.objects.all():
        files[f.hash_sum] = f.id

    for progress in apps.get_model("service", "SolvingProgress").objects.all().select_related('job'):
        conf = BytesIO(progress.configuration)
        checksum = file_checksum(conf)
        if checksum in files:
            progress.conf_file_id = files[checksum]
        else:
            db_file = JobFile(hash_sum=checksum)
            db_file.file.save('job-%s.conf' % progress.job.identifier[:5], File(conf), save=True)
            progress.conf_file = db_file
        progress.save()


class Migration(migrations.Migration):
    dependencies = [('jobs', '0003_auto_20180427_1241'), ('service', '0002_solvingprogress_conf_file')]
    operations = [migrations.RunPython(move_configuration_to_files)]
