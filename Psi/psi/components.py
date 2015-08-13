import io
import multiprocessing
import os
import signal
import subprocess
import sys
import time
import traceback

import psi.utils


class PsiComponentError(ChildProcessError):
    pass


class _PsiComponentBase(multiprocessing.Process):
    def __init__(self, component, conf, logger, reports_mq=None):
        # Actually initialize process.
        multiprocessing.Process.__init__(self)

        # Component configuration.
        self.conf = conf
        # Parent logger will be used untill component will change working directory and get its own logger. We should
        # avoid to use parent logger in component process.
        self.logger = logger
        # Reports MQ.
        self.reports_mq = reports_mq

        # Use component specific name if defined. Otherwise multiprocessing.Process will use some artificial name.
        if hasattr(component, 'name'):
            self.name = component.name
        else:
            self.logger.warning('Component "{0}" does not specify its name via value of global variable "name"'.format(
                component.__package__))

        # Component working directory.
        self.work_dir = self.name.lower()

        # Component start time.
        self.start_time = 0
        # Information on component exception.
        self.exception_info = None
        # Whether component was terminated by us.
        self.terminated = None

    def join(self, timeout=None):
        # Actually join process.
        multiprocessing.Process.join(self, timeout)

        if self.terminated:
            self.logger.debug('Do not panic since component "{0}" was terminated by us'.format(self.name))
            return 0

        # Examine component exit code in parent process.
        if self.exitcode:
            self.logger.error('Component "{0}" exitted with "{1}"'.format(self.name, self.exitcode))
            raise PsiComponentError('Component "{0}" failed'.format(self.name))

    def run(self):
        # Change working directory in child process.
        os.chdir(self.work_dir)
        # Get component specific logger.
        self.logger = psi.utils.get_logger(self.name, self.conf['logging'])

    def start(self):
        # Component working directory will be created in parent process.
        if not os.path.isdir(self.work_dir):
            self.logger.info(
                'Create working directory "{0}" for component "{1}"'.format(self.work_dir, self.name))
            os.makedirs(self.work_dir)

        self.logger.info('Change working directory to "{0}" for component "{1}"'.format(self.work_dir, self.name))

        # Actually start process.
        multiprocessing.Process.start(self)

    def terminate(self):
        self.terminated = True

        self.logger.info('Terminate component "{0}"'.format(self.name))

        # Actually terminate process.
        multiprocessing.Process.terminate(self)


class PsiComponentCallbacksBase(_PsiComponentBase):
    def run(self):
        _PsiComponentBase.run(self)

        # Try to get component specific callbacks.
        if hasattr(self.__class__, 'get_callbacks') and callable(getattr(self.__class__, 'get_callbacks')):
            # Catch all exceptions to print them to logs.
            try:
                self.get_callbacks()
            except Exception:
                self.logger.exception('Raised exception:')
                exit(1)
        else:
            self.logger.info('Have not any callbacks yet')


class PsiComponentBase(_PsiComponentBase):
    def run(self):
        # Remember approximate time of start to count wall time.
        self.start_time = time.time()

        # Specially process SIGTERM since it can be sent by parent when some other component(s) failed. Official
        # documentation says that exit handlers and finally clauses, etc., will not be executed. But we still need
        # to count consumed resources and create finish report - all this is done in self.__finalize().
        signal.signal(signal.SIGTERM, self.__finalize)

        _PsiComponentBase.run(self)

        start_report_file = psi.utils.dump_report(self.logger, 'start',
                                                  {'id': self.name, 'parent id': '/', 'name': self.name})
        self.reports_mq.put(os.path.relpath(start_report_file, self.conf['root id']))


        # Try to launch component. Catch all exceptions to print information on them to logs (without this
        # multiprocessing will print information on exceptions to STDERR).
        try:
            self.launch()
        except Exception:
            self.exception_info = traceback.format_exc().rstrip()
            exit(1)
        finally:
            self.__finalize()

    def __finalize(self, signum=None, frame=None):
        # If component didn't raise exception but exitted abnormally (that assumes special SystemExit exception).
        if not self.exception_info and sys.exc_info()[0]:
            self.exception_info = traceback.format_exc().rstrip()

        # Print information on exception to logs.
        if self.exception_info:
            self.logger.error('Raised exception:\n{0}'.format(self.exception_info))
        # Print information on termination to logs.
        elif signum == signal.SIGTERM:
            self.logger.error('Terminated since some other component(s) likely failed')

        # Either use problem decription provided by component or create it by filling with information on raised
        # exception including abnormal exitting or with note that component was terminated.
        if not os.path.isfile('problem desc') and self.exception_info or signum == signal.SIGTERM:
            with open('problem desc', 'w') as fp:
                if self.exception_info:
                    fp.write(self.exception_info)
                elif signum == signal.SIGTERM:
                    fp.write('Terminated since some other component(s) likely failed')

        if os.path.isfile('problem desc'):
            with open('problem desc') as fp:
                unknown_report_file = psi.utils.dump_report(self.logger, 'unknown',
                                                            {'id': 'unknown', 'parent id': self.name,
                                                             'problem desc': fp.read()})
                self.reports_mq.put(os.path.relpath(unknown_report_file, self.conf['root id']))

        with open('desc') if os.path.isfile('desc') else io.StringIO('') as desc_fp:
            with open('log') as log_fp:
                finish_report_file = psi.utils.dump_report(self.logger, 'finish',
                                                           {'id': self.name,
                                                            'resources': psi.utils.count_consumed_resources(
                                                                self.logger,
                                                                self.start_time),
                                                            'desc': desc_fp.read(),
                                                            'log': log_fp.read(),
                                                            'data': ''})
                self.reports_mq.put(os.path.relpath(finish_report_file, self.conf['root id']))

        # Don't forget to terminate itself if somebody tries to do such.
        if signum:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            os.kill(self.pid, signal.SIGTERM)


# TODO: it is necessary to disable simultaneous execution of several components since their outputs and consumed resources will be intermixed.
# TODO: count resources consumed by the component and either create a component start and finish report with these resoruces or "add" them to parent resources.
class Component:
    def __init__(self, logger, cmd, timeout=0.5):
        self.logger = logger
        self.cmd = cmd
        self.timeout = timeout
        self.stdout = []
        self.stderr = []

    def start(self):
        self.logger.debug('Execute "{0}"'.format(self.cmd))

        p = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Print to logs everything that is printed to STDOUT and STDERR each self.timeout seconds.
        while p.poll() is None:
            for stream in (('STDOUT', p.stdout, self.stdout), ('STDERR', p.stderr, self.stderr)):
                output = [line.decode('utf8').rstrip() for line in stream[1]]
                stream[2].extend(output)
                if output:
                    self.logger.debug('"{0}" outputted to {1}:\n{2}'.format(self.cmd[0], stream[0], '\n'.join(output)))
            time.sleep(self.timeout)
