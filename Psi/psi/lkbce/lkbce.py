#!/usr/bin/python3

import os
import shutil
import tarfile
import urllib.parse

import psi.component
import psi.utils


class Component(psi.component.ComponentBase):
    def launch(self):
        self.__fetch_linux_kernel_work_src_tree()

    def __fetch_linux_kernel_work_src_tree(self):
        self.logger.info('Fetch Linux kernel working source tree "linux"')

        linux_kernel_src = self.conf['Linux kernel']['src']
        linux_kernel_work_src_tree = os.path.join(self.conf['root id'], 'linux')

        o = urllib.parse.urlparse(linux_kernel_src)
        if o[0] in ('http', 'https', 'ftp'):
            raise NotImplementedError('Linux kernel is likely provided in unsopported form of remote archive')
        elif o[0] == 'git':
            raise NotImplementedError('Linux kernel is likely provided in unsopported form of Git repository')
        elif o[0]:
            raise ValueError('Linux kernel is provided in unsupported form "{0}"'.format(o[0]))

        linux_kernel_src = psi.utils.find_file_or_dir(self.logger, self.conf['root id'], linux_kernel_src)

        if os.path.isdir(linux_kernel_src):
            self.logger.debug('Linux kernel is provided in form of source tree')
            shutil.copytree(linux_kernel_src, linux_kernel_work_src_tree)
        elif os.path.isfile(linux_kernel_src):
            self.logger.debug('Linux kernel is provided in form of archive')
            with tarfile.open(linux_kernel_src) as TarFile:
                TarFile.extractall(linux_kernel_work_src_tree)
