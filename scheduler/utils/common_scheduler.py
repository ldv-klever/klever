#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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


class CalculationSystem:

    def __init__(self):
        pass

    def update_nodes(self, nodes):
        pass

    def update_status(self, status):
        pass

    def schedule_tasks(self):
        pass

    def schedule_jobs(self):
        pass

    def claim_resources(self, identifier, job=False):
        pass

    def release_resources(self, identifier, job=False, KeepDisk=False):
        pass

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'