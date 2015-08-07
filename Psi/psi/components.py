import io
import json
import multiprocessing
import os
import re
import signal
import time
import traceback

import psi.utils

# Psi components
import psi.lkbce.lkbce
import psi.lkvog.lkvog
import psi.avtg.avtg
import psi.vtg.vtg

_job_class_component_modules = {'Verification of Linux kernel modules': [psi.lkbce.lkbce, psi.lkvog.lkvog],
                                # These components are likely appropriate for all job classes.
                                'Common': [psi.avtg.avtg, psi.vtg.vtg]}


class Component:
    def __init__(self, module, conf, logger, reports_mq):
        self.module = module
        self.conf = conf
        self.logger = logger
        self.reports_mq = reports_mq
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
            self.logger.info('Change directory to "{0}" for component "{1}"'.format(self.work_dir, self.name))
            os.chdir(self.work_dir)

            logger = psi.utils.get_logger(self.name, self.conf['logging'])

            self.module.Component(self.conf, logger).get_callbacks()
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
            # Specially process SIGTERM since it can be sent by Psi when some other component(s) failed. Official
            # documentation says that exit handlers and finally clauses, etc., will not be executed. But we still need
            # to count consumed resources and create finish report - all this is done in self.__finalize().
            signal.signal(signal.SIGTERM, self.__finalize)

            self.logger.info('Change directory to "{0}" for component "{1}"'.format(self.work_dir, self.name))
            os.chdir(self.work_dir)

            start_report_file = psi.utils.dump_report(self.logger, self.name, 'start',
                                                      {'id': self.name, 'parent id': '/', 'name': self.name})
            self.reports_mq.put(os.path.relpath(start_report_file, self.conf['root id']))

            logger = psi.utils.get_logger(self.name, self.conf['logging'])

            self.module.Component(self.conf, logger).launch()
        except Exception as e:
            # Write information on exception to file with problem description rather than create unknown report. Psi
            # will create unknown report itself when it will see exit code 1.
            with open('problem desc', 'w') as fp:
                traceback.print_exc(file=fp)

            logger.exception('Catch exception')
            self.logger.error('Component "{0}" raised exception'.format(self.name))

            exit(1)
        finally:
            self.__finalize()

    def __finalize(self, signum=None, frame=None):
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
            self.reports_mq.put(os.path.relpath(finish_report_file, self.conf['root id']))

        # Don't forget to terminate itself if somebody tries to do such.
        if signum:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            os.kill(self.process.pid, signal.SIGTERM)

    def terminate(self):
        if not self.process:
            self.logger.warning('Component "{0}" was not started yet'.format(self.name))
            return

        # Do not terminate components that already exitted.
        if self.process.is_alive():
            self.process.terminate()
            # Official documentation says that exit handlers and finally clauses, etc., will not be executed. So we need
            # to create unknown report ourselves. It has especial sense since terminated components can operate properly
            # and we should report that we are terminating them rather than report they were terminated unexpectedly.
            unknown_report_file = psi.utils.dump_report(self.logger, self.name, 'unknown',
                                                        {'id': 'unknown', 'parent id': self.name,
                                                         'problem desc': 'Terminated since some other component(s) failed'},
                                                        self.work_dir)
            self.reports_mq.put(unknown_report_file)
            self.logger.debug('Component "{0}" was terminated'.format(self.name))


def get_components(conf, logger, kind, reports_mq):
    logger.info('Get components necessary to solve job')

    if kind not in _job_class_component_modules:
        raise KeyError('Job class "{0}" is not supported'.format(kind))

    # Get modules of components specific for job class.
    component_modules = _job_class_component_modules[kind]

    # Get modules of common components.
    component_modules.extend(_job_class_component_modules['Common'])

    # Get components.
    components = [Component(component_module, conf, logger, reports_mq) for component_module in component_modules]

    logger.debug('Components to be launched: "{0}"'.format(', '.join([component.name for component in components])))

    return components
