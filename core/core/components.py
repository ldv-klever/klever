import multiprocessing
import os
import re
import signal
import sys
import time
import traceback
import types

import core.utils


class ComponentError(ChildProcessError):
    pass


class ComponentStopped(ChildProcessError):
    pass


class Component(multiprocessing.Process):
    def __init__(self, conf, logger, parent_id, callbacks, mqs, id=None, work_dir=None, attrs=None,
                 separate_from_parent=False,
                 include_child_resources=False):
        # Actually initialize process.
        multiprocessing.Process.__init__(self)

        self.conf = conf
        # Parent logger will be used untill component will change working directory and get its own logger. We should
        # avoid to use parent logger in component process.
        self.logger = logger
        self.parent_id = parent_id
        self.callbacks = callbacks
        self.mqs = mqs
        self.attrs = attrs
        # Create special message queue where child resources of processes separated from parents will be printed.
        if separate_from_parent:
            self.mqs.update({'child resources': multiprocessing.Queue()})
        self.separate_from_parent = separate_from_parent
        self.include_child_resources = include_child_resources

        self.name = self.__class__.__name__
        # Include parent identifier into the child one. This is required to distinguish reports for different sub-jobs.
        self.id = '{0}/{1}'.format(parent_id, id if id else self.name)
        self.work_dir = work_dir if work_dir else self.name.lower()
        # Component start time.
        self.start_time = 0

    def start(self):
        # Component working directory will be created in parent process.
        if self.separate_from_parent and not os.path.isdir(self.work_dir):
            self.logger.info(
                'Create working directory "{0}" for component "{1}"'.format(self.work_dir, self.name))
            os.makedirs(self.work_dir)

        # Actually start process.
        multiprocessing.Process.start(self)

    def main(self):
        self.logger.error('I forgot to define main function!')
        exit(1)

    def run(self):
        # Remember approximate time of start to count wall time.
        self.start_time = time.time()

        # Specially process SIGTERM since it can be sent by parent when some other component(s) failed. Official
        # documentation says that exit handlers and finally clauses, etc., will not be executed. But we still need
        # to count consumed resources and create finish report - all this is done in self.__finalize().
        signal.signal(signal.SIGUSR1, self.__stop)

        if self.separate_from_parent:
            self.logger.info('Change working directory to "{0}" for component "{1}"'.format(self.work_dir, self.name))
            os.chdir(self.work_dir)

        # Try to launch component.
        try:
            if self.separate_from_parent:
                # Get component specific logger.
                self.logger = core.utils.get_logger(self.name, self.conf['logging'])

                report = {
                    'id': self.id,
                    'parent id': self.parent_id,
                    'name': self.name
                }
                if self.attrs:
                    report.update({'attrs': self.attrs})
                core.utils.report(self.logger,
                                  'start',
                                  report,
                                  self.mqs['report files'],
                                  self.conf['main working directory'])

            core.utils.invoke_callbacks(self.main)
        finally:
            # Print information on exception to logs and as problem description. Do not consider component stopping.
            if sys.exc_info()[0] and sys.exc_info()[0] != ComponentStopped:
                exception_info = '{0}Raise exception:\n{1}'.format(self.__get_subcomponent_name(),
                                                                   traceback.format_exc().rstrip())
                self.logger.error(exception_info)
                with open('problem desc.txt', 'a', encoding='ascii') as fp:
                    if fp.tell():
                        fp.write('\n')
                    fp.write(exception_info)

            if self.separate_from_parent:
                if os.path.isfile('problem desc.txt'):
                    core.utils.report(self.logger,
                                      'unknown',
                                      {
                                          'id': 'unknown',
                                          'parent id': self.id,
                                          'problem desc': 'problem desc.txt',
                                          'files': ['problem desc.txt']
                                      },
                                      self.mqs['report files'],
                                      self.conf['main working directory'])

                self.logger.info('Terminate child resources message queue')
                self.mqs['child resources'].put(None)

                all_child_resources = {}
                while True:
                    child_resources = self.mqs['child resources'].get()

                    if child_resources is None:
                        self.logger.debug('Child resources message queue was terminated')
                        self.mqs['child resources'].close()
                        break

                    all_child_resources.update(child_resources)

                core.utils.report(self.logger,
                                  'finish',
                                  {
                                      'id': self.id,
                                      'resources': core.utils.count_consumed_resources(
                                          self.logger,
                                          self.start_time,
                                          self.include_child_resources,
                                          all_child_resources),
                                      'desc': 'desc.txt' if os.path.isfile('desc.txt') else '',
                                      'log': 'log',
                                      'data': '',
                                      'files': (['desc.txt'] if os.path.isfile('desc.txt') else []) + ['log']
                                  },
                                  self.mqs['report files'],
                                  self.conf['main working directory'])
            else:
                self.mqs['child resources'].put(
                    {self.name: core.utils.count_consumed_resources(self.logger, self.start_time,
                                                                    self.include_child_resources)})

            if sys.exc_info()[0]:
                # Treat component stopping as normal termination.
                if sys.exc_info()[0] == ComponentStopped:
                    exit(0)
                else:
                    exit(1)

    def __get_subcomponent_name(self):
        return '' if self.separate_from_parent else '[{0}] '.format(self.name)

    def stop(self):
        self.logger.info('Stop component "{0}"'.format(self.name))

        # We need to send some signal to do interrupt execution of component. Otherwise it will continue its execution.
        os.kill(self.pid, signal.SIGUSR1)

        self.join(None, True)

    def __stop(self, signum, frame):
        self.logger.debug('Stop all children')
        # TODO: LKVOG uses Manager that is separate unnamed process.
        for child in multiprocessing.active_children():
            os.kill(child.pid, signal.SIGUSR1)
            child.join()

        self.logger.error('{0}Stop since some other component(s) likely failed'.format(self.__get_subcomponent_name()))

        with open('problem desc.txt', 'a', encoding='ascii') as fp:
            if fp.tell():
                fp.write('\n')
            fp.write(
                '{0}Stop since some other component(s) likely failed'.format(self.__get_subcomponent_name(), self.name))

        raise ComponentStopped

    def join(self, timeout=None, stopped=False):
        # Actually join process.
        multiprocessing.Process.join(self, timeout)

        if stopped:
            self.logger.debug('Do not panic since component "{0}" was stopped by us'.format(self.name))
            return 0

        # Examine component exit code in parent process.
        if self.exitcode:
            self.logger.warning('Component "{0}" exitted with "{1}"'.format(self.name, self.exitcode))
            raise ComponentError('Component "{0}" failed'.format(self.name))

    # TODO: very close to code in core/__init__.py. Maybe join them.
    def launch_subcomponents(self, subcomponents):
        subcomponent_processes = []
        try:
            for subcomponent in subcomponents:
                subcomponent_class = types.new_class(
                    ''.join(re.findall(r'_(.)', subcomponent.__name__)).upper() + subcomponent.__name__[0].upper(),
                    (self.__class__,))
                setattr(subcomponent_class, 'main', subcomponent)
                # Do not try to separate these subcomponents from their parents - it is a true headache.
                # We always include child resources into resources of these components since otherwise they will
                # disappear from resources statistics.
                p = subcomponent_class(self.conf, self.logger, self.id, self.callbacks, self.mqs,
                                       include_child_resources=True)
                p.start()
                subcomponent_processes.append(p)

            self.logger.info('Wait for subcomponents')
            while True:
                operating_subcomponents_num = 0

                for p in subcomponent_processes:
                    p.join(1.0 / len(subcomponent_processes))
                    operating_subcomponents_num += p.is_alive()

                if not operating_subcomponents_num:
                    break
        finally:
            for p in subcomponent_processes:
                if p.is_alive():
                    p.stop()
