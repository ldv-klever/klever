#
# Copyright (c) 2022 ISP RAS (http://www.ispras.ru)
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

import base64
import requests


class Session:
    # Currently, signing in is not necessary for Consul, but this can change one day.
    def __init__(self):
        self.address = 'http://localhost:8500'

    def kv_get(self, key):
        url = self.address + '/v1/kv/' + key
        response = requests.get(url)

        if response.status_code == 404:
            return None

        if not response.ok:
            raise RuntimeError(
                f'Cannot get value by key "{key}" (url: "{url}", status code: "{response.status_code}",' +
                f'failure reason: "{response.reason}")')

        return base64.b64decode(response.json()[0]['Value'].encode('utf-8')).decode('utf-8')

    def kv_put(self, key, value):
        url = self.address + '/v1/kv/' + key
        response = requests.put(url, value)

        if not response.ok:
            raise RuntimeError(
                f'Cannot set value by key "{key}" (url: "{url}", status code: "{response.status_code}",' +
                f'failure reason: "{response.reason}")')

    def kv_delete(self, key):
        url = self.address + '/v1/kv/' + key
        response = requests.delete(url)

        if not response.ok:
            raise RuntimeError(
                f'Cannot delete value by key "{key}" (url: "{url}", status code: "{response.status_code}",' +
                f'failure reason: "{response.reason}")')
