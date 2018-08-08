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
import subprocess

import core.utils
from core.vog.source import Source


class Linux(Source):
    """This class correspnds to Linux kernel sources and external source"""

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

    def __init__(self, logger, conf):
        super(Linux, self).__init__(logger, conf)
        self.kernel = self.conf['project'].get('build kernel', False)

    def configure(self):
        self.logger.info('Configure Linux kernel')
        super(Linux, self).configure()

        self.logger.info('Get Linux kernel version')
        if not self.version:
            output = self._make_linux_kernel(['kernelversion'], collect_all_stdout=True)
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

        self._make_linux_kernel(target)
        self.configuration = conf_hash

    def _build(self, model_headers):
        self.logger.info('Build Linux kernel')

        # We get some identifiers from strategy and we have to convert if possible them into make targets
        targets_to_build = set(self.conf['project'].get('verification targets', []))
        targets_to_build = sorted(targets_to_build)
        ext_modules = self._prepare_ext_modules()
        if self.kernel:
            targets_to_build = ['all']

        loadable_modules_support = False
        try:
            # Try to prepare for building modules. This is necessary and should finish successfully when the Linux
            # kernel has loadable modules support.
            self._make_linux_kernel(['modules_prepare'], intercept_build_cmds=True)
            loadable_modules_support = True
        except subprocess.CalledProcessError:
            # Otherwise the command above will most likely fail. In this case compile special file, namely,
            # scripts/mod/empty.o, that seems to exist in all Linux kernel versions and that will provide options for
            # building
            self._make_linux_kernel(['scripts/mod/empty.o'], intercept_build_cmds=True)

        if self.kernel:
            self._make_linux_kernel(['vmlinux'], intercept_build_cmds=True)

        # To build external Linux kernel modules we need to specify "M=path/to/ext/modules/dir".
        ext_modules_make_opt = ['M=' + ext_modules] if ext_modules else []

        # Specially process building of all modules.
        if 'all' in targets_to_build:
            if len(targets_to_build) != 1:
                raise ValueError('Can not build all modules and something else')

            # Use target "modules" when the Linux kernel supports loadable modules.
            if loadable_modules_support:
                self._make_linux_kernel(ext_modules_make_opt + ['modules'], intercept_build_cmds=True)
            # Otherwise build all builtin modules indirectly by using target "all".
            else:
                self._make_linux_kernel(ext_modules_make_opt + ['all'], intercept_build_cmds=True)
        else:
            # Check that module sets aren't intersect explicitly.
            for i, modules1 in enumerate(targets_to_build):
                for j, modules2 in enumerate(targets_to_build):
                    if i != j and modules1.startswith(modules2):
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
                        modules_dir = os.path.join(ext_modules, modules)

                        if not os.path.isdir(modules_dir):
                            raise ValueError('There is not directory "{0}" inside "{1}"'.format(modules, ext_modules))

                        build_targets.append(['M=' + modules_dir])
                    else:
                        if not os.path.isdir(os.path.join(self.work_src_tree, modules)):
                            raise ValueError('There is not directory "{0}" inside "{1}"'.
                                             format(modules, self.work_src_tree))

                        build_targets.append(['M=' + modules])

            for build_target in build_targets:
                self._make_linux_kernel(build_target, intercept_build_cmds=True)

        if not model_headers:
            return

        # todo: what to do with external headers
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

    def cleanup(self):
        # TODO: this extension will be redundant if all commented code will be removed.
        self.logger.info('Clean Linux kernel working source tree')

        # TODO: I hope that we won't build external source within Linux kernel working source tree anymore.
        # if os.path.isdir(os.path.join(work_src_tree, 'ext-modules')):
        #     shutil.rmtree(os.path.join(work_src_tree, 'ext-modules'))

        # TODO: this optimization shouldn't be needed.
        # if self.linux_kernel['prepared to build ext modules']:
        #     return

        # TODO: this command can fail but most likely this shouldn't be an issue.
        subprocess.check_call(('make', 'mrproper'), cwd=self.work_src_tree)

        # TODO: I am almost sure that we don't need this anymore.
        # Remove intermediate files and directories that could be created during previous run.
        # if self.ext_conf.get('use original source tree'):
        #     for dirpath, dirnames, filenames in os.walk(work_src_tree):
        #         for filename in filenames:
        #             if re.search(r'\.json$', filename):
        #                 os.remove(os.path.join(dirpath, filename))
        #         for dirname in dirnames:
        #             if re.search(r'\.task$', dirname):
        #                 shutil.rmtree(os.path.join(dirpath, dirname))

    def _make_linux_kernel(self, target, env=None, intercept_build_cmds=False, collect_all_stdout=False):
        return self._make(target, ['{0}={1}'.format(name, value) for name, value in self._ARCH_OPTS[self.arch].items()],
                          env, intercept_build_cmds, collect_all_stdout)

    def _prepare_ext_modules(self):
        if 'external source' not in self.conf['project']:
            return None

        work_src_tree = self._EXT_DIR

        # todo: replace option
        self.logger.info(
            'Fetch source code of external Linux kernel modules from "{0}" to working source tree "{1}"'
            .format(self.conf['project']['external source'], work_src_tree))

        src = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                          self.conf['project']['external source'])

        if os.path.isdir(src):
            self.logger.debug('External Linux kernel modules source code is provided in form of source tree')
            shutil.copytree(src, work_src_tree, symlinks=True)
        elif os.path.isfile(src):
            self.logger.debug('External Linux kernel modules source code is provided in form of archive')
            with tarfile.open(src, encoding='utf8') as TarFile:
                TarFile.extractall(work_src_tree)

        self.logger.info('Make canonical working source tree of external Linux kernel modules')
        work_src_tree_root = None
        for dirpath, dirnames, filenames in os.walk(work_src_tree):
            ismakefile = False
            for filename in filenames:
                if filename == 'Makefile':
                    ismakefile = True
                    break

            # Generate Linux kernel module Makefiles recursively starting from source tree root directory if they do not
            # exist.
            # todo: Move this inside project subcategory
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
                        fp.write('ccflags-y += -isystem ' + os.path.abspath(os.path.dirname(
                            core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                                        self.conf['rule specifications DB']))))
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

        return work_src_tree
