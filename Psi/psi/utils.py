import fcntl
import json
import logging
import os
import re
import resource
import subprocess
import sys
import threading
import time
import queue

_callback_kinds = ('before', 'instead', 'after')


# Based on https://pypi.python.org/pypi/filelock/.
class LockedOpen(object):
    def __init__(self, file, *args, **kwargs):
        self.file = file
        self.args = args
        self.kwargs = kwargs

        self.lock_file = '{0}.lock'.format(self.file)
        self.lock_file_descriptor = None
        self.file_descriptor = None

    def __enter__(self):
        # Ensure that specified file is opened exclusively.
        while True:
            self.lock_file_descriptor = os.open(self.lock_file, os.O_RDWR | os.O_CREAT | os.O_TRUNC)
            try:
                fcntl.flock(self.lock_file_descriptor, fcntl.LOCK_EX)
            except (IOError, OSError):
                os.close(self.lock_file_descriptor)
                continue
            else:
                self.file_descriptor = open(self.file, *self.args, **self.kwargs)
                return self.file_descriptor

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.file_descriptor.flush()
        self.file_descriptor.close()
        fcntl.flock(self.lock_file_descriptor, fcntl.LOCK_UN)
        os.close(self.lock_file_descriptor)
        try:
            os.remove(self.lock_file)
        except OSError:
            pass


def count_consumed_resources(logger, start_time, include_child_resources=False, child_resources=None):
    """
    Count resources (wall time, CPU time and maximum memory size) consumed by the process without its childred.
    Note that launching under PyCharm gives its maximum memory size rather than the process one.
    :return: resources.
    """
    logger.debug('Count consumed resources')

    assert not (include_child_resources and child_resources), \
        'Do not calculate resources of process with children and simultaneosly provide resources of children'

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
            utime += child_resources[child]['CPU time'] / 1000
            maxrss = max(maxrss, child_resources[child]['max mem size'] / 1000)
            # Wall time of children is included in wall time of their parent.

    resources = {'wall time': round(1000 * (time.time() - start_time)),
                 'CPU time': round(1000 * (utime + stime)),
                 'max mem size': 1000 * maxrss}

    logger.debug('Consumed the following resources:\n%s',
                 '\n'.join(['    {0} - {1}'.format(res, resources[res]) for res in sorted(resources)]))

    return resources


class CommandError(ChildProcessError):
    pass


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


def execute(logger, args, env=None, cwd=None, timeout=0.5, collect_all_stdout=False):
    cmd = args[0]
    logger.debug('Execute "{0}{1}{2}"'.format(cmd,
                                              '' if len(args) == 1 else ' ',
                                              ' '.join('"{0}"'.format(arg) for arg in args[1:])))

    p = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)

    out_q, err_q = (StreamQueue(p.stdout, 'STDOUT', collect_all_stdout), StreamQueue(p.stderr, 'STDERR', True))

    for stream_q in (out_q, err_q):
        stream_q.start()

    # Print to logs everything that is printed to STDOUT and STDERR each timeout seconds. Last try is required to
    # print last messages queued before command finishes.
    last_try = True
    while not out_q.finished or not err_q.finished or last_try:
        last_try = not out_q.finished or not err_q.finished
        time.sleep(timeout)

        for stream_q in (out_q, err_q):
            output = []
            while True:
                line = stream_q.get()
                if line is None:
                    break
                output.append(line)
            if output:
                m = '"{0}" outputted to {1}:\n{2}'.format(cmd, stream_q.stream_name, '\n'.join(output))
                if stream_q is out_q:
                    logger.debug(m)
                else:
                    logger.warning(m)

    for stream_q in (out_q, err_q):
        stream_q.join()

    if p.poll():
        logger.error('"{0}" exitted with "{1}"'.format(cmd, p.poll()))
        raise CommandError('"{0}" failed'.format(cmd))

    return out_q.output


def find_file_or_dir(logger, root_id, file_or_dir):
    search_dirs = tuple(
        os.path.relpath(os.path.join(root_id, search_dir)) for search_dir in ('job/root', os.path.pardir))

    for search_dir in search_dirs:
        found_file_or_dir = os.path.join(search_dir, file_or_dir)
        if os.path.isfile(found_file_or_dir):
            logger.debug('Find file "{0}" in directory "{1}"'.format(file_or_dir, search_dir))
            return found_file_or_dir
        elif os.path.isdir(found_file_or_dir):
            logger.debug('Find directory "{0}" in directory "{1}"'.format(file_or_dir, search_dir))
            return found_file_or_dir

    raise FileExistsError(
        'Could not find file or directory "{0}" in directories "{1}"'.format(file_or_dir, ', '.join(search_dirs)))


def is_src_tree_root(filenames):
    for filename in filenames:
        if filename == 'Makefile':
            return True
    return False


def get_component_callbacks(logger, components, components_conf):
    logger.info('Get callbacks for components "{0}"'.format([component.__name__ for component in components]))

    # At the beginning there is no callbacks of any kind.
    callbacks = {kind: {} for kind in _callback_kinds}

    for component in components:
        module = sys.modules[component.__module__]
        for attr in dir(module):
            for kind in _callback_kinds:
                match = re.search(r'^{0}_(.+)$'.format(kind), attr)
                if match:
                    event = match.groups()[0]
                    if event not in callbacks[kind]:
                        callbacks[kind][event] = []
                    callbacks[kind][event].append((component.__name__, getattr(module, attr)))

            # This special function implies that component has subcomponents for which callbacks should be get as well
            # using this function.
            if attr == 'get_subcomponent_callbacks':
                subcomponents_callbacks = getattr(module, attr)(components_conf, logger)

                # Merge subcomponent callbacks into component ones.
                for kind in _callback_kinds:
                    for event in subcomponents_callbacks[kind]:
                        if event not in callbacks[kind]:
                            callbacks[kind][event] = []
                        callbacks[kind][event].extend(subcomponents_callbacks[kind][event])

    return callbacks


def get_entity_val(logger, name, cmd):
    """
    Return a value of the specified entity name by executing the specified command and reading its first string
    printed to STDOUT.
    :param logger: a logger for printing debug messages.
    :param name: an entity name.
    :param cmd: a command to be executed to get an entity value.
    """
    logger.info('Get {0}'.format(name))

    val = subprocess.getoutput(cmd)

    if not val:
        raise ValueError('Could not get {0}'.format(name))

    # Convert obtained value to integer if it is represented so.
    try:
        int(val)
        val = int(val)
    except ValueError:
        pass

    # TODO: str.capitalize() capilalizes a first symbol and makes all other symbols lower.
    logger.debug('{0} is "{1}"'.format(name.capitalize(), val))

    return val


def get_logger(name, conf):
    """
    Return a logger with the specified name, creating it in accordance with the specified configuration if necessary.
    :param name: a logger name (usually it should be a name of tool that is going to use this logger, note, that
                 extensions are thrown away and name is converted to uppercase).
    :param conf: a logger configuration.
    """
    name, ext = os.path.splitext(name)
    logger = logging.getLogger(name.upper())
    # Actual levels will be set for logger handlers.
    logger.setLevel(logging.DEBUG)
    # Tool specific logger (with name equals to tool name) is more preferred then "default" logger.
    pref_logger_conf = None
    for pref_logger_conf in conf['loggers']:
        if pref_logger_conf['name'] == name:
            pref_logger_conf = pref_logger_conf
            break
        elif pref_logger_conf['name'] == 'default':
            pref_logger_conf = pref_logger_conf

    if not pref_logger_conf:
        raise KeyError(
            'Neither "default" nor tool specific logger "{0}" is specified'.format(name))

    # Set up logger handlers.
    for handler_conf in pref_logger_conf['handlers']:
        if handler_conf['name'] == 'console':
            # Always print log to STDOUT.
            handler = logging.StreamHandler(sys.stdout)
        elif handler_conf['name'] == 'file':
            # Always print log to file "log" in working directory.
            handler = logging.FileHandler('log', encoding='utf8')
        else:
            raise KeyError(
                'Handler "{0}" (logger "{1}") is not supported, please use either "console" or "file"'.format(
                    handler_conf['name'], pref_logger_conf['name']))

        # Set up handler logging level.
        log_levels = {'NOTSET': logging.NOTSET, 'DEBUG': logging.DEBUG, 'INFO': logging.INFO,
                      'WARNING': logging.WARNING, 'ERROR': logging.ERROR, 'CRITICAL': logging.CRITICAL}
        if not handler_conf['level'] in log_levels:
            raise KeyError(
                'Logging level "{0}" {1} is not supported{2}'.format(
                    handler_conf['level'],
                    '(logger "{0}", handler "{1}")'.format(pref_logger_conf['name'], handler_conf['name']),
                    ', please use one of the following logging levels: "{0}"'.format(
                        '", "'.join(log_levels.keys()))))

        handler.setLevel(log_levels[handler_conf['level']])

        # Find and set up handler formatter.
        formatter = None
        for formatter_conf in conf['formatters']:
            if formatter_conf['name'] == handler_conf['formatter']:
                formatter = logging.Formatter(formatter_conf['value'], "%Y-%m-%d %H:%M:%S")
                break
        if not formatter:
            raise KeyError('Handler "{0}" references undefined formatter "{1}"'.format(handler_conf['name'],
                                                                                       handler_conf['formatter']))
        handler.setFormatter(formatter)

        logger.addHandler(handler)

    logger.debug("Logger was set up")

    return logger


def get_parallel_threads_num(logger, conf, action):
    logger.info('Get the number of parallel threads for "{0}"'.format(action))

    raw_parallel_threads_num = conf['parallelism'][action]

    # In case of integer number it is already the number of parallel threads.
    if isinstance(raw_parallel_threads_num, int):
        parallel_threads_num = raw_parallel_threads_num
    # In case of decimal number it is fraction of the number of CPUs.
    elif isinstance(raw_parallel_threads_num, float):
        parallel_threads_num = conf['sys']['CPUs num'] * raw_parallel_threads_num
    else:
        raise ValueError(
            'The number of parallel threads ("{0}") for "{1}" is neither integer nor decimal number'.format(
                raw_parallel_threads_num, action))

    parallel_threads_num = int(parallel_threads_num)

    if parallel_threads_num < 1:
        raise ValueError('The computed number of parallel threads ("{0}") for "{1}" is less than 1'.format(
            parallel_threads_num, action))
    elif parallel_threads_num > 2 * conf['sys']['CPUs num']:
        raise ValueError(
            'The computed number of parallel threads ("{0}") for "{1}" is greater than the double number of CPUs'.format(
                parallel_threads_num, action))

    logger.debug('The number of parallel threads for "{0}" is "{1}"'.format(action, parallel_threads_num))

    return parallel_threads_num


def invoke_callbacks(event, args=None):
    name = event.__name__
    logger = event.__self__.logger
    callbacks = event.__self__.callbacks
    context = event.__self__
    ret = None

    for kind in _callback_kinds:
        # Invoke callbacks if so.
        if name in callbacks[kind]:
            for component, callback in callbacks[kind][name]:
                logger.debug('Invoke {0} callback of component "{1}" for "{2}"'.format(kind, component, name))
                ret = callback(context)
        # Invoke event itself.
        elif kind == 'instead':
            if args:
                ret = event(*args)
            else:
                ret = event()

    # Return what event or instead/after callbacks returned.
    return ret


def report(logger, type, report, mq=None, dir=None, suffix=None):
    logger.debug('Create {0} report'.format(type))

    # Specify report type.
    report.update({'type': type})

    # Create report file in current working directory.
    report_file = '{0}{1} report.json'.format(type, suffix or '')
    rel_report_file = os.path.relpath(report_file, dir) if dir else report_file
    if os.path.isfile(report_file):
        raise FileExistsError('Report file "{0}" already exists'.format(rel_report_file))
    with open(report_file, 'w') as fp:
        json.dump(report, fp, sort_keys=True, indent=4)

    logger.debug('{0} report was dumped to file "{1}"'.format(type.capitalize(), rel_report_file))

    # Put report to message queue if it is specified.
    if mq:
        mq.put(rel_report_file)

    return report_file
