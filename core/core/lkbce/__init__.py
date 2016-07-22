#!/usr/bin/python3

import hashlib
import multiprocessing
import os
import re
import shutil
import subprocess
import tarfile
import time
import urllib.parse
import json

import core.components
import core.utils
import core.lkbce.utils

# Architecture name to search for architecture specific header files can differ from the target architecture.
# See Linux kernel Makefile for details. Mapping below was extracted from Linux 3.5.
_arch_hdr_arch = {
    'i386': 'x86',
    'x86_64': 'x86',
    'sparc32': 'sparc',
    'sparc64': 'sparc',
    'sh64': 'sh',
    'tilepro': 'tile',
    'tilegx': 'tile',
}


def before_launch_sub_job_components(context):
    context.mqs['model cc options and headers'] = multiprocessing.Queue()


def after_set_model_cc_opts_and_headers(context):
    context.mqs['model cc options and headers'].put(context.model_cc_opts_and_headers)


class LKBCE(core.components.Component):
    def extract_linux_kernel_build_commands(self):
        self.linux_kernel = {'prepared to build ext modules': None}
        # Prepare Linux kernel source code and extract build commands exclusively but just with other sub-jobs of a
        # given job. It would be more properly to lock working source trees especially if different sub-jobs use
        # different trees (https://forge.ispras.ru/issues/6647).
        with self.locks['build']:
            self.fetch_linux_kernel_work_src_tree()
            self.make_canonical_linux_kernel_work_src_tree()
            self.set_shadow_src_tree()
            # Determine Linux kernel configuration just after Linux kernel working source tree is prepared since it
            # affect value of KCONFIG_CONFIG specified for various make targets if provided configuration file rather
            # than configuration target.
            self.get_linux_kernel_conf()
            self.check_preparation_for_building_external_modules()
            self.clean_linux_kernel_work_src_tree()
            # We need to copy Linux kernel configuration file if so after clean up since it can be removed there if it
            # has name ".config".
            if 'conf file' in self.linux_kernel:
                shutil.copy(self.linux_kernel['conf file'], self.linux_kernel['work src tree'])
            self.set_linux_kernel_attrs()
            self.set_hdr_arch()
            core.utils.report(self.logger,
                              'attrs',
                              {
                                  'id': self.id,
                                  'attrs': self.linux_kernel['attrs']
                              },
                              self.mqs['report files'],
                              self.conf['main working directory'])
            # This file should be specified to collect build commands during configuring and building of the Linux
            # kernel.
            self.linux_kernel['build cmd descs file'] = 'Linux kernel build cmd descs'
            self.configure_linux_kernel()
            # Always create Linux kernel raw build commands file prior to its reading in
            # self.process_all_linux_kernel_raw_build_cmds().
            with open(self.linux_kernel['build cmd descs file'], 'w'):
                pass

            self.extract_module_files()
            self.receive_modules_to_build()

            self.launch_subcomponents(('LKB', self.build_linux_kernel),
                                      ('ALKBCDG', self.get_all_linux_kernel_build_cmd_descs))

            self.extract_module_deps_and_sizes()

            if not self.conf['keep intermediate files']:
                os.remove(self.linux_kernel['build cmd descs file'])

    def extract_module_deps_and_sizes(self):
        if self.linux_kernel['build kernel']:
            if 'module dependencies file' not in self.conf['Linux kernel']:
                self.extract_all_linux_kernel_mod_deps_function()
                self.mqs['Linux kernel module dependencies'].put(self.linux_kernel['module dependencies'])

            if 'module sizes file' not in self.conf['Linux kernel']:
                self.extract_all_linux_kernel_mod_size()
                self.mqs['Linux kernel module sizes'].put(self.linux_kernel['module sizes'])

    def receive_modules_to_build(self):
        linux_kernel_modules = self.mqs['Linux kernel modules'].get()
        self.mqs['Linux kernel modules'].close()
        self.linux_kernel['modules'] = linux_kernel_modules.get('modules', [])
        self.linux_kernel['build kernel'] = linux_kernel_modules.get('build kernel', False)
        if 'external modules' in self.conf['Linux kernel'] and not self.linux_kernel['build kernel']:
            self.linux_kernel['modules'] = [module if not module.startswith('ext-modules/') else module[12:]
                                            for module in self.linux_kernel['modules']]

    def extract_module_files(self):
        if 'module dependencies file' in self.conf['Linux kernel']:
            dependencies_file = core.utils.find_file_or_dir(self.logger,self.conf['main working directory'],
                                               self.conf['Linux kernel']['module dependencies file'])
            with open(dependencies_file) as fp:
                self.parse_linux_kernel_mod_function_deps(fp, True)
                self.mqs['Linux kernel module dependencies'].put(self.linux_kernel['module dependencies'])
        if 'module sizes file' in self.conf['Linux kernel']:
            sizes_file = core.utils.find_file_or_dir(self.logger,self.conf['main working directory'],
                                                     self.conf['Linux kernel']['module sizes file'])
            with open(sizes_file) as fp:
                self.mqs['Linux kernel module sizes'].put(json.load(fp))

    main = extract_linux_kernel_build_commands

    def build_linux_kernel(self):
        self.logger.info('Build Linux kernel')

        # First of all collect all targets to be built.
        build_targets = []

        if 'build kernel' in self.linux_kernel and self.linux_kernel['build kernel']:
            build_targets.append(('all',))

        if 'external modules' in self.conf['Linux kernel']:
            self.linux_kernel['ext modules work src tree'] = os.path.join(self.linux_kernel['work src tree'],
                                                                          'ext-modules')

            self.logger.info('Fetch working source tree of external Linux kernel modules to "{0}"'.format(
                self.linux_kernel['ext modules work src tree']))

            self.linux_kernel['ext modules src'] = core.utils.find_file_or_dir(self.logger,
                                                                               self.conf['main working directory'],
                                                                               self.conf['Linux kernel'][
                                                                                   'external modules'])
            if os.path.isdir(self.linux_kernel['ext modules src']):
                self.logger.debug('External Linux kernel modules source code is provided in form of source tree')
                shutil.copytree(self.linux_kernel['ext modules src'], self.linux_kernel['ext modules work src tree'],
                                symlinks=True)
            elif os.path.isfile(self.linux_kernel['ext modules src']):
                self.logger.debug('External Linux kernel modules source code is provided in form of archive')
                with tarfile.open(self.linux_kernel['ext modules src']) as TarFile:
                    TarFile.extractall(self.linux_kernel['ext modules work src tree'])

            self.logger.info('Make canonical working source tree of external Linux kernel modules')
            self.__make_canonical_work_src_tree(self.linux_kernel['ext modules work src tree'])

            # Linux kernel external modules always require this preparation.
            build_targets.append(('modules_prepare',))

            if 'build kernel' in self.linux_kernel and self.linux_kernel['build kernel']:
                build_targets.append(('M=ext-modules', 'modules'))

        if self.linux_kernel['modules']:
            # Specially process building of all modules.
            if 'all' in self.linux_kernel['modules']:
                build_targets.append(('M=ext-modules', 'modules')
                                     if 'external modules' in self.conf['Linux kernel'] else ('modules',))
                self.linux_kernel['modules'] = [module for module in self.linux_kernel['modules'] if module != 'all']
            # Check that module sets aren't intersect explicitly.
            for i, modules1 in enumerate(self.linux_kernel['modules']):
                for j, modules2 in enumerate(self.linux_kernel['modules']):
                    if i != j and modules1.startswith(modules2):
                        raise ValueError(
                            'Module set "{0}" is subset of module set "{1}"'.format(modules1, modules2))

            # Examine module sets.
            if 'build kernel' not in self.linux_kernel or not self.linux_kernel['build kernel']:
                for modules_set in self.linux_kernel['modules']:
                    # Module sets ending with .ko imply individual modules.
                    if re.search(r'\.k?o$', modules_set):
                        build_targets.append(('M=ext-modules', modules_set)
                                             if 'external modules' in self.conf['Linux kernel'] else (modules_set,))
                    # Otherwise it is directory that can contain modules.
                    else:
                        # Add "modules_prepare" target once.
                        if not build_targets or build_targets[0] != ('modules_prepare',):
                            build_targets.insert(0, ('modules_prepare',))

                        modules_dir = os.path.join('ext-modules', modules_set) \
                            if 'external modules' in self.conf['Linux kernel'] else modules_set

                        if not os.path.isdir(os.path.join(self.linux_kernel['work src tree'], modules_dir)):
                            raise ValueError(
                                'There is not directory "{0}" inside "{1}"'.format(modules_dir,
                                                                                   self.linux_kernel['work src tree']))

                        build_targets.append(('M=' + modules_dir, 'modules'))
        elif not self.linux_kernel['build kernel']:
            self.logger.warning('Nothing will be verified since modules are not specified')

        if build_targets:
            self.logger.debug('Build following targets:\n{0}'.format(
                '\n'.join([' '.join(build_target) for build_target in build_targets])))

        jobs_num = core.utils.get_parallel_threads_num(self.logger, self.conf, 'Build')

        for build_target in build_targets:
            if build_target[0] == 'modules_prepare' and self.linux_kernel['prepared to build ext modules']:
                continue

            self.__make(build_target,
                        jobs_num=jobs_num,
                        specify_arch=True, collect_build_cmds=True)

            if build_target[0] == 'modules_prepare' and 'external modules' in self.conf['Linux kernel'] and not \
                    self.linux_kernel['prepared to build ext modules']:
                with open(os.path.join(self.linux_kernel['work src tree'], 'prepared ext modules conf'), 'w',
                          encoding='ascii') as fp:
                    fp.write(self.linux_kernel['conf'])

            if build_target[0] == 'modules_prepare':
                self.copy_model_headers()

        self.logger.info('Terminate Linux kernel build command decsriptions "message queue"')
        with core.utils.LockedOpen(self.linux_kernel['build cmd descs file'], 'a', encoding='ascii') as fp:
            fp.write('\n')

    def extract_all_linux_kernel_mod_deps_function(self):
        self.logger.info('Extract all Linux kernel module dependencies')

        self.logger.info('Install Linux kernel modules')

        # Specify installed Linux kernel modules directory like Linux kernel working source tree in
        # fetch_linux_kernel_work_src_tree().
        self.linux_kernel['installed modules dir'] = os.path.abspath(os.path.join(os.path.pardir, 'linux-modules'))
        os.mkdir(self.linux_kernel['installed modules dir'])
        # TODO: whether parallel execution has some benefits here?
        self.__make(['INSTALL_MOD_PATH={0}'.format(self.linux_kernel['installed modules dir']), 'modules_install'],
                    jobs_num=core.utils.get_parallel_threads_num(self.logger, self.conf, 'Build'),
                    specify_arch=False, collect_build_cmds=False)
        if 'external modules' in self.conf['Linux kernel']:
            self.__make(['INSTALL_MOD_PATH={0}'.format(self.linux_kernel['installed modules dir']),
                         'M=ext-modules', 'modules_install'],
                        jobs_num=core.utils.get_parallel_threads_num(self.logger, self.conf, 'Build'),
                        specify_arch=False, collect_build_cmds=False)

        depmod_output = core.utils.execute(self.logger, ['/sbin/depmod', '-b',
                                                         self.linux_kernel['installed modules dir'],
                                                         self.linux_kernel['version'], '-v'],
                                           collect_all_stdout=True)
        self.parse_linux_kernel_mod_function_deps(depmod_output, False)

    def extract_all_linux_kernel_mod_size(self):
        all_modules = set()
        for module, _, module2 in self.linux_kernel['module dependencies']:
            all_modules.add(module)
            all_modules.add(module2)

        self.linux_kernel['module sizes'] = {}

        for module in all_modules:
            if os.path.isfile(os.path.join(self.linux_kernel['installed modules dir'], 'lib', 'modules',
                                           self.linux_kernel['version'], 'kernel', module)):
                self.linux_kernel['module sizes'][module] = \
                    os.path.getsize(os.path.join(self.linux_kernel['installed modules dir'], 'lib', 'modules',
                                                 self.linux_kernel['version'], 'kernel', module))
            elif module.startswith('ext-modules') and os.path.isfile(os.path.join(
                    self.linux_kernel['installed modules dir'], 'lib', 'modules',
                    self.linux_kernel['version'], 'extra', module.replace('ext-modules/', ''))):
                self.linux_kernel['module sizes'][module] = \
                    os.path.getsize(os.path.join(self.linux_kernel['installed modules dir'], 'lib', 'modules',
                                                 self.linux_kernel['version'], 'extra', module.replace('ext-modules/',
                                                                                                       '')))

    def parse_linux_kernel_mod_function_deps(self, lines, remove_newline_symbol):
        self.linux_kernel['module dependencies'] = []
        for line in lines:
            if remove_newline_symbol:
                line = line[:-1]
            splts = line.split(' ')
            first = splts[0]
            if 'kernel' in first:
                first = first[first.find('kernel') + 7:]
            elif 'extra' in first:
                first = 'ext-modules/' + first[first.find('extra') + 6:]
            second = splts[3]
            if 'kernel' in second:
                second = second[second.find('kernel') + 7:]
            elif 'extra' in second:
                second = 'ext-modules/' + second[second.find('extra') + 6:]
            func = splts[2][1:-2]
            self.linux_kernel['module dependencies'].append((second, func, first))

    def check_preparation_for_building_external_modules(self):
        prepared_ext_modules_conf_file = os.path.join(self.linux_kernel['work src tree'], 'prepared ext modules conf')
        if 'external modules' in self.conf['Linux kernel'] and os.path.isfile(prepared_ext_modules_conf_file):
            with open(prepared_ext_modules_conf_file, encoding='ascii') as fp:
                if fp.readline().rstrip() == self.linux_kernel['conf']:
                    self.linux_kernel['prepared to build ext modules'] = True

    def clean_linux_kernel_work_src_tree(self):
        self.logger.info('Clean Linux kernel working source tree')

        if os.path.isdir(os.path.join(self.linux_kernel['work src tree'], 'ext-modules')):
            shutil.rmtree(os.path.join(self.linux_kernel['work src tree'], 'ext-modules'))

        if self.linux_kernel['prepared to build ext modules']:
            return

        self.__make(('mrproper',))

        # In this case we need to remove intermediate files and directories that could be created during previous run.
        if self.conf['allow local source directories use']:
            for dirpath, dirnames, filenames in os.walk(self.linux_kernel['work src tree']):
                for filename in filenames:
                    if re.search(r'\.json$', filename):
                        os.remove(os.path.join(dirpath, filename))
                for dirname in dirnames:
                    if re.search(r'\.task$', dirname):
                        shutil.rmtree(os.path.join(dirpath, dirname))

    def get_linux_kernel_conf(self):
        self.logger.info('Get Linux kernel configuration')

        # Linux kernel configuration can be specified by means of configuration file or configuration target.
        try:
            self.linux_kernel['conf file'] = core.utils.find_file_or_dir(self.logger,
                                                                         self.conf['main working directory'],
                                                                         self.conf['Linux kernel']['configuration'])
            self.logger.debug('Linux kernel configuration file is "{0}"'.format(self.linux_kernel['conf file']))
            # Use configuration file SHA1 digest as value of Linux kernel:Configuration attribute.
            with open(self.linux_kernel['conf file'], 'rb') as fp:
                self.linux_kernel['conf'] = hashlib.sha1(fp.read()).hexdigest()[:7]
            self.logger.debug('Linux kernel configuration file SHA1 digest is "{0}"'.format(self.linux_kernel['conf']))
        except FileNotFoundError:
            self.logger.debug(
                'Linux kernel configuration target is "{0}"'.format(self.conf['Linux kernel']['configuration']))
            # Use configuration target name as value of Linux kernel:Configuration attribute.
            self.linux_kernel['conf'] = self.conf['Linux kernel']['configuration']

    def configure_linux_kernel(self):
        if self.linux_kernel['prepared to build ext modules']:
            return

        self.logger.info('Configure Linux kernel')
        self.__make(('oldconfig' if 'conf file' in self.linux_kernel else self.conf['Linux kernel']['configuration'],),
                    specify_arch=True, collect_build_cmds=False, collect_all_stdout=True)

    def set_linux_kernel_attrs(self):
        self.logger.info('Set Linux kernel atributes')

        self.logger.debug('Get Linux kernel version')
        stdout = self.__make(('-s', 'kernelversion'), specify_arch=False, collect_all_stdout=True)

        self.linux_kernel['version'] = stdout[0]
        self.logger.debug('Linux kernel version is "{0}"'.format(self.linux_kernel['version']))

        self.logger.debug('Get Linux kernel architecture')
        self.linux_kernel['arch'] = self.conf['Linux kernel'].get('architecture') or self.conf['architecture']
        self.logger.debug('Linux kernel architecture is "{0}"'.format(self.linux_kernel['arch']))

        self.linux_kernel['attrs'] = [
            {'Linux kernel': [{'version': self.linux_kernel['version']},
                              {'architecture': self.linux_kernel['arch']},
                              {'configuration': self.linux_kernel['conf']}]}]

    def set_hdr_arch(self):
        self.logger.info('Set architecture name to search for architecture specific header files')
        self.hdr_arch = _arch_hdr_arch[self.linux_kernel['arch']]

    def set_shadow_src_tree(self):
        self.logger.info('Set shadow source tree')
        # All other components should find shadow source tree relatively to main working directory.
        self.shadow_src_tree = os.path.relpath(os.curdir, self.conf['main working directory'])

    def fetch_linux_kernel_work_src_tree(self):
        self.linux_kernel['work src tree'] = 'linux'

        self.logger.info('Fetch Linux kernel working source tree to "{0}"'.format(self.linux_kernel['work src tree']))

        self.linux_kernel['src'] = self.conf['Linux kernel']['source']

        o = urllib.parse.urlparse(self.linux_kernel['src'])
        if o[0] in ('http', 'https', 'ftp'):
            raise NotImplementedError(
                'Linux kernel source code is likely provided in unsopported form of remote archive')
        elif o[0] == 'git':
            raise NotImplementedError(
                'Linux kernel source code is likely provided in unsopported form of Git repository')
        elif o[0]:
            raise ValueError('Linux kernel source code is provided in unsupported form "{0}"'.format(o[0]))

        self.linux_kernel['src'] = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                                               self.linux_kernel['src'])

        if os.path.isdir(self.linux_kernel['src']):
            if os.path.isdir(os.path.join(self.linux_kernel['src'], '.git')):
                self.logger.debug('Linux kernel source code is provided in form of Git repository')
            else:
                self.logger.debug('Linux kernel source code is provided in form of source tree')

            if self.conf['allow local source directories use']:
                self.linux_kernel['work src tree'] = self.linux_kernel['src']
            else:
                shutil.copytree(self.linux_kernel['src'], self.linux_kernel['work src tree'], symlinks=True)

            # TODO: do not allow to checkout both branch and commit and to checkout branch or commit for source tree.
            if 'Git repository' in self.conf['Linux kernel']:
                for commit_or_branch in ('commit', 'branch'):
                    if commit_or_branch in self.conf['Linux kernel']['Git repository']:
                        self.logger.info('Checkout Linux kernel Git repository {0} "{1}"'.format(commit_or_branch,
                                                                                                 self.conf[
                                                                                                     'Linux kernel'][
                                                                                                     'Git repository'][
                                                                                                     commit_or_branch]))
                        # In case of dirty Git working directory checkout may fail so clean up it first.
                        core.utils.execute(self.logger, ('git', 'clean', '-f', '-d'),
                                           cwd=self.linux_kernel['work src tree'])
                        core.utils.execute(self.logger, ('git', 'reset', '--hard'),
                                           cwd=self.linux_kernel['work src tree'])
                        core.utils.execute(self.logger,
                                           ('git', 'checkout', '-f',
                                            self.conf['Linux kernel']['Git repository'][commit_or_branch]),
                                           cwd=self.linux_kernel['work src tree'])
        elif os.path.isfile(self.linux_kernel['src']):
            self.logger.debug('Linux kernel source code is provided in form of archive')
            with tarfile.open(self.linux_kernel['src']) as TarFile:
                TarFile.extractall(self.linux_kernel['work src tree'])

    def make_canonical_linux_kernel_work_src_tree(self):
        self.logger.info('Make canonical Linux kernel working source tree')
        self.__make_canonical_work_src_tree(self.linux_kernel['work src tree'])

    def get_all_linux_kernel_build_cmd_descs(self):
        self.logger.info('Get all Linux kernel build command decscriptions')

        # It looks quite reasonable to scan Linux kernel build command descriptions file once a second since build isn't
        # performed neither too fast nor too slow.
        # Offset is used to scan just new lines from Linux kernel build command descriptions file.
        offset = 0
        while True:
            time.sleep(1)

            with core.utils.LockedOpen(self.linux_kernel['build cmd descs file'], 'r+', encoding='ascii') as fp:
                # Move to previous end of file.
                fp.seek(offset)

                # Read new lines from file.
                for line in fp:
                    if line == '\n':
                        self.logger.debug('Linux kernel build command decscriptions "message queue" was terminated')
                        return
                    elif line == 'KLEVER FATAL ERROR\n':
                        raise RuntimeError('Build command wrapper(s) failed')
                    else:
                        self.linux_kernel['build cmd desc file'] = line.rstrip()
                        self.get_linux_kernel_build_cmd_desc()

                if self.conf['keep intermediate files']:
                    # When debugging we keep all file content. So move offset to current end of file to scan just new
                    # lines from file on the next iteration.
                    offset = fp.tell()
                else:
                    # Clean up all already scanned content of file to save disk space.
                    fp.seek(0)
                    fp.truncate()

    # This method is inteded just for calbacks.
    def get_linux_kernel_build_cmd_desc(self):
        pass

    def copy_model_headers(self):
        self.logger.info('Copy model headers')

        linux_kernel_work_src_tree = os.path.realpath(self.linux_kernel['work src tree'])

        os.makedirs('model-headers')

        model_cc_opts_and_headers = self.mqs['model cc options and headers'].get()

        for model_c_file in model_cc_opts_and_headers:
            self.logger.debug('Copy headers of model with C file "{0}"'.format(model_c_file))

            model_headers_c_file = os.path.join('model-headers', os.path.basename(model_c_file))

            cc_opts = model_cc_opts_and_headers[model_c_file]['CC options']
            headers = model_cc_opts_and_headers[model_c_file]['headers']

            with open(model_headers_c_file, mode='w', encoding='utf8') as fp:
                for header in headers:
                    fp.write('#include <{0}>\n'.format(header))

            model_headers_deps_file = model_headers_c_file + '.d'

            # This is required to get compiler (Aspectator) specific stdarg.h since kernel C files are compiled with
            # "-nostdinc" option and system stdarg.h couldn't be used.
            stdout = core.utils.execute(self.logger,
                                        ('aspectator', '-print-file-name=include'),
                                        collect_all_stdout=True)

            core.utils.execute(self.logger,
                               tuple(
                                   ['aspectator', '-M', '-MF', os.path.relpath(model_headers_deps_file, linux_kernel_work_src_tree)] +
                                   cc_opts + ['-isystem{0}'.format(stdout[0])] +
                                   [os.path.relpath(model_headers_c_file, linux_kernel_work_src_tree)]
                               ),
                               cwd=self.linux_kernel['work src tree'])

            deps = core.lkbce.utils.get_deps_from_gcc_deps_file(model_headers_deps_file)

            # Like in Command.copy_deps() in lkbce/wrappers/common.py but much more simpler.
            for dep in deps:
                if (os.path.isabs(dep) and os.path.commonprefix((linux_kernel_work_src_tree, dep)) != \
                        linux_kernel_work_src_tree) or dep.endswith('.c'):
                    continue

                dest_dep = os.path.relpath(dep, linux_kernel_work_src_tree) if os.path.isabs(dep) else dep

                if not os.path.isfile(dest_dep):
                    self.logger.debug('Copy model header "{0}"'.format(dep))
                    os.makedirs(os.path.dirname(dest_dep), exist_ok=True)
                    shutil.copy2(dep if os.path.isabs(dep) else os.path.join(linux_kernel_work_src_tree, dep), dest_dep)

    def __make_canonical_work_src_tree(self, work_src_tree):
        work_src_tree_root = None

        for dirpath, dirnames, filenames in os.walk(work_src_tree):
            if core.utils.is_src_tree_root(filenames):
                work_src_tree_root = dirpath
                break

        if not work_src_tree_root:
            raise ValueError('Could not find Makefile in working source tree "{0}"'.format(work_src_tree))

        if not os.path.samefile(work_src_tree_root, work_src_tree):
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

    def __make(self, build_target, jobs_num=1, specify_arch=False, collect_build_cmds=False, collect_all_stdout=False):
        # Update environment variables so that invoke build command wrappers and optionally collect build commands.
        env = dict(os.environ)

        env.update({
            'PATH': '{0}:{1}'.format(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'wrappers'),
                                     os.environ['PATH']),
            'KLEVER_RULE_SPECS_DIR': os.path.abspath(os.path.dirname(
                core.utils.find_file_or_dir(self.logger, self.conf['main working directory'],
                                            self.conf['rule specifications DB'])))
        })


        if collect_build_cmds:
            env.update({
                'KLEVER_BUILD_CMD_DESCS_FILE': os.path.abspath(self.linux_kernel['build cmd descs file']),
                'KLEVER_MAIN_WORK_DIR': self.conf['main working directory'],
            })

        return core.utils.execute(self.logger,
                                  tuple(['make', '-j', str(jobs_num)] +
                                        (['ARCH={0}'.format(self.linux_kernel['arch'])] if specify_arch else []) +
                                        (['KCONFIG_CONFIG=' + os.path.basename(self.linux_kernel['conf file'])]
                                         if 'conf file' in self.linux_kernel else []) +
                                        list(build_target)),
                                  env,
                                  cwd=self.linux_kernel['work src tree'],
                                  collect_all_stdout=collect_all_stdout)
