#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
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

import os

from core.vtg.mpv import MPV


# Multy-Property Verification Bug Types.
class MPVBT(MPV):

    def print_strategy_information(self):
        self.logger.info('Launch strategy "Multy-Property Verification Bug Types"')
        self.logger.info('Generate one verification task and check all bug types at once by means of MPV')

    def create_asserts(self):
        for extra_c_file in self.conf['abstract task desc']['extra C files']:
            if 'bug kinds' in extra_c_file:
                bug_kinds_for_rule_specification = extra_c_file['bug kinds']
                common_bug_kind = bug_kinds_for_rule_specification[0]
                rule = self.parse_bug_kind(common_bug_kind)
                if rule:
                    common_bug_kind = rule
                automaton = extra_c_file['automaton']
                self.property_automata[common_bug_kind] = automaton
        self.logger.debug('Multi-Property Verification will check "{0}" properties'.
                          format(self.property_automata.__len__()))
