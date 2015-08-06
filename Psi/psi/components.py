import io
import json
import multiprocessing
import os
import re
import time
import traceback

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
    reports_mq = None

    def __init__(self, module):
        self.module = module
        self.name = re.search(r'^.*\.(.+)$', self.module.__name__).groups()[0].upper()
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
            self.logger.info('Read configuration for component "{0}"'.format(self.name))
            with open('components conf.json') as fp:
                self.module.conf = json.load(fp)

            self.logger.info('Change directory to "{0}" for component "{1}"'.format(self.work_dir, self.name))
            os.chdir(self.work_dir)

            self.module.logger = psi.utils.get_logger(self.name, self.module.conf['logging'])

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
            problem_desc_file = os.path.join(self.work_dir, 'problem desc')
            with open(problem_desc_file) if os.path.isfile(problem_desc_file) else io.StringIO('') as fp:
                unknown_report_file = psi.utils.dump_report(self.logger, self.name, 'unknown',
                                                            {'id': 'unknown', 'parent id': self.name,
                                                             'problem desc': fp.read()}, self.work_dir)
                self.reports_mq.put(unknown_report_file)
            self.logger.error('Component "{0}" exited with "{1}"'.format(self.name, self.process.exitcode))
            raise ChildProcessError('Component "{0}" failed'.format(self.name))
        elif self.process.exitcode == 0:
            self.logger.debug('Component "{0}" exitted normally'.format(self.name))

        return 0

    def launch(self):
        # Remember approximate time of start to count wall time.
        self.start_time = time.time()

        self.logger.info('Launch component "{0}"'.format(self.name))
        self.process = multiprocessing.Process(target=self.__launch)
        self.process.start()

    def __launch(self):
        try:
            self.logger.info('Read configuration for component "{0}"'.format(self.name))
            with open('components conf.json') as fp:
                self.module.conf = json.load(fp)

            self.logger.info('Change directory to "{0}" for component "{1}"'.format(self.work_dir, self.name))
            os.chdir(self.work_dir)

            start_report_file = psi.utils.dump_report(self.logger, self.name, 'start',
                                                      {'id': self.name, 'parent id': '/', 'name': self.name})
            self.reports_mq.put(os.path.relpath(start_report_file, self.module.conf['root id']))

            self.module.logger = psi.utils.get_logger(self.name, self.module.conf['logging'])

            self.module.launch()
        except Exception as e:
            # Write traceback to file with problem description rather than create unknown report. Psi will create
            # unknown report itself when it will see exit code 1.
            with io.StringIO() as tb_fp:
                traceback.print_tb(e.__traceback__, file=tb_fp)
                with open('problem desc', 'w') as problem_desc_fp:
                    problem_desc_fp.write(tb_fp.getvalue())

            self.module.logger.exception('Catch exception')
            self.logger.error('Component "{0}" raised exception'.format(self.name))

            exit(1)
        finally:
            with open('desc') if os.path.isfile('desc') else io.StringIO('') as desc_fp:
                with open('log') as log_fp:
                    finish_report_file = psi.utils.dump_report(self.logger, self.name, 'finish',
                                                               {'id': self.name,
                                                                'resources': psi.utils.count_consumed_resources(
                                                                    self.logger,
                                                                    self.name,
                                                                    self.start_time),
                                                                'desc': desc_fp.read(),
                                                                'log': log_fp.read()})
                    self.reports_mq.put(os.path.relpath(finish_report_file, self.module.conf['root id']))

    def terminate(self):
        if not self.process:
            raise ValueError('Component "{0}" was not started yet'.format(self.name))

        # Do not terminate components that already exitted.
        if self.process.is_alive():
            self.process.terminate()
            # Official documentation says that exit handlers and finally clauses, etc., will not be executed. So we need
            # to create unknown and finish reports ourselves. It has especial sense since terminated components can
            # operate properly and we should report that we are terminating them rather than report they were terminated
            # unexpectedly.
            # TODO: resources will be calculated improperly.
            with open('desc') if os.path.isfile('desc') else io.StringIO('') as desc_fp:
                with open(os.path.join(self.work_dir, 'log')) as log_fp:
                    finish_report_file = psi.utils.dump_report(self.logger, self.name, 'finish',
                                                               {'id': self.name,
                                                                'resources': psi.utils.count_consumed_resources(
                                                                    self.logger,
                                                                    self.name,
                                                                    self.start_time),
                                                                'desc': desc_fp.read(),
                                                                'log': log_fp.read()}, self.work_dir)
                    self.reports_mq.put(finish_report_file)
            unknown_report_file = psi.utils.dump_report(self.logger, self.name, 'unknown',
                                                        {'id': 'unknown', 'parent id': self.name,
                                                         'problem desc': 'Terminated since some other component(s) failed'},
                                                        self.work_dir)
            self.reports_mq.put(unknown_report_file)
            self.logger.debug('Component "{0}" was terminated'.format(self.name))
