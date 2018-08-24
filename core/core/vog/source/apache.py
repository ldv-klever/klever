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

import os
import json

import core.utils
from core.vog.source.userspace import Userspace


class Apache(Userspace):
    """This class correspnds to Busybox and its applets"""
    # todo: We need a better filter
    _CLADE_CONF = {
        "log_level": "INFO",
        "CC.which_list": [
            "/usr/lib/gcc/x86_64-linux-gnu/7/cc1",
            "/usr/bin/x86_64-linux-gnu-gcc"
        ],
        "CC.store_deps": True,
        "Common.filter": [
            "/tmp/.*"
        ],
        "Common.filter_in": [
            ".*?\\.tmp$",
            "tmp\\.\\w+\\.c$",
            "^tmp.*?\\.c$",
            "-",
            "/dev/null",
            ".*?built-in\\.o$"
        ],
        "Common.filter_out": [
            "/dev/null",
            ".*?\\.cmd$",
            "tmp\\.\\w+"
        ]
    }

    def __init__(self, logger, conf):
        super().__init__(logger, conf)
        self._subsystems = {m: False for m in self.conf['project'].get('subsystem', [])}
        self._targets = {s: False for s in self.conf['project'].get('files', [])}

    def check_target(self, candidate):
        if 'all' in self._subsystems:
            self._subsystems['all'] = True
            return True
        if 'all' in self._targets:
            self._targets['all'] = True
            return True
        return True
