#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import os
import time
import logging
import pika

from klever.core.utils import time_units_converter
from klever.scheduler.server import Server
from klever.scheduler.utils import memory_units_converter
from klever.scheduler.utils.bridge import BridgeError
from klever.scheduler.schedulers.docker_runner import Docker


class SchedulerException(RuntimeError):
    """Exception is used to determine when task or job fails but not scheduler."""


class DockerWorker:
    """Class provide general scheduler API."""

    def __init__(self, conf, logger, work_dir):
        """
        Get configuration and prepare working directory.

        :param conf: Dictionary with relevant configuration.
        :param logger: Logger object.
        :param work_dir: Path to the working directory.
        """
        # todo: remove useless data
        self.conf = conf
        self.logger = logger
        self.work_dir = work_dir
        self.runner = None
        self.server = None
        self._current = {}
        self._nodes = None
        self._tools = None
        self._iteration_period = 0.5
        self.production = self.conf["scheduler"].setdefault("production", False)

        logging.getLogger("pika").setLevel(logging.WARNING)
        self.init_scheduler()

        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=self.conf["Klever jobs and tasks queue"]["host"],
                credentials=pika.credentials.PlainCredentials(self.conf["Klever jobs and tasks queue"]["username"],
                                                              self.conf["Klever jobs and tasks queue"]["password"]))
        )
        self.channel = connection.channel()
        self.channel.queue_declare(queue=self.conf["Klever jobs and tasks queue"]["name"], durable=True)

    def init_scheduler(self):
        """
        Initialize scheduler completely. This method should be called both at constructing stage and scheduler
        reinitialization. Thus, all object attribute should be cleaned up and set as it is a newly created object.
        """
        self._current = {}
        self._nodes = None
        self._tools = None
        self.server = Server(self.logger, self.conf["Klever Bridge"], os.path.join(self.work_dir, "requests"))

        # Check configuration completeness
        self.logger.debug("Check whether configuration contains all necessary data")

        # Initialize interaction
        self.server.register(Docker.scheduler_type())

        self.runner = Docker(self.conf, self.logger, self.work_dir, self.server)
        self.runner.init()
        self.runner.update_tools()
        self.runner.update_nodes()

        self.logger.info("Scheduler base initialization has been successful")

    @staticmethod
    def _add_missing_restrictions(collection):
        """
        If resource limits are incomplete the method adds to given json all necessary fields filled with zeroes.

        :param collection: 'resource limits' dictionary from a task description or job configuration.
        """
        if len(collection.keys()) == 0:
            raise SchedulerException("Resource limitations are missing: upload correct tasks.json file and properly "
                                     "set job resource limitations")

        for tag in ['memory size', 'number of CPU cores', 'disk memory size']:
            if tag not in collection or collection[tag] is None:
                collection[tag] = 0
        if 'CPU model' not in collection:
            collection['CPU model'] = None

        # Make unit translation
        try:
            for tag in (m for m in ("memory size", "disk memory size")
                        if m in collection and collection[m] is not None):
                collection[tag] = memory_units_converter(collection[tag])[0]
            for tag in (t for t in ("wall time", "CPU time") if t in collection and collection[t] is not None):
                collection[tag] = time_units_converter(collection[tag])[0]
        except Exception as exc:
            raise SchedulerException(
                'Cannot interpret {} resource limitations: {!r}'.format(tag, collection[tag])) from exc

    def _job_status(self, status):
        job_map = {
            '0': 'NOT SOLVED',
            '1': 'PENDING',
            '2': 'PROCESSING',
            '3': 'SOLVED',
            '4': 'FAILED',
            '5': 'CORRUPTED',
            '6': 'CANCELLING',
            '7': 'CANCELLED',
            '8': 'TERMINATED',
            '9': 'REFINED'
        }

        if len(status) == 1:
            # This is digital status and we can return the word
            return job_map[status]
        # Else
        return tuple(job_map.keys())[tuple(job_map.values()).index(status)]


class JobWorker(DockerWorker):

    def _get_one_job(self):
        for method, _, body in self.channel.consume(self.conf["Klever jobs and tasks queue"]["name"],
                                                    inactivity_timeout=1):
            if not body or not method:
                # empty queue
                return None, None

            # Just forward to main loop all data. This can be done faster but it will require additional locks and sync
            data = body.decode('utf-8').split(' ')
            if len(data) == 4:
                if data[0] == 'job':
                    self.logger.info("Get new job {} with {}".format(data[1], self._job_status(data[2])))
                    if self._current and data[1] == self._current['id']:
                        # Update of current job
                        self.channel.basic_ack(method.delivery_tag)
                        return None, self._job_status(data[2])
                    if not self._current and data[2] == '1':
                        # New pending job
                        self.channel.basic_ack(method.delivery_tag)
                        return data[1], None
                    if data[2] == 'PROCESSING':
                        # Ignore for now
                        self.channel.basic_ack(method.delivery_tag)
                        continue
                    if not self._current:
                        # TODO: Ignore all statuses with empty job
                        # In case of several workers it is incorrect
                        # But currently, it just avoids infinite missed messages
                        self.channel.basic_ack(method.delivery_tag)
                        continue
                self.channel.basic_nack(method.delivery_tag, requeue=True)
            else:
                # Just ignore the message
                self.channel.basic_ack(method.delivery_tag)
            return None, None

    def launch(self):
        """
        Start scheduler loop. This is an infinite loop that exchange data with Bridge to fetch new jobs and tasks and
        upload result of solution previously received tasks and jobs. After data exchange it prepares for solution
        new jobs and tasks, updates statuses of running jobs and tasks and schedule for solution pending ones.
        This is just an algorithm, and all particular logic and resource management should be implemented in classes
        that inherits this one.
        """

        self.logger.info("Start scheduler loop")
        while True:
            if self._current and self.runner.process_job_result(self._current['id'], self._current, []):
                if self._current['status'] == 'FINISHED' and not self._current.get('error'):
                    self.server.submit_job_status(self._current['id'], self._job_status('SOLVED'))
                elif self._current.get('error'):
                    self.server.submit_job_error(self._current['id'], self._current['error'])
                else:
                    raise NotImplementedError("Cannot determine status of the job {!r}".format(self._current['id']))
                self._current = {}

            identifier, status = self._get_one_job()
            if identifier:
                self.logger.debug("New status of job {!r} is {!r}".format(identifier, status))
                self.add_new_pending_job(identifier)
                self.logger.info("Going to start a new job")

                started = self.runner.solve_job(self._current['id'], self._current)
                if started:
                    self._current['status'] = 'PROCESSING'

            elif status in ('FAILED', 'CORRUPTED', 'CANCELLED'):
                self.runner.cancel_job(self._current['id'], self._current, [])
                self._current = {}
            elif status == 'CANCELLING':
                self.runner.cancel_job(self._current['id'], self._current, [])
                self.server.submit_job_status(self._current['id'], self._job_status('CANCELLED'))
                for task_id, status in self.server.get_job_tasks(self._current['id']):
                    if status in ('PENDING', 'PROCESSING'):
                        self.server.submit_task_status(task_id, 'CANCELLED')
                self._current = {}
            elif status:
                raise NotImplementedError('Unknown job status {!r}'.format(status))

            time.sleep(self._iteration_period)

    def terminate(self):
        """Abort solution of all running tasks and any other actions before termination."""
        if self._current and self._current['status'] in ["PENDING", "PROCESSING"]:
            self.server.submit_job_error(self._current['id'], 'Scheduler has been terminated or reset')

        # Do final uninitializations
        self.runner.terminate()

    def add_new_pending_job(self, identifier):
        """
        Add new pending job and prepare its description.

        :param identifier: Job identifier string.
        """
        job_conf = self.server.pull_job_conf(identifier)
        if not job_conf:
            self.server.submit_job_error(identifier, 'Failed to download configuration')
            return
        if 'tasks' not in job_conf:
            self.server.submit_job_error(identifier, 'Job has not tasks.json file with resource limits')
            return

        job_conf['configuration']['identifier'] = identifier
        job_conf['configuration']['task resource limits'] = job_conf['tasks']
        # TODO: Get Verifier Cloud login and password

        self.logger.info("Prepare new job {} before launching".format(identifier))

        # Check and set necessary restrictions for further scheduling
        for collection in [job_conf['configuration']["resource limits"],
                           job_conf['configuration']['task resource limits']]:
            try:
                self._add_missing_restrictions(collection)
            except SchedulerException as err:
                self._current = {
                    "id": identifier,
                    "status": "ERROR",
                    "error": str(err)
                }
                break

        self._current = {
            "id": identifier,
            "status": "PENDING",
            "configuration": job_conf['configuration']
        }


class TaskWorker(DockerWorker):

    def _get_one_task(self):
        for method, _, body in self.channel.consume(self.conf["Klever jobs and tasks queue"]["name"],
                                                    inactivity_timeout=1):
            if not body or not method:
                # empty queue
                return None, None

            # Just forward to main loop all data. This can be done faster but it will require additional locks and sync
            data = body.decode('utf-8').split(' ')
            if len(data) == 4:
                if data[0] == 'task':
                    # self.logger.info("Get new task {} with {}".format(data[1], data[2]))
                    # self.logger.info("Current task: {}".format(self._task))
                    if data[2] == 'FINISHED' or data[2] == 'PROCESSING':
                        # Ignore for now
                        self.channel.basic_ack(method.delivery_tag)
                        continue
                    if self._current and data[1] == self._current['id']:
                        # Update of current task
                        self.channel.basic_ack(method.delivery_tag)
                        return None, data[2]
                    if not self._current and data[2] == 'PENDING':
                        # New pending task
                        self.channel.basic_ack(method.delivery_tag)
                        return data[1], None
                    # if data[1] in self._finished_tasks:
                    #     # ignore finished
                    #     self.channel.basic_ack(method.delivery_tag)
                    #     continue
                self.channel.basic_nack(method.delivery_tag, requeue=True)

            else:
                # Just ignore the message
                self.channel.basic_ack(method.delivery_tag)
            return None, None

    def launch(self):
        """
        Start scheduler loop. This is an infinite loop that exchange data with Bridge to fetch new jobs and tasks and
        upload result of solution previously received tasks and jobs. After data exchange it prepares for solution
        new jobs and tasks, updates statuses of running jobs and tasks and schedule for solution pending ones.
        This is just an algorithm, and all particular logic and resource management should be implemented in classes
        that inherits this one.
        """

        self.logger.info("Start scheduler loop")
        while True:
            if self._current and self.runner.process_task_result(self._current['id'], self._current):
                if self._current['status'] == 'FINISHED' and not self._current.get('error'):
                    self.server.submit_task_status(self._current['id'], 'FINISHED')
                    self._current = {}
                elif self._current.get('error'):
                    self.server.submit_task_error(self._current['id'], self._current['error'])
                else:
                    raise NotImplementedError("Cannot determine status of the task {!r}: {!r}".
                                              format(self._current['id'], self._current["status"]))

            identifier, status = self._get_one_task()
            if identifier:
                self.add_new_pending_task(identifier)
                # Schedule new tasks
                self.logger.info("Going to start new task")
                started = self.runner.solve_task(identifier, self._current)
                if not started and self._current['status'] == 'ERROR':
                    self.server.submit_task_error(identifier, self._current['error'])
                    continue

                self.server.submit_task_status(identifier, 'PROCESSING')

            elif status in ('FINISHED', 'ERROR', 'CANCELLED'):
                if self.runner.is_solving(self._current):
                    self.runner.cancel_task(identifier, self._current)
                self._current = {}
            elif status:
                raise NotImplementedError('Unknown task status {!r}'.format(status))

            time.sleep(self._iteration_period)

    def terminate(self):
        """Abort solution of all running tasks and any other actions before termination."""
        # Note here that some schedulers can solve tasks of jobs which run elsewhere
        if self._current["status"] in ["PENDING", "PROCESSING"]:
            self.runner.cancel_task(self._current['id'], self._current)

        # Terminate tasks
        self.cancel_all_tasks()

        # Do final uninitializations
        self.runner.terminate()

    def add_new_pending_task(self, identifier):
        """
        Add new pending task and prepare its description.

        :param identifier: Task identifier string.
        """
        task_conf = self.server.pull_task_conf(identifier)
        if not task_conf:
            self.server.submit_task_error(identifier, 'Failed to download configuration')
            return

        # Check job status
        status = self._job_status(self.server.get_job_status(task_conf['description']['job id']))
        if status != 'PROCESSING':
            # Likely we are cancelling
            self.server.submit_task_error(identifier,
                                          "Try to solve task {} for a job with status {}".format(
                                              identifier, status))
            return

        self.logger.info("Add new PENDING task {}".format(identifier))
        self._current = {
            "id": identifier,
            "status": "PENDING",
            "description": task_conf['description'],
            "priority": task_conf['description']["priority"]
        }

        self.logger.debug("Prepare new task {!r} before launching".format(identifier))

    def cancel_all_tasks(self):
        """Cancel and delete all jobs and tasks before terminating or restarting scheduler."""
        # Check all tasks and cancel them
        tasks = self.server.get_all_tasks()
        for identifier, status in tasks:
            # TODO: Remove this when Bridge will not raise an error 'Job is not solving'
            if status in ('PENDING', 'PROCESSING'):
                self.server.submit_task_error(identifier, 'Scheduler terminated or reset')
            try:
                self.server.delete_task(identifier)
            except BridgeError as err:
                self.logger.warning('Bridge reports an error on attempt to delete task {}: {!r}'.
                                    format(identifier, err))
