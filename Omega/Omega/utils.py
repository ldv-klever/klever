from Omega.settings import DEBUG

BLOCKER = {}


def print_err(message):
    if DEBUG:
        print(message)


def unparallel(f):
    from datetime import datetime
    import time

    def wait_other(*args, **kwargs):
        t1 = datetime.now()
        if f.__name__ not in BLOCKER:
            BLOCKER[f.__name__] = 0
        while BLOCKER[f.__name__] == 1:
            if (datetime.now() - t1).seconds > 10:
                BLOCKER[f.__name__] = 0
            time.sleep(0.1)
        BLOCKER[f.__name__] = 1
        res = f(*args, **kwargs)
        BLOCKER[f.__name__] = 0
        return res
    return wait_other
