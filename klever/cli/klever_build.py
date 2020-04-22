
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

import argparse
import distutils.dir_util
import hashlib
import json
import pathlib
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse

from clade import Clade
from klever.cli.utils import execute_cmd, get_logger, make_relative_path
from klever.cli.descs import common_target_program_descs, gcc46_clade_cif_opts


class CProgram:
    _CLADE_CONF = dict()
    _CLADE_PRESET = "klever_linux_kernel"

    def __init__(self, logger, target_program_desc):
        self.logger = logger
        self.target_program_desc = target_program_desc

        # Main working source tree where various build and auxiliary actions will be performed.
        self.work_src_tree = None

        # The number of parallel jobs for make.
        self.jobs = str(os.cpu_count())

        # C program attributes. We expect that architecture is always specified in target program description while
        # configuration and version can be either obtained during build somehow or remained unspecified.
        self.architecture = self.target_program_desc['architecture']
        self.configuration = None
        self.version = None

        # Working source trees are directories to be trimed from file names.
        self.work_src_trees = []
        # Temporary directories that should be removed at the end of work.
        self.tmp_dirs = []

    def _build(self):
        self.logger.info('Build C program')
        self._make(intercept_build_cmds=True)

    def _clean(self):
        self.logger.info('Clean working source tree')
        self._make('clean')

    def _configure(self):
        self.logger.info('Configure C program')
        execute_cmd(self.logger, './configure', cwd=self.work_src_tree)

    def _fetch_work_src_tree(self):
        src = self.target_program_desc['source code']
        self.work_src_tree = tempfile.mkdtemp()
        self.tmp_dirs.append(self.work_src_tree)

        self.logger.info('Fetch source code from "{0}" to working source tree "{1}"'.format(src, self.work_src_tree))

        o = urllib.parse.urlparse(src)
        if o[0] in ('http', 'https', 'ftp'):
            raise NotImplementedError('Source code is provided in unsupported form of remote archive')
        elif o[0] == 'git':
            raise NotImplementedError('Source code is provided in unsupported form of remote Git repository')
        elif o[0]:
            raise ValueError('Source code is provided in unsupported form "{0}"'.format(o[0]))

        if os.path.isdir(src):
            if self.target_program_desc['allow local source trees use']:
                self.logger.info('Use original source tree "{0}" rather than fetch it to working source tree "{1}"'
                                 .format(src, self.work_src_tree))
                self.work_src_tree = src
            else:
                shutil.copytree(src, self.work_src_tree, symlinks=True)

            if os.path.isdir(os.path.join(src, '.git')):
                self.logger.debug("Source code is provided in form of Git repository")
            else:
                self.logger.debug("Source code is provided in form of source tree")

            if 'git repository version' in self.target_program_desc:
                self.logger.info('Checkout Git repository "{0}"'
                                 .format(self.target_program_desc['git repository version']))

                # Always remove Git repository lock file .git/index.lock if it exists since it can remain after
                # some previous Git commands crashed.
                git_index_lock = os.path.join(self.work_src_tree, '.git', 'index.lock')
                if os.path.isfile(git_index_lock):
                    os.remove(git_index_lock)

                # In case of dirty Git working directory checkout may fail so clean up it first.
                execute_cmd(self.logger, 'git', 'clean', '-f', '-d', cwd=self.work_src_tree)
                execute_cmd(self.logger, 'git', 'reset', '--hard', cwd=self.work_src_tree)
                execute_cmd(self.logger, 'git', 'checkout', '-f', self.target_program_desc['git repository version'],
                            cwd=self.work_src_tree)

                # Use Git describe to properly identify C program version which source code is provided in form of Git
                # repository.
                stdout = execute_cmd(self.logger, 'git', 'describe', cwd=self.work_src_tree, get_output=True)
                self.version = stdout[0]
        elif os.path.isfile(src):
            self.logger.debug('Source code is provided in form of archive')
            with tarfile.open(src, encoding='utf8') as TarFile:
                TarFile.extractall(self.work_src_tree)
        else:
            raise ValueError('Source code is not provided at "{0}"'.format(src))

        self.work_src_trees.append(os.path.realpath(self.work_src_tree))

    def _get_version(self):
        if self.target_program_desc.get('version'):
            self.version = self.target_program_desc.get('version')

    def _make(self, *target, opts=None, env=None, intercept_build_cmds=False, get_output=False):
        if opts is None:
            opts = []

        cmd = ['make', '-j', self.jobs] + opts + list(target)

        if intercept_build_cmds:
            clade = Clade(cmds_file=os.path.realpath(os.path.join(self.work_src_tree, 'cmds.txt')))

            r = clade.intercept(cmd, append=True, cwd=self.work_src_tree)

            if r:
                raise RuntimeError('Build failed')

            return r
        else:
            return execute_cmd(self.logger, *(cmd), cwd=self.work_src_tree, env=env, get_output=get_output)

    def _make_canonical_work_src_tree(self):
        self.logger.info('Make canonical working source tree "{0}"'.format(self.work_src_tree))

        def _is_src_tree_root(fnames):
            for filename in fnames:
                if filename == 'Makefile':
                    return True

            return False

        work_src_tree_root = None
        for dirpath, _, filenames in os.walk(self.work_src_tree):
            if _is_src_tree_root(filenames):
                work_src_tree_root = dirpath
                break

        if not work_src_tree_root:
            raise ValueError('Could not find Makefile in working source tree "{0}"'.format(self.work_src_tree))

        if os.path.samefile(work_src_tree_root, self.work_src_tree):
            return

        self.logger.debug('Move contents of "{0}" to "{1}"'.format(work_src_tree_root, self.work_src_tree))
        for path in os.listdir(work_src_tree_root):
            shutil.move(os.path.join(work_src_tree_root, path), self.work_src_tree)
        trash_dir = work_src_tree_root
        while True:
            parent_dir = os.path.join(trash_dir, os.path.pardir)
            if os.path.samefile(parent_dir, self.work_src_tree):
                break
            trash_dir = parent_dir

        self.logger.debug('Remove "{0}"'.format(trash_dir))
        shutil.rmtree(os.path.realpath(trash_dir))

    def build(self):
        self._fetch_work_src_tree()
        self._make_canonical_work_src_tree()
        self._clean()
        self._get_version()

        if self.version:
            self.logger.info('C program version is "{0}"'.format(self.version))

        self._configure()

        if self.configuration:
            self.logger.info('C program configuration is "{0}"'.format(self.configuration))

        self._build()

        if os.path.isdir(self.target_program_desc['build base']):
            shutil.rmtree(self.target_program_desc['build base'])

        if 'extra Clade options' in self.target_program_desc:
            clade_conf = dict(self._CLADE_CONF)
            clade_conf.update(self.target_program_desc['extra Clade options'])
        else:
            clade_conf = self._CLADE_CONF

        clade = Clade(work_dir=self.target_program_desc['build base'],
                      cmds_file=os.path.join(self.work_src_tree, 'cmds.txt'),
                      conf=clade_conf,
                      preset=self._CLADE_PRESET)
        clade.parse_list(["CrossRef", "Callgraph", "Variables", "Typedefs", "Macros"])

        self.logger.info('Save project attributes, working source trees and target program description to build base')
        clade.add_meta_by_key('project attrs', [{
            'name': 'project',
            'value': [
                {
                    'name': 'name',
                    'value': type(self).__name__
                },
                {
                    'name': 'architecture',
                    'value': self.architecture
                },
                {
                    'name': 'version',
                    'value': self.version
                },
                {
                    'name': 'configuration',
                    'value': self.configuration
                }
            ]
        }])
        clade.add_meta_by_key('working source trees', self.work_src_trees)
        clade.add_meta_by_key('target program description', self.target_program_desc)

        self.logger.info('Remove temporary directories')
        for tmp_dir in self.tmp_dirs:
            shutil.rmtree(tmp_dir)


class Linux(CProgram):
    _ARCH_OPTS = {
        'arm': {
            'ARCH': 'arm',
            'CROSS_COMPILE': 'arm-unknown-linux-gnueabi-'
        },
        'x86_64': {
            'ARCH': 'x86_64'
        }
    }
    _CLADE_CONF = dict()
    _CLADE_PRESET = 'klever_linux_kernel'

    def __init__(self, logger, target_program_desc):
        super().__init__(logger, target_program_desc)
        self.kconfig_config = None

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
            support_loadable_kernel_modules = True
        except subprocess.CalledProcessError:
            # Otherwise the command above will most likely fail. In this case compile special file, namely,
            # scripts/mod/empty.o, that seems to exist in all Linux kernel versions and that will provide options for
            # building C files including headers necessary for models.
            self._make('scripts/mod/empty.o', intercept_build_cmds=True)
            support_loadable_kernel_modules = False

        def modules_make_target():
            # Use target "modules" when the Linux kernel supports loadable modules.
            if support_loadable_kernel_modules:
                return 'modules'
            # Otherwise build all builtin modules indirectly by using target "all".
            else:
                return 'all'

        if len(self.target_program_desc.get('loadable kernel modules', [])) > 0:
            self.logger.info('Build loadable kernel modules')

            # Specially process building of all modules.
            if 'all' in self.target_program_desc['loadable kernel modules']:
                if len(self.target_program_desc['loadable kernel modules']) != 1:
                    raise ValueError('Can not build all modules and something else')

                self._make(*((['M=' + os.path.join(ext_modules, 'ext-modules')] if ext_modules else []) +
                             [modules_make_target()]),
                           intercept_build_cmds=True)
            else:
                # Check that modules aren't intersect explicitly.
                for i, modules1 in enumerate(self.target_program_desc['loadable kernel modules']):
                    for j, modules2 in enumerate(self.target_program_desc['loadable kernel modules']):
                        if i != j:
                            if modules1 == modules2:
                                raise ValueError('Modules "{0}" are duplicated'.format(modules1))
                            else:
                                # Get rid of file names, remain just directories.
                                if not re.search(r'\.ko$', modules1) or not re.search(r'\.ko$', modules2):
                                    modules1_dir = os.path.dirname(modules1) \
                                        if re.search(r'\.ko$', modules1) else modules1
                                    modules2_dir = os.path.dirname(modules2) \
                                        if re.search(r'\.ko$', modules2) else modules2

                                    if modules1_dir != make_relative_path([modules2_dir], modules1_dir):
                                        raise ValueError('Modules "{0}" are subset of modules "{1}"'
                                                         .format(modules1, modules2))

                # Examine modules to get all build targets. Do not build immediately to catch mistakes earlier.
                build_targets = []
                for modules in self.target_program_desc['loadable kernel modules']:
                    # Modules ending with .ko imply individual modules.
                    if re.search(r'\.ko$', modules):
                        if ext_modules:
                            build_targets.append([os.path.join(ext_modules, modules)])
                        else:
                            build_targets.append([modules])
                    # Otherwise it is directory that can contain modules.
                    else:
                        if ext_modules:
                            if not os.path.isdir(os.path.join(ext_modules, modules)):
                                raise ValueError('There is no directory "{0}" inside "{1}"'
                                                 .format(modules, ext_modules))

                            build_target = 'M=' + os.path.join(ext_modules, modules)
                        else:
                            if not os.path.isdir(os.path.join(self.work_src_tree, modules)):
                                raise ValueError('There is no directory "{0}" inside "{1}"'.
                                                 format(modules, self.work_src_tree))

                            build_target = 'M=' + modules

                        build_targets.append([build_target, modules_make_target()])

                for build_target in build_targets:
                    self._make(*build_target, intercept_build_cmds=True)

        # Generate C file including extra headers and Makefile. Compile this C file. It will be treated as part of
        # kernel, so, one will need to filter them out later if required.
        if 'extra headers' in self.target_program_desc:
            tmp_dir = tempfile.mkdtemp()
            self.tmp_dirs.append(tmp_dir)

            with open(os.path.join(tmp_dir, 'extra-headers.c'), 'w', encoding='utf8') as fp:
                for header in self.target_program_desc['extra headers']:
                    if header not in self.target_program_desc.get('exclude extra headers', []):
                        fp.write('#include <{0}>\n'.format(header))

            with open(os.path.join(tmp_dir, 'Makefile'), 'w', encoding='utf-8') as fp:
                fp.write('obj-y += extra-headers.o\n')

            self._make('M=' + tmp_dir, intercept_build_cmds=True)

    def _clean(self):
        self._make('mrproper')

    def _configure(self):
        self.logger.info('Configure Linux kernel')

        # Linux kernel configuration can be specified by means of configuration file or configuration target.
        # all configuration files are located in the description directory
        conf_file = os.path.join(self.target_program_desc['description directory'], self.target_program_desc['configuration'])
        if os.path.isfile(conf_file):
            self.logger.info('Linux kernel configuration file is "{0}"'.format(conf_file))

            # Use configuration file SHA1 digest as Linux kernel configuration.
            with open(conf_file, 'rb') as fp:
                self.configuration = hashlib.sha1(fp.read()).hexdigest()[:7]

            self.logger.info('Linux kernel configuration file SHA1 digest is "{0}"'.format(self.configuration))
            shutil.copy(conf_file, self.work_src_tree)
            self.kconfig_config = os.path.basename(conf_file)
            target = ['oldconfig', 'KCONFIG_CONFIG={0}'.format(self.kconfig_config)]
        else:
            self.logger.debug('Linux kernel configuration target is "{0}"'
                              .format(self.target_program_desc['configuration']))

            # Use configuration target as Linux kernel configuration.
            self.configuration = self.target_program_desc['configuration']

            target = [self.configuration]

        self._make(*target)

    def _get_version(self):
        self.logger.info('Get Linux kernel version')

        if not self.version:
            output = self._make('kernelversion', get_output=True)
            self.version = output[0]

    def _make(self, *target, **kwargs):
        kwargs['opts'] = ['{0}={1}'.format(name, value) for name, value in self._ARCH_OPTS[self.architecture].items()]
        if self.kconfig_config:
            kwargs['opts'].append('KCONFIG_CONFIG={0}'.format(self.kconfig_config))

        return super()._make(*target, **kwargs)

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
            'Fetch source code of external loadable Linux kernel modules from "{0}" to working source tree "{1}"'
            .format(ext_modules, work_src_tree))

        if os.path.isdir(ext_modules):
            self.logger.debug('External loadable Linux kernel modules source code is provided in form of source tree')
            distutils.dir_util.copy_tree(ext_modules, work_src_tree)
        elif os.path.isfile(ext_modules):
            self.logger.debug('External loadable Linux kernel modules source code is provided in form of archive')
            with tarfile.open(ext_modules, encoding='utf8') as TarFile:
                TarFile.extractall(work_src_tree)

        self.logger.info('Make canonical working source tree of external loadable Linux kernel modules')
        work_src_tree_root = None
        for dirpath, _, filenames in os.walk(work_src_tree):
            ismakefile = False
            for filename in filenames:
                if filename == 'Makefile':
                    ismakefile = True
                    break

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
                        # Specify additional directory to search for model headers.
                        fp.write('ccflags-y += -I' + os.path.realpath(
                            self.target_program_desc['external modules header files search directory']))
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

        return tmp_dir


class BusyBox(CProgram):
    _ARCH_OPTS = {
        'x86_64': {
            'ARCH': 'x86_64'
        }
    }
    _CLADE_CONF = dict()
    _CLADE_PRESET = 'klever_busybox_linux'

    def __init__(self, logger, target_program_desc):
        super().__init__(logger, target_program_desc)
        self.configuration = self.target_program_desc.get('configuration')

    def _configure(self):
        self.logger.info(f'Configure BusyBox as {self.configuration}')
        target = [self.configuration]
        self._make(*target)


def get_descs_dir():
    return os.path.join(os.path.dirname(__file__), 'descs')


def get_desc_paths(desc_name_pattern=None):
    desc_paths = []

    for desc_path in pathlib.Path.rglob(pathlib.Path(get_descs_dir()), "desc.json"):
        desc_paths.append(str(desc_path))

    if desc_name_pattern:
        desc_paths = [x for x in desc_paths if desc_name_pattern in os.path.relpath(x, get_descs_dir())]

    return desc_paths


def get_desc_name(desc_path):
    return os.path.dirname(os.path.relpath(desc_path, start=get_descs_dir()))


def get_all_desc_names():
    # Get names of all json files with target program descriptions (without .json extension)
    desc_names = []

    for desc_path in get_desc_paths():
        desc_names.append(get_desc_name(desc_path))

    return desc_names


def parse_args(logger):
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-o',
        '--output',
        help='path to the directory where build bases will be stored. Default: {!r}'.format('build bases'),
        default='build bases',
        metavar='PATH'
    )

    parser.add_argument(
        '-r',
        '--repositories',
        help='path to the directory that contains all required git repositorues (linux-stable, userspace)',
        default='.',
        metavar='PATH'
    )

    parser.add_argument(
        '-l',
        '--list',
        help='show the list of available target program descriptions and exit',
        action='store_true'
    )

    parser.add_argument(
        dest='descriptions',
        nargs=argparse.REMAINDER,
        help='list of descriptions to use',
    )

    args = parser.parse_args(sys.argv[1:])

    if args.list:
        logger.info('Available target program descriptions:\n{}'.format(
            '\n'.join(sorted(get_all_desc_names()))
        ))
        sys.exit()

    if not args.descriptions:
        logger.error('You need to specify at least one target program description')
        sys.exit(-1)

    return args


def klever_build():
    logger = get_logger(__name__)
    args = parse_args(logger)
    all_desc_paths = []

    for desc_name_pattern in args.descriptions:
        desc_paths = get_desc_paths(desc_name_pattern)
        all_desc_paths.extend(desc_paths)

        if not desc_paths:
            logger.error('There are no json files corresponding to the specified description pattern {!r}'.format(
                desc_name_pattern
            ))
            logger.error('Target program descriptions are stored in the {!r} directory'.format(get_descs_dir()))
            sys.exit(-1)

    for desc_path in all_desc_paths:
        with open(desc_path, 'r', encoding='utf-8') as fp:
            descs = json.load(fp)

        logger.info('Use {!r} description'.format(get_desc_name(desc_path)))
        for desc in descs:
            desc['description directory'] = os.path.dirname(desc_path)
            desc['build base'] = os.path.abspath(os.path.join(args.output, desc['build base']))

            if "GCC 4.6 Clade CIF options" in desc:
                desc.update(gcc46_clade_cif_opts)

            logger.info('Prepare build base "{}"'.format(desc['build base']))

            common_desc = dict(common_target_program_descs[desc['name']])
            common_desc.update(desc)
            common_desc['source code'] = os.path.abspath(os.path.join(args.repositories, common_desc['source code']))

            CProgramClass = getattr(sys.modules[__name__], desc['name'])
            CProgramObj = CProgramClass(logger, common_desc)
            CProgramObj.build()

            logger.info('Build base "{}" was successfully prepared'.format(desc['build base']))


if __name__ == '__main__':
    klever_build()
