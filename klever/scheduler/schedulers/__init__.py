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
import pika
import queue
import logging
import traceback
import threading
import sys

from klever.scheduler.server import Server
from klever.scheduler.utils.bridge import BridgeError
from klever.scheduler.utils import sort_priority, time_units_converter, memory_units_converter


class SchedulerException(RuntimeError):
    """Exception is used to determine when task or job fails but not scheduler."""


class ListeningThread(threading.Thread):
    conf = None

    def __init__(self, local_queue, accept_jobs, accept_tag, cnf=None):
        super().__init__()
        self._is_interrupted = False
        self.accept_jobs = accept_jobs
        self.accept_tag = accept_tag
        if cnf:
            self.conf = cnf
        self._queue = local_queue

    def stop(self):
        self._is_interrupted = True

    def run(self):
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=self.conf["host"],
                credentials=pika.credentials.PlainCredentials(self.conf["username"], self.conf["password"]))
        )
        channel = connection.channel()
        channel.queue_declare(queue=self.conf["name"], durable=True)
        for method, _, body in channel.consume(self.conf["name"], inactivity_timeout=1):
            if self._is_interrupted:
                break
            if not body or not method:
                continue

            # Just forward to main loop all data. This can be done faster but it will require additional locks and sync
            data = body.decode('utf-8').split(' ')
            if len(data) == 4:
                if (data[0] == 'job' and self.accept_jobs) or (data[0] == 'task' and data[-1] == self.accept_tag):
                    channel.basic_ack(method.delivery_tag)
                    self._queue.put(body)
                else:
                    channel.basic_nack(method.delivery_tag, requeue=True)
            else:
                # Just ignore the message
                channel.basic_ack(method.delivery_tag)
                continue


class Scheduler:
    """Class provide general scheduler API."""

    def __init__(self, conf, logger, work_dir, runner_class):
        """
        Get configuration and prepare working directory.

        :param conf: Dictionary with relevant configuration.
        :param logger: Logger object.
        :param work_dir: Path to the working directory.
        :param runner_class: Runner class to work with hardware or cloud.
        """
        # todo: remove useless data
        self.conf = conf
        self.logger = logger
        self.work_dir = work_dir
        self.runner = None
        self.server = None
        self._runner_class = runner_class
        self._tasks = {}
        self._jobs = {}
        self._nodes = None
        self._tools = None
        self._iteration_period = 0.5
        self._server_queue = None
        self._channel = None
        self._listening_thread = None
        self._loop_thread = None
        self.production = self.conf["scheduler"].setdefault("production", False)

        logging.getLogger("pika").setLevel(logging.WARNING)
        self.init_scheduler()

    def init_scheduler(self):
        """
        Initialize scheduler completely. This method should be called both at constructing stage and scheduler
        reinitialization. Thus, all object attribute should be cleaned up and set as it is a newly created object.
        """
        self._tasks = {}
        self._jobs = {}
        self._nodes = None
        self._tools = None
        self._server_queue = queue.Queue()
        self.server = Server(self.logger, self.conf["Klever Bridge"], os.path.join(self.work_dir, "requests"))

        _old_tasks_status = None
        _old_jobs_status = None

        # Check configuration completeness
        self.logger.debug("Check whether configuration contains all necessary data")

        # Initialize interaction
        self.server.register(self._runner_class.scheduler_type())

        self.runner = self._runner_class(self.conf, self.logger, self.work_dir, self.server)
        self.runner.init()

        # Create listening thread
        if self._listening_thread and not self._listening_thread.is_alive():
            self._listening_thread.stop()
            self._listening_thread.join()
        self._listening_thread = ListeningThread(self._server_queue, self._runner_class.accept_jobs,
                                                 self._runner_class.accept_tag,
                                                 self.conf["Klever jobs and tasks queue"])
        self._listening_thread.start()

        # Before we proceed lets check all existing jobs
        self._check_jobs_status()

        self.logger.info("Scheduler base initialization has been successful")

    def launch(self):
        """
        Start scheduler loop. This is an infinite loop that exchange data with Bridge to fetch new jobs and tasks and
        upload result of solution previously received tasks and jobs. After data exchange it prepares for solution
        new jobs and tasks, updates statuses of running jobs and tasks and schedule for solution pending ones.
        This is just an algorithm, and all particular logic and resource management should be implemented in classes
        that inherits this one.
        """

        def nth_iteration(n):
            return iteration_number % n == 0

        self.logger.info("Start scheduler loop")
        iteration_number = 0
        while True:
            try:
                if iteration_number == 10000:
                    iteration_number = 0
                else:
                    iteration_number += 1

                if not self._listening_thread.is_alive():
                    raise ValueError("Listening thread is not alive, terminating")

                while True:
                    msg = self._server_queue.get_nowait()
                    kind, identifier, status, _ = msg.decode('utf-8').split(' ')
                    if kind == 'job':
                        self.logger.debug("New status of job {!r} is {!r}".format(identifier, status))
                        sch_status = self._jobs.get(identifier, {}).get('status', None)
                        status = self._job_status(status)

                        if status == 'PENDING':
                            if identifier in self._jobs and sch_status not in ('PROCESSING', 'PENDING'):
                                self.logger.warning('Job {!r} is still tracking and has status {!r}'.
                                                    format(identifier, sch_status))
                                del self._jobs[identifier]
                            self.add_new_pending_job(identifier)
                        elif status == 'PROCESSING':
                            if sch_status in ('PENDING', 'PROCESSING'):
                                self._jobs[identifier]['status'] = 'PROCESSING'
                            elif identifier not in self._jobs:
                                self.server.submit_job_error(identifier, 'Job {!r} is not tracked by the scheduler'.
                                                             format(identifier))
                            else:
                                self.logger.warning('Job {!r} already has status {!r}'.format(identifier, sch_status))
                        elif status in ('FAILED', 'CORRUPTED', 'CANCELLED'):
                            if identifier in self._jobs and self.runner.is_solving(self._jobs[identifier]):
                                self.logger.warning('Job {!r} is running but got status '.format(identifier))
                                self.runner.cancel_job(identifier, self._jobs[identifier],
                                                       self.relevant_tasks(identifier))
                            if identifier in self._jobs:
                                del self._jobs[identifier]
                        elif status == 'CORRUPTED':
                            # CORRUPTED
                            if identifier in self._jobs and self.runner.is_solving(self._jobs[identifier]):
                                self.logger.info('Job {!r} was corrupted'.format(identifier))
                                self.runner.cancel_job(identifier, self._jobs[identifier],
                                                       self.relevant_tasks(identifier))
                            if identifier in self._jobs:
                                del self._jobs[identifier]
                        elif status == 'CANCELLING':
                            # CANCELLING
                            if identifier in self._jobs and self.runner.is_solving(self._jobs[identifier]):
                                self.runner.cancel_job(identifier, self._jobs[identifier],
                                                       self.relevant_tasks(identifier))
                            self.server.submit_job_status(identifier, self._job_status('CANCELLED'))
                            for task_id, status in self.server.get_job_tasks(identifier):
                                if status in ('PENDING', 'PROCESSING'):
                                    self.server.submit_task_status(task_id, 'CANCELLED')
                            if identifier in self._jobs:
                                del self._jobs[identifier]
                        else:
                            raise NotImplementedError('Unknown job status {!r}'.format(status))
                    else:
                        sch_status = self._tasks.get(identifier, {}).get('status', None)

                        if status == 'PENDING':
                            if identifier in self._tasks and sch_status not in ('PROCESSING', 'PENDING'):
                                self.logger.warning('The task {!r} is still tracking and has status {!r}'.
                                                    format(identifier, sch_status))
                                del self._jobs[identifier]
                            self.add_new_pending_task(identifier)
                        elif status == 'PROCESSING':
                            # PROCESSING
                            if identifier not in self._tasks:
                                self.logger.warning("There is running task {!r}".format(identifier))
                                self.server.submit_task_error(identifier, 'Unknown task')
                            elif identifier in self._tasks and not self.runner.is_solving(self._tasks[identifier]) \
                                    and sch_status != 'PROCESSING':
                                self.logger.warning("Task {!r} already has status {!r} and is not PROCESSING".
                                                    format(identifier, sch_status))
                        elif status in ('FINISHED', 'ERROR', 'CANCELLED'):
                            # CANCELLED
                            if identifier in self._tasks and self.runner.is_solving(self._tasks[identifier]):
                                self.runner.cancel_task(identifier, self._tasks[identifier])
                            if identifier in self._tasks:
                                del self._tasks[identifier]
                        else:
                            raise NotImplementedError('Unknown task status {!r}'.format(status))
            except queue.Empty:
                pass

            try:
                for job_id, desc in list(self._jobs.items()):
                    if self.runner.is_solving(desc) and desc["status"] == "PENDING":
                        desc["status"] = "PROCESSING"
                    elif desc['status'] == 'PROCESSING' and \
                            self.runner.process_job_result(
                                job_id, desc,
                                [tid for tid, item in self._tasks.items() if desc["status"] in ["PENDING", "PROCESSING"]
                                                                             and item["description"][
                                                                                 "job id"] == job_id]):
                        if desc['status'] == 'FINISHED' and not desc.get('error'):
                            self.server.submit_job_status(job_id, self._job_status('SOLVED'))
                        elif desc.get('error'):
                            # Sometimes job can be rescheduled, lets check this doing the following
                            if not desc.get('rescheduled'):
                                server_status = self._job_status(self.server.get_job_status(job_id))
                                if server_status == 'PENDING':
                                    desc['rescheduled'] = True
                                    desc['status'] = 'PENDING'
                                    continue
                            self.server.submit_job_error(job_id, desc['error'])
                        else:
                            raise NotImplementedError("Cannot determine status of the job {!r}".format(job_id))
                        if job_id in self._jobs:
                            del self._jobs[job_id]
                    elif desc['status'] == 'PROCESSING':
                        # Request progress if it is available
                        if nth_iteration(10) and self.relevant_tasks(job_id):
                            progress = self.server.get_job_progress(job_id)
                            if progress:
                                self.runner.add_job_progress(job_id, self._jobs[job_id], progress)

                for task_id, desc in list(self._tasks.items()):
                    if self.runner.is_solving(desc) and desc["status"] == "PENDING":
                        desc["status"] = "PROCESSING"
                    elif desc["status"] == "PROCESSING" and self.runner.process_task_result(task_id, desc):
                        if desc['status'] == 'FINISHED' and not desc.get('error'):
                            self.server.submit_task_status(task_id, 'FINISHED')
                        elif desc["status"] == 'PENDING':
                            # This case is for rescheduling
                            continue
                        elif desc.get('error'):
                            self.server.submit_task_error(task_id, desc['error'])
                        else:
                            raise NotImplementedError("Cannot determine status of the task {!r}: {!r}".
                                                      format(task_id, desc["status"]))
                        if task_id in self._tasks:
                            del self._tasks[task_id]

                # Submit tools
                try:
                    self.runner.update_tools()
                except Exception as err:
                    self.logger.warning('Cannot submit verification tools information: {}'.format(err))

                # Get actual information about connected nodes
                submit = True
                try:
                    self.runner.update_nodes()
                except Exception as err:
                    self.logger.error("Cannot obtain information about connected nodes: {}".format(err))
                    submit = False
                    self.logger.warning("Do not run tasks until actual information about the nodes will be obtained")

                if submit:
                    # Update resource limitations before scheduling
                    messages = {}
                    # Avoid concurrent modification
                    pending_tasks = ((i, desc) for i, desc in self._tasks.items()
                                     if desc["status"] == "PENDING")
                    for i, desc in list(pending_tasks):
                        messages[i] = self.runner.prepare_task(i, desc)
                        if not messages[i]:
                            self.server.submit_task_error(i, desc['error'])
                            del self._tasks[i]

                    # Schedule new tasks
                    pending_tasks = [desc for task_id, desc in self._tasks.items() if desc["status"] == "PENDING"]
                    pending_jobs = [desc for job_id, desc in self._jobs.items() if desc["status"] == "PENDING"
                                    and not self.runner.is_solving(desc)]
                    pending_jobs = sorted(pending_jobs, key=lambda i: sort_priority(i['configuration']['priority']))
                    pending_tasks = sorted(pending_tasks, key=lambda i: sort_priority(i['description']['priority']))

                    tasks_to_start, jobs_to_start = self.runner.schedule(pending_tasks, pending_jobs)
                    if len(tasks_to_start) > 0 or len(jobs_to_start) > 0:
                        self.logger.info("Going to start {} new tasks and {} jobs".
                                         format(len(tasks_to_start), len(jobs_to_start)))
                        self.logger.info("There are {} pending and {} solving jobs".format(
                            len(pending_jobs),
                            len({j for j, desc in self._jobs.items() if desc['status'] == 'PROCESSING'})))
                        self.logger.info("There are {} pending and {} solving tasks".format(
                            len(pending_tasks),
                            len({t for t, desc in self._tasks.items() if desc['status'] == 'PROCESSING'})))

                        for job_id in jobs_to_start:
                            started = self.runner.solve_job(job_id, self._jobs[job_id])
                            if started and self._jobs[job_id]['status'] not in ('PENDING', 'PROCESSING'):
                                raise RuntimeError('Expect that status of started job {!r} is solving but it has status'
                                                   ' {!r}'.format(self._jobs[job_id]['status'], job_id))
                            if not started and self._jobs[job_id]['status'] == 'ERROR':
                                self.server.submit_job_error(job_id, self._jobs[job_id]['error'])
                                if job_id in self._jobs:
                                    del self._jobs[job_id]

                        for task_id in tasks_to_start:
                            # This check is very helpful for debugging
                            msg = messages.get(task_id)
                            if msg and isinstance(msg, str):
                                self.logger.info(msg)
                            started = self.runner.solve_task(task_id, self._tasks[task_id])
                            if started and self._tasks[task_id]['status'] != 'PROCESSING':
                                raise RuntimeError('Expect that status of started task is PROCESSING but it is {!r} '
                                                   'for {!r}'.format(self._tasks[task_id]['status'], task_id))
                            if started and self._tasks[task_id]['status'] == 'PROCESSING':
                                if not self._tasks[task_id].get("rescheduled"):
                                    self.server.submit_task_status(task_id, 'PROCESSING')
                            elif not started and self._tasks[task_id]['status'] == 'PROCESSING':
                                raise RuntimeError('In case of error task cannot be \'PROCESSING\' but it is for '
                                                   '{!r}'.format(task_id))
                            elif not started and self._tasks[task_id]['status'] == 'ERROR':
                                self.server.submit_task_error(task_id, self._tasks[task_id]['error'])
                                if task_id in self._tasks:
                                    del self._tasks[task_id]

                    # Flushing tasks
                    if len(tasks_to_start) > 0 or \
                            len([True for i, desc in self._tasks.items() if desc["status"] == "PROCESSING"]) > 0:
                        self.runner.flush()

                # Periodically check for jobs and task that have an unexpected status. This should help notice bugs
                # related to interaction with Bridge through RabbitMQ
                if nth_iteration(100):
                    self._check_jobs_status()

                time.sleep(self._iteration_period)
            except KeyboardInterrupt:
                self.logger.error("Scheduler execution is interrupted, cancel all running threads")
                self.terminate()
                self._listening_thread.stop()
                self._listening_thread.join()
                sys.exit(137)
            except Exception:
                exception_info = 'An error occurred:\n{}'.format(traceback.format_exc().rstrip())
                self.logger.error(exception_info)
                self.terminate()
                self._listening_thread.stop()
                self._listening_thread.join()
                if self.production:
                    self.logger.info("Reinitialize scheduler and try to proceed execution in 30 seconds...")
                    time.sleep(30)
                    self.init_scheduler()
                else:
                    sys.exit(1)

    @staticmethod
    def __add_missing_restrictions(collection):
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

    def terminate(self):
        """Abort solution of all running tasks and any other actions before termination."""
        running_jobs = [job_id for job_id, desc in self._jobs.items() if desc["status"] in ["PENDING", "PROCESSING"]]

        # First, stop jobs
        for job_id, item in [(job_id, self._jobs[job_id]) for job_id in running_jobs]:
            relevant_tasks = self.relevant_tasks(job_id)
            self.runner.cancel_job(job_id, item, relevant_tasks)

        # Note here that some schedulers can solve tasks of jobs which run elsewhere
        for task_id, item in [(task_id, item) for task_id, item in self._tasks.items()
                              if item["status"] in ["PENDING", "PROCESSING"]]:
            self.runner.cancel_task(task_id, item)

        # Terminate tasks
        self.cancel_all_tasks()

        # Submit errors on all jobs
        for job_id in running_jobs:
            self.server.submit_job_error(job_id, 'Scheduler has been terminated or reset')

        # Do final uninitializations
        self.runner.terminate()

    def add_new_pending_job(self, identifier):
        """
        Add new pending job and prepare its description.

        :param identifier: Job identifier string.
        """
        if identifier not in self._jobs:
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
            if identifier in self._jobs and self._jobs[identifier]["status"] == "PROCESSING":
                raise RuntimeError(
                    "This should not be possible to get PENDING status for a PROCESSING jib {!r}".format(identifier))

            # Check and set necessary restrictions for further scheduling
            for collection in [job_conf['configuration']["resource limits"],
                               job_conf['configuration']['task resource limits']]:
                try:
                    self.__add_missing_restrictions(collection)
                except SchedulerException as err:
                    self._jobs[identifier] = {
                        "id": identifier,
                        "status": "ERROR",
                        "error": str(err)
                    }
                    break

            self._jobs[identifier] = {
                "id": identifier,
                "status": "PENDING",
                "configuration": job_conf['configuration']
            }
            prepared = self.runner.prepare_job(identifier, self._jobs[identifier])
            if not prepared:
                self.server.submit_job_error(identifier, self._jobs[identifier]['error'])
                del self._jobs[identifier]
        else:
            self.logger.warning('Attempt to schedule job {} second time but it already has status {}'.
                                format(identifier, self._jobs[identifier]['status']))

    def add_new_pending_task(self, identifier):
        """
        Add new pending task and prepare its description.

        :param identifier: Task identifier string.
        """
        if identifier not in self._tasks:
            task_conf = self.server.pull_task_conf(identifier)
            if not task_conf:
                self.server.submit_task_error(identifier, 'Failed to download configuration')
                return

            self.logger.info("Add new PENDING task {}".format(identifier))
            self._tasks[identifier] = {
                "id": identifier,
                "status": "PENDING",
                "description": task_conf['description'],
                "priority": task_conf['description']["priority"]
            }

            self.logger.debug("Prepare new task {!r} before launching".format(identifier))
            # Add missing restrictions
            try:
                self.__add_missing_restrictions(
                    self._tasks[identifier]["description"]["resource limits"])
            except SchedulerException as err:
                self._jobs[identifier] = {
                    "id": identifier,
                    "status": "ERROR",
                    "error": str(err)
                }
            else:
                prepared = self.runner.prepare_task(identifier, self._tasks[identifier])
                if not prepared:
                    self.server.submit_task_error(identifier, self._tasks[identifier]['error'])
                    del self._tasks[identifier]
        else:
            self.logger.warning('Attempt to schedule job {} second time but it already has status {}'.
                                format(identifier, self._tasks[identifier]['status']))

    def relevant_tasks(self, job_id):
        """
        Collect and return the list of task descriptions for a particular job.

        :param job_id: Relevant job identifier.
        :return: List of dictionaries.
        """
        return [desc for tid, desc in self._tasks.items()
                if desc["status"] in ["PENDING", "PROCESSING"]
                and desc["description"]["job id"] == job_id]

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

    def _check_jobs_status(self):
        """This functions checks compliance of server and scheduler statuses."""
        if self._runner_class.accept_jobs:
            # todo: At the moment we do not have several schedulers that can serve jobs but in other case this should
            #       be fixed
            result = self.server.get_all_jobs()
            if result:
                for identifier, status in result:
                    status = self._job_status(status)
                    if identifier not in self._jobs and status == 'PENDING':
                        self.add_new_pending_job(identifier)
                    elif identifier not in self._jobs and status == 'PROCESSING':
                        self.server.submit_job_error(identifier, 'Scheduler terminated or reset and does not '
                                                                 'track the job {}'.format(identifier))
                    elif identifier not in self._jobs and status == 'CANCELLING':
                        self.server.cancel_job(identifier)

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
