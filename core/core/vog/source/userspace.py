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
import core.utils
from core.vog.source import Source


class Userspace(Source):
    """This class correspnds to Linux kernel sources and external modules"""

    _CLADE_CONF = {
        "log_level": "INFO",
        "CC.store_deps": True,
        "Common.filter": [],
        "Common.filter_in": [
            ".*?\\.tmp$",
            "tmp\\.\\w+\\.c$",
            "^tmp.*?\\.c$",
            "/tmp/\\w+.o",
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
    _source_paths = []

    def __init__(self, logger, conf):
        super().__init__(logger, conf)
        self._subsystems = {m: False for m in self.conf['project'].get('directories', [])}
        self._targets = {s: False for s in self.conf['project'].get('objects', [])}

    def check_target(self, candidate):
        candidate = core.utils.make_relative_path(self.source_paths, candidate)

        if 'all' in self._subsystems:
            self._subsystems['all'] = True
            return True

        if 'all' in self._targets:
            self._targets['all'] = True
            return True

        if os.path.dirname(candidate) in self._subsystems:
            self._subsystems[os.path.dirname(candidate)] = True
            return True

        if candidate in self._targets:
            self._targets[candidate] = True
            return True

        matched_subsystems = list(s for s in self._subsystems if os.path.commonpath([candidate, s]) == s)
        if len(matched_subsystems) == 1:
            self._subsystems[matched_subsystems[0]] = True
            return True

        # This should not be true ever.
        if len(matched_subsystems) > 1:
            raise ValueError('Several subsystems "{0}" match candidate "{1}"'.format(matched_subsystems, candidate))

        return False

    def _cleanup(self):
        super()._cleanup()
        self.logger.info('Clean working source tree')
        core.utils.execute(self.logger, ('make', 'clean'), cwd=self.work_src_tree)

    def configure(self):
        self.logger.info('Configure given userspace program')
        super().configure()
        core.utils.execute(self.logger, ['./configure'], cwd=self.work_src_tree)

    def _build(self):
        self.logger.info('Build the given userspace program')
        self._make([], opts=[], intercept_build_cmds=True)

    def prepare_model_headers(self, model_headers):
        # todo: We need to develop some proper scheme for this
        raise NotImplementedError
