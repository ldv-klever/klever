# -*- coding: utf-8 -*-

import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LOGIN_URL = '/users/signin/'

SECRET_KEY = '-u7-e699vgy%8uu_ng%%h68v7k8txs&=(ki+6eh88y-yb9mspw'

LOGGING = {
    'version': 1,
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django.request': {
            'handlers': ['console'],
            'propagate': True,
            'level': 'DEBUG',
        },
    },
}

INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
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
    'default': json.load(open(os.path.join(BASE_DIR, 'bridge', 'db.json'))),
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
_KLEVER_CORE_LOG_FORMATTERS = {
    'brief': "%(name)s %(levelname)5s> %(message)s",
    'detailed': "%(asctime)s (%(filename)s:%(lineno)03d) %(name)s %(levelname)5s> %(message)s",
    'paranoid': "%(asctime)s (%(filename)s:%(lineno)03d) %(name)s (%(process)d) %(levelname)5s> %(message)s",
}

# Each Klever Core parallelism pack represents set of numbers of parallel threads/processes for following actions:
#   build,
#   tasks generation.
_KLEVER_CORE_PARALLELISM_PACKS = {
    'sequantial': (1, 1),
    'slow': (2, 2),
    'fast': (1.0, 1.0),
    'very fast': (2.0, 2.0),
}

# Each Klever Core mode represents sets of values for following sets of attributes:
#   scheduling:
#     job priority - see bridge.vars.PRIORITY for available values,
#     task scheduler - see bridge.vars.SCHEDULER_TYPE for available values,
#     abstract task generation priority - see service.utils.AVTG_PRIORITY for available values,
#   parallism pack - one of packs from _KLEVER_CORE_PARALLELISM_PACKS,
#   limits:
#     memory size - in GB,
#     number of CPU cores,
#     disk memory size - in GB,
#     CPU model,
#     CPU time - in minutes,
#     wall time - in minutes,
#   logging:
#     console log level - see documentation for Python 3 logging for available values,
#     console log formatter - one of formatters from _KLEVER_CORE_LOG_FORMATTERS,
#     file log level - like console log level,
#     file log formatter - like console log formatter,
#   keep intermediate files - True or False,
#   upload input files of static verifiers - True or False,
#   upload other intermediate files - True or False,
#   allow local source directories use - True or False,
#   ignore another instance of Klever Core - True or False.
DEF_KLEVER_CORE_MODES = [
    {
        'production': (
            ('LOW', 'Klever', 'balance',),
            'slow',
            (1.0, 2, 100.0, '', 0, 0,),
            ('WARNING', 'brief', 'INFO', 'brief',),
            False, False, False, False, False,
        )
    },
    {
        'development': (
            ('IDLE', 'Klever', 'balance',),
            'fast',
            (1.0, 1.0, 100.0, '', 0, 0,),
            ('INFO', 'detailed', 'DEBUG', 'detailed',),
            True, True, False, True, True,
        )
    },
    {
        'paranoid development': (
            ('IDLE', 'Klever', 'balance',),
            'fast',
            (1.0, 1.0, 100.0, '', 0, 0,),
            ('INFO', 'detailed', 'DEBUG', 'paranoid',),
            True, True, True, True, True,
        )
    },
]

DEF_USER = {
    'dataformat': 'hum',  # See bridge.vars.DATAFORMAT for options
    'language': 'en',  # See bridge.vars.LANGUAGES for options
    'timezone': 'Europe/Moscow',  # See pytz.common_timezones for options
    'accuracy': 2,  # 0 - 10
}
