import json
import logging
import os.path
import requests
import subprocess
import sys
import time


class Session:
    def __init__(self, logger, user, passwd, name):
        # Check arguments passed.
        if not isinstance(logger, logging.Logger):
            raise ValueError('Logger should be an instance of Logger')
        if not isinstance(user, str):
            raise ValueError('User name should be a string')
        if len(user) == 0:
            raise ValueError('User name should not be empty')
        if not isinstance(passwd, str):
            raise ValueError('Password should be a string')
        if len(passwd) == 0:
            raise ValueError('Password should not be empty')
        if not isinstance(name, str):
            raise ValueError('Server name should be a string')
        if len(name) == 0:
            raise ValueError('Server name should not be empty')

        logger.info('Create session for user "{0}" on server "{1}"'.format(user, name))

        self.logger = logger
        self.user = user
        self.name = name
        self.session = requests.Session()

        # Get CSRF token via GET request.
        self.__request('users/psi_signin/')

        # Sign in.
        self.__request('users/psi_signin/', 'POST', {
            'username': user,
            'password': passwd,
        })
        logger.debug('Session was created')

    def __request(self, path_url, method='GET', data=None, **kwargs):
        while True:
            try:
                url = 'http://' + self.name + '/' + path_url

                self.logger.debug('Send "{0}" request to "{1}"'.format(method, url))

                if data:
                    data.update({'csrfmiddlewaretoken': self.session.cookies['csrftoken']})

                resp = self.session.get(url, **kwargs) if method == 'GET' else self.session.post(url, data, **kwargs)

                if resp.status_code != 200:
                    with open('response-error.html', 'w+') as fp:
                        fp.write(resp.text)
                        fp.close()
                    raise IOError(
                        'Got unexpected status code "{0}" when send "{1}" request to "{2}"'.format(resp.status_code,
                                                                                                   method, url))
                if resp.headers['content-type'] == 'application/json' and 'error' in resp.json():
                    raise IOError(
                        'Got error "{0}" when send "{1}" request to "{2}"'.format(resp.json()['error'], method, url))

                return resp
            except requests.ConnectionError as err:
                self.logger.warning('Could not send "{0}" request to "{1}"'.format(method, err.request.url))
                time.sleep(1)

    def decide_job(self, job, start_report_file):
        # Acquire download lock.
        resp = self.__request('jobs/downloadlock/')
        if 'status' not in resp.json() or 'hash_sum' not in resp.json():
            raise IOError('Could not get download lock at "{0}"'.format(resp.request.url))

        with open(start_report_file) as fp:
            resp = self.__request('jobs/decide_job/', 'POST', {
                'job id': job['id'],
                'job format': job['format'],
                'report': fp.read(),
                'hash sum': resp.json()['hash_sum']
            }, stream=True)

        with open(job['archive'], 'wb') as fp:
            for chunk in resp.iter_content(1024):
                fp.write(chunk)

    def sign_out(self):
        self.logger.info('Finish session for user "{0}" on server "{1}"'.format(self.user, self.name))
        self.__request('users/psi_signout/')

    def upload_report(self, report_file):
        with open(report_file) as fp:
            self.__request('reports/upload/', 'POST', {'report': fp.read()})


def dump_report(logger, kind, report):
    """
    Dump the specified report of the specified kind to a file.
    :param logger: a logger for printing debug messages.
    :param kind: a report kind (a file where a report will be dumped will be named "kind report.json").
    :param report: a report object (usually it should be a dictionary).
    """
    logger.info('Dump {0} report'.format(kind))

    report_file = '{0} report.json'.format(kind)
    with open(report_file, 'w') as fp:
        json.dump(report, fp, sort_keys=True, indent=4)

    logger.debug('{0} report was dumped to file "{1}"'.format(kind.capitalize(), report_file))

    return report_file


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
