#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
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

import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LOGIN_URL = '/users/signin/'

SECRET_KEY = '-u7-e699vgy%8uu_ng%%h68v7k8txs&=(ki+6eh88y-yb9mspw'

INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.humanize',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'jobs',
    'marks',
    'reports',
    'service',
    'tools',
    'users',
)

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.security.SecurityMiddleware',
)

ROOT_URLCONF = 'bridge.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.tz',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'bridge.wsgi.application'

# In db.json ENGINE should be either "django.db.backends.postgresql_psycopg2" or "django.db.backends.mysql"
DATABASES = {
    'default': json.load(open(os.path.join(BASE_DIR, 'bridge', 'db.json'), encoding='utf8')),
}

LANGUAGE_CODE = 'en-us'

LANGUAGES = (
    ('ru', 'Русский'),
)
LOCALE_PATHS = (
    os.path.join(BASE_DIR, 'locale'),
)
DEFAULT_LANGUAGE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

STATIC_URL = '/static/'

MEDIA_URL = '/media/'

MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Definitions of Klever Core log formatters (see documentation for Python 3 logging for details)
# WARNING!!! Change also KLEVER_CORE_FORMATTERS from bridge.vars when you change these packs
KLEVER_CORE_LOG_FORMATTERS = {
    'brief': "%(name)s %(levelname)5s> %(message)s",
    'detailed': "%(asctime)s (%(filename)s:%(lineno)03d) %(name)s %(levelname)5s> %(message)s",
    'paranoid': "%(asctime)s (%(filename)s:%(lineno)03d) %(name)s (%(process)d) %(levelname)5s> %(message)s",
}

# Each Klever Core parallelism pack represents set of numbers of parallel threads/processes for following actions:
#   sub-jobs processing,
#   build,
#   tasks generation.
# WARNING!!! Change also KLEVER_CORE_PARALLELISM from bridge.vars when you change these packs
KLEVER_CORE_PARALLELISM_PACKS = {
    'sequential': (1, 1, 1),
    'slow': (1, 2, 2),
    'quick': (1, 1.0, 1.0),
    'very quick': (1, 2.0, 2.0),
}

LOGGING_LEVELS = ['NONE', 'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET']

# Each Klever Core mode represents sets of values for following sets of attributes:
#   scheduling:
#     job priority - see bridge.vars.PRIORITY for available values,
#     task scheduler - see bridge.vars.SCHEDULER_TYPE for available values,
#     abstract task generation priority - see service.utils.AVTG_PRIORITY for available values,
#   parallelism pack - one of packs from KLEVER_CORE_PARALLELISM_PACKS,
#   limits:
#     memory size - in GB,
#     number of CPU cores,
#     disk memory size - in GB,
#     CPU model,
#     CPU time - in minutes,
#     wall time - in minutes,
#   logging:
#     console log level - see documentation for Python 3 logging for available values,
#     console log formatter - one of formatters from KLEVER_CORE_LOG_FORMATTERS,
#     file log level - like console log level,
#     file log formatter - like console log formatter,
#   keep intermediate files - True or False,
#   upload input files of static verifiers - True or False,
#   upload other intermediate files - True or False,
#   allow local source directories use - True or False,
#   ignore other instances - True or False,
#   ignore failed sub-jobs - True of False.
#   weight of decision - '0' for full-weight and '1' for lightweight jobs.
# WARNING!!! Change also START_JOB_DEFAULT_MODES from bridge.vars when you change these packs
DEF_KLEVER_CORE_MODES = [
    {
        'production': [
            ['LOW', '0', 'balance'],
            'slow',
            [1.0, 0, 100.0, None, None, None],
            ['NONE', 'brief', 'NONE', 'brief'],
            False, False, False, False, False, False, '1'
        ]
    },
    {
        'development': [
            ['IDLE', '0', 'balance'],
            'quick',
            [1.0, 0, 100.0, None, None, None],
            ['INFO', 'detailed', 'DEBUG', 'detailed'],
            True, True, False, True, True, True, '0'
        ]
    },
    {
        'paranoid development': [
            ['IDLE', '0', 'balance'],
            'quick',
            [1.0, 0, 100.0, None, None, None],
            ['INFO', 'detailed', 'DEBUG', 'paranoid'],
            True, True, True, True, True, True, '0'
        ]
    },
]

DEF_USER = {
    'dataformat': 'hum',  # See bridge.vars.DATAFORMAT for options
    'language': 'en',  # See bridge.vars.LANGUAGES for options
    'timezone': 'Europe/Moscow',  # See pytz.common_timezones for options
    'accuracy': 2,  # 0 - 10
    'assumptions': False,
    'triangles': False,
    'coverage_data': False
}

LOGGING = {
    'version': 1,
    'formatters': {
        'with_separator': {
            'format': '=' * 50 + '\n[%(asctime)s] %(message)s',
            'datefmt': "%d.%b.%Y %H:%M:%S"
        },
        'simple': {
            'format': '[%(asctime)s] %(message)s',
            'datefmt': "%d.%b.%Y %H:%M:%S"
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
        },
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': os.path.join(MEDIA_ROOT, 'internal-server-error.log'),
            'formatter': 'with_separator'
        },
        'errors': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': os.path.join(MEDIA_ROOT, 'error.log'),
            'formatter': 'with_separator'
        },
        'other': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': os.path.join(MEDIA_ROOT, 'info.log'),
            'formatter': 'simple'
        },
    },
    'loggers': {
        'django.request': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': True
        },
        'bridge': {
            'handlers': ['errors', 'console', 'other'],
            'level': 'INFO',
            'propagate': True
        },
    }
}

MAX_FILE_SIZE = 104857600  # 100MB

ENABLE_SAFE_MARKS = False
