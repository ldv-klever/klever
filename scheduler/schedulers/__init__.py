#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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

import abc
import concurrent.futures
import logging
import os
import shutil
import time
import traceback
import json

import server.testgenerator as testgenerator
import server.bridge as bridge
from utils import sort_priority, time_units_converter, memory_units_converter


def get_gateway(conf, work_dir):
    """
    Check which implementation of Session object to choose to get tasks

    :param conf: Configuration dictionary.
    :param work_dir: Path to the working directory.
    :return: Return object of the implementation of Session abstract class.
    """
    if "debug with testgenerator" in conf["scheduler"] and conf["scheduler"]["debug with testgenerator"]:
        return testgenerator.Server(logging, conf["testgenerator"], work_dir)
    else:
        return bridge.Server(logging, conf["Klever Bridge"], work_dir)


class SchedulerException(RuntimeError):
    """Exception is used to determine when task or job fails but not scheduler."""
    pass


class SchedulerExchange(metaclass=abc.ABCMeta):
    """Class provide general scheduler API."""

    @staticmethod
    @abc.abstractstaticmethod
    def scheduler_type():
        """Return type of the scheduler: 'VerifierCloud' or 'Klever'."""
        return "Klever"

    @abc.abstractmethod
    def __init__(self, conf, work_dir):
        """
        Get configuration and prepare working directory.

        :param conf: Dictionary with relevant configuration.
        :param work_dir: PAth to the working directory.
        """
        self.conf = conf
        self.work_dir = work_dir
        self.__tasks = {}
        self.__jobs = {}
        self.__nodes = None
        self.__tools = None
        self.__iteration_period = None
        self.__last_exchange = None
        self.server = get_gateway(self.conf, os.path.join(self.work_dir, "requests"))
        self.production = None
        self.__current_period = None

    def init_scheduler(self):
        """
        Initialize scheduler completely. This method should be called both at constructing stage and scheduler
        reinitialization. Thus, all object attribute should be cleaned up and set as it is a newly created object.
        """
        self.__tasks = {}
        self.__jobs = {}
        self.__nodes = None
        self.__tools = None
        self.__iteration_period = {
            "short": 5,
            "medium": 10,
            "long": 20
        }
        self.__last_exchange = None
        self.server = get_gateway(self.conf, os.path.join(self.work_dir, "requests"))

        # Check configuration completeness
        logging.debug("Check whether configuration contains all necessary data")

        # Initialize interaction
        self.server.register(self.scheduler_type())

        # Reinitialization flag
        if "production" in self.conf["scheduler"] and self.conf["scheduler"]["production"]:
            self.production = True
        else:
            self.production = False

        if "iteration timeout" in self.conf["scheduler"]:
            for tag in (t for t in self.__iteration_period.keys() if t in self.conf["scheduler"]["iteration timeout"]):
                self.__iteration_period[tag] = self.conf["scheduler"]["iteration timeout"][tag]
        self.__current_period = self.__iteration_period['short']

        logging.info("Scheduler base initialization has been successful")

    def launch(self):
        """
        Start scheduler loop. This is an infinite loop that exchange data with Bridge to fetch new jobs and tasks and
        upload result of solution previously received tasks and jobs. After data exchange it prepares for solution
        new jobs and tasks, updates statuses of running jobs and tasks and schedule for solution pending ones.
        This is just an algorythm, and all particular logic and resource management should be implemented in classes
        that inherits this one.
        """
        transition_done = False
        logging.info("Start scheduler loop")
        to_cancel = set()
        while True:
            try:
                # Prepare scheduler state
                logging.info("Start scheduling iteration with statuses exchange with the server")
                scheduler_state = {
                    "tasks": {
                        "pending": [task_id for task_id in self.__tasks if "status" in self.__tasks[task_id] and
                                    self.__tasks[task_id]["status"] == "PENDING"],
                        "processing": [task_id for task_id in self.__tasks if "status" in self.__tasks[task_id] and
                                       self.__tasks[task_id]["status"] == "PROCESSING"],
                        "finished": [task_id for task_id in self.__tasks if "status" in self.__tasks[task_id] and
                                     self.__tasks[task_id]["status"] == "FINISHED"],
                        "error": [task_id for task_id in self.__tasks if "status" in self.__tasks[task_id] and
                                  self.__tasks[task_id]["status"] == "ERROR"]
                    },
                }
                logging.info("Scheduler has {} pending, {} processing, {} finished and {} error tasks".
                             format(len(scheduler_state["tasks"]["pending"]),
                                    len(scheduler_state["tasks"]["processing"]),
                                    len(scheduler_state["tasks"]["finished"]),
                                    len(scheduler_state["tasks"]["error"])))
                scheduler_state["jobs"] = {
                    "pending": [job_id for job_id in self.__jobs if "status" in self.__jobs[job_id] and
                                self.__jobs[job_id]["status"] == "PENDING"],
                    "processing": [job_id for job_id in self.__jobs if "status" in self.__jobs[job_id] and
                                   self.__jobs[job_id]["status"] == "PROCESSING"],
                    "finished": [job_id for job_id in self.__jobs if "status" in self.__jobs[job_id] and
                                 self.__jobs[job_id]["status"] == "FINISHED"],
                    "error": [job_id for job_id in self.__jobs if "status" in self.__jobs[job_id] and
                              self.__jobs[job_id]["status"] == "ERROR"],
                    "cancelled": list(to_cancel)
                }
                # Update
                logging.info("Scheduler has {} pending, {} processing, {} finished and {} error jobs and {} cancelled".
                             format(len(scheduler_state["jobs"]["pending"]),
                                    len(scheduler_state["jobs"]["processing"]),
                                    len(scheduler_state["jobs"]["finished"]),
                                    len(scheduler_state["jobs"]["error"]),
                                    len(to_cancel)))
                if len(to_cancel) > 0:
                    transition_done = True

                # Add task errors
                logging.debug("Add task {} error descriptions".format(len(scheduler_state["tasks"]["error"])))
                if len(scheduler_state["tasks"]["error"]):
                    scheduler_state["task errors"] = {}
                for task_id in scheduler_state["tasks"]["error"]:
                    scheduler_state["task errors"][task_id] = str(self.__tasks[task_id]["error"])

                # Add jobs errors
                logging.debug("Add job {} error descriptions".format(len(scheduler_state["jobs"]["error"])))
                if len(scheduler_state["jobs"]["error"]):
                    scheduler_state["job errors"] = {}
                for job_id in scheduler_state["jobs"]["error"]:
                    scheduler_state["job errors"][job_id] = str(self.__jobs[job_id]["error"])

                # Submit scheduler state and receive server state
                if transition_done or self.__need_exchange:
                    transition_done = False
                    to_cancel = set()
                    server_state = self.server.exchange(scheduler_state)
                    self.__last_exchange = int(time.time())
                    try:
                        # Ignore tasks which have been finished or cancelled
                        for task_id in [task_id for task_id in self.__tasks
                                        if self.__tasks[task_id]["status"] in ["FINISHED", "ERROR"]]:
                            if task_id in server_state["tasks"]["pending"]:
                                logging.debug("Ignore PENDING task {}, since it has been processed recently".
                                              format(task_id))
                                server_state["tasks"]["pending"].remove(task_id)
                            if task_id in server_state["tasks"]["processing"]:
                                logging.debug("Ignore PROCESSING task {}, since it has been processed recently")
                                server_state["tasks"]["processing"].remove(task_id)

                        # Ignore jobs which have been finished or cancelled
                        for job_id in [job_id for job_id in self.__jobs
                                       if self.__jobs[job_id]["status"] in ["FINISHED", "ERROR"]]:
                            if job_id in server_state["jobs"]["pending"]:
                                logging.debug("Ignore PENDING job {}, since it has been processed recently".
                                              format(job_id))
                                server_state["jobs"]["pending"].remove(job_id)
                            if job_id in server_state["jobs"]["processing"]:
                                logging.debug("Ignore PROCESSING job {}, since it has been processed recently")
                                server_state["jobs"]["processing"].remove(job_id)
                    except KeyError as missed_tag:
                        self.__report_error_server_state(
                            server_state,
                            "Missed tag {} in a received server state".format(missed_tag))

                    # Remove finished or error tasks which have been already submitted
                    logging.debug("Remove tasks with statuses FINISHED and ERROR which have been submitted")
                    for task_id in set(scheduler_state["tasks"]["finished"] + scheduler_state["tasks"]["error"]):
                        logging.debug("Delete task {} with status {}".format(task_id, self.__tasks[task_id]["status"]))
                        del self.__tasks[task_id]

                    # Remove finished or error jobs
                    logging.debug("Remove jobs with statuses FINISHED and ERROR")
                    for job_id in set(scheduler_state["jobs"]["finished"] + scheduler_state["jobs"]["error"]):
                        logging.debug("Delete job {} with status {}".format(job_id, self.__jobs[job_id]["status"]))
                        del self.__jobs[job_id]

                    # Add new PENDING tasks
                    for task_id in [task_id for task_id in server_state["tasks"]["pending"]
                                    if task_id not in self.__tasks]:
                        logging.debug("Add new PENDING task {}".format(task_id))
                        try:
                            self.__tasks[task_id] = {
                                "id": task_id,
                                "status": "PENDING",
                                "description": server_state["task descriptions"][task_id]["description"],
                                "priority": server_state["task descriptions"][task_id]["description"]["priority"]
                            }

                            # TODO: VerifierCloud user name and password are specified in task description and
                            # shouldn't be extracted from it here.
                            if self.scheduler_type() == "VerifierCloud":
                                self.__tasks[task_id]["user"] = \
                                    server_state["task descriptions"][task_id]["VerifierCloud user name"]
                                self.__tasks[task_id]["password"] = \
                                    server_state["task descriptions"][task_id]["VerifierCloud user password"]
                            else:
                                self.__tasks[task_id]["user"] = None
                                self.__tasks[task_id]["password"] = None
                        except KeyError as missed_tag:
                            self.__report_error_server_state(
                                server_state,
                                "Missed tag '{}' in the description of pendng task {}".format(missed_tag, task_id))

                        # Try to prepare task
                        logging.debug("Prepare new task {} before launching".format(task_id))
                        try:
                            # Add missing restrictions
                            self.__add_missing_restrictions(self.__tasks[task_id]["description"]["resource limits"])

                            self.prepare_task(task_id, self.__tasks[task_id]["description"])
                        except SchedulerException as err:
                            logging.error("Cannot prepare task {!r} for submission: {!r}".format(task_id, err))
                            self.__tasks[task_id]["status"] = "ERROR"
                            self.__tasks[task_id]["error"] = err

                    # Add new PENDING jobs
                    for job_id in [job_id for job_id in server_state["jobs"]["pending"] if job_id not in self.__jobs]:
                        logging.debug("Add new PENDING job {}".format(job_id))
                        self.__jobs[job_id] = {
                            "id": job_id,
                            "status": "PENDING",
                            "configuration": server_state["job configurations"][job_id]
                        }

                        # Prepare jobs before launching
                        logging.debug("Prepare new job {} before launching".format(job_id))
                        try:
                            # Check and set necessary restrictions for further scheduling
                            for collection in [self.__jobs[job_id]["configuration"]["resource limits"],
                                               self.__jobs[job_id]["configuration"]["task resource limits"]]:
                                self.__add_missing_restrictions(collection)

                            self.prepare_job(job_id, self.__jobs[job_id]["configuration"])
                        except SchedulerException as err:
                            logging.error("Cannot prepare job {} for submission: {}".format(job_id, err))
                            self.__jobs[job_id]["status"] = "ERROR"
                            self.__jobs[job_id]["error"] = err

                    # Cancel tasks
                    for task_id in [task_id for task_id in set(scheduler_state["tasks"]["pending"] +
                                                               scheduler_state["tasks"]["processing"])
                                    if task_id not in
                                    set(server_state["tasks"]["pending"] + scheduler_state["tasks"]["processing"])]:
                        logging.debug("Cancel task {} with status {}".format(task_id, self.__tasks[task_id]['status']))
                        if "future" in self.__tasks[task_id]:
                            self.__tasks[task_id]["future"].cancel()
                        self.__process_future(self.cancel_task, self.__tasks[task_id], task_id)
                        del self.__tasks[task_id]
                        if not transition_done:
                            transition_done = True

                    # Cancel jobs
                    for job_id in [job_id for job_id in self.__jobs if self.__jobs[job_id]["status"] in
                                   ["PENDING", "PROCESSING"] and
                                   (job_id not in set(server_state["jobs"]["pending"] +
                                    server_state["jobs"]["processing"])
                                    or job_id in server_state["jobs"]["cancelled"])]:
                        logging.debug("Cancel job {} with status {}".format(job_id, self.__jobs[job_id]['status']))
                        if "future" in self.__jobs[job_id]:
                            self.__jobs[job_id]["future"].cancel()
                        # Make cancellation in scheduler implementation (del dir and so on)
                        self.__process_future(self.cancel_job, self.__jobs[job_id], job_id)

                        # Then terminate all pending and processing tasks for the job
                        self.__cancel_job_tasks(job_id)

                        del self.__jobs[job_id]
                        if not transition_done:
                            transition_done = True

                        if job_id in server_state["jobs"]["cancelled"]:
                            to_cancel.add(job_id)

                    # Add confirmation if necessary
                    to_cancel.update(
                        {j for j in server_state["jobs"]["cancelled"] if j not in to_cancel and
                         j not in self.__jobs})

                    # Update jobs processing status
                    for job_id in server_state["jobs"]["processing"]:
                        if job_id in self.__jobs:
                            if "future" in self.__jobs[job_id] and self.__jobs[job_id]["status"] == "PENDING":
                                self.__jobs[job_id]["status"] = "PROCESSING"
                                if not transition_done:
                                    transition_done = True
                            elif "future" not in self.__jobs[job_id] or self.__jobs[job_id]["status"] != "PROCESSING":
                                raise ValueError("Scheduler has lost information about job {} with PROCESSING status.".
                                                 format(job_id))
                        else:
                            logging.warning("Job {} has status PROCESSING but it was not running actually".
                                            format(job_id))
                            self.__jobs[job_id] = {
                                "id": job_id,
                                "status": "ERROR",
                                "error": "Job {} has status PROCESSING but it was not running actually".
                                         format(job_id)
                            }
                            if not transition_done:
                                transition_done = True

                    # Update tasks processing status
                    for task_id in server_state["tasks"]["processing"]:
                        if task_id in self.__tasks:
                            if "future" not in self.__tasks[task_id] or self.__tasks[task_id]["status"] != "PROCESSING":
                                raise ValueError("Scheduler has lost information about task {} with PROCESSING status.".
                                                 format(task_id))
                        else:
                            logging.warning("Task {} has status PROCESSING but it was not running actually".
                                            format(task_id))
                            self.__tasks[task_id] = {
                                "id": task_id,
                                "status": "ERROR",
                                "error": "task {} has status PROCESSING but it was not running actually".
                                         format(task_id)
                            }
                            if not transition_done:
                                transition_done = True

                # Update statuses and run new tasks

                # Wait there until all threads are terminated
                if "debug each iteration" in self.conf["scheduler"] and self.conf["scheduler"]["debug each iteration"]:
                    wait_list = [self.__tasks[task_id]["future"] for task_id in self.__tasks if "future" in
                                 self.__tasks[task_id]]
                    if "iteration timeout" not in self.conf["scheduler"]:
                        logging.debug("Wait for termination of {} tasks".format(len(wait_list)))
                        concurrent.futures.wait(wait_list, timeout=None, return_when="ALL_COMPLETED")
                    else:
                        logging.debug("Wait {} seconds for termination of {} tasks".
                                      format(self.conf["scheduler"]["iteration timeout"], len(wait_list)))
                        concurrent.futures.wait(wait_list, timeout=self.conf["scheduler"]["iteration timeout"],
                                                return_when="ALL_COMPLETED")

                # Update statuses
                for task_id in [task_id for task_id in self.__tasks
                                if self.__tasks[task_id]["status"] == "PROCESSING" and
                                "future" in self.__tasks[task_id] and self.__tasks[task_id]["future"].done()]:
                    self.__process_future(self.process_task_result, self.__tasks[task_id], task_id)
                    if not transition_done:
                        transition_done = True

                # Update jobs
                for job_id in [job_id for job_id in self.__jobs
                               if self.__jobs[job_id]["status"] in ["PENDING", "PROCESSING"] and
                               "future" in self.__jobs[job_id] and self.__jobs[job_id]["future"].done()]:
                    self.__process_future(self.process_job_result, self.__jobs[job_id], job_id)
                    if not transition_done:
                        transition_done = True

                    if self.__jobs[job_id]["status"] == "ERROR":
                        # Then terminate all pending and processing tasks for the job
                        self.__cancel_job_tasks(job_id)

                # Submit tools
                # todo: iteration period
                try:
                    logging.debug("Update information about available verification tools")
                    self.update_tools()
                except Exception as err:
                    logging.warning('Cannot submit verification tools information: {}'.format(err))

                # Get actual information about connected nodes
                # todo: proper error checking
                # todo: iteration period
                submit = True
                try:
                    logging.debug("Update information about connected nodes")
                    self.update_nodes()
                except Exception as err:
                    logging.error("Cannot obtain information about connected nodes: {}".format(err))
                    submit = False

                if submit:
                    # Schedule new tasks
                    logging.info("Start scheduling new tasks")
                    pending_tasks = [self.__tasks[task_id] for task_id in self.__tasks
                                     if self.__tasks[task_id]["status"] == "PENDING"]
                    pending_jobs = [self.__jobs[job_id] for job_id in self.__jobs
                                    if self.__jobs[job_id]["status"] == "PENDING"
                                    and "future" not in self.__jobs[job_id]]
                    pending_jobs = sorted(pending_jobs, key=lambda i: sort_priority(i['configuration']['priority']))
                    pending_tasks = sorted(pending_tasks, key=lambda i: sort_priority(i['description']['priority']))
                    tasks_to_start, jobs_to_start = self.schedule(pending_tasks, pending_jobs)
                    logging.info("Going to start {} new tasks and {} jobs".
                                 format(len(tasks_to_start), len(jobs_to_start)))

                    for job_id in jobs_to_start:
                        if "future" in self.__jobs[job_id] or self.__jobs[job_id]["status"] != "PENDING":
                            raise ValueError("Attempt to scheduler running or processed job {}".format(job_id))
                        try:
                            self.__jobs[job_id]["future"]\
                                = self.__attempts(self.solve_job, 1, 'start job {}'.format(job_id),
                                                  (job_id,
                                                   self.__jobs[job_id]))
                            if not transition_done:
                                transition_done = True
                        except SchedulerException as err:
                            msg = "Cannot start job {}: {}".format(job_id, err)
                            logging.warning(msg)
                            self.__jobs[job_id]["status"] = "ERROR"
                            self.__jobs[job_id]["error"] = msg

                    for task_id in tasks_to_start:
                        # This check is very helpful for debugging
                        if "future" in self.__tasks[task_id] or self.__tasks[task_id]["status"] != "PENDING":
                            raise ValueError("Attempt to scheduler running or processed task {}".format(task_id))
                        try:
                            self.__tasks[task_id]["future"]\
                                = self.__attempts(self.solve_task, 1, 'start task {}'.format(task_id),
                                                  (task_id,
                                                   self.__tasks[task_id]["description"],
                                                   self.__tasks[task_id]["user"],
                                                   self.__tasks[task_id]["password"]))
                            self.__tasks[task_id]["status"] = "PROCESSING"
                            if not transition_done:
                                transition_done = True
                        except SchedulerException as err:
                            msg = "Cannot start task {}: {}".format(task_id, err)
                            logging.warning(msg)
                            self.__tasks[task_id]["status"] = "ERROR"
                            self.__tasks[task_id]["error"] = msg

                    # Flushing tasks
                    logging.debug("Flush submitted tasks and jobs if necessary")
                    if isinstance(tasks_to_start, dict) and len(tasks_to_start.keys()) > 0:
                        self.flush()
                    else:
                        self.flush()
                else:
                    logging.warning("Do not run any tasks until actual information about the nodes will be obtained")

                logging.debug("Scheduler iteration has finished")
                if not transition_done:
                    self.__update_iteration_period()
                    time.sleep(self.__iteration_period['short'])
                else:
                    logging.info("Do not wait besause of statuses changing")
                    time.sleep(1)
            except KeyboardInterrupt:
                logging.error("Scheduler execution is interrupted, cancel all running threads")
                self.terminate()
                self.server.stop()
                exit(137)
            except Exception:
                exception_info = 'An error occured:\n{}'.format(traceback.format_exc().rstrip())
                logging.error(exception_info)
                self.terminate()
                if self.production:
                    logging.info("Reinitialize scheduler and try to proceed execution in 30 seconds...")
                    self.server.stop()
                    time.sleep(30)
                    self.init_scheduler()
                else:
                    self.server.stop()
                    exit(1)

    @abc.abstractmethod
    def schedule(self, pending_tasks, pending_jobs):
        """
        Get a list of new tasks which can be launched during current scheduler iteration. All pending jobs and tasks
        should be sorted reducing the priority to the end. Each task and job in arguments are dictionaries with full
        configuration or description.

        :param pending_tasks: List with all pending tasks.
        :param pending_jobs: List with all pending jobs.
        :return: List with identifiers of pending tasks to launch and list woth identifiers of jobs to launch.
        """
        return []

    @abc.abstractmethod
    def prepare_task(self, identifier, description):
        """
        Prepare a working directory before starting the solution.

        :param identifier: Verification task identifier.
        :param description: Dictionary with task description.
        :raise SchedulerException: If a task cannot be scheduled or preparation failed.
        """
        return

    @abc.abstractmethod
    def prepare_job(self, identifier, configuration):
        """
        Prepare a working directory before starting the solution.

        :param identifier: Verification task identifier.
        :param configuration: Job configuration.
        :raise SchedulerException: If a job cannot be scheduled or preparation failed.
        """
        return

    @abc.abstractmethod
    def solve_task(self, identifier, description, user, password):
        """
        Solve given verification task.

        :param identifier: Verification task identifier.
        :param description: Verification task description dictionary.
        :param user: User name.
        :param password: Password.
        :return: Return Future object.
        """
        return

    @abc.abstractmethod
    def solve_job(self, identifier, configuration):
        """
        Solve given verification job.

        :param identifier: Job identifier.
        :param configuration: Job configuration.
        :return: Return Future object.
        """
        return

    @abc.abstractmethod
    def flush(self):
        """Start solution explicitly of all recently submitted tasks."""

    @abc.abstractmethod
    def process_task_result(self, identifier, future):
        """
        Process result and send results to the server.

        :param identifier: Task identifier string.
        :param future: Future object.
        :return: status of the task after solution: FINISHED.
        :raise SchedulerException: in case of ERROR status.
        """
        return

    @abc.abstractmethod
    def process_job_result(self, identifier, future):
        """
        Process future object status and send results to the server.

        :param identifier: Job identifier string.
        :param future: Future object.
        :return: status of the job after solution: FINISHED.
        :raise SchedulerException: in case of ERROR status.
        """
        return

    @abc.abstractmethod
    def cancel_job(self, identifier, future):
        """
        Stop the job solution.

        :param identifier: Verification task ID.
        :param future: Future object.
        :return: Status of the task after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        :raise SchedulerException: In case of exception occured in future task.
        """
        return

    @abc.abstractmethod
    def cancel_task(self, identifier, future):
        """
        Stop the task solution.

        :param identifier: Verification task ID.
        :param future: Future object.
        :return: Status of the task after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        :raise SchedulerException: In case of exception occured in future task.
        """
        return

    @abc.abstractmethod
    def terminate(self):
        """
        Abort solution of all running tasks and any other actions before termination.
        """
        # Stop tasks
        for task_id in [task_id for task_id in self.__tasks if self.__tasks[task_id]["status"]
                        in ["PENDING", "PROCESSING"]]:
            self.__process_future(self.cancel_task, self.__tasks[task_id], task_id)
        # stop jobs
        for job_id in [job_id for job_id in self.__jobs if self.__jobs[job_id]["status"]
                       in ["PENDING", "PROCESSING"]]:
            self.__process_future(self.cancel_job, self.__jobs[job_id], job_id)

    @abc.abstractmethod
    def update_nodes(self, wait_controller=False):
        """
        Update statuses and configurations of available nodes and push them to the server.

        :param wait_controller: Ignore KV fails until it become working.
        :return: Return True if nothing has changes.
        """
        return True

    @abc.abstractmethod
    def update_tools(self):
        """
        Generate a dictionary with available verification tools and push it to the server.
        """
        return

    @property
    def __need_exchange(self):
        """
        Calculate how many seconds passed since the last data exchange. If that value is more than chosen currently
        exchange period then do exchange, otherwise skip it.

        :return: True if we should send data to Bridge now and False otherwise.
        """
        if not self.__last_exchange:
            return True
        elif int(time.time() - self.__last_exchange) > self.__current_period:
            return True
        else:
            logging.info("Skip the next data exchange iteration with Bridge")
            return False

    def __update_iteration_period(self):
        """
        Calculates the period of data exchange between Bridge and this scheduler. It tries dynamically adjust the value
        to not repeatedly send the same information but increasing the period if new tasks or jobs are expected.
        """
        def new_period(new):
            if self.__current_period < new:
                logging.info("Increase data exchange period from {}s to {}s".format(self.__current_period, new))
                self.__current_period = new
            elif self.__current_period > new:
                logging.info("Reduce data exchange period from {}s to {}s".format(self.__current_period, new))
                self.__current_period = new

        processing_jobs = [i for i in self.__jobs if self.__jobs[i]["status"] == 'PROCESSING' and
                           self.__jobs[i]["configuration"]["task scheduler"] == "Klever"]
        if len(processing_jobs) > 0:
            # Calculate pending resources of running tasks
            pairs = []
            for job in processing_jobs:
                pending = [t for t in self.__tasks if self.__tasks[t]["status"] == "PENDING" and
                           self.__tasks[t]["description"]["job id"] == job]
                processing = [t for t in self.__tasks if self.__tasks[t]["status"] in ["PROCESSING", "FINISHED"] and
                              self.__tasks[t]["description"]["job id"] == job]
                pair = [len(pending), len(processing)]
                pairs.append(pair)

            # Detect fast solving jobs
            for pair in pairs:
                # No tasks available
                if pair[0] == 0 and pair[1] == 0:
                    new_period(self.__iteration_period['short'])
                    return

            for pair in pairs:
                # Check wether we have free resources
                if pair[0] > 0 and pair[1] > 0:
                    new_period(self.__iteration_period['long'])
                    return

        new_period(self.__iteration_period['medium'])

    def __cancel_job_tasks(self, job_id):
        """
        Cancel all running and pending tasks for given job id.

        :param job_id: Job identifier string.
        :raise SchedulerException: Raised this in case of an exception occured in the future task.
        """

        for task_id in [task_id for task_id in self.__tasks
                        if self.__tasks[task_id]["status"] in ["PENDING", "PROCESSING"] and
                        self.__tasks[task_id]["description"]["job id"] == job_id]:
            self.__process_future(self.cancel_task, self.__tasks[task_id], task_id)

    @staticmethod
    def __process_future(handler, item, identifier):
        """
        Perform given method for given future object of solving job or task. It can be solving, canceling or anything
        else. It catches SchedulerException and update status to ERROR or in case of success set a new status provided
        by called handler.

        :param handler: Handler to do something with the job or task. It receives an identifier and future argument as
                        an input and returns new status.
        :param item: It is a value from either self.__tasks or self.__jobs collection.
        :param identifier: Identifier of a job or a task.
        """
        try:
            item["status"] = handler(identifier, item["future"] if "future" in item else None)
            logging.debug("Task {} new status is {}".format(identifier, item["status"]))
            if item["status"] not in ["FINISHED", "ERROR"]:
                raise ValueError("Scheduler got non-finished status {} for finished task {}".
                                 format(item["status"], identifier))
        except SchedulerException as err:
            logging.error("Cannot process results of task {}: {}".format(identifier, err))
            item["status"] = "ERROR"
            item["error"] = err

    @staticmethod
    def __attempts(handler, attempts, action, args):
        """
        Just performs N attempts of calling given handler until no exceptions arise. All exceptions are ignored.

        :param handler: Given handler method.
        :param attempts: Integer.
        :param action: String name of the action for logging.
        :param args: Arguments for the handler.
        :return: Result returned by the handler.
        """
        result = None
        error = None
        while attempts > 0:
            try:
                logging.info("Try to {}".format(action))
                result = handler(*args)
                break
            # todo: ignore particular exceptions
            except Exception as err:
                logging.error("Failed to {}: {}".format(action, err))
                time.sleep(30)
                attempts -= 1
                error = err
        if attempts == 0 and error:
            raise SchedulerException(error)

        return result

    @staticmethod
    def __report_error_server_state(server_state, message):
        """
        If an inconsistent server state json has been received from Bridge the method saves it to the disk with
        necessary additional information.

        :param server_state: Dictionary obtained from Bridge.
        :param message: String with a message intended for the log.
        :raise RuntimeError: At the end always rises the exception since the scheduler should not proceed with broken
                             Bridge.
        :return:
        """
        # Save server state file
        state_file_name = time.strftime("%d-%m-%Y %H:%M:%S server state.json")
        error_file = os.path.join(os.path.curdir, state_file_name)
        with open(error_file, 'w') as outfile:
            json.dump(server_state, outfile, ensure_ascii=False, sort_keys=True, indent=4)

        # Raise an exception
        raise RuntimeError("Received invalid server state (printed at {!r}): {!r}".
                           format(os.path.abspath(error_file), message))

    @staticmethod
    def __add_missing_restrictions(collection):
        """
        If resource limits are incomplete the method adds to given json all necessary fields filled with zeroes.

        :param collection: 'resource limits' dictionary from a task description or job configuration.
        """
        if len(collection.keys()) == 0:
            raise SchedulerException("Resource limitations are missing: upload filled tasks.json file and properly "
                                     "set job resource limitiations")

        for tag in ['memory size', 'number of CPU cores', 'disk memory size']:
            if tag not in collection:
                collection[tag] = 0
        if 'CPU model' not in collection:
            collection['CPU model'] = None

        # Make unit translation
        for mem in (m for m in ("memory size", "disk memory size") if m in collection and collection[m] is not None):
            collection[mem] = memory_units_converter(collection[mem])[0]
        for t in (t for t in ("wall time", "CPU time") if t in collection and collection[t] is not None):
            collection[t] = time_units_converter(collection[t])[0]

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
