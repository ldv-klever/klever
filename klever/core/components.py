#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import glob
import json
import multiprocessing
import os
import shutil
import signal
import sys
import time
import traceback
import types
import resource
import re

import klever.core.utils
from klever.scheduler.schedulers.global_config import reserve_workers_cpu_cores, clear_workers_cpu_cores

CALLBACK_KINDS = ('before', 'instead', 'after')

# Generate decorators to use them across the project
for tp in CALLBACK_KINDS:
    # Access namespace of the decorated function and insert there a new one with the name like 'before_' + function_name
    def new_decorator(decorated_function, tp=tp):
        if decorated_function.__name__[0:2] != '__':
            raise ValueError("Callbacks should be private, call function {!r} with '__' prefix".
                             format(decorated_function.__name__))
        callback_function_name = "{}_{}".format(str(tp), decorated_function.__name__[2:])
        if hasattr(sys.modules[decorated_function.__module__], callback_function_name):
            raise KeyError("Cannot create callback {!r} in {!r}".
                           format(callback_function_name, decorated_function.__module__))

        setattr(sys.modules[decorated_function.__module__], callback_function_name, decorated_function)

        return decorated_function

    # Add new decorator to this module to use it
    globals()[tp + '_callback'] = new_decorator
    new_decorator = None


def set_component_callbacks(logger, component, callbacks):
    logger.info('Set callbacks for component "{0}"'.format(component.__name__))

    modl = sys.modules[component.__module__]
    for callback in callbacks:
        logger.debug('Set callback "{0}" for component "{1}"'.format(callback.__name__, component.__name__))
        if not any(callback.__name__.startswith(kind) for kind in CALLBACK_KINDS):
            raise ValueError('Callback "{0}" does not start with one of {1}'.format(callback.__name__, ', '.join(
                ('"{0}"'.format(kind) for kind in CALLBACK_KINDS))))
        if callback.__name__ in dir(modl):
            raise ValueError(
                'Callback "{0}" already exists for component "{1}"'.format(callback.__name__, component.__name__))
        setattr(modl, callback.__name__, callback)


def get_component_callbacks(logger, components):
    logger.info('Get callbacks for components "{0}"'.format([component.__name__ for component in components]))

    # At the beginning there is no callbacks of any kind.
    callbacks = {kind: {} for kind in CALLBACK_KINDS}

    for component in components:
        modl = sys.modules[component.__module__]
        for attr in dir(modl):
            for kind in CALLBACK_KINDS:
                match = re.search(r'^{0}_(.+)$'.format(kind), attr)
                if match:
                    event = match.groups()[0]
                    if event not in callbacks[kind]:
                        callbacks[kind][event] = []
                    callbacks[kind][event].append((component.__name__, getattr(modl, attr)))

    return callbacks


def remove_component_callbacks(logger, component):
    logger.info('Remove callbacks for component "{0}"'.format(component.__name__))

    modl = sys.modules[component.__module__]
    for attr in dir(modl):
        if any(attr.startswith(kind) for kind in CALLBACK_KINDS):
            delattr(modl, attr)


def all_child_resources():
    total_child_resources = {}
    for child_resources_file in glob.glob(os.path.join('child resources', '*')):
        with open(child_resources_file, encoding='utf-8') as fp:
            child_resources = json.load(fp)
        total_child_resources[
            os.path.splitext(os.path.basename(child_resources_file))[0]] = child_resources
    return total_child_resources


def count_consumed_resources(logger, start_time, include_child_resources=False, child_resources=None):
    """
    Count resources (wall time, CPU time and maximum memory size) consumed by the process without its children.
    Note that launching under PyCharm gives its maximum memory size rather than the process one.
    :return: resources.
    """
    logger.debug('Count consumed resources')

    assert not (include_child_resources and child_resources), \
        'Do not calculate resources of process with children and simultaneously provide resources of children'

    utime, stime, maxrss = resource.getrusage(resource.RUSAGE_SELF)[0:3]

    # Take into account children resources if necessary.
    if include_child_resources:
        utime_children, stime_children, maxrss_children = resource.getrusage(resource.RUSAGE_CHILDREN)[0:3]
        utime += utime_children
        stime += stime_children
        maxrss = max(maxrss, maxrss_children)
    elif child_resources:
        for child in child_resources:
            # CPU time is sum of utime and stime, so add it just one time.
            utime += child_resources[child]['cpu_time'] / 1000
            maxrss = max(maxrss, child_resources[child]['memory'] / 1000)
            # Wall time of children is included in wall time of their parent.

    resources = {
        'wall_time': round(1000 * (time.time() - start_time)),
        'cpu_time': round(1000 * (utime + stime)),
        'memory': 1000 * maxrss
    }

    logger.debug('Consumed the following resources:\n%s',
                 '\n'.join(['    {0} - {1}'.format(res, resources[res]) for res in sorted(resources)]))

    return resources


def launch_workers(logger, workers, monitoring_list=None):
    """
    Wait until all given components will finish their work. If one among them fails, terminate the rest.

    :param logger: Logger object.
    :param workers: List of Component objects.
    :param monitoring_list: List with already started Components that should be checked as other workers and if some of
                            them fails then we should also terminate the rest workers.
    :return: None
    """
    logger.info('Run {} components'.format(len(workers)))
    try:
        for w in workers:
            w.start()

        logger.info('Wait for components')
        while True:
            operating_subcomponents_num = 0

            for p in workers:
                p.join(1.0 / len(workers))
                operating_subcomponents_num += p.is_alive()
            check_components(logger, monitoring_list)

            if not operating_subcomponents_num:
                break
    finally:
        for p in workers:
            if p.is_alive():
                p.stop()
    logger.info('All components finished')


def launch_queue_workers(logger, queue, constructor, max_threads, fail_tolerant, monitoring_list=None,
                         sleep_interval=1):
    """
    Blocking function that run given number of workers processing elements of particular queue.

    :param logger: Logger object.
    :param queue: multiprocessing.Queue
    :param constructor: Function that gets element and returns Component
    :param max_threads: Max number of simultaneously running workers (may be specified as a list for different components).
    :param fail_tolerant: True if no need to stop processing on fail.
    :param monitoring_list: List with already started Components that should be checked as other workers and if some of
                            them fails then we should also terminate the rest workers.
    :param sleep_interval: Interval between workers check in seconds.
    :return: 0 if all workers finish successfully and 1 otherwise.
    """
    active = True
    elements = []
    components = []
    ret = 0
    if isinstance(max_threads, list):
        # If we specify max_threads as a list, then maximum number of parallel running threads will
        # be changed dynamically. For example, if a thread pool is used for different components,
        # its size may vary depending on which components are used. In such a case, the number
        # should be changed later during thread pool main loop iteration.
        number = max_threads[0]
        is_agile_threads = True
    else:
        number = max_threads
        is_agile_threads = False
    logger.info("Start children set with {!r} workers".format(number))
    is_limit_cores_globally = False
    try:
        while True:
            # Fetch all new elements
            if active:
                active = klever.core.utils.drain_queue(elements, queue)

            # Then run new workers
            diff = number - len(components)
            if len(components) < number and len(elements) > 0:
                logger.debug("Going to start {} new workers".format(diff))
                for _ in range(min(number - len(components), len(elements))):
                    element = elements.pop(0)
                    worker = constructor(element)
                    if isinstance(worker, Component):
                        components.append(worker)
                        if not is_limit_cores_globally and worker.name == "PLUGINS":
                            is_limit_cores_globally = True
                        worker.start()
                    else:
                        raise TypeError("Incorrect constructor, expect Component but get {}".
                                        format(type(worker).__name__))
            if is_limit_cores_globally:
                used_cores = len(components)
                reserve_workers_cpu_cores(used_cores)
                logger.debug(f"Reserve {used_cores} cores for tasks preparation")
                if is_agile_threads:
                    # Do not fail if we got list with only one element
                    if len(max_threads) >= 2:
                        number = max_threads[1]
                    is_agile_threads = False
                    logger.info("Change number of workers to {!r}".format(number))

            # Wait for components termination
            finished = 0
            # Because we use i for deletion we always delete the element near the end to not break order of
            # following of the rest unprocessed elements
            for i, p in reversed(list(enumerate(list(components)))):
                try:
                    p.join(1.0 / len(components))
                except ComponentError:
                    # Ignore or terminate the rest
                    if fail_tolerant:
                        ret = 1
                    else:
                        raise
                # If all is OK
                if not p.is_alive():
                    # Make to be sure to execute join the last time
                    try:
                        p.join()
                    except ComponentError:
                        # Ignore or terminate the rest
                        if fail_tolerant:
                            ret = 1
                        else:
                            raise

                    # Just remove it
                    components.pop(i)
                    finished += 1
            # Check additional components, actually they should not terminate or finish during this function run so
            # just check that they are OK
            check_components(logger, monitoring_list)

            if finished > 0:
                logger.debug("Finished {} workers".format(finished))

            # Check that we can quit or must wait
            if len(components) == 0 and len(elements) == 0:
                if not active:
                    break
            if len(components) >= number or len(elements) == 0:
                # sleep if thread pool is full or there are no new elements
                time.sleep(sleep_interval)
    finally:
        if is_limit_cores_globally:
            clear_workers_cpu_cores()
        for p in components:
            if p.is_alive():
                p.terminate()

    return ret


def check_components(logger, components):
    """
    Check that all given processes are alive and raise an exception if it is not so.

    :param logger: Logger Object.
    :param components: List with Component objects.
    :return: None.
    """
    # Check additional components, actually they should not terminate or finish during this function run so
    # just check that they are OK
    if isinstance(components, list):
        for mc in (m for m in components if not m.is_alive()):
            # Here we expect an exception
            logger.info("Some of the subcomponents running in the background exited: {!r}".format(mc.id))
            mc.join()


class ComponentError(ChildProcessError):
    pass


class CallbacksCaller:
    def __getattribute__(self, name):
        attr = object.__getattribute__(self, name)
        if callable(attr) and not attr.__name__.startswith('_'):
            def callbacks_caller(*args, **kwargs):
                ret = None

                for kind in CALLBACK_KINDS:
                    # Invoke callbacks if so.
                    if kind in self.callbacks and name in self.callbacks[kind]:
                        for component, callback in self.callbacks[kind][name]:
                            self.logger.debug(
                                'Invoke {0} callback of component "{1}" for "{2}"'.format(kind, component, name))
                            ret = callback(self)
                    # Invoke event itself.
                    elif kind == 'instead':
                        # Do not pass auxiliary objects created for subcomponents to methods that implement them and
                        # that are actually component object methods.
                        if args and type(args[0]).__name__.startswith('KleverSubcomponent'):
                            ret = attr(*args[1:], **kwargs)
                        else:
                            ret = attr(*args, **kwargs)

                # Return what event or instead/after callbacks returned.
                return ret

            return callbacks_caller

        return attr


class Component(multiprocessing.Process, CallbacksCaller):
    MAX_ID_LEN = 200

    def __init__(self, conf, logger, parent_id, callbacks, mqs, vals, cur_id=None, work_dir=None, attrs=None,
                 separate_from_parent=False, include_child_resources=False):
        # Actually initialize process.
        multiprocessing.Process.__init__(self)

        self.conf = conf
        # Parent logger will be used until component will change working directory and get its own logger. We should
        # avoid to use parent logger in component process.
        self.logger = logger
        self.parent_id = parent_id
        self.callbacks = callbacks
        self.mqs = mqs
        self.vals = vals
        self.attrs = attrs
        self.separate_from_parent = separate_from_parent
        self.include_child_resources = include_child_resources
        self.coverage = None

        self.name = type(self).__name__.replace('KleverSubcomponent', '')
        # Include parent identifier into the child one. This is required to distinguish reports for different sub-jobs.
        self.id = os.path.join(parent_id, cur_id if cur_id else self.name)

        # Component identifiers are used either directly or with some quite restricted suffixes as report identifiers.
        # Bridge limits the latter with 255 symbols. Unfortunately, it does not log identifiers that cause troubles.
        # Moreover, it could not point out particular places where long identifiers were created. Core can do both, but
        # unfortunately it is impossible to show corresponding exceptions in Bridge if we will raise them in
        # klever.core.utils.report(). This is the fundamental infrastructure limitation. For instance,
        # klever.core.components.launch_queue_workers ignores exception raised by workers if fail_tolerant is set to
        # true that is the case for sub-jobs and VTG workers. Also, these exception will likely happen prior start
        # reports will be uploaded, so, corresponding unknown reports will not be created as it will not be possible to
        # bind them with non-existing start reports. There will be errors in logs, but it is not convenient to
        # investigate them (though, sometimes this is the only possible way).
        # The only bad thing is that at this point we are not aware about lengths of suffixes to be used, so, if one
        # will suddenly exceed limit "255 - self.MAX_ID_LEN", there still will be an unclear failure in Bridge without
        # good unknown reports. Let's hope that this will not happen ever.
        if len(self.id) > self.MAX_ID_LEN:
            raise ValueError(
                'Too large component identifier "{0}" (current length is {1} while {2} can be used at most)'
                .format(self.id, len(self.id), self.MAX_ID_LEN))

        self.work_dir = work_dir if work_dir else self.name.lower()
        # Component start time.
        self.tasks_start_time = 0
        self.__pid = None

        self.clean_dir = False
        self.excluded_clean = []
        self._cur_dir = None

    def start(self):
        # Component working directory will be created in parent process.
        if self.separate_from_parent and not os.path.isdir(self.work_dir):
            self.logger.info(
                'Create working directory "%s" for component "%s"', self.work_dir, self.name)
            os.makedirs(self.work_dir.encode('utf-8'))

        # Actually start process.
        multiprocessing.Process.start(self)

    def main(self):
        self.logger.error('I forgot to define main function!')
        sys.exit(1)

    def run(self):
        # Remember approximate time of start to count wall time.
        self.tasks_start_time = time.time()

        # Remember component pid to distinguish it from its auxiliary subcomponents, e.g. synchronization managers,
        # later during finalization on stopping.
        self.__pid = os.getpid()

        # Specially process SIGUSR1 since it can be sent by parent when some other component(s) failed. Counting
        # consumed resources and creating reports will be performed in self.__finalize() both when components terminate
        # normally and are stopped.
        signal.signal(signal.SIGUSR1, self.__stop)

        if self.separate_from_parent:
            self.logger.info('Change working directory to "%s" for component "%s"', self.work_dir, self.name)
            # dir restore
            self._cur_dir = os.getcwd()
            os.chdir(self.work_dir)

        # Try to launch component.
        exception = False
        try:
            # Get component specific logger.
            self.logger = klever.core.utils.get_logger(self.name, self.conf['logging'])
            if self.separate_from_parent:
                # Create special directory where child resources of processes separated from parents will be printed.
                self.logger.info('Create child resources directory "child resources"')
                os.makedirs('child resources'.encode('utf-8'))

                report = {
                    'identifier': self.id,
                    'parent': self.parent_id,
                    'component': self.name
                }
                if self.attrs:
                    report.update({'attrs': self.attrs})
                klever.core.utils.report(self.logger, 'start', report, self.mqs['report files'], self.vals['report id'],
                                         self.conf['main working directory'])

            self.main()
        except Exception:  # pylint: disable=broad-exception-caught
            exception = True

            # Print information on exception to logs and as problem description.
            exception_info = '{0}Raise exception:\n{1}'.format(self.__get_subcomponent_name(),
                                                               traceback.format_exc().rstrip())
            self.logger.error(exception_info)
            with open('problem desc.txt', 'a', encoding='utf-8') as fp:
                if fp.tell():
                    fp.write('\n')
                fp.write(exception_info)
        finally:
            self.__finalize(exception=exception)

    def __finalize(self, exception=False):
        # Like in Core at least print information about unexpected exceptions in code below and properly exit.
        try:
            if self.separate_from_parent and self.__pid == os.getpid():
                if os.path.isfile('problem desc.txt'):
                    klever.core.utils.report(
                        self.logger,
                        'unknown',
                        {
                            'identifier': self.id + '/',
                            'parent': self.id,
                            'problem_description': klever.core.utils.ArchiveFiles(['problem desc.txt'])
                        },
                        self.mqs['report files'],
                        self.vals['report id'],
                        self.conf['main working directory']
                    )

                child_resources = all_child_resources()
                report = {'identifier': self.id}
                report.update(count_consumed_resources(self.logger, self.tasks_start_time, self.include_child_resources,
                                                       child_resources))
                # todo: this is embarrassing
                if self.coverage:
                    report['coverage'] = self.coverage

                if os.path.isfile('log.txt') and self.conf['weight'] == "0":
                    report['log'] = klever.core.utils.ArchiveFiles(['log.txt'])

                klever.core.utils.report(self.logger, 'finish', report, self.mqs['report files'],
                                         self.vals['report id'], self.conf['main working directory'])
            else:
                with open(os.path.join('child resources', self.name + '.json'), 'w', encoding='utf-8') as fp:
                    klever.core.utils.json_dump(count_consumed_resources(self.logger, self.tasks_start_time,
                                                                         self.include_child_resources),
                                                fp, self.conf['keep intermediate files'])
        except Exception:  # pylint: disable=broad-exception-caught
            exception = True
            self.logger.exception('Catch exception')
        finally:
            # Clean dir if needed
            if self.clean_dir and not self.conf['keep intermediate files']:
                self.logger.debug('Going to clean %s', os.path.abspath('.'))
                for to_del in os.listdir('.'):
                    if to_del in self.excluded_clean:
                        continue
                    if os.path.isfile(to_del) or os.path.islink(to_del):
                        os.remove(to_del)
                    elif os.path.isdir(to_del):
                        shutil.rmtree(to_del)
            if self._cur_dir:
                # restore dir
                os.chdir(self._cur_dir)
            if exception:
                raise klever.core.components.ComponentError

    def __get_subcomponent_name(self):
        return '' if self.separate_from_parent else '[{0}] '.format(self.name)

    def stop(self):
        self.logger.info('Stop component "%s"', self.name)

        # We need to send some signal to do interrupt execution of component. Otherwise it will continue its execution.
        os.kill(self.pid, signal.SIGUSR1)

        self.join(stopped=True)

    def __stop(self, signum, frame):  # pylint:disable=unused-argument
        self.logger.info('%s Stop all children', self.__get_subcomponent_name())
        for child in multiprocessing.active_children():
            self.logger.info('%s Stop child "%s"', self.__get_subcomponent_name(), child.name)
            os.kill(child.pid, signal.SIGUSR1)
            # Such the errors can happen here most likely just when unexpected exceptions happen when exiting
            # component. These exceptions are likely printed to logs but don't become unknown reports. In addition
            # finish reports including these logs aren't created. So they are invisible for the most of users
            # unfortunately. Nonetheless advanced users will examine logs manually when they will see status Corrupted
            # that will be set because of absence of finish reports.
            try:
                child.join()
            except ComponentError:
                pass

        self.logger.error('%s Stop since some other component(s) likely failed', self.__get_subcomponent_name())

        self.__finalize()

    def join(self, timeout=None, stopped=False):
        # Actually join process.
        multiprocessing.Process.join(self, timeout)

        if stopped:
            self.logger.debug('Do not panic since component "%s" was stopped by us', self.name)
            return 0

        # Examine component exit code in parent process.
        if self.exitcode:
            self.logger.warning('Component "%s" exited with "%s"', self.name, self.exitcode)
            raise ComponentError('Component "{0}" failed'.format(self.name))

        return 0

    def dump_if_necessary(self, file_name, data, desc):
        if self.conf['keep intermediate files']:
            self.logger.debug('Put "%s" to file %s', desc, file_name)
            with open(file_name, 'w', encoding='utf-8') as fp:
                klever.core.utils.json_dump(data, fp, self.conf['keep intermediate files'])

    def function_to_subcomponent(self, include_child_resources, name, executable):
        """
        Convert given function or component into Component to run it as a subcomponent.

        :param include_child_resources: Flag.
        :param name: Component name string.
        :param executable: Function or Class.
        :return: Component
        """
        if isinstance(executable, (types.MethodType, types.FunctionType)):
            subcomponent_class = types.new_class(name, (type(self),))
            setattr(subcomponent_class, 'main', executable)
        else:
            subcomponent_class = types.new_class(name, (executable,))
        p = subcomponent_class(self.conf, self.logger, self.id, self.callbacks, self.mqs, self.vals,
                               separate_from_parent=False, include_child_resources=include_child_resources)
        return p

    def launch_subcomponents(self, include_child_resources, *subcomponents):
        subcomponent_processes = []
        for index, subcomponent in enumerate(subcomponents):
            # Do not try to separate these subcomponents from their parents - it is a true headache.
            # We always include child resources into resources of these components since otherwise they will
            # disappear from resources statistics.
            if isinstance(subcomponent, (list, tuple)):
                name = 'KleverSubcomponent' + subcomponent[0] + str(index)
                executable = subcomponent[1]
            else:
                name = 'KleverSubcomponent' + str(subcomponent.__name__) + str(index)
                executable = subcomponent
            p = self.function_to_subcomponent(include_child_resources, name, executable)
            subcomponent_processes.append(p)
        # Wait for their termination
        launch_workers(self.logger, subcomponent_processes)
