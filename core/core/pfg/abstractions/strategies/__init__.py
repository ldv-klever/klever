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


class Abstract:

    DESC_FILE = 'agregations description.json'

    def __init__(self, logger, conf, desc, deps):
        self.logger = logger
        self.conf = conf
        self.desc = desc
        self.deps = deps
        self._groups = dict()

    def add_group(self, name, fragments):
        if name in self._groups:
            raise ValueError('Cannot add a group with the same name {!r}'.format(name))

        self._groups[name] = fragments

    def get_groups(self):
        self._make_groups()
        return self._groups

    def _make_groups(self):
        for frag in self.deps.target_fragments:
            self.add_group(frag.name, {frag})
