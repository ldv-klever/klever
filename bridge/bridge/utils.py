import os
import time
import hashlib
import traceback
from django.conf import settings
from bridge.settings import DEBUG
from django.utils.timezone import now

BLOCKER = {}
GROUP_BLOCKER = {}
BRIDGE_ERROR_LOG = 'error.log'
BRIDGE_LOG = 'bridge.log'


def print_err(message):
    with open(os.path.join(settings.MEDIA_ROOT, BRIDGE_ERROR_LOG), mode='a') as fp:
        fp.write('=' * 30 + 'ERROR' + '=' * 30 + '\n')
        traceback.print_stack(file=fp)
        fp.close()

    if DEBUG:
        print(message)


def print_log():
    with open(os.path.join(settings.MEDIA_ROOT, BRIDGE_LOG), mode='a') as fp:
        fp.write('=' * 30 + '\n')
        traceback.print_stack(file=fp)
        fp.close()


def print_exec_time(f):
    def wrapper(*args, **kwargs):
        start = now()
        res = f(*args, **kwargs)
        print_err('%s: %s' % (f.__name__, now() - start))
        return res
    return wrapper


def unparallel(f):

    def wait_other(*args, **kwargs):
        if f.__name__ not in BLOCKER:
            BLOCKER[f.__name__] = 0
        while BLOCKER[f.__name__] == 1:
            time.sleep(0.1)
        BLOCKER[f.__name__] = 1
        res = f(*args, **kwargs)
        BLOCKER[f.__name__] = 0
        return res
    return wait_other


def unparallel_group(groups):
    def unparallel_inner(f):

        def block_access():
            for g in groups:
                if g not in GROUP_BLOCKER:
                    GROUP_BLOCKER[g] = 0
                if GROUP_BLOCKER[g] == 1:
                    return False
            return True

        def change_block(status):
            for g in groups:
                GROUP_BLOCKER[g] = status

        def wait(*args, **kwargs):
            while not block_access():
                time.sleep(0.1)
            change_block(1)
            res = f(*args, **kwargs)
            change_block(0)
            return res

        return wait

    return unparallel_inner


def file_checksum(f, block_size=2**20):
    md5 = hashlib.md5()
    while True:
        data = f.read(block_size)
        if not data:
            break
        md5.update(data)
    f.seek(0)
    return md5.hexdigest()
