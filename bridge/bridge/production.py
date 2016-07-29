from bridge.common import *

# TODO: switch value to False when everything will work fine.
TEMPLATES[0]['OPTIONS']['debug'] = DEBUG = True

ALLOWED_HOSTS = ['*']

STATIC_ROOT = os.path.join(BASE_DIR, 'static')
# STATICFILES_DIRS = (os.path.join(BASE_DIR, 'static'),)

DEF_KLEVER_CORE_MODE = 'production'

LIGHTWEIGHTNESS = True
