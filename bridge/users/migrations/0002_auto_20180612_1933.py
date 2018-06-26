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

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('users', '0001_initial')]

    operations = [
        migrations.AlterField(model_name='view', name='type', field=models.CharField(choices=[
            ('0', 'component attributes'), ('1', 'jobTree'), ('2', 'DecisionResults'),
            ('3', 'reportChildren'), ('4', 'SafesAndUnsafesList'), ('5', 'SafesAndUnsafesList'),
            ('6', 'UnknownsList'), ('7', 'marksList'), ('8', 'marksList'), ('9', 'marksList'),
            ('10', 'UnsafeAssMarks'), ('11', 'SafeAssMarks'), ('12', 'UnknownAssMarks'),
            ('13', 'UnsafeAssReports'), ('14', 'SafeAndUnknownAssReports'), ('15', 'SafeAndUnknownAssReports'),
            ('16', 'AssociationChanges'), ('17', 'AssociationChanges'), ('18', 'AssociationChanges')
        ], default='1', max_length=2)),
    ]
