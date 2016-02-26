#!/usr/bin/python3

import os
import re
import shutil
import sys
import tarfile
import time
import urllib.parse

import core.components
import core.lkbce.cmds.cmds
import core.utils

# We assume that CC/LD options always start with "-".
# Some CC/LD options always require values that can be specified either together with option itself (maybe separated
# with "=") or by means of the following option.
# Some CC options allow to omit both CC input and output files.
# Value of -o is CC/LD output file.
# The rest options are CC/LD input files.
_cmd_opts = {
    'CC': {'opts requiring vals': ('D', 'I', 'O', 'include', 'isystem', 'mcmodel', 'o', 'print-file-name', 'x'),
           'opts discarding in files': ('print-file-name', 'v'),
           'opts discarding out file': ('E', 'print-file-name', 'v')},
    'LD': {'opts requiring vals': ('T', 'm', 'o',),
           'opts discarding in files': (),
           'opts discarding out file': ()}}

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


class LKBCE(core.components.Component):
    def extract_linux_kernel_build_commands(self):
        self.linux_kernel = {}
        self.fetch_linux_kernel_work_src_tree()
        self.make_canonical_linux_kernel_work_src_tree()
        core.utils.invoke_callbacks(self.extract_src_tree_root)
        self.clean_linux_kernel_work_src_tree()
        core.utils.invoke_callbacks(self.extract_linux_kernel_attrs)
        core.utils.invoke_callbacks(self.extract_hdr_arch)
        core.utils.report(self.logger,
                          'attrs',
                          {
                              'id': self.id,
                              'attrs': self.linux_kernel['attrs']
                          },
                          self.mqs['report files'],
                          self.conf['main working directory'])
        # This file should be specified to collect build commands during configuring and building of the Linux kernel.
        self.linux_kernel['raw build cmds file'] = 'Linux kernel raw build cmds'
        self.configure_linux_kernel()
        # Always create Linux kernel raw build commands file prior to its reading in
        # self.process_all_linux_kernel_raw_build_cmds().
        with open(self.linux_kernel['raw build cmds file'], 'w'):
            pass
        self.launch_subcomponents((self.build_linux_kernel, self.process_all_linux_kernel_raw_build_cmds))
        # Linux kernel raw build commands file should be kept just in debugging.
        if not self.conf['debug']:
            os.remove(self.linux_kernel['raw build cmds file'])

    main = extract_linux_kernel_build_commands

    def build_linux_kernel(self):
        self.logger.info('Build Linux kernel')

        # First of all collect all targets to be built.
        build_targets = []

        if 'build kernel' in self.conf['Linux kernel'] and self.conf['Linux kernel']['build kernel']:
            build_targets.append(('vmlinux',))

        if 'modules' in self.conf['Linux kernel']:
            # Specially process building of all modules.
            if 'all' in self.conf['Linux kernel']['modules']:
                if not len(self.conf['Linux kernel']['modules']) == 1:
                    raise ValueError('You can not specify "all" modules together with some other modules')

                build_targets.append(('modules',))
            else:
                # Check that module sets aren't intersect explicitly.
                for i, modules1 in enumerate(self.conf['Linux kernel']['modules']):
                    for j, modules2 in enumerate(self.conf['Linux kernel']['modules']):
                        if i != j and modules1.startswith(modules2):
                            raise ValueError(
                                'Module set "{0}" is subset of module set "{1}"'.format(modules1, modules2))

                # Examine module sets.
                for modules_set in self.conf['Linux kernel']['modules']:
                    # Module sets ending with .ko imply individual modules.
                    if re.search(r'\.ko$', modules_set):
                        build_targets.append((modules_set,))
                    # Otherwise it is directory that can contain modules.
                    else:
                        # Add "modules_prepare" target once.
                        if not build_targets or build_targets[0] != ('modules_prepare',):
                            build_targets.insert(0, ('modules_prepare',))

                        if not os.path.isdir(os.path.join(self.linux_kernel['work src tree'], modules_set)):
                            raise ValueError('There is not directory "{0}" inside "{1}"'.format(modules_set,
                                                                                                self.linux_kernel[
                                                                                                    'work src tree']))

                        build_targets.append(('M={0}'.format(modules_set), 'modules'))
        else:
            self.logger.warning('Nothing will be verified since modules are not specified')

        if build_targets:
            self.logger.debug('Build following targets:\n{0}'.format(
                '\n'.join([' '.join(build_target) for build_target in build_targets])))

        jobs_num = core.utils.get_parallel_threads_num(self.logger, self.conf, 'Linux kernel build')
        for build_target in build_targets:
            self.__make(build_target,
                        jobs_num=jobs_num,
                        specify_arch=True, collect_build_cmds=True)

        self.extract_all_linux_kernel_mod_deps()

        self.logger.info('Terminate Linux kernel raw build commands "message queue"')
        with core.utils.LockedOpen(self.linux_kernel['raw build cmds file'], 'a', encoding='ascii') as fp:
            fp.write(core.lkbce.cmds.cmds.Command.cmds_separator)

    def extract_all_linux_kernel_mod_deps(self):
        self.linux_kernel['module deps'] = {}

        if 'modules' in self.conf['Linux kernel'] and 'all' in self.conf['Linux kernel']['modules'] \
                and 'build kernel' in self.conf['Linux kernel'] and self.conf['Linux kernel']['build kernel']:
            self.logger.info('Extract all Linux kernel module dependencies')

            self.logger.info('Install Linux kernel modules')

            # Specify installed Linux kernel modules directory like Linux kernel working source tree in
            # fetch_linux_kernel_work_src_tree().
            self.linux_kernel['installed modules dir'] = os.path.join(os.path.pardir, 'linux-modules')
            os.mkdir(self.linux_kernel['installed modules dir'])
            self.__make(['INSTALL_MOD_PATH={0}'.format(self.linux_kernel['installed modules dir']), 'modules_install'],
                        jobs_num=core.utils.get_parallel_threads_num(self.logger, self.conf, 'Linux kernel build'),
                        specify_arch=False, collect_build_cmds=False)

            path = os.path.join(self.linux_kernel['installed modules dir'], "lib/modules",
                                self.linux_kernel['version'], "modules.dep")

            with open(path, encoding='ascii') as fp:
                for line in fp:
                    splits = line.split(':')
                    if len(splits) == 1:
                        continue
                    module_name = splits[0]
                    module_name = module_name[7:] if module_name.startswith('kernel/') else module_name
                    module_deps = splits[1][:-1]
                    module_deps = list(filter(lambda x: x != '', module_deps.split(' ')))
                    if len(module_deps) == 1:
                        continue
                    module_deps = [dep[7:] if dep.startswith('kernel/') else dep for dep in module_deps]
                    module_deps = list(sorted(module_deps))
                    self.linux_kernel['module deps'][module_name] = module_deps
            self.conf['Linux kernel']['module deps'] = self.linux_kernel['module deps']

    def clean_linux_kernel_work_src_tree(self):
        self.logger.info('Clean Linux kernel working source tree')
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

    def configure_linux_kernel(self):
        self.logger.info('Configure Linux kernel')
        if 'configuration' in self.conf['Linux kernel']:
            self.__make((self.conf['Linux kernel']['configuration'],), specify_arch=True, collect_build_cmds=False,
                        collect_all_stdout=True)
        else:
            raise NotImplementedError('Linux kernel configuration is provided in unsupported form')

    def extract_linux_kernel_attrs(self):
        self.logger.info('Extract Linux kernel atributes')

        self.logger.debug('Get Linux kernel version')
        stdout = self.__make(('-s', 'kernelversion'), specify_arch=False, collect_all_stdout=True)

        self.linux_kernel['version'] = stdout[0]
        self.logger.debug('Linux kernel version is "{0}"'.format(self.linux_kernel['version']))

        self.logger.debug('Get Linux kernel architecture')
        self.linux_kernel['arch'] = self.conf['Linux kernel'].get('architecture') or self.conf['sys']['arch']
        self.logger.debug('Linux kernel architecture is "{0}"'.format(self.linux_kernel['arch']))

        self.logger.debug('Get Linux kernel configuration shortcut')
        self.linux_kernel['conf shortcut'] = self.conf['Linux kernel']['configuration']
        self.logger.debug('Linux kernel configuration shortcut is "{0}"'.format(self.linux_kernel['conf shortcut']))

        self.linux_kernel['attrs'] = [
            {'Linux kernel': [{'version': self.linux_kernel['version']},
                              {'architecture': self.linux_kernel['arch']},
                              {'configuration': self.linux_kernel['conf shortcut']}]}]

    def extract_hdr_arch(self):
        self.hdr_arch = _arch_hdr_arch[self.linux_kernel['arch']]

    def extract_src_tree_root(self):
        self.src_tree_root = os.path.abspath(self.linux_kernel['work src tree'])

    def fetch_linux_kernel_work_src_tree(self):
        # Fetch Linux kernel working source tree to root directory of all Klever Core components for convenience and to
        # keep it when several sub-jobs are decided (each such sub-job will have its own Linux kernel working source
        # tree).
        self.linux_kernel['work src tree'] = os.path.join(os.path.pardir, 'linux')

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
                os.symlink(os.path.abspath(self.linux_kernel['src']), self.linux_kernel['work src tree'])
            else:
                shutil.copytree(self.linux_kernel['src'], self.linux_kernel['work src tree'])

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

        linux_kernel_work_src_tree_root = None

        for dirpath, dirnames, filenames in os.walk(self.linux_kernel['work src tree']):
            if core.utils.is_src_tree_root(filenames):
                linux_kernel_work_src_tree_root = dirpath
                break

        if not linux_kernel_work_src_tree_root:
            raise ValueError('Could not find Makefile in Linux kernel source code')

        if not os.path.samefile(linux_kernel_work_src_tree_root, self.linux_kernel['work src tree']):
            self.logger.debug('Move contents of "{0}" to "{1}"'.format(linux_kernel_work_src_tree_root,
                                                                       self.linux_kernel['work src tree']))
            for path in os.listdir(linux_kernel_work_src_tree_root):
                shutil.move(os.path.join(linux_kernel_work_src_tree_root, path), self.linux_kernel['work src tree'])
            trash_dir = linux_kernel_work_src_tree_root
            while True:
                parent_dir = os.path.join(trash_dir, os.path.pardir)
                if os.path.samefile(parent_dir, self.linux_kernel['work src tree']):
                    break
                trash_dir = parent_dir
            self.logger.debug('Remove "{0}"'.format(trash_dir))
            os.rmdir(trash_dir)

    def process_all_linux_kernel_raw_build_cmds(self):
        self.logger.info('Process all Linux kernel raw build commands')

        # It looks quite reasonable to scan Linux kernel raw build commands file once a second since build isn't
        # performed neither too fast nor too slow.
        # Offset is used to scan just new lines from Linux kernel raw build commands file.
        offset = 0
        prev_line = None
        while True:
            time.sleep(1)

            with core.utils.LockedOpen(self.linux_kernel['raw build cmds file'], 'r+', encoding='ascii') as fp:
                # Move to previous end of file.
                fp.seek(offset)

                # Read new lines from file.
                self.linux_kernel['build cmd'] = {}
                self.linux_kernel['build cmd']['type'] = None
                opts = []
                for line in fp:
                    if line == core.lkbce.cmds.cmds.Command.cmds_separator:
                        # If there is no Linux kernel raw build commands just one separator will be printed by LKBCE
                        # itself when terminating corresponding message queue.
                        if not prev_line or prev_line == core.lkbce.cmds.cmds.Command.cmds_separator:
                            self.logger.debug('Linux kernel raw build commands "message queue" was terminated')
                            return
                        else:
                            core.utils.invoke_callbacks(self.process_linux_kernel_raw_build_cmd, (opts,))

                            # Go to the next command or finish operation.
                            self.linux_kernel['build cmd']['type'] = None
                            opts = []
                    else:
                        if not self.linux_kernel['build cmd']['type']:
                            self.linux_kernel['build cmd']['type'] = line.rstrip()
                        else:
                            opts.append(line.rstrip())

                    prev_line = line

                if self.conf['debug']:
                    # When debugging we keep all file content. So move offset to current end of file to scan just new
                    # lines from file on the next iteration.
                    offset = fp.tell()
                else:
                    # Clean up all already scanned content of file to save disk space.
                    fp.seek(0)
                    fp.truncate()

    def process_linux_kernel_raw_build_cmd(self, opts):
        self.logger.info('Process Linux kernel raw build command "{0}"'.format(self.linux_kernel['build cmd']['type']))

        self.linux_kernel['build cmd']['in files'] = []
        self.linux_kernel['build cmd']['out file'] = None
        self.linux_kernel['build cmd']['opts'] = []
        # Input files and output files should be presented almost always.
        cmd_requires_in_files = True
        cmd_requires_out_file = True

        if self.linux_kernel['build cmd']['type'] in ('CC', 'LD'):
            opts_requiring_vals = _cmd_opts[self.linux_kernel['build cmd']['type']]['opts requiring vals']
            skip_next_opt = False
            for idx, opt in enumerate(opts):
                # Option represents already processed value of the previous option.
                if skip_next_opt:
                    skip_next_opt = False
                    continue

                for opt_discarding_in_files in \
                        _cmd_opts[self.linux_kernel['build cmd']['type']]['opts discarding in files']:
                    if re.search(r'^-{0}'.format(opt_discarding_in_files), opt):
                        cmd_requires_in_files = False

                for opt_discarding_out_file in \
                        _cmd_opts[self.linux_kernel['build cmd']['type']]['opts discarding out file']:
                    if re.search(r'^-{0}'.format(opt_discarding_out_file), opt):
                        cmd_requires_out_file = False

                # Options with values.
                match = None
                for opt_requiring_val in opts_requiring_vals:
                    match = re.search(r'^-({0})(=?)(.*)'.format(opt_requiring_val), opt)
                    if match:
                        opt, eq, val = match.groups()

                        # Option value is specified by means of the following option.
                        if not val:
                            val = opts[idx + 1]
                            skip_next_opt = True

                        # Output file.
                        if opt == 'o':
                            self.linux_kernel['build cmd']['out file'] = val
                        else:
                            # Use original formatting of options.
                            if skip_next_opt:
                                self.linux_kernel['build cmd']['opts'].extend(['-{0}'.format(opt), val])
                            else:
                                self.linux_kernel['build cmd']['opts'].append('-{0}{1}{2}'.format(opt, eq, val))

                        break

                if not match:
                    # Options without values.
                    if re.search(r'^-.+$', opt):
                        self.linux_kernel['build cmd']['opts'].append(opt)
                    # Input files.
                    else:
                        self.linux_kernel['build cmd']['in files'].append(opt)
        elif self.linux_kernel['build cmd']['type'] == 'MV':
            # We assume that MV options always have such the form:
            #     [-opt]... in_file out_file
            for opt in opts:
                if re.search(r'^-', opt):
                    self.linux_kernel['build cmd']['opts'].append(opt)
                elif not self.linux_kernel['build cmd']['in files']:
                    self.linux_kernel['build cmd']['in files'].append(opt)
                else:
                    self.linux_kernel['build cmd']['out file'] = opt
        else:
            raise NotImplementedError('Linux kernel raw build command "{0}" is not supported yet'.format(
                self.linux_kernel['build cmd']['type']))

        if cmd_requires_in_files and not self.linux_kernel['build cmd']['in files']:
            raise ValueError(
                'Could not get Linux kernel raw build command input files' + ' from options "{0}"'.format(opts))
        if cmd_requires_out_file and not self.linux_kernel['build cmd']['out file']:
            raise ValueError(
                'Could not get Linux kernel raw build command output file' + ' from options "{0}"'.format(opts))

        # Check thar all original options becomes either input files or output file or options.
        # Option -o isn't included in the resulting set.
        original_opts = opts
        if '-o' in original_opts:
            original_opts.remove('-o')
        resulting_opts = self.linux_kernel['build cmd']['in files'] + self.linux_kernel['build cmd']['opts']
        if self.linux_kernel['build cmd']['out file']:
            resulting_opts.append(self.linux_kernel['build cmd']['out file'])
        if set(original_opts) != set(resulting_opts):
            raise RuntimeError('Some options were not parsed: "{0} != {1} + {2} + {3}"'.format(original_opts,
                                                                                               self.linux_kernel[
                                                                                                   'build cmd'][
                                                                                                   'in files'],
                                                                                               self.linux_kernel[
                                                                                                   'build cmd'][
                                                                                                   'out file'],
                                                                                               self.linux_kernel[
                                                                                                   'build cmd'][
                                                                                                   'opts']))

        self.logger.debug('Input files are "{0}"'.format(self.linux_kernel['build cmd']['in files']))
        self.logger.debug('Output file is "{0}"'.format(self.linux_kernel['build cmd']['out file']))
        self.logger.debug('Options are "{0}"'.format(self.linux_kernel['build cmd']['opts']))

    def __make(self, build_target, jobs_num=1, specify_arch=False, collect_build_cmds=False, collect_all_stdout=False):
        # Update environment variables so that invoke build command wrappers and optionally collect build commands.
        env = dict(os.environ)
        env.update({'PATH': '{0}:{1}'.format(os.path.join(sys.path[0], os.path.pardir, 'core', 'lkbce', 'cmds'),
                                             os.environ['PATH'])})
        if collect_build_cmds:
            env.update({'LINUX_KERNEL_RAW_BUILD_CMDS_FILE': os.path.abspath(self.linux_kernel['raw build cmds file'])})

        return core.utils.execute(self.logger,
                                  tuple(['make', '-j', str(jobs_num)] +
                                        (['ARCH={0}'.format(self.linux_kernel['arch'])] if specify_arch else []) +
                                        list(build_target)),
                                  env,
                                  cwd=self.linux_kernel['work src tree'],
                                  collect_all_stdout=collect_all_stdout)
