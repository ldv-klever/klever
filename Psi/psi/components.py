import multiprocessing
import os
import re
import time

import psi.utils

# Psi components
import psi.lkbce.lkbce
import psi.lkvog.lkvog
import psi.avtg.avtg
import psi.vtg.vtg

job_class_component_modules = {'Verification of Linux kernel modules': [psi.lkbce.lkbce, psi.lkvog.lkvog],
                               # These components are likely appropriate for all job classes.
                               'Common': [psi.avtg.avtg, psi.vtg.vtg]}


class Component:
    logger = None

    def __init__(self, module):
        self.module = module
        self.name = re.search(r'^.*\.(.+)$', self.module.__name__).groups()[0].upper()
        self.logger_conf = None
        self.work_dir = None
        self.start_time = None
        self.process = None

    def create_work_dir(self):
        self.work_dir = self.name.lower()
        self.logger.info(
            'Create working directory "{0}" for component "{1}"'.format(self.work_dir, self.name))
        os.makedirs(self.work_dir)

    def get_callbacks(self):
        self.logger.info('Gather callbacks for component "{0}"'.format(self.name))

        p = multiprocessing.Process(target=self.__get_callbacks)
        p.start()
        p.join()
        if p.exitcode:
            self.logger.error('Component "{0}" exited with "{1}"'.format(self.name, p.exitcode))
            raise ChildProcessError('Could not gather callbacks for component "{0}"'.format(self.name))

        self.logger.debug('The number of gathered callbacks is "{0}"'.format(0))

        # TODO: get callbacks!
        return []

    # We don't need to measure consumed resources here.
    def __get_callbacks(self):
        try:
            self.logger.info('Change directory to "{0}" for component "{1}"'.format(self.work_dir, self.name))
            os.chdir(self.work_dir)
            self.module.logger = psi.utils.get_logger(self.name, self.logger_conf)
            self.module.get_callbacks()
        except Exception:
            # TODO: send problem description to Omega.
            self.logger.exception('Component "{0}" raised exception'.format(self.name))
            exit(1)

    def is_operating(self):
        if not self.process:
            raise ValueError('Component "{0}" was not started yet'.format(self.name))

        if self.process.is_alive():
            return 1

        if self.process.exitcode:
            self.logger.error('Component "{0}" exited with "{1}"'.format(self.name, self.process.exitcode))
            raise ChildProcessError('Component "{0}" failed'.format(self.name))
        elif self.process.exitcode == 0:
            self.logger.debug('Component "{0}" exitted normally'.format(self.name))

        return 0

    def launch(self):
        self.logger.info('Launch component "{0}"'.format(self.name))
        self.start_time = time.time()
        self.process = multiprocessing.Process(target=self.__launch)
        self.process.start()

    def __launch(self):
        try:
            self.logger.info('Change directory to "{0}" for component "{1}"'.format(self.work_dir, self.name))
            os.chdir(self.work_dir)
            self.module.logger = psi.utils.get_logger(self.name, self.logger_conf)
            self.module.launch()
        except Exception:
            # TODO: send problem description to Omega.
            self.logger.exception('Component "{0}" raised exception'.format(self.name))
            exit(1)

    def set_logger_conf(self, conf):
        self.logger_conf = conf

    def terminate(self):
        if not self.process:
            raise ValueError('Component "{0}" was not started yet'.format(self.name))

        # Do not terminate components that already exitted.
        if self.process.is_alive():
            self.process.terminate()
            self.logger.debug('Component "{0}" was terminated'.format(self.name))
