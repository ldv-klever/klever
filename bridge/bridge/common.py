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

import json
import logging
import os
import sys

from datetime import timedelta
from celery.schedules import crontab

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

AUTH_USER_MODEL = 'users.User'
LOGIN_URL = 'users:login'
LOGIN_REDIRECT_URL = 'jobs:tree'

SECRET_KEY = '-u7-e699vgy%8uu_ng%%h68v7k8txs&=(ki+6eh88y-yb9mspw'

INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.humanize',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework', 'rest_framework.authtoken', 'mptt', 'compressor', 'django_celery_results',
    'bridge', 'jobs', 'marks', 'reports', 'service', 'tools', 'users', 'caches'
)

MIDDLEWARE = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'bridge.utils.BridgeMiddlware'
)

AUTHENTICATION_BACKENDS = [
    'bridge.backends.BridgeModelBackend',
]

ROOT_URLCONF = 'bridge.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.tz',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'bridge.utils.klever_version_template_context'
            ],
        },
    },
]

WSGI_APPLICATION = 'bridge.wsgi.application'

# In db.json ENGINE should be either "django.db.backends.postgresql_psycopg2"
DB_SETTINGS_FILE = os.path.join(BASE_DIR, 'bridge', 'db.json')
if os.path.isfile(DB_SETTINGS_FILE):
    DATABASES = {
        'default': json.load(open(DB_SETTINGS_FILE, encoding='utf8')),
    }
else:
    DATABASES = {
        'default': {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": "127.0.0.1",
            "NAME": "klever",
            "USER": "klever",
            "PASSWORD": "klever"
        }
    }

LANGUAGE_CODE = 'en-us'

LANGUAGES = (
    ('ru', 'Русский'),
    ('en-us', 'English'),
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
STATIC_ROOT = os.path.join(BASE_DIR, 'static')
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'compressor.finders.CompressorFinder',
)
COMPRESS_ENABLED = True
COMPRESS_FILTERS = {
    'css': ['compressor.filters.cssmin.rCSSMinFilter'],
    'js': ['compressor.filters.jsmin.JSMinFilter']
}

MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

ALLOWED_HOSTS = ['*']

# Klever core configuration parameters are moved to jobs/configuration.py

DEF_USER = {
    'dataformat': 'hum',  # See bridge.vars.DATAFORMAT for options
    'language': 'en',  # See bridge.vars.LANGUAGES for options
    'timezone': 'Europe/Moscow',  # See pytz.common_timezones for options
    'accuracy': 2,  # 0 - 10
    'assumptions': False,
    'triangles': False,
    'coverage_data': False,
    'declarations_number': 3,
    'notes_level': 2
}

LOGS_DIR = os.path.join(BASE_DIR, 'logs')
LOGGING = {
    'version': 1,
    'filters': {
        'justInfo': {
            "()": 'bridge.utils.InfoFilter',
            'level': logging.INFO
        }
    },
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
            'stream': sys.stdout
        },
        'uncatched': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': os.path.join(LOGS_DIR, 'uncatched-error.log'),
            'formatter': 'with_separator'
        },
        'db-file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': os.path.join(LOGS_DIR, 'db.log'),
            'formatter': 'simple'
        },
        'errors': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': os.path.join(LOGS_DIR, 'error.log'),
            'formatter': 'with_separator'
        },
        'other': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': os.path.join(LOGS_DIR, 'info.log'),
            'formatter': 'simple',
            'filters': ['justInfo']
        },
    },
    'loggers': {
        'django.request': {'handlers': ['console', 'uncatched'], 'level': 'DEBUG', 'propagate': True},
        'bridge': {'handlers': ['errors', 'console', 'other'], 'level': 'INFO', 'propagate': True},
        # 'django.db': {'handlers': ['db-file'], 'level': 'DEBUG', 'propagate': True},
    }
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'NON_FIELD_ERRORS_KEY': 'general',
    'UPLOADED_FILES_USE_URL': False,
    'EXCEPTION_HANDLER': 'bridge.serializers.bridge_exception_handler'
}

MAX_FILE_SIZE = 104857600  # 100MB

# RabbitMQ
# username, password, host are requried, port can be specified
RMQ_SETTINGS_FILE = os.path.join(BASE_DIR, 'bridge', 'rmq.json')

if os.path.isfile(RMQ_SETTINGS_FILE):
    with open(RMQ_SETTINGS_FILE, encoding='utf8') as fp:
        RABBIT_MQ = json.load(fp)
    RABBIT_MQ.setdefault('port', '5672')
    RABBIT_MQ_QUEUE = RABBIT_MQ.get('queue', 'klever')
else:
    RABBIT_MQ = {
        "username": "service",
        "password": "service",
        "host": "localhost",
        "port": "5672"
    }
    RABBIT_MQ_QUEUE = "Klever jobs and tasks"

# Celery, using the same RabbitMQ server
CELERY_BROKER_URL = 'amqp://{username}:{password}@{host}:{port}'.format(**RABBIT_MQ)
CELERY_RESULT_BACKEND = 'django-db'
CELERY_TIMEZONE = 'Europe/Moscow'

CELERY_BEAT_SCHEDULE = {
    'remove-call-logs-every-month': {
        'task': 'tools.tasks.clear_call_logs',
        'schedule': crontab(0, 0, day_of_month='1'),
        'args': (30,)  # 30 days
    },
    'remove-old-job-archives': {
        'task': 'jobs.tasks.clear_old_uploads',
        'schedule': timedelta(hours=1),
        'args': (60,)  # Clear archives older than 60 minutes
    },
    'remove-old-source-code-cache': {
        'task': 'reports.tasks.clear_old_source_code_cache',
        'schedule': timedelta(hours=1),
        'args': (1,)  # Clear cache objects older than 1 hour
    },
}

ENABLE_CALL_LOGS = False
ENABLE_UPLOAD_REPORTS_LOGS = False

UPLOAD_LOG_FILE = 'upload.log'
