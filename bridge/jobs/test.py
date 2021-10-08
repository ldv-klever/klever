#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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

import json
from bridge.utils import file_get_or_create

from jobs.models import JobFile


def create_jobfile():
    data = {'test': 'x', 'data': [1, 2, 3], 'new': None}
    res = file_get_or_create(json.dumps(data), 'test.json', JobFile)
    print("The db file:", res, res.pk)
    print("Delete:", res.delete())
