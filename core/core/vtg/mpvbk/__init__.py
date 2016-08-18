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

import re

from core.vtg.mpv import MPV


# Multy-Property Verification Bug Kinds.
class MPVBK(MPV):

    def print_strategy_information(self):
        self.logger.info('Launch strategy "Multy-Property Verification Bug Kinds"')
        self.logger.info('Generate one verification task and check all bug kinds at once by means of MPV')

    def create_asserts(self):
        for extra_c_file in self.conf['abstract task desc']['extra C files']:
            if 'bug kinds' in extra_c_file:
                counter = 0
                automaton = extra_c_file['automaton']
                for bug_kind in extra_c_file['bug kinds']:
                    counter += 1
                    preprocessed_automaton = "{0}.{1}.spc".format(automaton, bug_kind)

                    with open(preprocessed_automaton, 'w', encoding='utf8') as fp_out, \
                        open(automaton, encoding='utf8') as fp_in:
                        for line in fp_in:
                            res = re.search(r'ERROR\(\"(.+)\"\);', line)
                            if res:
                                current_bug_kind = res.group(1)
                                if not current_bug_kind == bug_kind:
                                    line = re.sub(r'ERROR\(\"(.+)\"\);', 'GOTO Stop;', line)
                                    self.logger.debug('Removing bug kind {0}'.format(current_bug_kind))
                            res = re.search(r'OBSERVER AUTOMATON (.+)', line)
                            if res:
                                old_name = res.group(1)
                                new_name = old_name + '_' + '{0}'.format(counter)
                                line = re.sub(old_name, new_name, line)
                            fp_out.write(line)
                    self.property_automata[bug_kind] = preprocessed_automaton
        self.logger.debug('Multi-Property Verification will check "{0}" properties'.
                          format(self.property_automata.__len__()))
