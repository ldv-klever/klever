#!/usr/bin/python3

import os
import re

from core.vtg import common


# This strategy is aimed at creating verification tasks for each
# bug kind and at solving them as separated verification runs
# until finding the first bug.
class ABKS(common.SequentialStrategy):

    src_files = []

    def generate_verification_tasks(self):
        self.logger.info('Generate verification tasks for each bug kinds')
        bug_kinds = self.get_all_bug_kinds()
        self.logger.info('Verification tasks contains {0} bug kinds'.format(bug_kinds.__len__()))

        self.src_files = self.conf['abstract task desc']['extra C files'].copy()

        for bug_kind in bug_kinds:
            self.process_sequential_verification_task(bug_kind)

    main = generate_verification_tasks

    def prepare_bug_kind_functions_file(self, bug_kind):
        self.logger.info('Prepare bug kind functions file "bug kind funcs.c"')

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
