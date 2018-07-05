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
import django.db.backends.utils
from django.db import OperationalError
from bridge.settings import DATABASES


original = django.db.backends.utils.CursorWrapper.execute


# Fix https://forge.ispras.ru/issues/7146.
def execute_wrapper(*args, **kwargs):
    if args[0].db.vendor == 'mysql':
        while True:
            try:
                return original(*args, **kwargs)
            except OperationalError as e:
                from MySQLdb.constants.ER import LOCK_DEADLOCK
                if e.args[0] != LOCK_DEADLOCK:
                    raise e
                time.sleep(0.1)
    else:
        return original(*args, **kwargs)

django.db.backends.utils.CursorWrapper.execute = execute_wrapper
