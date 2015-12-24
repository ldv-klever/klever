# -*- coding: utf-8 -*-

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LOGIN_URL = '/users/signin/'

SECRET_KEY = '-u7-e699vgy%8uu_ng%%h68v7k8txs&=(ki+6eh88y-yb9mspw'

# TODO: switch value to False when everything will work fine.
DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'users', 'jobs', 'marks', 'reports', 'service', 'tools'
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
            'debug': DEBUG
        },
    },
]

WSGI_APPLICATION = 'bridge.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'OPTIONS': {'read_default_file': os.path.join(BASE_DIR, 'bridge', 'mysql-db.cnf')},
    }
}

LANGUAGE_CODE = 'en-us'

LANGUAGES = (
    ('ru', 'Русский'),
)
LOCALE_PATHS = (
    os.path.join(BASE_DIR,  'locale'),
)
DEFAULT_LANGUAGE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

STATIC_URL = '/static/'

STATIC_ROOT = os.path.join(BASE_DIR, 'static')

MEDIA_URL = '/media/'

MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEF_KLEVER_CORE_RESTRICTIONS = {
    'max_ram': '2.0',
    'max_cpus': '2',
    'max_disk': '100.0',
    'max_wall_time': '',
    'max_cpu_time': '',
    'cpu_model': '',
}

DEF_LINUX_KERNEL_BUILD_PARALLELISM = 1.0

DEF_KLEVER_CORE_FORMATTERS = {
    'console': "%(name)s %(levelname)5s> %(message)s",
    'file': "%(asctime)s (%(filename)s:%(lineno)03d) %(name)s %(levelname)5s> %(message)s"
}

DEF_KLEVER_CORE_CONFIGURATION = {
    'debug': True,
    'allow_local_dir': True,  # Allow use of local source directories
    'priority': 'IDLE',  # See bridge.vars.PRIORITY for more options
    'avtg_priority': 'balance'  # See service.utils.AVTG_PRIORITY for more options
}

DEF_USER_DATAFORMAT = 'hum'  # See bridge.vars.DATAFORMAT for options

DEF_USER_LANGUAGE = 'en'  # See bridge.vars.LANGUAGES for options

DEF_USER_TIMEZONE = 'Europe/Moscow'  # See pytz.common_timezones for options

DEF_USER_ACCURACY = 2  # 0 - 10
