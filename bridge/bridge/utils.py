import time
from django.utils.timezone import now
from bridge.settings import DEBUG

BLOCKER = {}
GROUP_BLOCKER = {}


def print_err(message):
    if DEBUG:
        print(message)


def unparallel(f):

    def wait_other(*args, **kwargs):
        t1 = now()
        if f.__name__ not in BLOCKER:
            BLOCKER[f.__name__] = 0
        while BLOCKER[f.__name__] == 1:
            # Max waiting time is 10 seconds
            if (now() - t1).seconds > 10:
                BLOCKER[f.__name__] = 0
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
            t1 = now()
            while not block_access():
                # Max waiting time is 10 seconds
                if (now() - t1).seconds > 10:
                    change_block(0)
                time.sleep(0.1)
            change_block(1)
            res = f(*args, **kwargs)
            change_block(0)
            return res

        return wait

    return unparallel_inner
