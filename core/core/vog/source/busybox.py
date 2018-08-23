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

    def __init__(self, logger, conf):
        super().__init__(logger, conf)
        self._subsystems = {m: False for m in self.conf['project'].get('applets dirs', [])}
        self._modules = {s: False for s in self.conf['project'].get('applets', [])}

    def check_target(self, candidate):
        raise NotImplementedError
        # candidate = core.utils.make_relative_path(self.source_paths, candidate)
        #
        # if 'all' in self._subsystems:
        #     self._subsystems['all'] = True
        #     return True
        #
        # if 'all' in self._modules:
        #     self._modules['all'] = True
        #     return True
        #
        # if self._kernel and candidate.endswith('built-in.o') and os.path.dirname(candidate) in self._subsystems:
        #     self._subsystems[os.path.dirname(candidate)] = True
        #     return True
        #
        # if not self._kernel:
        #     if candidate in self._modules:
        #         self._modules[candidate] = True
        #         return True
        #
        #     matched_subsystems = list(s for s in self._subsystems if os.path.commonpath([candidate, s]) == s)
        #
        #     if len(matched_subsystems) == 1:
        #         self._subsystems[matched_subsystems[0]] = True
        #         return True
        #
        #     # This should not be true ever.
        #     if len(matched_subsystems) > 1:
        #         raise ValueError('Several subsystems "{0}" match candidate "{1}"'.format(matched_subsystems, candidate))
        #
        # return False

    def check_targets_consistency(self):
        raise NotImplementedError
        # for module in (m for m in self._modules if not self._modules[m]):
        #     raise ValueError("No verification objects generated for Linux loadable kernel module {!r}: "
        #                      "check Clade base cache or job.json".format(module))
        # for subsystem in (m for m in self._subsystems if not self._subsystems[m]):
        #     raise ValueError("No verification objects generated for Linux kernel subsystem {!r}: "
        #                      "check Clade base cache or job.json".format(subsystem))

    def configure(self):
        self.logger.info('Configure Busybox')
        # Do not call configure
        super(Userspace, self).configure()
        # Use make
        self._make([self.configuration], opts=[])