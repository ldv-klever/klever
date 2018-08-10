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
    dependencies = [('service', '0003_move_conf_to_files')]

    operations = [
        migrations.RemoveField(model_name='solvingprogress', name='configuration'),
        migrations.AlterField(model_name='solvingprogress', name='conf_file',
                              field=models.ForeignKey(on_delete=models.deletion.CASCADE, to='jobs.JobFile')),
        migrations.RenameField(model_name='solvingprogress', old_name='conf_file', new_name='configuration'),
    ]
