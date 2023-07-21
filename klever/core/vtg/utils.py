#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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

import klever.core.utils

from clade.extensions.opts import filter_opts


def define_arch_dependent_macro(conf):
    return '-DLDV_{0}'.format(conf['architecture'].upper().replace('-', '_'))


# Many files and directories which are searched by VTG plugins are located within directory "specifications". Help to
# discover them by adding that directory as prefix.
def find_file_or_dir(logger, main_work_dir, file_or_dir):
    try:
        return klever.core.utils.find_file_or_dir(logger, main_work_dir, os.path.join('specifications', file_or_dir))
    except FileNotFoundError:
        return klever.core.utils.find_file_or_dir(logger, main_work_dir, file_or_dir)


def get_cif_or_aspectator_exec(conf, exec_cmd):
    return conf['CIF']['cross compile prefix'] + exec_cmd


def prepare_cif_opts(opts, clade, model_opts=False):
    new_opts = []
    meta = clade.get_meta()

    # Keep model options as well as build options when input files were not preprocessed.
    if model_opts or not meta['conf'].get("Compiler.preprocess_cmds", False):
        new_opts = filter_opts(opts, clade.get_storage_path)

    extra_cc_opts = meta['conf'].get('Info.extra_CIF_opts', [])
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
