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

import os
import re
import subprocess

from core.lkvog.linux_kernel.make import make_linux_kernel


def build_linux_kernel(logger, work_src_tree, jobs, arch, kernel, modules, ext_modules, model_headers):
    logger.info('Build Linux kernel')

    loadable_modules_support = False
    try:
        # Try to prepare for building modules. This is necessary and should finish successfully when the Linux
        # kernel has loadable modules support.
        make_linux_kernel(work_src_tree, jobs, arch, ['modules_prepare'])
        loadable_modules_support = True
    except subprocess.CalledProcessError:
        # TODO: indeed this looks to be project specific, thus, it should be optional.
        # Otherwise the command above will most likely fail. In this case compile special file, namely,
        # scripts/mod/empty.o, that seems to exist in all Linux kernel versions and that will provide options for
        # building
        make_linux_kernel(work_src_tree, jobs, arch, ['scripts/mod/empty.o'])

    if kernel:
        make_linux_kernel(work_src_tree, jobs, arch, ['vmlinux'])

    # To build external Linux kernel modules we need to specify "M=path/to/ext/modules/dir".
    ext_modules_make_opt = ['M=' + ext_modules] if ext_modules else []

    # Specially process building of all modules.
    if 'all' in modules:
        if len(modules) != 1:
            raise ValueError('Can not build all modules and something else')

        # Use target "modules" when the Linux kernel supports loadable modules.
        if loadable_modules_support:
            make_linux_kernel(work_src_tree, jobs, arch, ext_modules_make_opt + ['modules'])
        # Otherwise build all builtin modules indirectly by using target "all".
        else:
            make_linux_kernel(work_src_tree, jobs, arch, ext_modules_make_opt + ['all'])
    else:
        # Check that module sets aren't intersect explicitly.
        for i, modules1 in enumerate(modules):
            for j, modules2 in enumerate(modules):
                if i != j and modules1.startswith(modules2):
                    raise ValueError('Module set "{0}" is subset of module set "{1}"'
                                     .format(modules1, modules2))

        # Examine module sets to get all build targets. Do not build immediately to catch mistakes earlier.
        build_targets = []
        for modules in modules:
            # Module sets ending with .ko imply individual modules.
            if re.search(r'\.ko$', modules):
                build_targets.append(ext_modules_make_opt + [modules])
            # Otherwise it is directory that can contain modules.
            else:
                if ext_modules:
                    modules_dir = os.path.join(ext_modules, modules)

                    if not os.path.isdir(modules_dir):
                        raise ValueError('There is not directory "{0}" inside "{1}"'.format(modules, ext_modules))

                    build_targets.append(['M=' + modules_dir])
                else:
                    if not os.path.isdir(os.path.join(work_src_tree, modules)):
                        raise ValueError('There is not directory "{0}" inside "{1}"'.format(modules, work_src_tree))

                    build_targets.append(['M=' + modules])

        for build_target in build_targets:
            make_linux_kernel(work_src_tree, jobs, arch, build_target)

    if not model_headers:
        return

    # # Find out CC command outputting 'scripts/mod/empty.o'. It will be used to compile artificial C files for
    # # getting model headers.
    # import clade
    #
    # clade = clade.Clade()
    # clade.set_work_dir(self.work_dir)
    # empty_cc = clade.get_cc().load_json_by_in('scripts/mod/empty.c')
    #
    # os.makedirs('model-headers')
    #
    # for c_file, headers in model_headers.items():
    #     logger.info('Copy headers for model with C file "{0}"'.format(c_file))
    #
    #     model_headers_c_file = os.path.join('model-headers', os.path.basename(c_file))
    #
    #     with open(model_headers_c_file, mode='w', encoding='utf8') as fp:
    #         for header in headers:
    #             fp.write('#include <{0}>\n'.format(header))
    #
    #     subprocess.check_call(['clade-exec', empty_cc['command']] + empty_cc['opts'] +
    #                           [os.path.abspath(model_headers_c_file)] +
    #                           ['-o', os.path.splitext(os.path.abspath(model_headers_c_file))[0] + '.o'],
    #                           cwd=empty_cc['cwd'], env=env)
