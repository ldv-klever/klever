import time
import django.db.backends.utils
from django.db import OperationalError
from bridge.settings import DATABASES


original = django.db.backends.utils.CursorWrapper.execute


# Fix https://forge.ispras.ru/issues/7146.
def execute_wrapper(*args, **kwargs):
    if args[0].db.vendor == 'mysql':
        while True:
            try:
                return original(*args, **kwargs)
            except OperationalError as e:
                from MySQLdb.constants.ER import LOCK_DEADLOCK
                if e.args[0] != LOCK_DEADLOCK:
                    raise e
                time.sleep(0.1)
    else:
        return original(*args, **kwargs)

django.db.backends.utils.CursorWrapper.execute = execute_wrapper
