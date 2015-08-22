import multiprocessing
import os
import signal
import subprocess
import sys
import time
import threading
import traceback
import queue

import psi.utils


class PsiComponentError(ChildProcessError):
    pass


class _PsiComponentBase(multiprocessing.Process):
    def __init__(self, component, conf, logger, mqs=None):
        # Actually initialize process.
        multiprocessing.Process.__init__(self)

        # Component configuration.
        self.conf = conf
        # Parent logger will be used untill component will change working directory and get its own logger. We should
        # avoid to use parent logger in component process.
        self.logger = logger
        # MQs.
        self.mqs = mqs

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

        psi.utils.report(self.logger,
                         'start',
                         {'id': self.name,
                          'parent id': '/',
                          'name': self.name},
                         self.mqs['report files'],
                         self.conf['root id'])

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
            psi.utils.report(self.logger,
                             'unknown',
                             {'id': 'unknown',
                              'parent id': self.name,
                              'problem desc': '__file:problem desc'},
                             self.mqs['report files'],
                             self.conf['root id'])

        psi.utils.report(self.logger,
                         'finish',
                         {'id': self.name,
                          'resources': psi.utils.count_consumed_resources(
                              self.logger,
                              self.start_time),
                          'desc': '__file:desc',
                          'log': '__file:log',
                          'data': ''},
                         self.mqs['report files'],
                         self.conf['root id'])

        # Don't forget to terminate itself if somebody tries to do such.
        if signum:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            os.kill(self.pid, signal.SIGTERM)


class AuxPsiComponentError(ChildProcessError):
    pass


# TODO: very close to _PsiComponentBase. Maybe join them together.
class AuxPsiComponent(multiprocessing.Process):
    def __init__(self, func, logger):
        multiprocessing.Process.__init__(self, target=func)

        self.func = func
        self.logger = logger

        self.name = func.__name__
        self.exception_info = None
        self.terminated = None

    def join(self, timeout=None):
        multiprocessing.Process.join(self, timeout)

        if self.terminated:
            self.logger.debug('Do not panic since "{0}" was terminated by us'.format(self.name))
            return 0

        if self.exitcode:
            self.logger.error('"{0}" exitted with "{1}"'.format(self.name, self.exitcode))
            raise AuxPsiComponentError('"{0}" failed'.format(self.name))

    def run(self):
        signal.signal(signal.SIGTERM, self.__finalize)

        try:
            self.func()
        except Exception:
            self.exception_info = traceback.format_exc().rstrip()
            exit(1)
        finally:
            self.__finalize()

    def __finalize(self, signum=None, frame=None):
        if not self.exception_info and sys.exc_info()[0]:
            self.exception_info = traceback.format_exc().rstrip()

        if self.exception_info:
            self.logger.error('"{0}" raised exception:\n{1}'.format(self.name, self.exception_info))
        elif signum == signal.SIGTERM:
            self.logger.error(
                '"{0}" was terminated since some other auxiliary component(s) likely failed'.format(self.name))

        if not os.path.isfile('problem desc') and self.exception_info or signum == signal.SIGTERM:
            with open('problem desc', 'a') as fp:
                if self.exception_info:
                    fp.write(self.exception_info)
                elif signum == signal.SIGTERM:
                    fp.write(
                        '"{0}" was terminated since some other auxiliary component(s) likely failed'.format(self.name))

        if signum:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            os.kill(self.pid, signal.SIGTERM)

    def terminate(self):
        self.terminated = True

        self.logger.info('Terminate "{0}"'.format(self.name))

        multiprocessing.Process.terminate(self)


# TODO: very close to code in Psi. Maybe join them.
def launch_in_parrallel(logger, funcs):
    processes = []
    try:
        for func in funcs:
            p = AuxPsiComponent(func, logger)
            p.start()
            processes.append(p)

        logger.info('Wait for auxiliary components')
        while True:
            operating_components_num = 0

            for p in processes:
                p.join(1.0 / len(processes))
                operating_components_num += p.is_alive()

            if not operating_components_num:
                break
    finally:
        for p in processes:
            if p.is_alive():
                p.terminate()
                p.join()


class ComponentError(ChildProcessError):
    pass


# TODO: it is necessary to disable simultaneous execution of several components since their outputs and consumed resources will be intermixed.
# TODO: count resources consumed by the component and either create a component start and finish report with these resoruces or "add" them to parent resources.
class Component:
    def __init__(self, logger, cmd, env=None, timeout=0.5, collect_all_stdout=False):
        self.logger = logger
        self.cmd = cmd
        self.env = env
        self.timeout = timeout
        self.collect_all_stdout = collect_all_stdout
        self.stdout = []
        self.stderr = []

    def start(self):
        self.logger.info('Execute "{0}"'.format(self.cmd))

        p = subprocess.Popen(self.cmd, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        out_q, err_q = (StreamQueue(p.stdout, 'STDOUT', self.collect_all_stdout), StreamQueue(p.stderr, 'STDERR', True))

        for stream_q in (out_q, err_q):
            stream_q.start()

        # Print to logs everything that is printed to STDOUT and STDERR each self.timeout seconds.
        while not out_q.finished or not err_q.finished:
            time.sleep(self.timeout)

            for stream_q in (out_q, err_q):
                output = []
                while True:
                    line = stream_q.get()
                    if line is None:
                        break
                    output.append(line)
                if output:
                    m = '"{0}" outputted to {1}:\n{2}'.format(self.cmd[0], stream_q.stream_name, '\n'.join(output))
                    if stream_q is out_q:
                        self.logger.debug(m)
                    else:
                        self.logger.warning(m)

        if self.collect_all_stdout:
            self.stdout = out_q.output

        self.stderr = err_q.output

        for stream_q in (out_q, err_q):
            stream_q.join()

        if p.poll():
            self.logger.error('"{0}" exitted with "{1}"'.format(self.cmd[0], p.poll()))
            raise ComponentError('"{0}" failed'.format(self.cmd[0]))


class StreamQueue:
    def __init__(self, stream, stream_name, collect_all_output=False):
        self.stream = stream
        self.stream_name = stream_name
        self.collect_all_output = collect_all_output
        self.queue = queue.Queue()
        self.finished = False
        self.thread = threading.Thread(target=self.__put_lines_from_stream_to_queue)
        self.output = []

    def get(self):
        try:
            return self.queue.get_nowait()
        except queue.Empty:
            return None

    def join(self):
        self.thread.join()

    def start(self):
        self.thread.start()

    def __put_lines_from_stream_to_queue(self):
        # This will put lines from stream to queue until stream will be closed. For instance it will happen when
        # execution of command will be completed.
        for line in self.stream:
            line = line.decode('utf8').rstrip()
            self.queue.put(line)
            if self.collect_all_output:
                self.output.append(line)

        # Nothing will be put to queue from now.
        self.finished = True
