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
import zipfile
from io import BytesIO

from django.db import migrations
from django.conf import settings

from bridge.vars import ERROR_TRACE_FILE
from bridge.utils import unique_id


def attrs_migrate(apps, schema_editor):
    attrs_ids = list(attr.id for attr in apps.get_model("reports", "Attr").objects
                     .filter(name__name__in=['Verification object', 'Rule specification']))
    apps.get_model("reports", "ReportAttr").objects.filter(attr_id__in=attrs_ids).update(compare=True, associate=True)


def clear_comparison_cache(apps, schema_editor):
    apps.get_model("reports", "CompareJobsInfo").objects.all().delete()


def add_unique_trace_id(apps, schema_editor):
    for unsafe in apps.get_model("reports", "ReportUnsafe").objects.all():
        unsafe.trace_id = unique_id()
        unsafe.save()
        time.sleep(0.1)


def split_trace_and_source(apps, schema_editor):
    old_archives = set()
    for unsafe in apps.get_model("reports", "ReportUnsafe").objects.all():
        trace_inmem = BytesIO()
        source_inmem = BytesIO()
        with unsafe.error_trace as et_fp:
            old_archives.add(et_fp.name)
            with zipfile.ZipFile(et_fp, mode='r') as et_zip:
                with zipfile.ZipFile(trace_inmem, 'w') as t_zip:
                    with zipfile.ZipFile(source_inmem, 'w') as s_zip:
                        for item in et_zip.infolist():
                            if item.filename == ERROR_TRACE_FILE:
                                t_zip.writestr(item, et_zip.read(item.filename))
                            else:
                                s_zip.writestr(item, et_zip.read(item.filename))
        if source_inmem.seek(0, 2) > 0:
            source_inmem.seek(0)
            et_src = apps.get_model("reports", "ErrorTraceSource")(root=unsafe.root)
            et_src.archive.save('Source.zip', source_inmem)
        else:
            unsafe.delete()
            continue
        trace_inmem.seek(0)
        unsafe.source = et_src
        unsafe.error_trace.save('ErrorTrace.zip', trace_inmem)

    for fname in old_archives:
        fpath = '/'.join([settings.MEDIA_ROOT, fname])
        if os.path.exists(fpath):
            os.remove(fpath)


class Migration(migrations.Migration):
    dependencies = [('reports', '0005_20180427_1241')]

    operations = [
        migrations.RunPython(attrs_migrate),
        migrations.RunPython(clear_comparison_cache),
        migrations.RunPython(add_unique_trace_id),
        migrations.RunPython(split_trace_and_source),
    ]
