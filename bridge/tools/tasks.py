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

import time

from celery import shared_task

from tools.models import CallLogs


@shared_task
def clear_call_logs(num_of_days):
    """
    Clear call logs that are older then "num_of_days" days.
    num_of_days: integer, number of days
    :return:
    """
    # 30 days exactly
    border_time = time.time() - 86400 * num_of_days
    CallLogs.objects.filter(enter_time__lt=border_time).delete()
