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
import zipfile


def _merge_files(self):
    regex = re.compile('# 40 ".*/arm-unknown-linux-gnueabi/4.6.0/include/stdarg.h"')
    files = []

    if self.conf['VTG strategy']['merge source files']:
        self.logger.info('Merge source files by means of CIL')

        # CIL doesn't support asm goto (https://forge.ispras.ru/issues/1323).
        self.logger.debug('Ignore asm goto expressions')

        c_files = ()
        for extra_c_file in self.conf['abstract task desc']['extra C files']:
            if 'C file' not in extra_c_file:
                continue
            trimmed_c_file = '{0}.trimmed.i'.format(os.path.splitext(os.path.basename(extra_c_file['C file']))[0])
            with open(os.path.join(self.conf['main working directory'], extra_c_file['C file']),
                      encoding='utf8') as fp_in, open(trimmed_c_file, 'w', encoding='utf8') as fp_out:
                trigger = False

                # Specify original location to avoid references to *.trimmed.i files in error traces.
                fp_out.write('# 1 "{0}"\n'.format(extra_c_file['C file']))
                # Each such expression occupies individual line, so just get rid of them.
                for line in fp_in:

                    # Asm volatile goto
                    l = re.sub(r'asm volatile goto.*;', '', line)

                    if not trigger and regex.match(line):
                        trigger = True
                    elif trigger:
                        l = line.replace('typedef __va_list __gnuc_va_list;',
                                         'typedef __builtin_va_list __gnuc_va_list;')
                        trigger = False

                    fp_out.write(l)

            extra_c_file['new C file'] = trimmed_c_file
            c_files += (trimmed_c_file, )

        args = (
                   'cilly.asm.exe',
                   '--printCilAsIs',
                   '--domakeCFG',
                   '--decil',
                   '--noInsertImplicitCasts',
                   # Now supported by CPAchecker frontend.
                   '--useLogicalOperators',
                   '--ignore-merge-conflicts',
                   # Don't transform simple function calls to calls-by-pointers.
                   '--no-convert-direct-calls',
                   # Don't transform s->f to pointer arithmetic.
                   '--no-convert-field-offsets',
                   # Don't transform structure fields into variables or arrays.
                   '--no-split-structs',
                   '--rmUnusedInlines',
                   '--out', 'cil.i',
               ) + c_files
        core.utils.execute_external_tool(self.logger, args=args)

        if not self.conf['keep intermediate files']:
            for extra_c_file in self.conf['abstract task desc']['extra C files']:
                if 'new C file' in extra_c_file:
                    os.remove(extra_c_file['new C file'])

        files.append('cil.i')

        self.logger.debug('Merged source files was outputted to "cil.i"')
    else:
        for extra_c_file in self.conf['abstract task desc']['extra C files']:
            files.append(extra_c_file['C file'])

    return files


def prepare_verification_task_files_archive(self, files):
    with zipfile.ZipFile('task files.zip', mode='w', compression=zipfile.ZIP_DEFLATED) as zfp:
        for file in files:
            zfp.write(file)