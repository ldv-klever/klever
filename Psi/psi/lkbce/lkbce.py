#!/usr/bin/python3

import os
import tarfile
import urllib.parse

import psi.component
import psi.utils


class Component(psi.component.ComponentBase):
    def launch(self):
        self.logger.info('Prepare Linux kernel working source tree "linux"')

        linux_kernel_src = self.conf['Linux kernel']['src']

        try:
            o = urllib.parse.urlparse(linux_kernel_src)
            raise NotImplementedError('Can not download Linux kernel "{0}"'.format(linux_kernel_src))
        except:
            self.logger.debug('Linux kernel is not provided in form of URL')

        linux_kernel_src = psi.utils.find_file(self.logger, self.conf['root id'], linux_kernel_src)

        if os.path.isdir(linux_kernel_src):
            self.logger.debug('Linux kernel is provided in form of source tree')
        elif os.path.isfile(linux_kernel_src):
            self.logger.debug('Linux kernel is provided in form of archive')
            #with tarfile.open(linux_kernel_src) as TarFile:
            #    TarFile.extractall(os.path.join(self.conf['root id'], 'linux'))
        else:
            raise ValueError('Linux kernel is provided in unsupported form')
