from django.conf import settings

from bridge.vars import SCHEDULER_TYPE, TASK_STATUS
from bridge.utils import RMQConnect
from service.models import Scheduler


def populuate_schedulers():
    for sch_type, sch_name in SCHEDULER_TYPE:
        Scheduler.objects.get_or_create(type=sch_type)


class TasksRMQPopulation:
    TASK_RMQ_QUEUES = {
        TASK_STATUS[0][0]: 'tasks_pending',
        TASK_STATUS[1][0]: 'tasks_processing',
        TASK_STATUS[2][0]: 'tasks_finished',
        TASK_STATUS[3][0]: 'tasks_error',
        TASK_STATUS[4][0]: 'tasks_cancelled'
    }

    def __init__(self):
        self._exchange = settings.RABBIT_MQ['tasks_exchange']
        self.__populate()

    def __populate(self):
        with RMQConnect() as channel:
            channel.exchange_declare(exchange=self._exchange, exchange_type='direct')
            for task_status, queue_name in self.TASK_RMQ_QUEUES.items():
                channel.queue_declare(queue=queue_name, durable=True)
                channel.queue_bind(exchange=self._exchange, queue=queue_name, routing_key=task_status)
