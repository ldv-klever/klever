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
import re
import shutil

from core.vtg.separated import SeparatedStrategy


# This strategy is aimed at merging all bug kinds inside each bug type
# and at checking each bug type as a separated verification run.
class SBT(SeparatedStrategy):
    def print_strategy_information(self):
        self.logger.info('Launch strategy "Single Bug Type"')
        self.logger.info('Generate one verification task for each bug type')

    def main_cycle(self):
        self.resources_written = False
        self.process_sequential_verification_task()

    def prepare_bug_kind_functions_file(self, bug_kind=None):
        self.logger.debug('Prepare bug kind functions file "bug kind funcs.c"')

        # Get all bug kinds.
        bug_kinds = self.get_all_bug_kinds()

        # Create bug kind function definitions that all call __VERIFIER_error() since this strategy doesn't distinguish
        # different bug kinds.
        with open('bug kind funcs.c', 'w', encoding='utf8') as fp:
            fp.write('/* http://sv-comp.sosy-lab.org/2015/rules.php */\nvoid __VERIFIER_error(void);\n')
            for bug_kind in bug_kinds:
                fp.write('void ldv_assert_{0}(int expr) {{\n\tif (!expr)\n\t\t__VERIFIER_error();\n}}\n'.format(
                    re.sub(r'\W', '_', bug_kind)))

        # Add bug kind functions file to other abstract verification task files. Absolute file path is required to get
        # absolute path references in error traces.
        self.conf['abstract task desc']['extra C files'].append({'C file': os.path.abspath('bug kind funcs.c')})
