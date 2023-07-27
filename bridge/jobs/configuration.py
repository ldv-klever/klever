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

import copy
import json

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext_lazy as _

from rest_framework import fields, serializers

from bridge.vars import PRIORITY, SCHEDULER_TYPE, DECISION_WEIGHT, COVERAGE_DETAILS, SCHEDULER_STATUS, DECISION_STATUS
from bridge.utils import BridgeException

from users.models import SchedulerUser
from jobs.models import Scheduler, DefaultDecisionConfiguration
from reports.models import Decision

# Each Klever Core mode represents sets of values for following sets of attributes:
#   priority - see bridge.vars.PRIORITY for available values (job priority),
#   scheduler - see bridge.vars.SCHEDULER_TYPE for available values (task scheduler),
#   max_tasks - positive number (max solving tasks per sub-job),
#   weight - see vars.DECISION_WEIGHT for available values (weight of decision),
#   parallelism: [Sub-jobs processing, EMG, Plugins, Weaving, Results processing]
#   memory - memory size in GB,
#   cpu_num - number of CPU cores; if number is None then any,
#   disk_size - disk memory size in GB,
#   cpu_model - CPU model,
#   cpu_time_exec_cmds - CPU time for executed commands in min,
#   memory_exec_cmds - memory size for executed commands in GB,
#   console_level - console log level; see documentation for Python 3 and
#     ConfigurationLogging.logging_levels for available values,
#   console_formatter - console log formatter,
#   file_level - file log level; like console_level,
#   file_formatter - file log formatter,
#   keep_intermediate_files - keep intermediate files (bool),
#   upload_verifier_files - upload verifier input files (bool),
#   upload_other_files - upload other intermediate files (bool),
#   ignore_subjobs - ignore failed sub-jobs (bool),
#   total_coverage - collect total code coverage (bool).
#   coverage_details - see vars.COVERAGE_DETAILS for available values,
# id 'file_conf' is reserved

LOGGING_LEVELS = ['NONE', 'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET']
DEFAULT_FORMATTER = (
    ('brief', _('Briefly'), "%(name)s %(levelname)5s> %(message)s"),
    ('detailed', _('In detail'), "%(asctime)s (%(filename)s:%(lineno)03d) %(name)s %(levelname)5s> %(message)s"),
    ('paranoid', _('Paranoidly'), "%(asctime)s (%(filename)s:%(lineno)03d) %(name)s "
                                  "(%(process)d) %(levelname)5s> %(message)s")
)
PARALLELISM_PACKS = [
    ('sequential', _('Sequentially'), ('1', '1', '1', '1', '1')),
    ('slow', _('Slowly'), ('1', '1', '1', '1', '1')),
    ('quick', _('Quickly'), ('1', '4', '2', '2', '1')),
    ('very quick', _('Very quickly'), ('1', '1.0', '0.5', '0.5', '2'))
]
KLEVER_CORE_DEF_MODES = [
    {
        'id': 'production', 'name': _('Production'),
        'data': {
            'priority': PRIORITY[2][0],
            'scheduler': SCHEDULER_TYPE[0][0],
            'max_tasks': 100,
            'weight': DECISION_WEIGHT[1][0],
            'parallelism': ['1', '3', '2', '2', '1'],
            'memory': 3,
            'cpu_num': None,
            'disk_size': 100,
            'cpu_model': None,
            'cpu_time_exec_cmds': 7.5,
            'memory_exec_cmds': 1,
            'console_level': 'NONE',
            'file_level': 'NONE',
            'console_formatter': DEFAULT_FORMATTER[0][2],
            'file_formatter': DEFAULT_FORMATTER[0][2],
            'keep_intermediate_files': False,
            'upload_verifier_files': False,
            'upload_other_files': False,
            'ignore_subjobs': False,
            'total_coverage': True,
            'coverage_details': COVERAGE_DETAILS[0][0]
        }
    },
    {
        'id': 'development', 'name': _('Development'),
        'data': {
            'priority': PRIORITY[3][0],
            'scheduler': SCHEDULER_TYPE[0][0],
            'max_tasks': 100,
            'weight': DECISION_WEIGHT[0][0],
            'parallelism': ['1', '5', '5', '0.5', '2'],
            'memory': 5,
            'cpu_num': None,
            'disk_size': 20,
            'cpu_model': None,
            'cpu_time_exec_cmds': 7.5,
            'memory_exec_cmds': 1,
            'console_level': 'INFO',
            'file_level': 'DEBUG',
            'console_formatter': DEFAULT_FORMATTER[1][2],
            'file_formatter': DEFAULT_FORMATTER[1][2],
            'keep_intermediate_files': True,
            'upload_verifier_files': True,
            'upload_other_files': False,
            'ignore_subjobs': True,
            'total_coverage': True,
            'coverage_details': COVERAGE_DETAILS[1][0]
        }
    },
    {
        'id': 'paranoid', 'name': _('Paranoid development'),
        'data': {
            'priority': PRIORITY[3][0],
            'scheduler': SCHEDULER_TYPE[0][0],
            'max_tasks': 100,
            'weight': DECISION_WEIGHT[0][0],
            'parallelism': ['1', '5', '5', '0.5', '2'],
            'memory': 5,
            'cpu_num': None,
            'disk_size': 20,
            'cpu_model': None,
            'cpu_time_exec_cmds': 7.5,
            'memory_exec_cmds': 1,
            'console_level': 'INFO',
            'file_level': 'DEBUG',
            'console_formatter': DEFAULT_FORMATTER[1][2],
            'file_formatter': DEFAULT_FORMATTER[2][2],
            'keep_intermediate_files': True,
            'upload_verifier_files': True,
            'upload_other_files': True,
            'ignore_subjobs': True,
            'total_coverage': True,
            'coverage_details': COVERAGE_DETAILS[2][0]
        }
    }
]


def get_configuration_value(name, value):
    if name == 'parallelism':
        for p_id, __, p_val in PARALLELISM_PACKS:
            if p_id == value:
                return {
                    'parallelism_0': p_val[0],
                    'parallelism_1': p_val[1],
                    'parallelism_2': p_val[2],
                    'parallelism_3': p_val[3],
                    'parallelism_4': p_val[4]
                }
    elif name == 'def_console_formatter':
        for f_id, __, f_val in DEFAULT_FORMATTER:
            if f_id == value:
                return {'console_formatter': f_val}
    elif name == 'def_file_formatter':
        for f_id, __, f_val in DEFAULT_FORMATTER:
            if f_id == value:
                return {'file_formatter': f_val}
    return {}


def get_default_configuration(user):
    try:
        defconf_obj = DefaultDecisionConfiguration.objects.select_related('file').get(user=user)
        return GetConfiguration(file_conf=defconf_obj.file.file)
    except DefaultDecisionConfiguration.DoesNotExist:
        return GetConfiguration(conf_name=settings.DEF_KLEVER_CORE_MODE)


class ConfigurationSerializer(serializers.Serializer):
    priority = fields.ChoiceField(PRIORITY)
    scheduler = fields.ChoiceField(SCHEDULER_TYPE)
    max_tasks = fields.IntegerField(min_value=1)
    weight = fields.ChoiceField(DECISION_WEIGHT)

    parallelism = fields.ListField(child=fields.RegexField(r'^\d+(\.\d+)?$'), min_length=5, max_length=5)

    memory = fields.FloatField()
    cpu_num = fields.IntegerField(allow_null=True, min_value=1)
    disk_size = fields.FloatField()
    cpu_model = fields.CharField(default='', allow_null=True, allow_blank=True)
    cpu_time_exec_cmds = fields.FloatField()
    memory_exec_cmds = fields.FloatField()

    console_level = fields.ChoiceField(LOGGING_LEVELS)
    file_level = fields.ChoiceField(LOGGING_LEVELS)
    console_formatter = fields.CharField()
    file_formatter = fields.CharField()

    keep_intermediate_files = fields.BooleanField()
    upload_verifier_files = fields.BooleanField()
    upload_other_files = fields.BooleanField()
    ignore_subjobs = fields.BooleanField()
    total_coverage = fields.BooleanField()
    coverage_details = fields.ChoiceField(COVERAGE_DETAILS)

    def create(self, validated_data):
        raise NotImplementedError

    def update(self, instance, validated_data):
        raise NotImplementedError


class GetConfiguration:
    def __init__(self, conf_name=None, file_conf=None, user_conf=None, base_decision=None):
        if conf_name is not None:
            self.configuration = self.__get_default_conf_args(conf_name)
        elif user_conf is not None:
            self.configuration = self.__validate_conf(user_conf)
        elif file_conf is not None:
            self.configuration = self.__json_to_conf(file_conf)
        elif base_decision is not None:
            with base_decision.configuration.file as fp:
                self.configuration = self.__json_to_conf(fp)
        else:
            self.configuration = self.__get_default_conf_args(settings.DEF_KLEVER_CORE_MODE)

    def __get_default_conf_args(self, name):
        for mode in KLEVER_CORE_DEF_MODES:
            if name == mode['id']:
                return self.__validate_conf(mode['data'])
        raise ValueError('Unsupported default configuration identifier: "{0}"'.format(name))

    def __str_to_int_or_float(self, value):
        return float(value) if '.' in value else int(value)

    def __json_to_conf(self, file):
        filedata = json.loads(file.read().decode('utf8'))

        if not isinstance(filedata, dict):
            raise BridgeException(_('The configuration file is wrong'))

        # Get logging arguments
        formatters = {}
        for f in filedata['logging']['formatters']:
            formatters[f['name']] = f['value']
        loggers = {}
        for conf_l in filedata['logging']['loggers']:
            if conf_l['name'] == 'default':
                for l_h in conf_l['handlers']:
                    loggers[l_h['name']] = {'formatter': formatters[l_h['formatter']], 'level': l_h['level']}

        configuration = {
            'priority': filedata['priority'],
            'scheduler': filedata['task scheduler'],
            'max_tasks': filedata['max solving tasks per sub-job'],
            'weight': filedata['weight'],
            'parallelism': [
                str(filedata['parallelism']['Sub-jobs processing']),
                str(filedata['parallelism'].get('EMG', 1)),  # backward compatibility with the old format
                str(filedata['parallelism'].get('Plugins', 1)),  # backward compatibility with the old format
                str(filedata['parallelism']['Weaving']),
                str(filedata['parallelism']['Results processing']),
            ],
            'memory': filedata['resource limits']['memory size'] / 10 ** 9,
            'cpu_num': filedata['resource limits']['number of CPU cores'],
            'disk_size': filedata['resource limits']['disk memory size'] / 10 ** 9,
            'cpu_model': filedata['resource limits']['CPU model'],
            'cpu_time_exec_cmds': filedata['resource limits']['CPU time for executed commands'] / 60,
            'memory_exec_cmds': filedata['resource limits']['memory size for executed commands'] / 10 ** 9,
            'console_level': loggers['console']['level'],
            'file_level': loggers['file']['level'],
            'console_formatter': loggers['console']['formatter'],
            'file_formatter': loggers['file']['formatter'],
            'keep_intermediate_files': filedata['keep intermediate files'],
            'upload_verifier_files': filedata['upload verifier input files'],
            'upload_other_files': filedata['upload other intermediate files'],
            'ignore_subjobs': filedata['ignore failed sub-jobs'],
            'total_coverage': filedata['collect total code coverage'],
            'coverage_details': filedata['code coverage details'],
        }
        serializer = ConfigurationSerializer(data=configuration)
        serializer.is_valid(raise_exception=True)
        return serializer.data

    def for_json(self):
        return {
            'priority': self.configuration['priority'],
            'weight': self.configuration['weight'],
            'task scheduler': self.configuration['scheduler'],
            'max solving tasks per sub-job': self.configuration['max_tasks'],
            'resource limits': {
                'memory size': int(self.configuration['memory'] * 10 ** 9),
                'disk memory size': int(self.configuration['disk_size'] * 10 ** 9),
                'number of CPU cores': self.configuration['cpu_num'],
                'CPU model': self.configuration['cpu_model'] or None,
                'CPU time for executed commands': int(self.configuration['cpu_time_exec_cmds'] * 60),
                'memory size for executed commands': int(self.configuration['memory_exec_cmds'] * 10 ** 9)
            },
            'parallelism': {
                'Sub-jobs processing': self.__str_to_int_or_float(self.configuration['parallelism'][0]),
                'EMG': self.__str_to_int_or_float(self.configuration['parallelism'][1]),
                'Plugins': self.__str_to_int_or_float(self.configuration['parallelism'][2]),
                'Weaving': self.__str_to_int_or_float(self.configuration['parallelism'][3]),
                'Results processing': self.__str_to_int_or_float(self.configuration['parallelism'][4])
            },
            'logging': {
                'formatters': [
                    {'name': 'formatter1', 'value': self.configuration['console_formatter']},
                    {'name': 'formatter2', 'value': self.configuration['file_formatter']}
                ],
                'loggers': [{'name': 'default', 'handlers': [
                    {'formatter': 'formatter1', 'level': self.configuration['console_level'], 'name': 'console'},
                    {'formatter': 'formatter2', 'level': self.configuration['file_level'], 'name': 'file'}
                ]}]
            },
            'keep intermediate files': self.configuration['keep_intermediate_files'],
            'upload verifier input files': self.configuration['upload_verifier_files'],
            'upload other intermediate files': self.configuration['upload_other_files'],
            'ignore failed sub-jobs': self.configuration['ignore_subjobs'],
            'collect total code coverage': self.configuration['total_coverage'],
            'code coverage details': self.configuration['coverage_details'],
        }

    def for_html(self):
        html_conf = copy.deepcopy(self.configuration)
        html_conf['priority'] = dict(PRIORITY)[html_conf['priority']]
        html_conf['coverage_details'] = dict(COVERAGE_DETAILS)[html_conf['coverage_details']]
        html_conf['weight'] = dict(DECISION_WEIGHT)[html_conf['weight']]
        html_conf['cpu_model'] = html_conf['cpu_model'] or '-'
        return html_conf

    def __validate_conf(self, configuration):
        serializer = ConfigurationSerializer(data=configuration)
        serializer.is_valid(raise_exception=True)
        return serializer.data


class StartDecisionData:
    def __init__(self, user, job, base_decision=None):
        self.recommended_mode = settings.DEF_KLEVER_CORE_MODE

        self.decisions = Decision.objects.filter(job=job).order_by('id') \
            .exclude(status=DECISION_STATUS[0][0]).only('id', 'title', 'start_date')

        self.modes = list((m['id'], m['name']) for m in KLEVER_CORE_DEF_MODES)
        if len(self.decisions):
            self.modes.append(('lastconf', _("Other decision's configuration")))
        self.modes.append(('file_conf', _('Use configuration from file')))

        self.base_decision = base_decision
        if self.base_decision:
            self.selected_mode = 'lastconf'
            self.conf = GetConfiguration(base_decision=self.base_decision).configuration
        else:
            self.selected_mode = 'default'
            self.conf = get_default_configuration(user).configuration

        self.need_auth = not SchedulerUser.objects.filter(user=user).exists()

        self.job_sch_err = None
        self.priorities = reversed(PRIORITY)
        self.weight = DECISION_WEIGHT
        self.parallelism = PARALLELISM_PACKS
        self.levels = LOGGING_LEVELS
        self.formatters = DEFAULT_FORMATTER
        self.coverage_details = COVERAGE_DETAILS
        self.schedulers = self.__get_schedulers()

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
        elif self.conf['scheduler'] == SCHEDULER_TYPE[1][0]:
            raise BridgeException(_('The scheduler for tasks is disconnected'))
        return schedulers
