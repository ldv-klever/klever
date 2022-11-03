# Copyright (c) 2020 ISP RAS (http://www.ispras.ru)
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

import distutils.dir_util
import hashlib
import os
import re
import shutil
import subprocess
import tarfile
import tempfile


from klever.cli.build.make import MakeProgram
from klever.cli.utils import make_relative_path


class Linux(MakeProgram):
    _CLADE_PRESET = 'klever_linux_kernel'
    _ARCH_OPTS = {
        'arm': {
            'ARCH': 'arm',
            'CROSS_COMPILE': 'arm-unknown-eabi-'
        },
        'arm64': {
            'ARCH': 'arm64',
            'CROSS_COMPILE': 'aarch64_be-unknown-linux-gnu-'
        },
        'x86_64': {
            'ARCH': 'x86_64'
        }
    }

    def __init__(self, logger, target_program_desc):
        # Always specify CIF to be used by Clade since this variable is global and it can be accidentally reused.
        architecture = target_program_desc['architecture']
        self._CLADE_CONF['Info.cif'] = self._ARCH_OPTS[architecture].get('CROSS_COMPILE', '') + 'cif'

        super().__init__(logger, target_program_desc)
        self.kconfig_config = None

        if not self.version:
            self.version = self._make('kernelversion', get_output=True)[0]

    def _clean(self):
        self._make('mrproper')

    def _configure(self):
        self.logger.info('Configure Linux kernel')

        # Linux kernel configuration can be specified by means of configuration file or configuration target.
        # all configuration files are located in the description directory
        conf_file = os.path.join(self.target_program_desc['description directory'],
                                 self.target_program_desc['configuration'])

        if os.path.isfile(conf_file):
            self.logger.info('Linux kernel configuration file is "{0}"'.format(conf_file))

            # Use configuration file SHA1 digest as Linux kernel configuration.
            with open(conf_file, 'rb') as fp:
                self.configuration = hashlib.sha1(fp.read()).hexdigest()[:7]

            self.logger.info(f'Linux kernel configuration file SHA1 digest is "{self.configuration}"')
            shutil.copy(conf_file, self.work_src_tree)
            self.kconfig_config = os.path.basename(conf_file)
            target = ['oldconfig', f'KCONFIG_CONFIG={self.kconfig_config}']
        else:
            # Use configuration target as Linux kernel configuration.
            self.configuration = self.target_program_desc['configuration']

            self.logger.debug(f'Linux kernel configuration target is "{self.configuration}"')

            target = [self.configuration]

        self._make(*target)

    def _make(self, *target, **kwargs):
        kwargs['opts'] = [f'{name}={value}' for name, value in self._ARCH_OPTS[self.architecture].items()]

        if self.kconfig_config:
            kwargs['opts'].append(f'KCONFIG_CONFIG={self.kconfig_config}')

        return super()._make(*target, **kwargs)

    def _build(self):
        self.logger.info('Build Linux kernel')

        # Build Linux kernel if necessary.
        if self.target_program_desc.get('build kernel'):
            self._make('vmlinux', intercept_build_cmds=True)

        # To build external Linux kernel modules we need to specify "M=path/to/ext/modules/dir".
        ext_modules = self.__prepare_ext_modules()

        try:
            # Try to prepare for building modules. This is necessary and should finish successfully when the Linux
            # kernel supports loadable modules.
            self._make('modules_prepare', intercept_build_cmds=True)
            # Use target "modules" when the Linux kernel supports loadable modules.
            modules_make_target = 'modules'
        except subprocess.CalledProcessError:
            # Otherwise the command above will most likely fail. In this case compile special file, namely,
            # scripts/mod/empty.o, that seems to exist in all Linux kernel versions and that will provide options for
            # building C files including headers necessary for models.
            self._make('scripts/mod/empty.o', intercept_build_cmds=True)
            # Build all builtin modules indirectly when the Linux kernel doesn't support loadable modules.
            modules_make_target = 'all'

        if len(self.target_program_desc.get('loadable kernel modules', [])) > 0:
            self.logger.info('Build loadable kernel modules')

            # Process building of all modules separately.
            if 'all' in self.target_program_desc['loadable kernel modules']:
                if len(self.target_program_desc['loadable kernel modules']) != 1:
                    raise ValueError('Can not build all modules and something else')

                self._make(*((['M=' + os.path.join(ext_modules, 'ext-modules')] if ext_modules else []) +
                             [modules_make_target]),
                           intercept_build_cmds=True)
            else:
                # Check that modules aren't intersect explicitly.
                self.__check_intersection_of_modules()

                for build_target in self.__get_build_targets(ext_modules, modules_make_target):
                    self._make(*build_target, intercept_build_cmds=True)

        # Generate C file including extra headers and Makefile. Compile this C file. It will be treated as part of
        # the kernel, so, one will need to filter them out later if required.
        if 'extra headers' in self.target_program_desc:
            tmp_dir = tempfile.mkdtemp()
            self.tmp_dirs.append(tmp_dir)

            with open(os.path.join(tmp_dir, 'extra-headers.c'), 'w', encoding='utf-8') as fp:
                for header in self.target_program_desc['extra headers']:
                    if header not in self.target_program_desc.get('exclude extra headers', []):
                        fp.write(f'#include <{header}>\n')

            with open(os.path.join(tmp_dir, 'Makefile'), 'w', encoding='utf-8') as fp:
                fp.write('obj-y += extra-headers.o\n')

            self._make('M=' + tmp_dir, 'extra-headers.o', intercept_build_cmds=True)

    def __prepare_ext_modules(self):
        ext_modules = self.target_program_desc.get('external modules')

        if not ext_modules:
            return None

        # all external modules are located in the description directory
        ext_modules = os.path.join(self.target_program_desc['description directory'], ext_modules)

        tmp_dir = tempfile.mkdtemp()
        self.tmp_dirs.append(tmp_dir)

        # Always put source code of external loadable Linux kernel modules into this magical directory as this will
        # allow to distinguish them at various stages later.
        work_src_tree = os.path.join(tmp_dir, 'ext-modules')
        # Parent directory of this magical directory will be trimmed from program fragment identifiers (absolute paths
        # to external loadable Linux kernel modules) and file names.
        self.work_src_trees.append(tmp_dir)

        self.logger.info(
            f'Fetch source code of external loadable Linux kernel modules from "{ext_modules}" to "{work_src_tree}"')

        if os.path.isdir(ext_modules):
            self.logger.debug('External loadable Linux kernel modules source code is provided in form of source tree')
            distutils.dir_util.copy_tree(ext_modules, work_src_tree)
        elif os.path.isfile(ext_modules):
            self.logger.debug('External loadable Linux kernel modules source code is provided in form of archive')
            with tarfile.open(ext_modules, encoding='utf-8') as TarFile:
                def is_within_directory(directory, target):
                    
                    abs_directory = os.path.abspath(directory)
                    abs_target = os.path.abspath(target)
                
                    prefix = os.path.commonprefix([abs_directory, abs_target])
                    
                    return prefix == abs_directory
                
                def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
                
                    for member in tar.getmembers():
                        member_path = os.path.join(path, member.name)
                        if not is_within_directory(path, member_path):
                            raise Exception("Attempted Path Traversal in Tar File")
                
                    tar.extractall(path, members, numeric_owner=numeric_owner) 
                    
                
                safe_extract(TarFile, work_src_tree)

        self.logger.info('Make canonical working source tree of external loadable Linux kernel modules')
        work_src_tree_root = None
        for dirpath, _, filenames in os.walk(work_src_tree):
            ismakefile = False
            if 'Makefile' in filenames:
                ismakefile = True

            # Generate Linux kernel module Makefiles recursively starting from source tree root directory if they do not
            # exist.
            if self.target_program_desc['generate makefiles']:
                if not work_src_tree_root:
                    work_src_tree_root = dirpath

                if not ismakefile:
                    with open(os.path.join(dirpath, 'Makefile'), 'w', encoding='utf-8') as fp:
                        fp.write('obj-m += $(patsubst %, %/, $(notdir $(patsubst %/, %, {0})))\n'
                                 .format('$(filter %/, $(wildcard $(src)/*/))'))
                        fp.write('obj-m += $(notdir $(patsubst %.c, %.o, $(wildcard $(src)/*.c)))\n')
                        fp.write('ccflags-y += '
                                 # Specify additional directory to search for model headers.
                                 '-I' + os.path.realpath(
                                        self.target_program_desc['external modules header files search directory']) +
                                 # Like in klever.core.vtg.weaver.Weaver.weave.
                                 ' -DLDV_{0}'.format(self.architecture.upper().replace('-', '_')))
            elif ismakefile:
                work_src_tree_root = dirpath
                break

        if not work_src_tree_root:
            raise ValueError(f'Could not find Makefile in working source tree "{work_src_tree}"')
        elif not os.path.samefile(work_src_tree_root, work_src_tree):
            self.logger.debug(f'Move contents of "{work_src_tree_root}" to "{work_src_tree}"')

            for path in os.listdir(work_src_tree_root):
                shutil.move(os.path.join(work_src_tree_root, path), work_src_tree)

            trash_dir = work_src_tree_root
            while True:
                parent_dir = os.path.join(trash_dir, os.path.pardir)
                if os.path.samefile(parent_dir, work_src_tree):
                    break
                trash_dir = parent_dir
            self.logger.debug(f'Remove "{trash_dir}"')
            shutil.rmtree(os.path.realpath(trash_dir))

        return tmp_dir

    def __check_intersection_of_modules(self):
        for i, modules1 in enumerate(self.target_program_desc['loadable kernel modules']):
            for j, modules2 in enumerate(self.target_program_desc['loadable kernel modules']):
                if i != j and modules1 == modules2:
                    raise ValueError(f'Modules "{modules1}" are duplicated')
                elif i != j and (not re.search(r'\.ko$', modules1) or not re.search(r'\.ko$', modules2)):
                    # Get rid of file names, remain just directories.
                    modules1_dir = os.path.dirname(modules1) \
                        if re.search(r'\.ko$', modules1) else modules1
                    modules2_dir = os.path.dirname(modules2) \
                        if re.search(r'\.ko$', modules2) else modules2

                    if modules1_dir != make_relative_path([modules2_dir], modules1_dir):
                        raise ValueError(f'Modules "{modules1}" are subset of modules "{modules2}"')

    def __get_build_targets(self, ext_modules, modules_make_target):
        # Examine modules to get all build targets. Do not build immediately to catch mistakes earlier.
        build_targets = []

        for modules in self.target_program_desc['loadable kernel modules']:
            # Modules ending with .ko imply individual modules.
            if re.search(r'\.ko$', modules):
                build_target = os.path.join(ext_modules, modules) if ext_modules else modules
                build_targets.append(['M={0}'.format(os.path.dirname(build_target)), os.path.basename(modules)])
            # Otherwise it is directory that can contain modules.
            else:
                if ext_modules:
                    if not os.path.isdir(os.path.join(ext_modules, modules)):
                        raise ValueError(f'There is no directory "{modules}" inside "{ext_modules}"')

                    build_target = 'M=' + os.path.join(ext_modules, modules)
                else:
                    if not os.path.isdir(os.path.join(self.work_src_tree, modules)):
                        raise ValueError(f'There is no directory "{modules}" inside "{self.work_src_tree}"')

                    build_target = 'M=' + modules

                build_targets.append([build_target, modules_make_target])

        return build_targets
