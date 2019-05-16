from django.conf import settings

from bridge.vars import SCHEDULER_TYPE, TASK_STATUS
from bridge.utils import RMQConnect
from service.models import Scheduler


def populuate_schedulers():
    for sch_type, sch_name in SCHEDULER_TYPE:
        Scheduler.objects.get_or_create(type=sch_type)


class TasksRMQPopulation:
    def __init__(self):
        with RMQConnect() as channel:
            channel.queue_declare(queue=settings.RABBIT_MQ['tasks_queue'], durable=True)
