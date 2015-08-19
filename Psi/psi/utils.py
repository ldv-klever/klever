import fcntl
import json
import logging
import os.path
import resource
import subprocess
import sys
import time


# Based on http://blog.gocept.com/2013/07/15/reliable-file-updates-with-python/.
class LockedOpen(object):
    def __init__(self, name, *args, **kwargs):
        self.name = name
        self.args = args
        self.kwargs = kwargs

        self.fp = None

    def __enter__(self):
        fp = open(self.name, *self.args, **self.kwargs)

        while True:
            fcntl.flock(fp, fcntl.LOCK_EX)

            fp_new = open(self.name, *self.args, **self.kwargs)

            # Other process didn't modify file between we open and lock it. So we can safely use created file stream.
            if os.path.sameopenfile(fp.fileno(), fp_new.fileno()):
                fp_new.close()
                break
            # Otherwise we need to reopen file.
            else:
                fp.close()
                fp = fp_new

        self.fp = fp

        return fp

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.fp.flush()
        self.fp.close()


def count_consumed_resources(logger, start_time):
    """
    Count resources (wall time, CPU time and maximum memory size) consumed by the process without its childred.
    Note that launching under PyCharm gives its maximum memory size rather than the process one.
    :return: resources.
    """
    logger.info('Count consumed resources')

    utime, stime, maxrss = resource.getrusage(resource.RUSAGE_SELF)[0:3]
    resources = {'wall time': round(100 * (time.time() - start_time)),
                 'CPU time': round(100 * (utime + stime)),
                 'max mem size': 1000 * maxrss}

    logger.debug('Consumed the following resources:\n%s',
                 '\n'.join(['    {0} - {1}'.format(res, resources[res]) for res in sorted(resources)]))

    return resources


def dump_report(logger, kind, report, suffix=''):
    """
    Dump the specified report of the specified kind to a file.
    :param logger: a logger for printing debug messages.
    :param kind: a report kind (a file where a report will be dumped will be named "kind report.json").
    :param report: a report object (usually it should be a dictionary).
    """
    logger.info('Dump {0} report'.format(kind))

    report_file = '{0}{1} report.json'.format(kind, suffix)
    if os.path.isfile(report_file):
        raise FileExistsError('Report file "{0}" already exists'.format(os.path.abspath(report_file)))

    # Specify report type.
    report.update({'type': kind})

    with open(report_file, 'w') as fp:
        json.dump(report, fp, sort_keys=True, indent=4)

    logger.debug('{0} report was dumped to file "{1}"'.format(kind.capitalize(), report_file))

    return report_file


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


def get_comp_desc(logger):
    """
    Return a given computer description (a node name, a CPU model, a number of CPUs, a memory size, a Linux kernel
    version and an architecture).
    :param logger: a logger for printing debug messages.
    """
    logger.info('Get computer description')

    return [{entity_name_cmd[0]: get_entity_val(logger,
                                                entity_name_cmd[1] if entity_name_cmd[1] else entity_name_cmd[0],
                                                entity_name_cmd[2])} for entity_name_cmd in
            [['node name', '', 'uname -n'],
             ['CPU model', '', 'cat /proc/cpuinfo | grep -m1 "model name" | sed -r "s/^.*: //"'],
             ['CPUs num', 'number of CPUs', 'cat /proc/cpuinfo | grep processor | wc -l'],
             ['mem size', 'memory size',
              'cat /proc/meminfo | grep "MemTotal" | sed -r "s/^.*: *([0-9]+).*/1024 * \\1/" | bc'],
             ['Linux kernel version', '', 'uname -r'],
             ['arch', 'architecture', 'uname -m']]]


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

    return str(parallel_threads_num)
