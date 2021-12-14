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

import fcntl
import json
import hashlib
import logging
import os
import re
import subprocess
import sys
import zipfile
import threading
import time
import queue
import tempfile
import shutil
import resource
import random
import string


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
                line = line.decode('utf-8').rstrip()
                self.queue.put(line)
                if self.collect_all_output:
                    self.output.append(line)

            # Nothing will be put to queue from now.
            self.finished = True
        except Exception:
            import traceback
            self.traceback = traceback.format_exc().rstrip()


def execute(logger, args, env=None, cwd=None, timeout=0.1, collect_all_stdout=False, filter_func=None,
            enforce_limitations=False, cpu_time_limit=450, memory_limit=1000000000):
    cmd = args[0]
    logger.debug('Execute:\n{0}{1}{2}'.format(cmd,
                                              '' if len(args) == 1 else ' ',
                                              ' '.join('"{0}"'.format(arg) for arg in args[1:])))

    if enforce_limitations:
        soft_time, hard_time = resource.getrlimit(resource.RLIMIT_CPU)
        soft_mem, hard_mem = resource.getrlimit(resource.RLIMIT_AS)
        logger.debug('Got the following limitations: CPU time = {}s, memory = {}B'.format(cpu_time_limit, memory_limit))

    p = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
    if enforce_limitations:
        resource.prlimit(p.pid, resource.RLIMIT_CPU, [cpu_time_limit, hard_time])
        resource.prlimit(p.pid, resource.RLIMIT_AS, [memory_limit, hard_mem])

    out_q, err_q = (StreamQueue(p.stdout, 'STDOUT', collect_all_stdout), StreamQueue(p.stderr, 'STDERR', True))

    for stream_q in (out_q, err_q):
        stream_q.start()

    # Print to logs everything that is printed to STDOUT and STDERR each timeout seconds. Last try is required to
    # print last messages queued before command finishes.
    last_try = True
    while not out_q.finished or not err_q.finished or last_try:
        if out_q.traceback:
            raise RuntimeError('STDOUT reader thread failed with the following traceback:\n{0}'.format(out_q.traceback))
        if err_q.traceback:
            raise RuntimeError('STDERR reader thread failed with the following traceback:\n{0}'.format(err_q.traceback))
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
        logger.error('"{0}" exited with "{1}"'.format(cmd, p.poll()))
        with open('problem desc.txt', 'a', encoding='utf-8') as fp:
            out = filter(filter_func, err_q.output) if filter_func else err_q.output
            fp.write('\n'.join(out))
        sys.exit(1)
    elif collect_all_stdout:
        return out_q.output


def reliable_rmtree(logger, directory):
    try:
        shutil.rmtree(directory)
    except OSError as error:
        logger.warning("Cannot delete directory {!r}: {!r}".format(directory, error))
        shutil.rmtree(directory, ignore_errors=True)


def get_search_dirs(main_work_dir, abs_paths=False):
    search_dirs = ['job/root', os.path.curdir]

    if 'KLEVER_DATA_DIR' in os.environ:
        search_dirs.append(os.environ['KLEVER_DATA_DIR'])

    # All search directories are represented by either absolute paths (so, join does not have any effect) or paths
    # relatively to main working directory. Thus, after this operation all search directories become absolute.
    search_dirs = [os.path.realpath(os.path.join(main_work_dir, search_dir)) for search_dir in search_dirs]

    if abs_paths:
        return search_dirs

    # Make search directories relative to current working directory if necessary.
    return tuple(os.path.relpath(search_dir) for search_dir in search_dirs)


# TODO: get value of the second parameter on the basis of passed configuration. Or, even better, implement wrapper around this function in components.Component.
def find_file_or_dir(logger, main_work_dir, file_or_dir):
    search_dirs = get_search_dirs(main_work_dir)

    for search_dir in search_dirs:
        # TODO: there is an undocumented feature here. If file_or_dir will be absolute one os.path.join will return it. If it exists find_file_or_dir will assume that it is located in first search directory and return it.
        found_file_or_dir = os.path.join(search_dir, file_or_dir)
        if os.path.isfile(found_file_or_dir):
            logger.debug('Find file "{0}" in directory "{1}"'.format(file_or_dir, search_dir))
            return found_file_or_dir
        elif os.path.isdir(found_file_or_dir):
            logger.debug('Find directory "{0}" in directory "{1}"'.format(file_or_dir, search_dir))
            return found_file_or_dir

    raise FileNotFoundError(
        'Could not find file or directory "{0}" in directories "{1}"'.format(file_or_dir, ', '.join(search_dirs)))


def make_relative_path(dirs, file_or_dir, absolutize=False):
    # Normalize paths first of all.
    dirs = [os.path.normpath(d) for d in dirs]
    file_or_dir = os.path.normpath(file_or_dir)

    # Check all dirs are absolute or relative.
    is_dirs_abs = False
    if all(os.path.isabs(d) for d in dirs):
        is_dirs_abs = True
    elif all(not os.path.isabs(d) for d in dirs):
        pass
    else:
        raise ValueError('Can not mix absolute and relative dirs')

    if os.path.isabs(file_or_dir):
        # Making absolute file_or_dir relative to relative dirs has no sense.
        if not is_dirs_abs:
            return file_or_dir
    else:
        # One needs to absolutize file_or_dir since it can be relative to Clade storage.
        if absolutize:
            if not is_dirs_abs:
                raise ValueError('Do not absolutize file_or_dir for relative dirs')

            file_or_dir = os.path.join(os.path.sep, file_or_dir)
        # file_or_dir is already relative.
        elif is_dirs_abs:
            return file_or_dir

    # Find and return if so path relative to the longest directory.
    for d in sorted(dirs, key=lambda t: len(t), reverse=True):
        if os.path.commonpath([file_or_dir, d]) == d:
            return os.path.relpath(file_or_dir, d)

    return file_or_dir


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
            handler = logging.FileHandler('log.txt', encoding='utf-8')
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


def get_parallel_threads_num(logger, conf, action=None):
    logger.info('Get the number of parallel threads for "{0}"'.format(action if action else "Default"))

    if 'CPU Virtual cores' in conf['task resource limits']\
            and conf['task resource limits']['CPU Virtual cores'] > 0:
        number_of_cores = conf['task resource limits']['CPU Virtual cores']
    else:
        number_of_cores = conf['number of CPU cores']

    # Without specified action the number of parallel threads equals to the number of CPU cores.
    if action:
        raw_parallel_threads_num = conf['parallelism'][action]
    else:
        raw_parallel_threads_num = 1.0

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
            'The computed number of parallel threads ("{0}") for "{1}" is greater than the double number of CPUs'
            .format(parallel_threads_num, action))

    logger.debug('The number of parallel threads for "{0}" is "{1}"'
                 .format(action if action else "Default", parallel_threads_num))

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


class ArchiveFiles:
    def __init__(self, files_and_dirs, arcnames={}):
        self.files_and_dirs = files_and_dirs
        self.arcnames = arcnames
        self.archive = None

    def make_archive(self, archive):
        self.archive = archive

        with open(self.archive, mode='w+b', buffering=0) as f:
            with zipfile.ZipFile(f, mode='w', compression=zipfile.ZIP_DEFLATED) as zfp:
                for file_or_dir in self.files_and_dirs:
                    # Archive file using specified archive name if so.
                    if os.path.isfile(file_or_dir):
                        arcname = self.arcnames.get(file_or_dir, None)
                        zfp.write(file_or_dir, arcname=arcname)
                    # Archive all files from directory cutting that directory from file names.
                    elif os.path.isdir(file_or_dir):
                        for root, dirs, files in os.walk(file_or_dir):
                            for file in files:
                                file = os.path.join(root, file)
                                zfp.write(file, arcname=make_relative_path([file_or_dir], file))
                    else:
                        raise NotImplementedError("Cannot interpret a kind of an object {!r}".format(file_or_dir))

                os.fsync(zfp.fp)


class ExtendedJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ArchiveFiles):
            return os.path.basename(obj.archive)

        return json.JSONEncoder.default(self, obj)


# Check that all attribute names/values are less than 64/255 characters.
def check_attr_values(attrs):
    for attr in attrs:
        if len(attr['name']) > 64:
            raise ValueError("Attribute name \"{0}\" is longer than 64 characters".format(attr['name']))

        # Like for capitalize_attr_names().
        if isinstance(attr['value'], list):
            check_attr_values(attr['value'])
        elif len(attr['value']) > 255:
            raise ValueError("Attribute \"{0}\" value \"{1}\" is longer than 255 characters"
                             .format(attr['name'], attr['value']))


# Capitalize first letters of attribute names.
def capitalize_attr_names(attrs):
    # Each attribute is dictionary with one element which value is either string or array of subattributes.
    for attr in attrs:
        # Does capitalize attribute name.
        attr['name'] = attr['name'][0].upper() + attr['name'][1:]

        if isinstance(attr['value'], list):
            capitalize_attr_names(attr['value'])


def report(logger, kind, report_data, mq, report_id, main_work_dir, report_dir='', data_files=None):
    logger.debug('Create {0} report'.format(kind))

    # Specify report type.
    report_data.update({'type': kind})

    logger.debug('{0} going to modify report id'.format(kind.capitalize()))
    with report_id.get_lock():
        cur_report_id = report_id.value
        report_id.value += 1

    prefix = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    archives = []
    if 'attrs' in report_data:
        check_attr_values(report_data['attrs'])
        capitalize_attr_names(report_data['attrs'])

        if data_files:
            archive_name = '{} data attributes.zip'.format(cur_report_id)
            data_zip = os.path.join(main_work_dir, 'reports', archive_name)
            with open(data_zip, mode='w+b', buffering=0) as f:
                with zipfile.ZipFile(f, mode='w', compression=zipfile.ZIP_DEFLATED) as zfp:
                    for df in data_files:
                        zfp.write(df)
                    os.fsync(zfp.fp)
            report_data['attr_data'] = archive_name
            archives.append(data_zip)

            # Create symlink to report file in current working directory.
            cwd_data_zip = os.path.join(report_dir, '{} {} data attributes.zip'.format(prefix, cur_report_id))
            if os.path.isfile(cwd_data_zip):
                raise FileExistsError('Report file "{0}" already exists'.format(cwd_data_zip))
            os.symlink(os.path.relpath(data_zip, report_dir), cwd_data_zip)
            logger.debug('{0} report was dumped to file "{1}"'.format(kind.capitalize(), cwd_data_zip))

    logger.debug('{0} prepare file archive'.format(kind.capitalize()))
    process_queue = [report_data]
    while process_queue:
        elem = process_queue.pop(0)
        if isinstance(elem, dict):
            process_queue.extend(elem.values())
        elif isinstance(elem, list) or isinstance(elem, tuple) or isinstance(elem, set):
            process_queue.extend(elem)
        elif isinstance(elem, ArchiveFiles):
            logger.debug('{0} going to pack report files to archive'.format(kind.capitalize()))

            archive = tempfile.mktemp(prefix='{0}-'.format(cur_report_id), suffix='.zip',
                                      dir=os.path.join(main_work_dir, 'reports'))
            elem.make_archive(archive)
            archives.append(elem.archive)

            # Create symlink to report files archive in current working directory.
            tmp_name = os.path.splitext('-'.join(os.path.relpath(elem.archive).split('-')[1:]))[0]
            cwd_report_files_archive = os.path.join(report_dir, '{0} report files {1}.zip'.format(kind, tmp_name))
            if os.path.isfile(cwd_report_files_archive):
                raise FileExistsError('Report files archive "{0}" already exists'.format(cwd_report_files_archive))
            os.symlink(os.path.relpath(os.path.join(main_work_dir, 'reports', elem.archive), report_dir),
                       cwd_report_files_archive)
            logger.debug('{0} report files were packed to archive "{1}"'.format(kind.capitalize(),
                                                                                cwd_report_files_archive))

    # Create report file in reports directory.
    report_file = os.path.join(main_work_dir, 'reports', '{0}.json'.format(cur_report_id))
    with open(report_file, 'w', encoding='utf-8') as fp:
        json.dump(report_data, fp, cls=ExtendedJSONEncoder, ensure_ascii=False, sort_keys=True, indent=4)

    # Create symlink to report file in current working directory.
    prefix = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    cwd_report_file = os.path.join(report_dir, '{} {} report.json'.format(prefix, kind))
    if os.path.isfile(cwd_report_file):
        raise FileExistsError('Report file "{0}" already exists'.format(cwd_report_file))
    os.symlink(os.path.relpath(report_file, report_dir), cwd_report_file)
    logger.debug('{0} report was dumped to file "{1}"'.format(kind.capitalize(), cwd_report_file))

    # Put report file and report file archives to message queue if it is specified.
    if mq:
        mq.put({'report file': report_file, 'report file archives': archives})

    return report_file


def report_image(logger, component_id, title, dot_file, image_file, mq, report_id, main_work_dir):
    logger.debug('Create image report')

    with report_id.get_lock():
        cur_report_id = report_id.value
        report_id.value += 1

    # We need to store files permanently outside of Component's directory to avoid their accidental removing.
    permanent_dot_file = os.path.join(main_work_dir, 'reports', '{0}.dot'.format(cur_report_id))
    permanent_image_file = os.path.join(main_work_dir, 'reports', '{0}.png'.format(cur_report_id))
    shutil.copy(dot_file, permanent_dot_file)
    shutil.copy(image_file, permanent_image_file)

    report_data = {
        'type': 'image',
        'component id': component_id,
        'title': title,
        'dot file': permanent_dot_file,
        'image file': permanent_image_file
    }

    report_file = os.path.join(main_work_dir, 'reports', '{0}.json'.format(cur_report_id))
    with open(report_file, 'w', encoding='utf-8') as fp:
        json.dump(report_data, fp, ensure_ascii=False, sort_keys=True, indent=4)

    mq.put({'report file': report_file})


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


def read_max_resource_limitations(logger, conf):
    """
    Get maximum resource limitations that can be set for a verification task.

    :param logger: Logger.
    :param conf: Configuration dictionary.
    :return: Dictionary.
    """
    # Read max restrictions for tasks
    restrictions_file = find_file_or_dir(logger, conf["main working directory"], "tasks.json")
    with open(restrictions_file, 'r', encoding='utf-8') as fp:
        restrictions = json.loads(fp.read())

    # Make unit translation
    for mem in (m for m in ("memory size", "disk memory size") if m in restrictions and restrictions[m] is not None):
        restrictions[mem] = memory_units_converter(restrictions[mem])[0]
    for t in (t for t in ("wall time", "CPU time") if t in restrictions and restrictions[t] is not None):
        restrictions[t] = time_units_converter(restrictions[t])[0]
    return restrictions


def drain_queue(collection, given_queue):
    """
    Get all available elements from the given queue without waiting.

    :param collection: List.
    :param given_queue: multiprocessing.Queue
    :return: False - no elements will come, True - otherwise
    """
    try:
        while True:
            element = given_queue.get_nowait()
            if element is None:
                given_queue.close()
                return False
            collection.append(element)
    except queue.Empty:
        return True


def get_waiting_first(given_queue, timeout=None):
    """
    First, wait for the first element, then drain the queue if there are waiting, then return the result. The idea is
    to wait until the queue is full to avoid useless loop iterations but still not wait for elements forever.

    :param given_queue: multiprocessing.Queue.
    :param timeout: Seconds.
    :return: a list with received items.
    """
    collection = []
    try:
        item = given_queue.get(True, timeout=timeout)
        collection.append(item)
    except queue.Empty:
        # Timeout!
        return collection
    if item:
        drain_queue(collection, given_queue)
    else:
        given_queue.close()
    return collection


def json_dump(obj, fp, pretty=True):
    """
    Save JSON file.

    :param obj: Some serializable object.
    :param fp: File descriptor.
    :param pretty: pretty printing flag.
    """
    if pretty:
        json.dump(obj, fp, ensure_ascii=True, sort_keys=True, indent=4)
    else:
        json.dump(obj, fp, ensure_ascii=True)


def save_program_fragment_description(program_fragment_desc, file_name):
    """
    Save file for program fragment data attribute value.

    :param program_fragment_desc: Program fragment description dict.
    :param file_name: File name to save values.
    """
    with open(file_name, 'w', encoding='utf-8') as fp:
        fp.writelines(['Lines of code: {}\n'.format(program_fragment_desc['size']), 'Files:\n'])
        fp.writelines('\n'.join(sorted(f for grp in program_fragment_desc['grps'] for f in grp['files'])))


def get_file_checksum(file_name):
    hash_sha256 = hashlib.sha256()

    with open(file_name, 'rb') as fp:
        for chunk in iter(lambda: fp.read(4096), b""):
            hash_sha256.update(chunk)

    return hash_sha256.hexdigest()


# TODO: rename it with something like get_str_checksum(str) since there is not filename specifics.
def get_file_name_checksum(file_name):
    hash_sha256 = hashlib.sha256()
    hash_sha256.update(file_name.encode('utf-8'))
    return hash_sha256.hexdigest()
