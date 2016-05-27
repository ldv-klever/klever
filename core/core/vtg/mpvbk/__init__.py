#!/usr/bin/python3

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
                    new_automaton = []
                    state = None
                    for line in automaton:
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
                        res = re.search(r'STATE (\w+) (\w+) :', line)
                        if res:
                            state = res.group(2)
                        new_automaton.append(line)
                    self.property_automata[bug_kind] = new_automaton
        self.logger.debug('Multi-Property Verification will check "{0}" properties'.
                          format(self.property_automata.__len__()))
