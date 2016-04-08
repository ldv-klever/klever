#!/usr/bin/python3

import os
import re
import shutil

from core.vtg.separated import SeparatedStrategy


# This strategy is aimed at creating verification tasks for each
# bug kind and at solving them as separated verification runs.
class SBK(SeparatedStrategy):

    src_files = []

    def print_strategy_information(self):
        self.logger.info('Launch strategy "Single Bug Kind"')
        self.logger.info('Generate one verification task for each bug kind')
        bug_kinds = self.get_all_bug_kinds()
        self.logger.info('Verification tasks contains {0} bug kinds'.format(bug_kinds.__len__()))

    def main_cycle(self):
        self.src_files = self.conf['abstract task desc']['extra C files'].copy()
        for bug_kind in self.get_all_bug_kinds():
            self.process_sequential_verification_task(bug_kind)
            # Clear output directory since it is the same for all runs.
            shutil.rmtree('output')

    def prepare_bug_kind_functions_file(self, bug_kind=None):
        self.logger.debug('Prepare bug kind functions file "bug kind funcs.c"')

        # Create bug kind function definitions that all call __VERIFIER_error() since this strategy doesn't distinguish
        # different bug kinds.
        with open('bug kind funcs.c', 'w') as fp:
            fp.write('/* http://sv-comp.sosy-lab.org/2015/rules.php */\nvoid __VERIFIER_error(void);\n')
            fp.write('void ldv_assert_{0}(int expr) {{\n\tif (!expr)\n\t\t__VERIFIER_error();\n}}\n'.format(
                re.sub(r'\W', '_', bug_kind)))

        # Clear from the previous iteration (*trimmed* files).
        self.conf['abstract task desc']['extra C files'].clear()
        self.conf['abstract task desc']['extra C files'] = self.src_files.copy()
        # Add bug kind functions file to other abstract verification task files.
        self.conf['abstract task desc']['extra C files'].append(
            {'C file': os.path.relpath('bug kind funcs.c', os.path.realpath(self.conf['source tree root']))})
