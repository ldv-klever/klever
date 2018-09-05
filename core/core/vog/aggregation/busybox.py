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

import os
import re

from core.vog.common import Aggregation
from core.vog.aggregation.abstract import Abstract


class Busybox(Abstract):
    """
    This is a strategy for the Busybox project. It implements creation of aggregations on base of applets. The algorythm
    collects all C files for a some *_main function and add library functions in accrodance with provided options.
    """

    def __init__(self, logger, conf, divider):
        super(Busybox, self).__init__(logger, conf, divider)
        self._black_list = self.conf['Aggregation strategy'].get('ignore libbb files', [])
        self._white_list = self.conf['Aggregation strategy'].get('allowed libbb files')
        self._single_file_mode = self.conf['Aggregation strategy'].get('ignore dependency from applet dirs', False)
        self._ignore_libbb = self.conf['Aggregation strategy'].get('ignore libbb', False)
        self._always_needed = self.conf['Aggregation strategy'].get('always add files', [])

    def _aggregate(self):
        """
        Just return target fragments as aggregations consisting of fragments that are required by a target one
        collecting required fragments for given depth.

        :return: Generator that retursn Aggregation objects.
        """
        main_func = re.compile("\\w*main")
        # First we need fragments that are completely fullfilled
        self.divider.establish_dependencies()
        for fragment in (f for f in self.divider.target_fragments
                         if any(map(main_func.fullmatch, {e for funcs in f.export_functions.values() for e in funcs}))):
            new = Aggregation(fragment)
            new.name = fragment.name
            new.fragments.add(fragment)
            self._add_dependencies(new)
            yield new

    def _check_fileters(self, fragment):
        # Check that it is not in a black list
        if any(self._belong(fragment, t) for t in self._always_needed):
            return True
        if any(self._belong(fragment, t) for t in self._black_list):
            return False
        # Check white list
        if self._white_list is not None and not any(self._belong(fragment, t) for t in self._white_list):
            return False
        # Check libbb
        if os.path.commonpath(['libbb', fragment]) and self._ignore_libbb:
            return False
        if not os.path.commonpath(['libbb', fragment]) and self._single_file_mode:
            return False
        return True
