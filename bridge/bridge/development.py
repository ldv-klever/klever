from bridge.common import *

TEMPLATES[0]['OPTIONS']['debug'] = DEBUG = True

ALLOWED_HOSTS = []

STATICFILES_DIRS = (os.path.join(BASE_DIR, 'static'),)
