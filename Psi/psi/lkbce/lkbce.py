#!/usr/bin/python3

import os
import tarfile

import psi.component
import psi.utils


class Component(psi.component.ComponentBase):
    def launch(self):
        self.logger.info('Prepare Linux kernel working source tree "linux"')
        with tarfile.open(
                psi.utils.find_file(self.logger, self.conf['root id'], self.conf['Linux kernel']['src'])) as TarFile:
            TarFile.extractall(os.path.join(self.conf['root id'], 'linux'))
