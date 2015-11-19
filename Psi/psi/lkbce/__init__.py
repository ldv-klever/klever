#!/usr/bin/python3

import os
import re
import shutil
import sys
import tarfile
import time
import urllib.parse

import psi.components
import psi.lkbce.cmds.cmds
import psi.utils

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


class LKBCE(psi.components.Component):
    def extract_linux_kernel_build_commands(self):
        self.linux_kernel = {}
        self.fetch_linux_kernel_work_src_tree()
        self.make_canonical_linux_kernel_work_src_tree()
        self.clean_linux_kernel_work_src_tree()
        psi.utils.invoke_callbacks(self.extract_linux_kernel_attrs)
        psi.utils.report(self.logger,
                         'attrs',
                         {'id': self.name,
                          'attrs': self.linux_kernel['attrs']},
                         self.mqs['report files'],
                         self.conf['root id'])
        # This file should be specified to collect build commands during configuring and building of the Linux kernel.
        self.linux_kernel['raw build cmds file'] = 'Linux kernel raw build cmds'
        self.configure_linux_kernel()
        self.launch_subcomponents((self.build_linux_kernel, self.process_all_linux_kernel_raw_build_cmds))
        # Linux kernel raw build commands file should be kept just in debugging.
        if not self.conf['debug']:
            os.remove(self.linux_kernel['raw build cmds file'])

    main = extract_linux_kernel_build_commands

    def build_linux_kernel(self):
        self.logger.info('Build Linux kernel')

        # First of all collect all build commands to be executed.
        cmds = []
        if 'whole build' in self.conf['Linux kernel']:
            cmds.append(('all',))
        elif 'modules' in self.conf['Linux kernel']:
            # Check that module sets aren't intersect explicitly.
            for i, modules1 in enumerate(self.conf['Linux kernel']['modules']):
                for j, modules2 in enumerate(self.conf['Linux kernel']['modules']):
                    if i != j and modules1.startswith(modules2):
                        raise ValueError('Module set "{0}" is subset of module set "{1}"'.format(modules1, modules2))

            # Examine module sets.
            for modules in self.conf['Linux kernel']['modules']:
                # Module sets ending with .ko imply individual modules.
                if re.search(r'\.ko$', modules):
                    cmds.append((modules,))
                # Otherwise it is directory that can contain modules.
                else:
                    # Add "modules_prepare" target once.
                    if not cmds or cmds[0] != ('modules_prepare',):
                        cmds.insert(0, ('modules_prepare',))

                    if not os.path.isdir(os.path.join(self.linux_kernel['work src tree'], modules)):
                        raise ValueError('There is not directory "{0}" inside "{1}"'.format(modules,
                                                                                            self.linux_kernel[
                                                                                                'work src tree']))

                    cmds.append(('M={0}'.format(modules), 'modules'))
        else:
            raise KeyError(
                'Neither "whole build" nor "modules" attribute of Linux kernel is specified in configuration')

        self.logger.debug(
            'Following build commands will be executed:\n{0}'.format('\n'.join([' '.join(cmd) for cmd in cmds])))

        for args in cmds:
            self.__make(args, jobs_num=psi.utils.get_parallel_threads_num(self.logger, self.conf, 'Linux kernel build'),
                        specify_arch=True, invoke_build_cmd_wrappers=True, collect_build_cmds=True)

         #TODO external module
        self.linux_kernel['module deps'] = {}
        if 'whole build' in self.conf['Linux kernel']:
            #Install modules
            self.linux_kernel['modules install'] = self.conf['root id'] + '/linux-modules'
            os.mkdir(self.linux_kernel['modules install'])
            psi.utils.execute(self.logger,
                                     tuple(['make', '-C', self.linux_kernel['work src tree'],
                                            'INSTALL_MOD_PATH={0}'.format(self.linux_kernel['modules install']), 'modules_install']),
                                     dict(os.environ,
                                              PATH='{0}:{1}'.format(
                                                  os.path.join(sys.path[0], os.path.pardir, 'psi', 'lkbce', 'cmds'),
                                                  os.environ['PATH']),
                                              LINUX_KERNEL_RAW_BUILD_CMS_FILE=os.path.abspath(
                                                  self.linux_kernel['raw build cmds file'])))
            #Extract mod deps
            self.extract_all_linux_kernel_mod_deps()

        self.logger.info('Terminate Linux kernel raw build commands "message queue"')
        with psi.utils.LockedOpen(self.linux_kernel['raw build cmds file'], 'a') as fp:
            fp.write(psi.lkbce.cmds.cmds.Command.cmds_separator)

    def extract_all_linux_kernel_mod_deps(self):
        if 'whole build' in self.conf['Linux kernel']:
            path = self.linux_kernel['modules install'] + "/lib/modules/" + self.linux_kernel['version'] + "/modules.dep"
            if not os.path.exists(path):
                path = "/home/alexey/kernel/modules/lib/modules/4.0.0-rc1/modules.dep"
            with open(path, 'r') as fp:
                for line in fp:
                    splits = line.split(':')
                    if len(splits) == 1:
                        continue
                    module_name = splits[0]
                    module_deps = splits[1][:-1]
                    module_deps = list(filter(lambda x: x != '', module_deps.split(' ')))
                    if len(module_deps) == 1:
                        continue
                    self.linux_kernel['module deps'][module_name] = module_deps

                    #l = line.split(':')
                    #if len(l) == 2:
                    #    module = re.sub('^kernel/', '', l[0])
                    #    deps = [re.sub('^kernel/', '', dep) for dep in l[1][1:-1].split(' ')]
                    #    self.linux_kernel['module deps'][module] = deps
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
            self.__make((self.conf['Linux kernel']['configuration'],), specify_arch=True,
                        invoke_build_cmd_wrappers=True, collect_build_cmds=True, collect_all_stdout=True)
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

    def fetch_linux_kernel_work_src_tree(self):
        self.linux_kernel['work src tree'] = os.path.relpath(os.path.join(self.conf['root id'], 'linux'))

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

        self.linux_kernel['src'] = psi.utils.find_file_or_dir(self.logger, self.conf['root id'],
                                                              self.linux_kernel['src'])

        if os.path.isdir(self.linux_kernel['src']):
            self.logger.debug('Linux kernel source code is provided in form of source tree')
            if self.conf['allow local source directories use']:
                os.symlink(os.path.abspath(self.linux_kernel['src']), self.linux_kernel['work src tree'])
            else:
                shutil.copytree(self.linux_kernel['src'], self.linux_kernel['work src tree'])
        elif os.path.isfile(self.linux_kernel['src']):
            self.logger.debug('Linux kernel source code is provided in form of archive')
            with tarfile.open(self.linux_kernel['src']) as TarFile:
                TarFile.extractall(self.linux_kernel['work src tree'])

    def make_canonical_linux_kernel_work_src_tree(self):
        self.logger.info('Make canonical Linux kernel working source tree')

        linux_kernel_work_src_tree_root = None

        for dirpath, dirnames, filenames in os.walk(self.linux_kernel['work src tree']):
            if psi.utils.is_src_tree_root(filenames):
                linux_kernel_work_src_tree_root = dirpath
                break

        if not linux_kernel_work_src_tree_root:
            raise ValueError('Could not find Makefile in Linux kernel source code')

        if not os.path.samefile(linux_kernel_work_src_tree_root, self.linux_kernel['work src tree']):
            self.logger.debug(
                'Move contents of "{0}" to "{1}"'.format(linux_kernel_work_src_tree_root,
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

            with psi.utils.LockedOpen(self.linux_kernel['raw build cmds file'], 'r+') as fp:
                # Move to previous end of file.
                fp.seek(offset)

                # Read new lines from file.
                self.linux_kernel['build cmd'] = {}
                self.linux_kernel['build cmd']['type'] = None
                opts = []
                for line in fp:
                    if line == psi.lkbce.cmds.cmds.Command.cmds_separator:
                        # If there is no Linux kernel raw build commands just one separator will be printed by LKBCE
                        # itself when terminating corresponding message queue.
                        if not prev_line or prev_line == psi.lkbce.cmds.cmds.Command.cmds_separator:
                            self.logger.debug('Linux kernel raw build commands "message queue" was terminated')
                            return
                        else:
                            psi.utils.invoke_callbacks(self.process_linux_kernel_raw_build_cmd, args=(opts,))

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
            raise NotImplementedError(
                'Linux kernel raw build command "{0}" is not supported yet'.format(
                    self.linux_kernel['build cmd']['type']))

        if cmd_requires_in_files and not self.linux_kernel['build cmd']['in files']:
            raise ValueError(
                'Could not get Linux kernel raw build command input files'
                + ' from options "{0}"'.format(
                    opts))
        if cmd_requires_out_file and not self.linux_kernel['build cmd']['out file']:
            raise ValueError(
                'Could not get Linux kernel raw build command output file'
                + ' from options "{0}"'.format(
                    opts))

        # Check thar all original options becomes either input files or output file or options.
        # Option -o isn't included in the resulting set.
        original_opts = opts
        if '-o' in original_opts:
            original_opts.remove('-o')
        resulting_opts = self.linux_kernel['build cmd']['in files'] + self.linux_kernel['build cmd']['opts']
        if self.linux_kernel['build cmd']['out file']:
            resulting_opts.append(self.linux_kernel['build cmd']['out file'])
        if set(original_opts) != set(resulting_opts):
            raise RuntimeError(
                'Some options were not parsed: "{0} != {1} + {2} + {3}"'.format(original_opts,
                                                                                self.linux_kernel['build cmd'][
                                                                                    'in files'],
                                                                                self.linux_kernel['build cmd'][
                                                                                    'out file'],
                                                                                self.linux_kernel['build cmd']['opts']))

        self.logger.debug(
            'Input files are "{0}"'.format(self.linux_kernel['build cmd']['in files']))
        self.logger.debug(
            'Output file is "{0}"'.format(self.linux_kernel['build cmd']['out file']))
        self.logger.debug('Options are "{0}"'.format(self.linux_kernel['build cmd']['opts']))

    def __make(self, args, jobs_num=1, specify_arch=False, invoke_build_cmd_wrappers=False, collect_build_cmds=False,
               collect_all_stdout=False):
        env = None

        # Update environment variables so that invoke build command wrappers and optionally collect build commands.
        if invoke_build_cmd_wrappers or collect_build_cmds:
            assert invoke_build_cmd_wrappers or not collect_build_cmds, \
                'Build commands can not be collected without invoking build command wrappers'
            env = dict(os.environ)
            if invoke_build_cmd_wrappers:
                env.update({'PATH': '{0}:{1}'.format(os.path.join(sys.path[0], os.path.pardir, 'psi', 'lkbce', 'cmds'),
                                                     os.environ['PATH'])})
            if collect_build_cmds:
                env.update(
                    {'LINUX_KERNEL_RAW_BUILD_CMDS_FILE': os.path.abspath(self.linux_kernel['raw build cmds file'])})

        return psi.utils.execute(self.logger,
                                 tuple(['make', '-j', str(jobs_num), '-C', self.linux_kernel['work src tree']] +
                                       (['ARCH={0}'.format(self.linux_kernel['arch'])] if specify_arch else []) +
                                       list(args)),
                                 env,
                                 collect_all_stdout=collect_all_stdout)
