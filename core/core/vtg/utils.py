#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
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

import core.utils


# Many files and directories which are searched by VTG plugins are located within directory "specifications". Help to
# discover them by addinig that directory as prefix.
def find_file_or_dir(logger, main_work_dir, file_or_dir):
    try:
        return core.utils.find_file_or_dir(logger, main_work_dir, file_or_dir)
    except FileNotFoundError:
        return core.utils.find_file_or_dir(logger, main_work_dir, os.path.join('specifications', file_or_dir))


def prepare_cif_opts(opts, clade, model_opts=False):
    new_opts = []
    meta = clade.get_meta()

    is_sysroot_search_dir = False
    is_include = False

    # Keep model options as well as build options when input files were not preprocessed.
    if model_opts or not meta['conf'].get("Compiler.preprocess_cmds", False):
        skip_opt_value = False
        for opt in opts:
            if skip_opt_value:
                skip_opt_value = False
                continue

            # Get rid of options unsupported by Aspectator.
            match = re.match('(-Werror=date-time|-mpreferred-stack-boundary|-fsanitize-coverage|--param=|.*?-MD).*'
                             , opt)
            if match:
                continue

            match = re.match('--param', opt)
            if match:
                skip_opt_value = True
                continue

            new_opt = opt

            # --sysroot has effect just if search directories specified with help of absolute paths start with "=".
            if is_sysroot_search_dir:
                if new_opt.startswith('/'):
                    new_opt = '=' + new_opt

                is_sysroot_search_dir = False
            else:
                match = re.match('-(I|iquote|isystem|idirafter)(.*)', new_opt)
                if match:
                    if match.group(2):
                        if match.group(2).startswith('/'):
                            new_opt = '-{0}={1}'.format(match.group(1), match.group(2))
                    else:
                        is_sysroot_search_dir = True

            # Explicitly change absolute paths passed to --include since --sysroot does not help with it.
            if is_include:
                if new_opt.startswith('/'):
                    new_opt = clade.storage_dir + new_opt

                is_include = False
            else:
                match = re.match('-include(.*)', new_opt)
                if match:
                    if match.group(1):
                        if match.group(1).startswith('/'):
                            new_opt = '-include' + clade.storage_dir + match.group(1)
                    else:
                        is_include = True

            new_opts.append(new_opt.replace('"', '\\"'))

        # Aspectator will search for headers within Clade storage.
        new_opts.append('-isysroot' + clade.storage_dir)

    extra_cc_opts = meta['conf'].get('Info.extra_CIF_opts', list())
    new_opts.extend(extra_cc_opts)

    return new_opts


# Catch only the first line having "error:" substring. This helps to filter out a lot of warnings and other errors.
class CIFErrorFilter:
    def __init__(self):
        self.found_first_error = False

    def __call__(self, line):
        if self.found_first_error:
            return False

        if 'error:' in line:
            self.found_first_error = True
            return True

        return False
