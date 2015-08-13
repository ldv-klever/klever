#!/usr/bin/python3

import os
import shutil
import subprocess
import tarfile
import urllib.parse

import psi.components
import psi.utils

name = 'LKBCE'


class PsiComponentCallbacks(psi.components.PsiComponentCallbacksBase):
    pass


class PsiComponent(psi.components.PsiComponentBase):
    def launch(self):
        self.linux_kernel_work_src_tree = os.path.relpath(os.path.join(self.conf['root id'], 'linux'))
        self.fetch_linux_kernel_work_src_tree()
        self.make_canonical_linux_kernel_work_src_tree()
        self.clean_linux_kernel_work_src_tree()

    def clean_linux_kernel_work_src_tree(self):
        self.logger.info('Clean Linux kernel working source tree')

        # cmd = ('make', '-C', self.linux_kernel_work_src_tree, 'mrproper')
        # self.logger.debug('"{0}" outputs:'.format(cmd))
        # p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # while not p.poll():
        #     import time
        #     time.sleep(1)
        #     self.logger.debug('One more second...')
        #     for line in p.stdout:
        #         self.logger.debug(line.decode('utf8').rstrip())
        #     for line in p.stderr:
        #         self.logger.debug(line.decode('utf8').rstrip())

    def fetch_linux_kernel_work_src_tree(self):
        self.logger.info('Fetch Linux kernel working source tree to "{0}"'.format(self.linux_kernel_work_src_tree))

        linux_kernel_src = self.conf['Linux kernel']['src']

        o = urllib.parse.urlparse(linux_kernel_src)
        if o[0] in ('http', 'https', 'ftp'):
            raise NotImplementedError(
                'Linux kernel source code is likely provided in unsopported form of remote archive')
        elif o[0] == 'git':
            raise NotImplementedError(
                'Linux kernel source code is likely provided in unsopported form of Git repository')
        elif o[0]:
            raise ValueError('Linux kernel source code is provided in unsupported form "{0}"'.format(o[0]))

        linux_kernel_src = psi.utils.find_file_or_dir(self.logger, self.conf['root id'], linux_kernel_src)

        if os.path.isdir(linux_kernel_src):
            self.logger.debug('Linux kernel source code is provided in form of source tree')
            shutil.copytree(linux_kernel_src, self.linux_kernel_work_src_tree)
        elif os.path.isfile(linux_kernel_src):
            self.logger.debug('Linux kernel source code is provided in form of archive')
            with tarfile.open(linux_kernel_src) as TarFile:
                TarFile.extractall(self.linux_kernel_work_src_tree)

    def make_canonical_linux_kernel_work_src_tree(self):
        self.logger.info('Make canonical Linux kernel working source tree')

        linux_kernel_work_src_tree_root = None

        for dirpath, dirnames, filenames in os.walk(self.linux_kernel_work_src_tree):
            if psi.utils.is_src_tree_root(filenames):
                linux_kernel_work_src_tree_root = dirpath
                break

        if not linux_kernel_work_src_tree_root:
            raise ValueError('Could not find Makefile in Linux kernel source code')

        # TODO: specification requires to remove everything in self.linux_kernel_work_src_tree:remove except moved linux_kernel_work_src_tree_root.
        if not os.path.samefile(linux_kernel_work_src_tree_root, self.linux_kernel_work_src_tree):
            self.logger.debug(
                'Move "{0}" to "{1}"'.format(linux_kernel_work_src_tree_root, self.linux_kernel_work_src_tree))
            os.rename(linux_kernel_work_src_tree_root, self.linux_kernel_work_src_tree)
