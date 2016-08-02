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
            self.resources_written = False
            self.process_sequential_verification_task(bug_kind)
            # Clear output directory since it is the same for all runs.
            shutil.rmtree('output')

    def prepare_property_automaton(self, bug_kind=None):
        for extra_c_file in self.conf['abstract task desc']['extra C files']:
            if 'bug kinds' in extra_c_file:
                for found_bug_kind in extra_c_file['bug kinds']:
                    if found_bug_kind == bug_kind:
                        original_automaton = extra_c_file['automaton']
                        automaton_name = bug_kind + ".spc"
                        self.automaton_file = automaton_name
                        with open(automaton_name, 'w', encoding='ascii') as fp_out, \
                                open(original_automaton) as fp_in:
                            for line in fp_in:
                                res = re.search(r'ERROR\(\"(.+)\"\);', line)
                                if res:
                                    current_bug_kind = res.group(1)
                                    if not current_bug_kind == bug_kind:
                                        line = re.sub(r'ERROR\(\"(.+)\"\);', 'GOTO Stop;', line)
                                        self.logger.debug('Removing bug kind {0}'.format(current_bug_kind))
                                fp_out.write('{0}'.format(line))
                        # Remove old '-spec' options from configuration.
                        tmp_verifier_options = []
                        for y in self.conf['VTG strategy']['verifier']['options']:
                            for attr, val in y.items():
                                if not attr == '-spec':
                                    tmp_verifier_options.append({attr: val})
                        self.conf['VTG strategy']['verifier']['options'] = tmp_verifier_options
                        self.conf['VTG strategy']['verifier']['options'].append({'-spec': automaton_name})

    def prepare_bug_kind_functions_file(self, bug_kind=None):
        if self.mpv:
            # We do not need it for property automata.
            return
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
        self.conf['abstract task desc']['extra C files'].append({'C file': os.path.abspath('bug kind funcs.c')})
