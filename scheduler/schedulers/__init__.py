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
import traceback
import threading
import queue
import pika
import logging

import server
from utils.bridge import BridgeError
from utils import sort_priority, time_units_converter, memory_units_converter


class SchedulerException(RuntimeError):
    """Exception is used to determine when task or job fails but not scheduler."""
    pass


class ListeningThread(threading.Thread):

    conf = None

    def __init__(self, local_queue, cnf=None):
        super(ListeningThread, self).__init__()
        self._is_interrupted = False
        if cnf:
            self.conf = cnf
        self._queue = local_queue

    def stop(self):
        self._is_interrupted = True

    def run(self):
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=self.conf["host"],
            credentials=pika.credentials.PlainCredentials(self.conf["username"], self.conf["password"]))
        )
        channel = connection.channel()
        channel.queue_declare(queue=self.conf["name"], durable=True)
        for method, properties, body in channel.consume(self.conf["name"], auto_ack=True, inactivity_timeout=1):
            if self._is_interrupted:
                break
            if not body:
                continue
            # Just forward to main loop all data. This can be done faster but it will require additional locks and sync
            self._queue.put(body)


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
        self.__runner_class = runner_class
        self.__tasks = {}
        self.__jobs = {}
        self.__nodes = None
        self.__tools = None
        self.__iteration_period = 0.5
        self.__server_queue = None
        self.__channel = None
        self.__listening_thread = None
        self.__loop_thread = None
        self.production = self.conf["scheduler"].setdefault("production", False)

        logging.getLogger("pika").setLevel(logging.WARNING)
        self.init_scheduler()

    def init_scheduler(self):
        """
        Initialize scheduler completely. This method should be called both at constructing stage and scheduler
        reinitialization. Thus, all object attribute should be cleaned up and set as it is a newly created object.
        """
        self.__tasks = {}
        self.__jobs = {}
        self.__nodes = None
        self.__tools = None
        self.__server_queue = queue.Queue()
        self.server = server.Server(self.logger, self.conf["Klever Bridge"], os.path.join(self.work_dir, "requests"))

        _old_tasks_status = None
        _old_jobs_status = None

        # Check configuration completeness
        self.logger.debug("Check whether configuration contains all necessary data")

        # Initialize interaction
        self.server.register(self.__runner_class.scheduler_type())

        self.runner = self.__runner_class(self.conf, self.logger, self.work_dir, self.server)
        self.runner.init()

        # Create listening thread
        if self.__listening_thread and not self.__listening_thread.is_alive():
            self.__listening_thread.stop()
            self.__listening_thread.join()
        self.__listening_thread = ListeningThread(self.__server_queue, self.conf["Klever jobs and tasks queue"])
        self.__listening_thread.start()

        # # Before we proceed lets check all existing jobs
        # for identifier, status in self.server.get_all_jobs():
        #     if identifier not in self.__jobs or status != self.__jobs['status']:
        #         self.server.submit_job_error(identifier,
        #                                      "Scheduler does not track the job, maybe the scheduler was restarted")

        self.logger.info("Scheduler base initialization has been successful")

    def launch(self):
        """
        Start scheduler loop. This is an infinite loop that exchange data with Bridge to fetch new jobs and tasks and
        upload result of solution previously received tasks and jobs. After data exchange it prepares for solution
        new jobs and tasks, updates statuses of running jobs and tasks and schedule for solution pending ones.
        This is just an algorythm, and all particular logic and resource management should be implemented in classes
        that inherits this one.
        """

        def nth_iteration(n):
            return True if iteration_number % n == 0 else False

        self.logger.info("Start scheduler loop")
        iteration_number = 0
        while True:
            try:
                if iteration_number == 10000:
                    iteration_number = 0
                else:
                    iteration_number += 1

                if not self.__listening_thread.is_alive():
                    raise ValueError("Listening thread is not alive, terminating")

                while True:
                    msg = self.__server_queue.get_nowait()
                    kind, identifier, status = msg.decode('utf-8').split(' ')
                    if kind == 'job':
                        self.logger.debug("New status of job {!r} is {!r}".format(identifier, status))

                        if status == '1':
                            job_conf = self.server.pull_job_conf(identifier)
                            job_conf['configuration']['identifier'] = identifier
                            job_conf['configuration']['task resource limits'] = job_conf['tasks']
                            # TODO: Get Verifier Cloud login and password

                            self.logger.debug("Prepare new job {} before launching".format(identifier))
                            if identifier in self.__jobs and self.__jobs[identifier]["status"] == "PROCESSING":
                                raise RuntimeError(
                                    "This should not be possible to get PEDING status for a PROCESSING jib {!r}".
                                    format(identifier))

                            # Check and set necessary restrictions for further scheduling
                            for collection in [job_conf['configuration']["resource limits"],
                                               job_conf['configuration']['task resource limits']]:
                                try:
                                    self.__add_missing_restrictions(collection)
                                except SchedulerException as err:
                                    self.__jobs[identifier] = {
                                        "id": identifier,
                                        "status": "ERROR",
                                        "error": str(err)
                                    }
                                    break

                            self.__jobs[identifier] = {
                                "id": identifier,
                                "status": "PENDING",
                                "configuration": job_conf['configuration']
                            }
                            self.runner.prepare_job(identifier, self.__jobs[identifier])
                        elif identifier not in self.__jobs:
                            # There is no such job
                            self.server.submit_job_error(identifier, 'This job was not tracked by the scheduler')
                        elif status == '2':
                            # PROCESSING
                            self.__jobs[identifier]['status'] = 'PROCESSING'
                        elif status == '3':
                            # SOLVED
                            del self.__jobs[identifier]
                        elif status == '4' or status == '7' or status == '8':
                            # FAILED or CANCELLED
                            if identifier in self.__jobs:
                                raise RuntimeError("Job {!r} failed and should be deleted")
                        elif status == '5':
                            # CORRUPTED
                            if identifier in self.__jobs:
                                self.runner.cancel_job(identifier, self.__jobs[identifier],
                                                       self.relevant_tasks(identifier))
                                del self.__jobs[identifier]
                        elif status == '6':
                            # CANCELLING
                            self.runner.cancel_job(identifier, self.__jobs[identifier], self.relevant_tasks(identifier))
                            self.server.cancel_job(identifier)
                            for task_id, status in self.server.get_job_tasks(identifier):
                                if status in ('PENDING', 'PROCESSING'):
                                    self.server.submit_task_cancelled(task_id)
                            del self.__jobs[identifier]
                        else:
                            raise NotImplementedError('Unknown job status {!r}'.format(status))
                    else:
                        if status == 'PENDING':
                            task_conf = self.server.pull_task_conf(identifier)
                            self.logger.info("Add new PENDING task {}".format(identifier))
                            self.__tasks[identifier] = {
                                "id": identifier,
                                "status": "PENDING",
                                "description": task_conf['description'],
                                "priority": task_conf['description']["priority"]
                            }

                            # TODO: VerifierCloud user name and password are specified in task description and
                            # shouldn't be extracted from it here.
                            if self.runner.scheduler_type() == "VerifierCloud":
                                self.__tasks[identifier]["user"] = task_conf['description']["VerifierCloud user name"]
                                self.__tasks[identifier]["password"] = \
                                    task_conf['description']["VerifierCloud user password"]
                            else:
                                self.__tasks[identifier]["user"] = None
                                self.__tasks[identifier]["password"] = None

                            self.logger.debug("Prepare new task {!r} before launching".format(identifier))
                            # Add missing restrictions
                            try:
                                self.__add_missing_restrictions(
                                    self.__tasks[identifier]["description"]["resource limits"])
                            except SchedulerException as err:
                                self.__jobs[identifier] = {
                                    "id": identifier,
                                    "status": "ERROR",
                                    "error": str(err)
                                }
                            else:
                                self.runner.prepare_task(identifier, self.__tasks[identifier])
                        elif status == 'PROCESSING':
                            # PROCESSING
                            if identifier not in self.__tasks:
                                raise RuntimeError("There is no task {!r}".format(identifier))
                        elif status in ('FINISHED', 'ERROR', 'CANCELLED'):
                            # CANCELLED
                            if identifier in self.__tasks:
                                del self.__tasks[identifier]
                        else:
                            raise NotImplementedError('Unknown task status {!r}'.format(status))
            except queue.Empty:
                pass

            try:
                for job_id, desc in list(self.__jobs.items()):
                    if self.runner.is_solving(desc) and desc["status"] == "PENDING":
                        desc["status"] = "PROCESSING"
                    elif desc['status'] == 'PROCESSING' and \
                        self.runner.process_job_result(
                            job_id, desc, [tid for tid in self.__tasks if desc["status"] in ["PENDING", "PROCESSING"]
                                           and self.__tasks[tid]["description"]["job id"] == job_id]):
                        if desc['status'] == 'FINISHED' and not desc.get('error'):
                            self.server.submit_job_finished(job_id)
                        elif desc.get('error'):
                            self.server.submit_job_error(job_id, desc['error'])
                        else:
                            raise NotImplementedError("Cannot determine status of the job {!r}".format(job_id))
                        if job_id in self.__jobs:
                            del self.__jobs[job_id]
                    elif desc['status'] == 'PROCESSING':
                        # Request progress if it is available
                        if nth_iteration(10) and self.relevant_tasks(job_id):
                            progress = self.server.get_job_progress(job_id)
                            if progress:
                                self.runner.add_job_progress(job_id, self.__jobs[job_id], progress)

                for task_id, desc in list(self.__tasks.items()):
                    if self.runner.is_solving(desc) and desc["status"] == "PENDING":
                        desc["status"] = "PROCESSING"
                    elif desc["status"] == "PROCESSING" and self.runner.process_task_result(task_id, desc):
                        if desc['status'] == 'FINISHED' and not desc.get('error'):
                            self.server.submit_task_finished(task_id)
                        elif desc.get('error'):
                            self.server.submit_task_error(task_id, desc['error'])
                        else:
                            raise NotImplementedError("Cannot determine status of the task {!r}".format(task_id))
                        if task_id in self.__tasks:
                            del self.__tasks[task_id]

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
                    messages = dict()
                    for i, desk in ((i, self.__tasks[i]) for i in self.__tasks
                                    if self.__tasks[i]["status"] == "PENDING"):
                        messages[i] = self.runner.prepare_task(i, desk)

                    # Schedule new tasks
                    pending_tasks = [desc for task_id, desc in self.__tasks.items() if desc["status"] == "PENDING"]
                    pending_jobs = [desc for job_id, desc in self.__jobs.items() if desc["status"] == "PENDING"
                                    and not self.runner.is_solving(desc)]
                    pending_jobs = sorted(pending_jobs, key=lambda i: sort_priority(i['configuration']['priority']))
                    pending_tasks = sorted(pending_tasks, key=lambda i: sort_priority(i['description']['priority']))

                    tasks_to_start, jobs_to_start = self.runner.schedule(pending_tasks, pending_jobs)
                    if len(tasks_to_start) > 0 or len(jobs_to_start) > 0:
                        self.logger.info("Going to start {} new tasks and {} jobs".
                                         format(len(tasks_to_start), len(jobs_to_start)))
                        self.logger.info("There are {} pending jobs in total and {} are solving".format(
                            len(pending_tasks), len({t for t in self.__tasks if self.__tasks[t]['status'] == 'PROCESSING'})))
                        self.logger.info("There are {} pending in total and {} are solving".format(
                            len(pending_jobs), len({j for j in self.__jobs if self.__jobs[j]['status'] == 'PROCESSING'})))

                        for job_id in jobs_to_start:
                            self.runner.solve_job(job_id, self.__jobs[job_id])

                        for task_id in tasks_to_start:
                            self.server.submit_processing_task(task_id)
                            # This check is very helpful for debugging
                            msg = messages.get(task_id)
                            if msg:
                                self.logger.info(msg)
                            self.runner.solve_task(task_id, self.__tasks[task_id])

                    # Flushing tasks
                    if len(tasks_to_start) > 0 or \
                            len([True for i in self.__tasks if self.__tasks[i]["status"] == "PROCESSING"]) > 0:
                        self.runner.flush()

                time.sleep(self.__iteration_period)
            except KeyboardInterrupt:
                self.logger.error("Scheduler execution is interrupted, cancel all running threads")
                self.terminate()
                self.server.stop()
                self.__listening_thread.stop()
                self.__listening_thread.join()
                exit(137)
            except Exception:
                exception_info = 'An error occured:\n{}'.format(traceback.format_exc().rstrip())
                self.logger.error(exception_info)
                self.terminate()
                self.__listening_thread.stop()
                self.__listening_thread.join()
                self.server.stop()
                if self.production:
                    self.logger.info("Reinitialize scheduler and try to proceed execution in 30 seconds...")
                    time.sleep(30)
                    self.init_scheduler()
                else:
                    exit(1)

    @staticmethod
    def __add_missing_restrictions(collection):
        """
        If resource limits are incomplete the method adds to given json all necessary fields filled with zeroes.

        :param collection: 'resource limits' dictionary from a task description or job configuration.
        """
        if len(collection.keys()) == 0:
            raise SchedulerException("Resource limitations are missing: upload correct tasks.json file and properly "
                                     "set job resource limitiations")

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
        except Exception:
            raise SchedulerException('Cannot interprete {} resource limitations: {!r}'.format(tag, collection[tag]))

    def terminate(self):
        """Abort solution of all running tasks and any other actions before termination."""
        running_jobs = [job_id for job_id in self.__jobs if self.__jobs[job_id]["status"] in ["PENDING", "PROCESSING"]]

        # First, stop jobs
        for job_id, item in [(job_id, self.__jobs[job_id]) for job_id in running_jobs]:
            relevant_tasks = self.relevant_tasks(job_id)
            self.runner.cancel_job(job_id, item, relevant_tasks)

        # Note here that some schedulers can solve tasks of jobs which run elsewhere
        for task_id, item in [(task_id, self.__tasks[task_id]) for task_id in self.__tasks
                              if self.__tasks[task_id]["status"] in ["PENDING", "PROCESSING"]]:
            self.runner.cancel_task(task_id, item)

        # Terminate tasks
        self.cancel_all_tasks()

        # Submit errors on all jobs
        for job_id in running_jobs:
            self.server.submit_job_error(job_id, 'Scheduler has been terminated or reset')

        # Do final unitializations
        self.runner.terminate()

    def relevant_tasks(self, job_id):
        return [self.__tasks[tid] for tid in self.__tasks
                if self.__tasks[tid]["status"] in ["PENDING", "PROCESSING"]
                and self.__tasks[tid]["description"]["job id"] == job_id]

    def cancel_all_tasks(self):
        # Check all tasks and cancel them
        tasks = self.server.get_all_tasks()
        for identifier, status in tasks:
            # TODO: Remove this when Bridge will not raise an error 'Job is not solving'
            if status in ('PENDING', 'PROCESSING'):
                try:
                    self.server.submit_task_error(identifier, 'Scheduler terminated or reset')
                except BridgeError as err:
                    self.logger.warning('Brdige reports an error on attempt to cancel task {}: {!r}'.
                                        format(identifier, err))
            try:
                self.server.delete_task(identifier)
            except BridgeError as err:
                self.logger.warning('Brdige reports an error on attempt to delete task {}: {!r}'.
                                    format(identifier, err))
