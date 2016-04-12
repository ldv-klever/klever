#!/usr/bin/python3

import os
import re

from core.vtg.separated import SeparatedStrategy


# This strategy is aimed at merging all bug kinds inside each bug type
# and at checking each bug type as a separated verification run.
class SBT(SeparatedStrategy):
    def print_strategy_information(self):
        self.logger.info('Launch strategy "Single Bug Type"')
        self.logger.info('Generate one verification task for each bug type')

    def main_cycle(self):
        self.process_sequential_verification_task()

    def prepare_property_automaton(self, bug_kind=None):
        for extra_c_file in self.conf['abstract task desc']['extra C files']:
            if 'automaton' in extra_c_file:
                automaton = extra_c_file['automaton']
                automaton_name = self.conf['abstract task desc']['attrs'][1]['rule specification'] + ".spc"
                self.automaton_file = automaton_name

                with open(automaton_name, 'w', encoding='ascii') as fp:
                    for line in automaton:
                        fp.write('{0}'.format(line))
                self.conf['VTG strategy']['verifier']['options'].append({'-spec': automaton_name})

    def prepare_bug_kind_functions_file(self, bug_kind=None):
        if self.mpv:
            # We do not need it for property automata.
            return
        self.logger.debug('Prepare bug kind functions file "bug kind funcs.c"')

        # Get all bug kinds.
        bug_kinds = self.get_all_bug_kinds()

        # Create bug kind function definitions that all call __VERIFIER_error() since this strategy doesn't distinguish
        # different bug kinds.
        with open('bug kind funcs.c', 'w') as fp:
            fp.write('/* http://sv-comp.sosy-lab.org/2015/rules.php */\nvoid __VERIFIER_error(void);\n')
            for bug_kind in bug_kinds:
                fp.write('void ldv_assert_{0}(int expr) {{\n\tif (!expr)\n\t\t__VERIFIER_error();\n}}\n'.format(
                    re.sub(r'\W', '_', bug_kind)))

        # Add bug kind functions file to other abstract verification task files.
        self.conf['abstract task desc']['extra C files'].append(
            {'C file': os.path.relpath('bug kind funcs.c', os.path.realpath(self.conf['source tree root']))})
