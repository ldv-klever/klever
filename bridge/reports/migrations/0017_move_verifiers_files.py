from __future__ import unicode_literals

import zipfile
from io import BytesIO

from django.core.files import File
from django.db import migrations


def move_files(apps, schema_editor):
    for report in apps.get_model("reports", "ReportComponent").objects.filter(verification=True).exclude(log=''):
        mem1 = BytesIO()
        mem2 = BytesIO()
        has_log = False
        has_files = False
        with zipfile.ZipFile(mem1, 'w', compression=zipfile.ZIP_DEFLATED) as log_p:
            with zipfile.ZipFile(mem2, 'w', compression=zipfile.ZIP_DEFLATED) as vif_p:
                with report.log as fp:
                    with zipfile.ZipFile(fp, 'r') as zfp:
                        for fname in zfp.namelist():
                            if fname == 'log.txt':
                                has_log = True
                                log_p.writestr(fname, zfp.read('log.txt').decode('utf8'))
                            else:
                                has_files = True
                                vif_p.writestr(fname, zfp.read(fname).decode('utf8'))
        if has_files:
            report.log.delete()
            if has_log:
                mem1.seek(0)
                report.log.save('log.zip', File(mem1), False)
            mem2.seek(0)
            report.verifier_input.save('VerifierInput.zip', File(mem2), True)


class Migration(migrations.Migration):
    dependencies = [('reports', '0016_auto_20170913_1804')]
    operations = [migrations.RunPython(move_files)]
