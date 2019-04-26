from bridge.vars import SCHEDULER_TYPE
from service.models import Scheduler


def populuate_schedulers():
    for sch_type, sch_name in SCHEDULER_TYPE:
        Scheduler.objects.get_or_create(type=sch_type)
