#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
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
import re

from core.vtg.mav import MAV


# Multiple Bug Kinds.
class MBK(MAV):

    def print_strategy_information(self):
        self.logger.info('Launch strategy "Multiple Bug Kinds"')
        self.logger.info('Generate one verification task and check all bug kinds at once')

    def create_asserts(self):
        # Bug kind is assert.
        bug_kinds = self.get_all_bug_kinds()
        for bug_kind in bug_kinds:
            self.number_of_asserts +=1
            function = "{0}".format(re.sub(r'\W', '_', bug_kind))
            self.assert_function[bug_kind] = function
        self.logger.debug('Multi-Aspect Verification will check "{0}" asserts'.format(self.number_of_asserts))

    def prepare_bug_kind_functions_file(self):
        self.logger.debug('Prepare bug kind functions file "bug kind funcs.c"')

        # Create file with all checked asserts.
        with open('bug kind funcs.c', 'w', encoding='utf8') as fp:
            fp.write('/* This file was generated for Multi-Aspect Verification*/\n')
            for bug_kind, function in self.assert_function.items():
                fp.write('void {0}{1}(void);\n'.format(self.error_function_prefix, function))
                fp.write('void ldv_assert_{0}(int expr) {{\n\tif (!expr)\n\t\t{1}{0}();\n}}\n'.
                    format(function, self.error_function_prefix))

        # Add bug kind functions file to other abstract verification task files.
        self.conf['abstract task desc']['extra C files'].append(
            {'C file': os.path.abspath('bug kind funcs.c')})
