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

import re


def get_deps_from_gcc_deps_file(deps_file):
    deps = []

    with open(deps_file, encoding='utf8') as fp:
        match = re.match(r'[^:]+:(.+)', fp.readline())
        if match:
            first_dep_line = match.group(1)
        else:
            raise AssertionError('Dependencies file has unsupported format')

        for dep_line in [first_dep_line] + fp.readlines():
            dep_line = dep_line.lstrip(' ')
            dep_line = dep_line.rstrip(' \\\n')
            if not dep_line:
                continue
            deps.extend(dep_line.split(' '))

    return deps
