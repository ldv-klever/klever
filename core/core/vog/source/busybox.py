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


class Busybox(Userspace):
    """This class correspnds to Busybox and its applets"""
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
    _APPLETS_FILE = 'busybox applets.json'

    def __init__(self, logger, conf):
        super().__init__(logger, conf)
        self._subsystems = {m: False for m in self.conf['project'].get('applets dirs', [])}
        self._targets = {s: False for s in self.conf['project'].get('applets', [])}
        self._all_applets = None

    @property
    def applets(self):
        if not self._all_applets and not self._build_flag:
            self._retrieve_applets_list()
        return self._all_applets

    def check_target(self, candidate):
        candidate = core.utils.make_relative_path(self.source_paths, candidate)
        path, name = os.path.split(candidate)
        name = os.path.splitext(name)[0]

        if 'all' in self._subsystems:
            self._subsystems['all'] = True
            return True
        matched_subsystems = list(s for s in self._subsystems if os.path.commonpath([path, s]) == s)
        if len(matched_subsystems) == 1:
            self._subsystems[matched_subsystems[0]] = True
            return True

        if name not in self.applets:
            return False
        else:
            if 'all' in self._targets:
                self._targets['all'] = True
                return True

            if name in self._targets:
                self._targets[name] = True
                return True

            # This should not be true ever.
            if len(matched_subsystems) > 1:
                raise ValueError('Several subsystems "{0}" match candidate "{1}"'.format(matched_subsystems, candidate))

            return False

    def _retrieve_applets_list(self):
        path = self._clade.FileStorage().convert_path(self._APPLETS_FILE)
        with open(path, 'r', encoding='utf8') as fp:
            self._all_applets = json.load(fp)

    def _cleanup(self):
        super()._cleanup()
        self.logger.info('Clean working source tree')
        core.utils.execute(self.logger, ('make', 'mrproper'), cwd=self.work_src_tree)

    def configure(self):
        self.logger.info('Configure Busybox')
        # Do not call configure
        super(Userspace, self).configure()
        # Use make
        self._make([self.configuration], opts=[])

    def build(self):
        super().build()

        # Run busybox and get full list of applets
        self._all_applets = core.utils.execute(self.logger, ['busybox', '--list'], cwd=self.work_src_tree, collect_all_stdout=True)
        if not isinstance(self._all_applets, list):
            raise RuntimeError('Cannot get list of applets from busybox, got {} instead of a list'.
                               format(self._all_applets))

        storage = self._clade.FileStorage()
        with open(self._APPLETS_FILE, 'w', encoding='utf8') as fp:
            json.dump(self._all_applets, fp)
        storage.save_file(self._APPLETS_FILE)
