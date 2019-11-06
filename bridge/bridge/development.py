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

from bridge.common import *

TEMPLATES[0]['OPTIONS']['debug'] = DEBUG = True
DEF_KLEVER_CORE_MODE = 'development'
UNLOCK_FAILED_REQUESTS = True
POPULATE_JUST_PRODUCTION_PRESETS = False
RABBIT_MQ_QUEUE = 'kleverdev'
