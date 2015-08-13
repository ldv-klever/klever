#!/usr/bin/python3

import os
import shutil
import tarfile
import urllib.parse

import psi.components
import psi.utils

name = 'LKBCE'


class PsiComponentCallbacks(psi.components.PsiComponentCallbacksBase):
    pass


class PsiComponent(psi.components.PsiComponentBase):
    def launch(self):
        self.linux_kernel = {}
        self.fetch_linux_kernel_work_src_tree()
        self.make_canonical_linux_kernel_work_src_tree()
        self.clean_linux_kernel_work_src_tree()
        self.extract_linux_kernel_attrs()

    def clean_linux_kernel_work_src_tree(self):
        self.logger.info('Clean Linux kernel working source tree')
        psi.components.Component(self.logger, ('make', '-C', self.linux_kernel['work src tree'], 'mrproper')).start()

    def extract_linux_kernel_attrs(self):
        self.logger.info('Extract Linux kernel atributes')

        self.logger.debug('Get Linux kernel version')
        p = psi.components.Component(self.logger, ('make', '-s', '-C', self.linux_kernel['work src tree'], 'kernelversion'))
        p.start()
        self.linux_kernel['version'] = p.stdout[0]
        self.logger.debug('Linux kernel version is "{0}"'.format(self.linux_kernel['version']))

        self.logger.debug('Get Linux kernel architecture')
        self.linux_kernel['arch'] = self.conf['Linux kernel'].get('arch') or self.conf['sys']['arch']
        self.logger.debug('Linux kernel architecture is "{0}"'.format(self.linux_kernel['arch']))

        self.logger.debug('Get Linux kernel configuration shortcut')
        self.linux_kernel['conf shortcut'] = self.conf['Linux kernel']['conf']
        self.logger.debug('Linux kernel configuration shortcut is "{0}"'.format(self.linux_kernel['conf shortcut']))


    def fetch_linux_kernel_work_src_tree(self):
        self.linux_kernel['work src tree'] = os.path.relpath(os.path.join(self.conf['root id'], 'linux'))

        self.logger.info('Fetch Linux kernel working source tree to "{0}"'.format(self.linux_kernel['work src tree']))

        self.linux_kernel['src'] = self.conf['Linux kernel']['src']

        o = urllib.parse.urlparse(self.linux_kernel['src'])
        if o[0] in ('http', 'https', 'ftp'):
            raise NotImplementedError(
                'Linux kernel source code is likely provided in unsopported form of remote archive')
        elif o[0] == 'git':
            raise NotImplementedError(
                'Linux kernel source code is likely provided in unsopported form of Git repository')
        elif o[0]:
            raise ValueError('Linux kernel source code is provided in unsupported form "{0}"'.format(o[0]))

        self.linux_kernel['src'] = psi.utils.find_file_or_dir(self.logger, self.conf['root id'], self.linux_kernel['src'])

        if os.path.isdir(self.linux_kernel['src']):
            self.logger.debug('Linux kernel source code is provided in form of source tree')
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

        # TODO: specification requires to remove everything in self.linux_kernel['work src tree'] except moved linux_kernel_work_src_tree_root.
        if not os.path.samefile(linux_kernel_work_src_tree_root, self.linux_kernel['work src tree']):
            self.logger.debug(
                'Move "{0}" to "{1}"'.format(linux_kernel_work_src_tree_root, self.linux_kernel['work src tree']))
            os.rename(linux_kernel_work_src_tree_root, self.linux_kernel['work src tree'])
