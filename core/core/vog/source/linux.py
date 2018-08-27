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
import shutil
import tarfile
import hashlib

import core.utils
from core.vog.source import Source


class Linux(Source):
    """This class correspnds to Linux kernel sources and external modules"""

    _ARCH_OPTS = {
        'arm': {
            'ARCH': 'arm',
            'CROSS_COMPILE': 'arm-unknown-linux-gnueabi-'
        },
        'x86_64': {
            'ARCH': 'x86_64'
        }
    }
    _EXT_DIR = 'ext-modules/'
    _CLADE_CONF = {
        "log_level": "INFO",
        "CC.store_deps": True,
        "Common.filter": [
            ".*?\\.tmp$"
        ],
        "Common.filter_in": [
            "-",
            "/dev/null",
            "scripts/(?!mod/empty\\.c)",
            "kernel/.*?bounds.*?",
            "arch/x86/tools/relocs",
            "arch/x86/kernel/asm-offsets.c",
            ".*\\.mod\\.c"
        ],
        "Common.filter_out": [
            "/dev/null",
            ".*?\\.cmd$",
            "vmlinux"
        ]
    }

    def __init__(self, logger, conf):
        super(Linux, self).__init__(logger, conf)
        self._kernel = self.conf['project'].get('build kernel', False)
        self.__loadable_modules_support = True
        self._subsystems = {m: False for m in self.conf['project'].get('kernel subsystems', [])}
        self._targets = {s: False for s in self.conf['project'].get('loadable kernel modules', [])}
        self._external_modules = self.conf['project'].get('external modules', False)

    def check_target(self, candidate):
        candidate = core.utils.make_relative_path(self.source_paths, candidate)

        if 'all' in self._subsystems:
            self._subsystems['all'] = True
            return True

        if 'all' in self._targets:
            self._targets['all'] = True
            return True

        if self._kernel and candidate.endswith('built-in.o') and os.path.dirname(candidate) in self._subsystems:
            self._subsystems[os.path.dirname(candidate)] = True
            return True

        if not self._kernel:
            if candidate in self._targets:
                self._targets[candidate] = True
                return True

            matched_subsystems = list(s for s in self._subsystems if os.path.commonpath([candidate, s]) == s)

            if len(matched_subsystems) == 1:
                self._subsystems[matched_subsystems[0]] = True
                return True

            # This should not be true ever.
            if len(matched_subsystems) > 1:
                raise ValueError('Several subsystems "{0}" match candidate "{1}"'.format(matched_subsystems, candidate))

        return False

    def configure(self):
        self.logger.info('Configure Linux kernel')
        super(Linux, self).configure()
        if 'configuration' in self.conf['project']:
            try:
                self.configuration = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                                                 self.conf['project']['configuration'])
            except FileNotFoundError:
                # Linux kernel configuration is not provided in form of file.
                self.configuration = self.conf['project']['configuration']

        self.logger.info('Get Linux kernel version')
        if not self.version:
            output = self._make(['kernelversion'], collect_all_stdout=True)
            self.version = output[0]

        # Linux kernel configuration can be specified by means of configuration file or configuration target.
        if os.path.isfile(self.configuration):
            self.logger.debug('Linux kernel configuration file is "{0}"'.format(self.configuration))

            # Use configuration file SHA1 digest as Linux kernel configuration hash.
            with open(self.configuration, 'rb') as fp:
                conf_hash = hashlib.sha1(fp.read()).hexdigest()[:7]

            self.logger.debug('Linux kernel configuration file SHA1 digest is "{0}"'.format(conf_hash))

            shutil.copy(self.configuration, self.work_src_tree)

            target = ['oldconfig', 'KCONFIG_CONFIG={0}'.format(os.path.basename(self.configuration))]
        else:
            self.logger.debug('Linux kernel configuration target is "{0}"'.format(self.configuration))

            # Use configuration target as Linux kernel configuration hash.
            conf_hash = self.configuration
            target = [self.configuration]

        self._make(target)
        self.configuration = conf_hash

    def _cleanup(self):
        super()._cleanup()
        self.logger.info('Clean working source tree')
        core.utils.execute(self.logger, ('make', 'mrproper'), cwd=self.work_src_tree)

    def _build(self):
        self.logger.info('Build Linux kernel')
        # We get some identifiers from strategy and we have to convert if possible them into make targets
        targets_to_build = list(self._targets.keys()) + list(self._subsystems.keys())
        targets_to_build = sorted(targets_to_build)

        # To build external Linux kernel modules we need to specify "M=path/to/ext/modules/dir".
        ext_modules = self._prepare_ext_modules()
        ext_modules_make_opt = ['M=' + ext_modules] if ext_modules else []

        if self._kernel:
            targets_to_build = ['all']

        if self._kernel:
            self._make(['vmlinux'], intercept_build_cmds=True)

        # Specially process building of all modules.
        if 'all' in targets_to_build:
            if len(targets_to_build) != 1:
                raise ValueError('Can not build all modules and something else')

            # Use target "modules" when the Linux kernel supports loadable modules.
            if self.__loadable_modules_support:
                self._make(ext_modules_make_opt + ['modules'], intercept_build_cmds=True)
            # Otherwise build all builtin modules indirectly by using target "all".
            else:
                self._make(ext_modules_make_opt + ['all'], intercept_build_cmds=True)
        else:
            # TODO: this doesn't look like "module sets", so, variable names and error messages should be improved.
            # Check that module sets aren't intersect explicitly.
            for i, modules1 in enumerate(targets_to_build):
                for j, modules2 in enumerate(targets_to_build):
                    if i != j:
                        if modules1 == modules2:
                            raise ValueError('Module set "{0}" is duplicated'.format(modules1))
                        else:
                            # Get rid of file names, remain just directories.
                            modules1_dir = os.path.dirname(modules1) if re.search(r'\.ko$', modules1) else modules1
                            modules2_dir = os.path.dirname(modules2) if re.search(r'\.ko$', modules2) else modules2

                            if modules1_dir != core.utils.make_relative_path([modules2_dir], modules1_dir):
                                raise ValueError('Module set "{0}" is subset of module set "{1}"'
                                                 .format(modules1, modules2))

            # Examine module sets to get all build targets. Do not build immediately to catch mistakes earlier.
            build_targets = []
            for modules in targets_to_build:
                # Module sets ending with .ko imply individual modules.
                if re.search(r'\.ko$', modules):
                    build_targets.append(ext_modules_make_opt + [modules])
                # Otherwise it is directory that can contain modules.
                else:
                    if ext_modules:
                        if not os.path.isdir(modules):
                            raise ValueError('There is no directory "{0}" inside "{1}"'.format(modules, os.getcwd()))

                        build_targets.append(['M=' + os.path.abspath(modules)])
                    else:
                        if not os.path.isdir(os.path.join(self.work_src_tree, modules)):
                            raise ValueError('There is no directory "{0}" inside "{1}"'.
                                             format(modules, self.work_src_tree))

                        build_targets.append(['M=' + modules])

            for build_target in build_targets:
                self._make(build_target, intercept_build_cmds=True)

    def _make(self, target, opts=None, env=None, intercept_build_cmds=False, collect_all_stdout=False):
        return super(Linux, self)._make(
            target, ['{0}={1}'.format(name, value) for name, value in self._ARCH_OPTS[self.arch].items()],
            env, intercept_build_cmds, collect_all_stdout)

    def prepare_model_headers(self, model_headers):
        super(Linux, self).prepare_model_headers(model_headers)

        try:
            # Try to prepare for building modules. This is necessary and should finish successfully when the Linux
            # kernel has loadable modules support.
            self._make(['modules_prepare'], intercept_build_cmds=True)
            self.__loadable_modules_support = True
        except core.utils.CommandError:
            # Otherwise the command above will most likely fail. In this case compile special file, namely,
            # scripts/mod/empty.o, that seems to exist in all Linux kernel versions and that will provide options for
            # building
            self._make(['scripts/mod/empty.o'], intercept_build_cmds=True)
            self.__loadable_modules_support = False

        # Generate Makefile and compile C files including model headers. These files will be treated as part of kernel -
        # one will need to filter them out later if required.
        with open(os.path.join(self._model_headers_path, 'Makefile'), 'w', encoding='utf-8') as fp:
            fp.write('obj-y += $(notdir $(patsubst %.c, %.o, $(wildcard $(src)/*.c)))\n')

        self._make(['M=' + os.path.abspath(self._model_headers_path)], intercept_build_cmds=True)

    def _prepare_ext_modules(self):
        if not self._external_modules:
            return None
        work_src_tree = self._EXT_DIR

        self.logger.info(
            'Fetch source code of external Linux kernel modules from "{0}" to working source tree "{1}"'
            .format(self._external_modules, work_src_tree))

        src = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                          self._external_modules)

        if os.path.isdir(src):
            self.logger.debug('External Linux kernel modules source code is provided in form of source tree')
            shutil.copytree(src, work_src_tree, symlinks=True)
        elif os.path.isfile(src):
            self.logger.debug('External Linux kernel modules source code is provided in form of archive')
            with tarfile.open(src, encoding='utf8') as TarFile:
                TarFile.extractall(work_src_tree)

        self.logger.info('Make canonical working source tree of external Linux kernel modules')
        work_src_tree_root = None
        requirement_dir = os.path.dirname(self.conf['requirements DB'])
        for dirpath, dirnames, filenames in os.walk(work_src_tree):
            ismakefile = False
            for filename in filenames:
                if filename == 'Makefile':
                    ismakefile = True
                    break

            # Generate Linux kernel module Makefiles recursively starting from source tree root directory if they do not
            # exist.
            if self.conf['generate makefiles']:
                if not work_src_tree_root:
                    work_src_tree_root = dirpath

                if not ismakefile:
                    with open(os.path.join(dirpath, 'Makefile'), 'w', encoding='utf-8') as fp:
                        fp.write('obj-m += $(patsubst %, %/, $(notdir $(patsubst %/, %, {0})))\n'
                                 .format('$(filter %/, $(wildcard $(src)/*/))'))
                        fp.write('obj-m += $(notdir $(patsubst %.c, %.o, $(wildcard $(src)/*.c)))\n')
                        # Specify additional directory to search for model headers. We assume that this directory is
                        # preserved as is at least during solving a given job. So, we treat headers from it as system
                        # ones, i.e. headers that aren't copied when .
                        fp.write('ccflags-y += -isystem {0}'.format(requirement_dir))
            elif ismakefile:
                work_src_tree_root = dirpath
                break

        if not work_src_tree_root:
            raise ValueError('Could not find Makefile in working source tree "{0}"'.format(work_src_tree))
        elif not os.path.samefile(work_src_tree_root, work_src_tree):
            self.logger.debug('Move contents of "{0}" to "{1}"'.format(work_src_tree_root, work_src_tree))
            for path in os.listdir(work_src_tree_root):
                shutil.move(os.path.join(work_src_tree_root, path), work_src_tree)
            trash_dir = work_src_tree_root
            while True:
                parent_dir = os.path.join(trash_dir, os.path.pardir)
                if os.path.samefile(parent_dir, work_src_tree):
                    break
                trash_dir = parent_dir
            self.logger.debug('Remove "{0}"'.format(trash_dir))
            shutil.rmtree(os.path.realpath(trash_dir))

        # Directory before self._EXT_DIR will be trimmed from program fragment identifiers (absolute paths to external
        # loadable kernel modules) and file names.
        self._source_paths.append(os.getcwd())

        return os.path.abspath(work_src_tree)
