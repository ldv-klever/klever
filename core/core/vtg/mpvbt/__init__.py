#!/usr/bin/python3

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
                common_bug_kind = os.path.commonprefix(bug_kinds_for_rule_specification)
                automaton = extra_c_file['automaton']
                self.property_automata[common_bug_kind] = automaton
        self.logger.debug('Multi-Property Verification will check "{0}" properties'.
                          format(self.property_automata.__len__()))
