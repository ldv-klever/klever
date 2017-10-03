#
# Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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

import fcntl
import json
import logging
import os
import re
import resource
import subprocess
import sys
import zipfile
import threading
import time
import queue
import hashlib
import tempfile
from benchexec.runexecutor import RunExecutor

CALLBACK_KINDS = ('before', 'instead', 'after')
CALLBACK_PROPOGATOR = 'get_subcomponent_callbacks'

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
        else:
            setattr(sys.modules[decorated_function.__module__], callback_function_name, decorated_function)

        return decorated_function

    # Add new decorator to this module to use it
    globals()[tp + '_callback'] = new_decorator
    new_decorator = None


def propogate_callbacks(decorated_function):
    """
    Decorates function that propogates subcomponent callbacks. Inserts a specific function that has necessary name
    to be called at callbacks propogating.

    :param decorated_function: Function object.
    :return: The same function.
    """
    if hasattr(sys.modules[decorated_function.__module__], CALLBACK_PROPOGATOR):
        raise ValueError('Module {!r} already has callback propogating function {!r}'.
                         format(decorated_function.__module__, CALLBACK_PROPOGATOR))

    setattr(sys.modules[decorated_function.__module__], CALLBACK_PROPOGATOR, decorated_function)

    return decorated_function


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
        else:
            return attr


class Cd:
    def __init__(self, path):
        self.new_path = path

    def __enter__(self):
        self.prev_path = os.getcwd()
        os.chdir(self.new_path)

    def __exit__(self, etype, value, traceback):
        os.chdir(self.prev_path)


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
            maxrss = max(maxrss, child_resources[child]['memory size'] / 1000)
            # Wall time of children is included in wall time of their parent.

    resources = {'wall time': round(1000 * (time.time() - start_time)),
                 'CPU time': round(1000 * (utime + stime)),
                 'memory size': 1000 * maxrss}

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
        self.traceback = None
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
        try:
            # This will put lines from stream to queue until stream will be closed. For instance it will happen when
            # execution of command will be completed.
            for line in self.stream:
                line = line.decode('utf8').rstrip()
                self.queue.put(line)
                if self.collect_all_output:
                    self.output.append(line)

            # Nothing will be put to queue from now.
            self.finished = True
        except Exception:
            import traceback
            self.traceback = traceback.format_exc().rstrip()


def execute(logger, args, env=None, cwd=None, timeout=0, collect_all_stdout=False):
    cmd = args[0]
    logger.debug('Execute:\n{0}{1}{2}'.format(cmd,
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
        if out_q.traceback:
            raise RuntimeError('STDOUT reader thread failed with the following traceback:\n{0}'. format(out_q.traceback))
        if err_q.traceback:
            raise RuntimeError('STDERR reader thread failed with the following traceback:\n{0}'. format(err_q.traceback))
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
        with open('problem desc.txt', 'a', encoding='utf8') as fp:
            fp.write('\n'.join(err_q.output))
        raise CommandError('"{0}" failed'.format(cmd))

    return out_q.output


def execute_external_tool(logger, args, timelimit=450000, memlimit=300000000):
    logger.debug('Execute:\n{!r}'.format(' '.join(args)))
    executor = RunExecutor()
    result = executor.execute_run(args=args,
                                  output_filename="output.log",
                                  walltimelimit=timelimit,
                                  memlimit=memlimit,
                                  maxLogfileSize=10000000)
    exit_code = int(result["exitcode"]) % 255
    if exit_code != 0:
        os.rename("output.log", "problem desc.txt")
        raise ValueError("Tool {!r} exited with non-zero exit code: {}".format(args[0], exit_code))
    else:
        with open("output.log") as fd:
            output = fd.read()

    return output


def get_search_dirs(main_work_dir):
    search_dirs = ['job/root', os.path.pardir]
    if 'KLEVER_WORK_DIR' in os.environ:
        search_dirs.append(os.environ['KLEVER_WORK_DIR'])
    search_dirs = tuple(
        os.path.relpath(os.path.join(main_work_dir, search_dir)) for search_dir in search_dirs)
    return search_dirs


# TODO: get value of the second parameter on the basis of passed configuration. Or, even better, implement wrapper around this function in components.Component.
def find_file_or_dir(logger, main_work_dir, file_or_dir):
    search_dirs = get_search_dirs(main_work_dir)

    for search_dir in search_dirs:
        found_file_or_dir = os.path.join(search_dir, file_or_dir)
        if os.path.isfile(found_file_or_dir):
            logger.debug('Find file "{0}" in directory "{1}"'.format(file_or_dir, search_dir))
            return found_file_or_dir
        elif os.path.isdir(found_file_or_dir):
            logger.debug('Find directory "{0}" in directory "{1}"'.format(file_or_dir, search_dir))
            return found_file_or_dir

    raise FileNotFoundError(
        'Could not find file or directory "{0}" in directories "{1}"'.format(file_or_dir, ', '.join(search_dirs)))


def make_relative_path(logger, main_work_dir, abs_path_to_file_or_dir):
    search_dirs = get_search_dirs(main_work_dir)
    for search_dir in search_dirs:
        if abs_path_to_file_or_dir.startswith(os.path.abspath(search_dir)):
            return os.path.relpath(abs_path_to_file_or_dir, search_dir)
    return abs_path_to_file_or_dir


def is_src_tree_root(filenames):
    for filename in filenames:
        if filename == 'Makefile':
            return True
    return False


def set_component_callbacks(logger, component, callbacks):
    logger.info('Set callbacks for component "{0}"'.format(component.__name__))

    module = sys.modules[component.__module__]

    for callback in callbacks:
        logger.debug('Set callback "{0}" for component "{1}"'.format(callback.__name__, component.__name__))
        if not any(callback.__name__.startswith(kind) for kind in CALLBACK_KINDS):
            raise ValueError('Callback "{0}" does not start with one of {1}'.format(callback.__name__, ', '.join(
                ('"{0}"'.format(kind) for kind in CALLBACK_KINDS))))
        if callback.__name__ in dir(module):
            raise ValueError(
                'Callback "{0}" already exists for component "{1}"'.format(callback.__name__, component.__name__))
        setattr(module, callback.__name__, callback)


def get_component_callbacks(logger, components, components_conf):
    logger.info('Get callbacks for components "{0}"'.format([component.__name__ for component in components]))

    # At the beginning there is no callbacks of any kind.
    callbacks = {kind: {} for kind in CALLBACK_KINDS}

    for component in components:
        module = sys.modules[component.__module__]
        for attr in dir(module):
            for kind in CALLBACK_KINDS:
                match = re.search(r'^{0}_(.+)$'.format(kind), attr)
                if match:
                    event = match.groups()[0]
                    if event not in callbacks[kind]:
                        callbacks[kind][event] = []
                    callbacks[kind][event].append((component.__name__, getattr(module, attr)))

            # This special function implies that component has subcomponents for which callbacks should be get as well
            # using this function.
            if attr == CALLBACK_PROPOGATOR:
                subcomponents_callbacks = getattr(module, attr)(components_conf, logger)

                # Merge subcomponent callbacks into component ones.
                for kind in CALLBACK_KINDS:
                    for event in subcomponents_callbacks[kind]:
                        if event not in callbacks[kind]:
                            callbacks[kind][event] = []
                        callbacks[kind][event].extend(subcomponents_callbacks[kind][event])

    return callbacks


def remove_component_callbacks(logger, component):
    logger.info('Remove callbacks for component "{0}"'.format(component.__name__))

    module = sys.modules[component.__module__]

    for attr in dir(module):
        if any(attr.startswith(kind) for kind in CALLBACK_KINDS):
            delattr(module, attr)


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
    if val.isdigit():
        val = int(val)

    logger.debug('{0} is "{1}"'.format(name[0].upper() + name[1:], val))

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
        raise KeyError('Neither "default" nor tool specific logger "{0}" is specified'.format(name))

    # Set up logger handlers.
    if 'handlers' not in pref_logger_conf:
        raise KeyError('Handlers are not specified for logger "{0}"'.format(pref_logger_conf['name']))
    for handler_conf in pref_logger_conf['handlers']:
        if 'level' not in handler_conf:
            raise KeyError(
                'Logging level of logger "{0}" and handler "{1}" is not specified'.format(
                    pref_logger_conf['name'], handler_conf['name'] if 'name' in handler_conf else ''))

        if handler_conf['level'] == 'NONE':
            continue

        if handler_conf['name'] == 'console':
            # Always print log to STDOUT.
            handler = logging.StreamHandler(sys.stdout)
        elif handler_conf['name'] == 'file':
            # Always print log to file "log" in working directory.
            handler = logging.FileHandler('log.txt', encoding='utf8')
        else:
            raise KeyError(
                'Handler "{0}" (logger "{1}") is not supported, please use either "console" or "file"'.format(
                    handler_conf['name'], pref_logger_conf['name']))

        # Set up handler logging level.
        log_levels = {'NOTSET': logging.NOTSET, 'DEBUG': logging.DEBUG, 'INFO': logging.INFO,
                      'WARNING': logging.WARNING, 'ERROR': logging.ERROR, 'CRITICAL': logging.CRITICAL}
        if handler_conf['level'] not in log_levels:
            raise KeyError(
                'Logging level "{0}" {1} is not supported{2}'.format(
                    handler_conf['level'],
                    'of logger "{0}" and handler "{1}"'.format(pref_logger_conf['name'], handler_conf['name']),
                    ', please use one of the following logging levels: "{0}"'.format(
                        '", "'.join(log_levels.keys()))))

        handler.setLevel(log_levels[handler_conf['level']])

        # Find and set up handler formatter.
        formatter = None
        if 'formatter' not in handler_conf:
            raise KeyError('Formatter (logger "{0}", handler "{1}") is not specified'.format(pref_logger_conf['name'],
                                                                                             handler_conf['name']))
        for formatter_conf in conf['formatters']:
            if formatter_conf['name'] == handler_conf['formatter']:
                formatter = logging.Formatter(formatter_conf['value'], "%Y-%m-%d %H:%M:%S")
                break
        if not formatter:
            raise KeyError(
                'Handler "{0}" of logger "{1}" references undefined formatter "{2}"'.format(handler_conf['name'],
                                                                                            pref_logger_conf['name'],
                                                                                            handler_conf['formatter']))
        handler.setFormatter(formatter)

        logger.addHandler(handler)

    if not logger.handlers:
        logger.disabled = True

    logger.debug("Logger was set up")

    return logger


def get_parallel_threads_num(logger, conf, action):
    logger.info('Get the number of parallel threads for "{0}"'.format(action))

    if 'CPU Virtual cores' in conf['task resource limits']\
            and conf['task resource limits']['CPU Virtual cores'] > 0:
        number_of_cores = conf['task resource limits']['CPU Virtual cores']
    else:
        number_of_cores = conf['number of CPU cores']

    raw_parallel_threads_num = conf['parallelism'][action]

    # In case of integer number it is already the number of parallel threads.
    if isinstance(raw_parallel_threads_num, int):
        parallel_threads_num = raw_parallel_threads_num
    # In case of decimal number it is fraction of the number of CPUs.
    elif isinstance(raw_parallel_threads_num, float):
        parallel_threads_num = number_of_cores * raw_parallel_threads_num
    else:
        raise ValueError(
            'The number of parallel threads ("{0}") for "{1}" is neither integer nor decimal number'.format(
                raw_parallel_threads_num, action))

    parallel_threads_num = int(parallel_threads_num)

    if parallel_threads_num < 1:
        raise ValueError('The computed number of parallel threads ("{0}") for "{1}" is less than 1'.format(
            parallel_threads_num, action))
    elif parallel_threads_num > 2 * number_of_cores:
        raise ValueError(
            'The computed number of parallel threads ("{0}") for "{1}" is greater than the double number of CPUs'.format(
                parallel_threads_num, action))

    logger.debug('The number of parallel threads for "{0}" is "{1}"'.format(action, parallel_threads_num))

    return parallel_threads_num


def merge_confs(a, b):
    for key in b:
        if key in a:
            # Perform sanity checks.
            if not isinstance(key, str):
                raise KeyError('Key is not string (its type is "{0}")'.format(type(key).__name__))
            elif not isinstance(a[key], type(b[key])):
                raise ValueError(
                    'Values of key "{0}" have different types ("{1}" and "{2}" respectively)'.format(key, type(a[key]),
                                                                                                     type(b[key])))
            # Recursively walk through sub-dictionaries.
            elif isinstance(a[key], dict):
                merge_confs(a[key], b[key])
            # Update key value from b to a for all other types (numbers, strings, lists).
            else:
                a[key] = b[key]
        # Just add new key-value from b to a.
        else:
            a[key] = b[key]
    return a


class ReportFiles:
    def __init__(self, files, arcnames={}):
        self.files = files
        self.arcnames = arcnames
        self.archive_name = None

    def make_archive(self):
        fp, self.archive_name = tempfile.mkstemp(suffix='.zip', dir='.')

        with open(self.archive_name, mode='w+b', buffering=0) as f:
            with zipfile.ZipFile(f, mode='w', compression=zipfile.ZIP_DEFLATED) as zfp:
                for file in self.files:
                    arcname = self.arcnames.get(file, None)
                    zfp.write(file, arcname=arcname)
                os.fsync(zfp.fp)
        os.close(fp)


class ExtendedJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ReportFiles):
            return os.path.basename(obj.archive_name)

        return json.JSONEncoder.default(self, obj)


def report(logger, kind, report_data, mq, report_id, directory, label=''):
    logger.debug('Create {0} report'.format(kind))

    # Specify report type.
    report_data.update({'type': kind})

    if 'attrs' in report_data:
        # Capitalize first letters of attribute names.
        def capitalize_attr_names(attrs):
            capitalized_name_attrs = []

            # Each attribute is dictionary with one element which value is either string or array of subattributes.
            for attr in attrs:
                attr_name = list(attr.keys())[0]
                attr_val = attr[attr_name]
                # Does capitalize attribute name.
                attr_name = attr_name[0].upper() + attr_name[1:]

                if isinstance(attr_val, str):
                    capitalized_name_attrs.append({attr_name: attr_val})
                else:
                    capitalized_name_attrs.append({attr_name: capitalize_attr_names(attr_val)})

            return capitalized_name_attrs

        report_data['attrs'] = capitalize_attr_names(report_data['attrs'])

    archives = []
    process_queue = [report_data]
    while process_queue:
        elem = process_queue.pop(0)
        if isinstance(elem, dict):
            process_queue.extend(elem.values())
        elif isinstance(elem, list) or isinstance(elem, tuple) or isinstance(elem, set):
            process_queue.extend(elem)
        elif isinstance(elem, ReportFiles):
            elem.make_archive()
            archives.append(elem.archive_name)

    with report_id.get_lock():
        cur_report_id = report_id.value
        report_id.value += 1

    # Create report file in reports directory.
    report_file = os.path.join(directory, 'reports', '{0}.json'.format(cur_report_id))
    with open(report_file, 'w', encoding='utf8') as fp:
        json.dump(report_data, fp, cls=ExtendedJSONEncoder, ensure_ascii=False, sort_keys=True, indent=4)

    # Create symlink to report file in current working directory.
    cwd_report_file = '{0}{1} report.json'.format(kind, ' ' + label if label else '')
    if os.path.isfile(cwd_report_file):
        raise FileExistsError('Report file "{0}" already exists'.format(cwd_report_file))
    os.symlink(os.path.relpath(report_file), cwd_report_file)
    logger.debug('{0} report was dumped to file "{1}"'.format(kind.capitalize(), cwd_report_file))

    # Put report file and report file archives to message queue if it is specified.
    if mq:
        mq.put({'report file': report_file, 'report file archives': archives})

    return report_file


def unique_file_name(file_name, suffix=''):
    if not os.path.isfile(file_name + suffix):
        return file_name

    i = 2
    while True:
        if not os.path.isfile("{0}({1}){2}".format(file_name, str(i), suffix)):
            return "{0}({1})".format(file_name, str(i))
        i += 1


def __converter(value, table, kind, outunit):
    """
    Converts units to uits.

    :param value: Given value as an integer, float or a string with units or without them.
    :param table: Table to translate units.
    :param kind: Time of units to print errors.
    :param outunit: Desired output unit, '' - means base.
    :return: Return the obtained value and the string of the value with units.
    """
    if isinstance(value, str):
        regex = re.compile("([0-9.]+)([a-zA-Z]*)$")
        if not regex.search(value):
            raise ValueError("Cannot parse string to extract the value and units: {!r}".format(value))
        else:
            value, inunit = regex.search(value).groups()
    else:
        inunit = ''
    # Check values
    for v in (inunit, outunit):
        if v not in table:
            raise ValueError("Get unknown {} unit {!r}".format(kind, v))

    # Get number and get bytes
    value_in_base = float(value) * table[inunit]

    # Than convert bytes into desired value
    value_in_out = value_in_base / table[outunit]

    # Align if necessary
    if outunit != '':
        fvalue = round(float(value_in_out), 2)
        ivalue = int(round(float(value_in_out), 0))
        if abs(fvalue - ivalue) < 0.1:
            value_in_out = ivalue
        else:
            value_in_out = fvalue
    else:
        value_in_out = int(value_in_out)

    return value_in_out, "{}{}".format(value_in_out, outunit)


def memory_units_converter(num, outunit=''):
    """
    Translate memory units.

    :param num: Given value as an integer, float or a string with units or without them.
    :param outunit: Desired output unit, '' - means Bytes.
    :return: Return the obtained value and the string of the value with units.
    """
    units_in_bytes = {
        '': 1,
        "B": 1,
        "KB": 10 ** 3,
        "MB": 10 ** 6,
        "GB": 10 ** 9,
        "TB": 10 ** 12,
        "KiB": 2 ** 10,
        "MiB": 2 ** 20,
        "GiB": 2 ** 30,
        "TiB": 2 ** 40,
    }

    return __converter(num, units_in_bytes, 'memory', outunit)


def time_units_converter(num, outunit=''):
    """
    Translate time units.

    :param num: Given value as an integer, float or a string with units or without them.
    :param outunit: Desired output unit, '' - means seconds.
    :return: Return the obtained value and the string of the value with units.
    """
    units_in_seconds = {
        '': 1,
        "s": 1,
        "min": 60,
        "h": 60 ** 2
    }

    return __converter(num, units_in_seconds, 'time', outunit)