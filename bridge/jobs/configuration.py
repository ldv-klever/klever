#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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

import json

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _

from bridge.vars import PRIORITY, SCHEDULER_TYPE, JOB_WEIGHT, SCHEDULER_STATUS
from bridge.utils import logger, BridgeException

from service.models import Scheduler, SchedulerUser

# Each Klever Core mode represents sets of values for following sets of attributes:
#   scheduling and decision weight:
#     job priority - see bridge.vars.PRIORITY for available values,
#     task scheduler - see bridge.vars.SCHEDULER_TYPE for available values,
#     max solving tasks per sub-job - positive number,
#     weight of decision - see vars.JOB_WEIGHT for available values,
#   parallelism:
#     pack - the identifier of default parallelism (see Parallelism.parallelism_packs for available values)
#       or parallelism values,
#     Example: ['slow'] or [1, 1, 1]
#   limits:
#     memory size - in GB,
#     number of CPU cores - if number <= 0 then any,
#     disk memory size - in GB,
#     CPU model,
#   logging:
#     console log level - see documentation for Python 3 and ConfigurationLogging.logging_levels
#       for available values,
#     console log formatter - one of formatters' identifiers from ConfigurationLogging.default_formatters,
#     file log level - like console log level,
#     file log formatter - like console log formatter,
#   various boolean values:
#     keep intermediate files,
#     upload input files of static verifiers,
#     upload other intermediate files,
#     ignore other instances,
#     ignore failed sub-jobs,
#     collect total code coverage,
# id 'file_conf' is reserved
KLEVER_CORE_DEF_MODES = [
    {
        'id': 'production', 'name': _('Production'),
        'values': [
            ['LOW', '0', 100, '1'],
            ['slow'],
            [2.0, 0, 100.0, None],
            ['NONE', 'brief', 'NONE', 'brief'],
            [False, False, False, False, False, True]
        ]
    },
    {
        'id': 'development', 'name': _('Development'),
        'values': [
            ['IDLE', '0', 100, '0'],
            ['quick'],
            [2.0, 0, 100.0, None],
            ['INFO', 'detailed', 'DEBUG', 'detailed'],
            [True, True, False, True, True, True]
        ]
    },
    {
        'id': 'paranoid development', 'name': _('Paranoid development'),
        'values': [
            ['IDLE', '0', 100, '0'],
            ['quick'],
            [2.0, 0, 100.0, None],
            ['INFO', 'detailed', 'DEBUG', 'paranoid'],
            [True, True, True, True, True, True]
        ]
    },
]


def str_to_int_or_float(value):
    if isinstance(value, (int, float)):
        return value
    val = value.replace(',', '.').strip()
    try:
        return int(val)
    except ValueError:
        return float(val)


class Parallelism:
    # Values format: (<html identifier>, <json key>, <html name>)
    parallelism_names = (
        ('sub_jobs_proc_parallelism', 'Sub-jobs processing', _('Sub-jobs processing')),
        ('tasks_gen_parallelism', 'Tasks generation', _('Tasks generation')),
        ('results_processing_parallelism', 'Results processing', _('Results processing'))
    )

    # Each Klever Core parallelism pack represents set of numbers of parallel threads/processes
    # for each action from parallelism_names.
    # Values format: (<pack html identifier>, <pack html name>, <pack values>)
    parallelism_packs = (
        ('sequential', _('Sequentially'), (1, 1, 1)),
        ('slow', _('Slowly'), (1, 1, 1)),
        ('quick', _('Quickly'), (1, 2, 1)),
        ('very quick', _('Very quickly'), (1, 1.0, 2))
    )

    def __init__(self, *args):
        self.columns_num = 'three'  # Number of values in a row
        if len(args) == 1:
            self.values = self.__get_default_values(*args)
        else:
            self.values = self.__get_values(*args)

    def packs(self):
        return self.parallelism_packs

    def for_template(self):
        # List of (<html identifier>, <html name>, <pack value>)
        return list(
            (self.parallelism_names[i][0], self.parallelism_names[i][2], self.values[i])
            for i in range(len(self.parallelism_names))
        )

    def for_json(self):
        # Dictionary: {<json key>: <pack value>}
        return dict((self.parallelism_names[i][1], self.values[i]) for i in range(len(self.parallelism_names)))

    def for_request(self):
        # Dictionary: {<html identifier>: <pack value>}
        return dict((self.parallelism_names[i][0], str(self.values[i])) for i in range(len(self.parallelism_names)))

    def __get_default_values(self, pack_name):
        if not isinstance(pack_name, str):
            raise ValueError('Unsupported parallelism pack identifier type is in values: {0}'.format(type(pack_name)))
        for i in range(len(self.parallelism_packs)):
            if self.parallelism_packs[i][0] == pack_name:
                return self.parallelism_packs[i][2]
        raise ValueError('Unsupported parallelism pack identifier is in values: "{0}"'.format(pack_name))

    def __get_values(self, *args):
        if len(args) != len(self.parallelism_names):
            raise ValueError('Wrong number of parallelism values: {0} expected, got {1}; values: {2}'
                             .format(len(self.parallelism_names), len(args), args))
        return tuple(str_to_int_or_float(a) for a in args)


class ConfigurationLogging:
    # See documentation for Python 3 logging for available values
    logging_levels = ['NONE', 'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET']

    # Values format: (<html identifier>, <html name>, <formatter>)
    default_formatters = (
        ('brief', _('Briefly'), "%(name)s %(levelname)5s> %(message)s"),
        ('detailed', _('In detail'), "%(asctime)s (%(filename)s:%(lineno)03d) %(name)s %(levelname)5s> %(message)s"),
        ('paranoid', _('Paranoidly'), "%(asctime)s (%(filename)s:%(lineno)03d) %(name)s "
                                      "(%(process)d) %(levelname)5s> %(message)s"),
    )

    def __init__(self, *args):
        self.values = self.__get_values(*args)

    def __get_log_level(self, level):
        if level not in self.logging_levels:
            raise ValueError('Logging level is not supported: "{0}"'.format(level))
        return level

    def __get_formatter(self, formatter):
        possible_name = formatter.strip()
        for i in range(len(self.default_formatters)):
            if possible_name == self.default_formatters[i][0]:
                return self.default_formatters[i][2]
        if len(formatter) == 0:
            raise ValueError('Formatter is empty')
        return formatter

    def for_template(self):
        return {
            'console': {'level': self.values[0], 'formatter': self.values[1]},
            'file': {'level': self.values[2], 'formatter': self.values[3]}
        }

    def for_json(self):
        return {
            'formatters': [
                {'name': 'formatter1', 'value': self.values[1]},
                {'name': 'formatter2', 'value': self.values[3]}
            ],
            'loggers': [{'name': 'default', 'handlers': [
                {'formatter': 'formatter1', 'level': self.values[0], 'name': 'console'},
                {'formatter': 'formatter2', 'level': self.values[2], 'name': 'file'}
            ]}]
        }

    def for_request(self, logging_type):
        return {logging_type: self.values[0]}

    def __get_values(self, *args):
        if len(args) == 1:
            for i in range(len(self.default_formatters)):
                if self.default_formatters[i][0] == args[0]:
                    return [self.default_formatters[i][2]]  # Just a formatter value
            raise ValueError('Unsupported formatter identifier: {0}'.format(args[0]))
        elif len(args) != 4:
            raise ValueError('Wrong number of logging arguments: {0}'.format(len(args)))
        return [
            self.__get_log_level(args[0]),  # Console log level
            self.__get_formatter(args[1]),  # Console log formatter
            self.__get_log_level(args[2]),  # File log level
            self.__get_formatter(args[3]),  # File log formatter
        ]


class BooleanValues:
    # Values format: (<html identifier>, <json identifier>, <html name>)
    boolean_names = (
        ('keep_files', 'keep intermediate files',
         _('Keep intermediate files inside the working directory of Klever Core')),
        ('upload_verifier', 'upload input files of static verifiers', _('Upload input files of static verifiers')),
        ('upload_other', 'upload other intermediate files', _('Upload other intermediate files')),
        ('ignore_core', 'ignore other instances', _('Ignore other instances of Klever Core')),
        ('ignore_failed_sub_jobs', 'ignore failed sub-jobs', _('Ignore failed sub-jobs')),
        ('collect_total_coverage', 'collect total code coverage', _('Collect total code coverage')),
    )

    def __init__(self, *args):
        if len(args) != len(self.boolean_names):
            raise ValueError('Expected {0} of boolean values, got {1}'
                             .format(len(self.boolean_names), len(args)))
        if any(not isinstance(x, bool) for x in args):
            raise ValueError('All boolean values must be boolean; got "{0}"'.format(args))
        self.values = args

    def names(self):
        return self.boolean_names

    def for_json(self):
        # Dictionary {<json identifier>: <value>}
        return dict((self.boolean_names[i][1], self.values[i]) for i in range(len(self.boolean_names)))

    def for_template(self):
        # List with values: (<html identifier>, <html name>, <value>)
        return list((self.boolean_names[i][0], self.boolean_names[i][2], self.values[i])
                    for i in range(len(self.boolean_names)))


class Configuration:
    def __init__(self, scheduling, parallelism, resources, logging, boolean):
        """
        Configuration for job decision.
        :param scheduling: list [
          <one of vars.PRIORITY identifiers>, <one of vars.SCHEDULER_TYPE identifiers>,
          <max_tasks: positive integer value>, <one of vars.JOB_WEIGHT identifiers>
        ]
        :param parallelism: list [<default pack name or parallelism values>]
        :param resources: list [max_ram, max_cpus, max_disk, cpu_model]
        :param logging: list [
          <console log level>, <console log formatter name or value>,
          <file log level>, <file log formatter name or value>
        ]
        :param boolean: list with boolean values. See BooleanValues.boolean_names.
        """
        if len(scheduling) != 4:
            raise ValueError('Wrong number of scheduling parameters: {0}'.format(scheduling))
        self.priority = self.__value_from_tuples_list(PRIORITY, scheduling[0])
        self.scheduler = self.__value_from_tuples_list(SCHEDULER_TYPE, scheduling[1])
        self.max_tasks = self.__integer_value(scheduling[2])
        self.weight = self.__value_from_tuples_list(JOB_WEIGHT, scheduling[3])

        self.parallelism = Parallelism(*parallelism)
        self.resources = self.__get_resources(*resources)
        self.logging = ConfigurationLogging(*logging)
        self.boolean = BooleanValues(*boolean)

    def __value_from_tuples_list(self, list_with_tuples, value):
        for i in range(len(list_with_tuples)):
            if list_with_tuples[i][0] == value:
                return value
        else:
            raise ValueError('Unknown value "{0}" for list {1}'.format(value, list_with_tuples))

    def __integer_value(self, value, null=False, positive=True):
        if null and value is None:
            return value
        if not isinstance(value, int) or (positive and value <= 0):
            raise ValueError('{0} expected, got value "{1}" of type {2}'
                             .format('Positive integer' if positive else 'Integer', value, type(value)))
        return value

    def __float_value(self, value, null=False, positive=True):
        if null and value is None:
            return value
        if isinstance(value, int):
            value = float(value)
        if not isinstance(value, float) or (positive and value < 0):
            raise ValueError('{0} expected, got value "{1}" of type {2}'
                             .format('Positive float' if positive else 'Float', value, type(value)))
        return value

    def __string_value(self, value, null=False, empty=False):
        if null and value is None:
            return value
        if not isinstance(value, str):
            raise ValueError('String expected, got "{0}"'.format(type(value)))
        value = value.strip()
        if not empty and len(value) == 0:
            raise ValueError('Non-empty string expected')
        return value

    def __get_resources(self, max_ram, max_cpus, max_disk, cpu_model):
        cpu_model = self.__string_value(cpu_model, null=True, empty=True)
        if cpu_model is not None and len(cpu_model) == 0:
            cpu_model = None

        return [
            self.__float_value(max_ram),
            self.__integer_value(max_cpus, positive=False),
            self.__float_value(max_disk),
            cpu_model
        ]

    def as_json(self, job_identifier):
        data = {
            'identifier': job_identifier,
            'priority': self.priority,
            'max solving tasks per sub-job': self.max_tasks,
            'resource limits': {
                'memory size': int(self.resources[0] * 10 ** 9), 'disk memory size': int(self.resources[2] * 10 ** 9),
                'number of CPU cores': self.resources[1], 'CPU model': self.resources[3]
            },
            'parallelism': self.parallelism.for_json(),
            'weight': self.weight,
            'logging': self.logging.for_json()
        }
        for sch in SCHEDULER_TYPE:
            if sch[0] == self.scheduler:
                data['task scheduler'] = sch[1]
                break
        data.update(self.boolean.for_json())
        return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=4)


def get_configuration_value(name, value):
    if name == 'parallelism':
        return Parallelism(value).for_request()
    elif name in {'console_log_formatter', 'file_log_formatter'}:
        return ConfigurationLogging(value).for_request(name)

    # Unknown name/value
    raise BridgeException()


class GetConfiguration:
    def __init__(self, conf_name=None, file_conf=None, user_conf=None, last_run=None):
        if conf_name is not None:
            conf_args = self.__get_default_conf_args(conf_name)
        elif user_conf is not None:
            conf_args = user_conf
        elif file_conf is not None:
            conf_args = self.__conf_args_from_json(file_conf)
        elif last_run is not None:
            with last_run.configuration.file as fp:
                conf_args = self.__conf_args_from_json(fp)
        else:
            conf_args = self.__get_default_conf_args(settings.DEF_KLEVER_CORE_MODE)
        self.configuration = Configuration(*conf_args)
        self.modes = list((m['id'], m['name']) for m in KLEVER_CORE_DEF_MODES)

    def __get_default_conf_args(self, name):
        for mode in KLEVER_CORE_DEF_MODES:
            if name == mode['id']:
                return mode['values']
        raise ValueError('Unsupported default configuration identifier: "{0}"'.format(name))

    def __conf_args_from_json(self, file):
        filedata = json.loads(file.read().decode('utf8'))

        # Get scheduler identifier
        for sch in SCHEDULER_TYPE:
            if sch[1] == filedata['task scheduler']:
                scheduler = sch[0]
                break
        else:
            raise ValueError('Unsupported scheduler name: "%s"' % filedata['task scheduler'])

        # Get logging arguments
        formatters = {}
        for f in filedata['logging']['formatters']:
            formatters[f['name']] = f['value']
        loggers = {}
        for l in filedata['logging']['loggers']:
            # TODO: what to do with other loggers?
            if l['name'] == 'default':
                for l_h in l['handlers']:
                    loggers[l_h['name']] = {'formatter': formatters[l_h['formatter']], 'level': l_h['level']}

        return [
            [filedata['priority'], scheduler, filedata['max solving tasks per sub-job'], filedata['weight']],
            list(filedata['parallelism'][x] for x in list(y[1] for y in Parallelism.parallelism_names)),
            [
                filedata['resource limits']['memory size'] / 10**9,
                filedata['resource limits']['number of CPU cores'],
                filedata['resource limits']['disk memory size'] / 10**9,
                filedata['resource limits']['CPU model']
            ],
            [
                loggers['console']['level'], loggers['console']['formatter'],
                loggers['file']['level'], loggers['file']['formatter']
            ],
            list(filedata[x] for x in list(y[1] for y in BooleanValues.boolean_names))
        ]


class StartDecisionData:
    def __init__(self, user, **kwargs):
        try:
            res = GetConfiguration(**kwargs)
        except Exception as e:
            logger.exception('Configuration error: %s' % e)
            raise BridgeException(_('Configuration has wrong format'))

        self.conf = res.configuration
        self.modes = res.modes

        self.job_sch_err = None
        self.schedulers = self.__get_schedulers()
        self.priorities = list(reversed(PRIORITY))
        self.job_weight = JOB_WEIGHT

        self.need_auth = False
        try:
            SchedulerUser.objects.get(user=user)
        except ObjectDoesNotExist:
            self.need_auth = True

    def __get_schedulers(self):
        schedulers = []
        try:
            klever_sch = Scheduler.objects.get(type=SCHEDULER_TYPE[0][0])
        except ObjectDoesNotExist:
            raise BridgeException(_('Population has to be done first'))
        try:
            cloud_sch = Scheduler.objects.get(type=SCHEDULER_TYPE[1][0])
        except ObjectDoesNotExist:
            raise BridgeException(_('Population has to be done first'))
        if klever_sch.status == SCHEDULER_STATUS[1][0]:
            self.job_sch_err = _("The Klever scheduler is ailing")
        elif klever_sch.status == SCHEDULER_STATUS[2][0]:
            raise BridgeException(_('The Klever scheduler is disconnected'))
        schedulers.append([
            klever_sch.type, '{0} ({1})'.format(klever_sch.get_type_display(), klever_sch.get_status_display())
        ])
        if cloud_sch.status != SCHEDULER_STATUS[2][0]:
            schedulers.append([
                cloud_sch.type, '{0} ({1})'.format(cloud_sch.get_type_display(), cloud_sch.get_status_display())
            ])
        elif self.conf.scheduler == SCHEDULER_TYPE[1][0]:
            raise BridgeException(_('The scheduler for tasks is disconnected'))
        return schedulers
