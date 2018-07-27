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

from core.lkvog.make import make


_ARCH_OPTS = {
    'arm': {
        'ARCH': 'arm',
        'CROSS_COMPILE': 'arm-unknown-linux-gnueabi-'
    },
    'x86_64': {
        'ARCH': 'x86_64'
    }
}


def make_linux_kernel(work_src_tree, jobs, arch, target, env=None):
    make(work_src_tree, jobs, target, ['{0}={1}'.format(name, value) for name, value in _ARCH_OPTS[arch].items()], env)
