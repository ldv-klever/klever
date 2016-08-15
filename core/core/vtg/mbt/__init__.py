#!/usr/bin/python3

import os
import re

from core.vtg.mav import MAV


# Multiple Bug Types.
class MBT(MAV):

    assert_to_bug_kinds = {}

    def print_strategy_information(self):
        self.logger.info('Launch strategy "Multiple Bug Types"')
        self.logger.info('Generate one verification task and check all bug types at once')

    def get_all_bug_kinds(self):
        bug_kinds = []
        for extra_c_file in self.conf['abstract task desc']['extra C files']:
            if 'bug kinds' in extra_c_file:
                bug_kinds_for_rule_specification = extra_c_file['bug kinds']
                common_bug_kind = bug_kinds_for_rule_specification[0]
                rule = self.parse_bug_kind(common_bug_kind)
                if rule:
                    common_bug_kind = rule
                self.assert_to_bug_kinds[common_bug_kind] = bug_kinds_for_rule_specification
                bug_kinds.append(common_bug_kind)
        return bug_kinds

    def create_asserts(self):
        self.logger.debug('Merging all bug kinds for each rule specification')
        # Bug kind is rule specification.
        bug_kinds = self.get_all_bug_kinds()
        for bug_kind in bug_kinds:
            self.number_of_asserts += 1
            function = "{0}".format(re.sub(r'\W', '_', bug_kind))
            self.assert_function[bug_kind] = function
        self.logger.debug('Multi-Aspect Verification will check "{0}" asserts'.format(self.number_of_asserts))

    def prepare_bug_kind_functions_file(self):
        self.logger.debug('Prepare bug kind functions file "bug kind funcs.c"')

        # Create file with all checked asserts.
        with open('bug kind funcs.c', 'w', encoding='utf8') as fp:
            fp.write('/* This file was generated for Multi-Aspect Verification*/\n')
            for rule_specification, bug_kinds in self.assert_to_bug_kinds.items():
                error_function_for_rule_specification = "{0}".format(re.sub(r'\W', '_', rule_specification))
                fp.write('void {0}{1}(void);\n'.format(self.error_function_prefix,
                                                       error_function_for_rule_specification))
                for bug_kind in bug_kinds:
                    error_function_for_bug_kind = "{0}".format(re.sub(r'\W', '_', bug_kind))
                    fp.write('void ldv_assert_{0}(int expr) {{\n\tif (!expr)\n\t\t{1}{2}();\n}}\n'.
                        format(error_function_for_bug_kind, self.error_function_prefix,
                               error_function_for_rule_specification))

        # Add bug kind functions file to other abstract verification task files.
        self.conf['abstract task desc']['extra C files'].append(
            {'C file': os.path.abspath('bug kind funcs.c')})
