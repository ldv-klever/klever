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

from django.db import models


class LockTable(models.Model):
    name = models.CharField(max_length=64, unique=True, db_index=True)
    locked = models.BooleanField(default=False)

    class Meta:
        db_table = 'lock_table'

    def __str__(self):
        return self.name


class CallLogs(models.Model):
    name = models.CharField(max_length=64, db_index=True)
    enter_time = models.DecimalField(max_digits=14, decimal_places=4)
    execution_time = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    return_time = models.DecimalField(max_digits=14, decimal_places=4, null=True)
    execution_delta = models.FloatField(default=0)
    wait1 = models.FloatField(default=0)
    wait2 = models.FloatField(default=0)
    is_failed = models.BooleanField(default=True)

    class Meta:
        db_table = 'tools_call_logs'
