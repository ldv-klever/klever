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

import concurrent.futures
import os
import time
import traceback
import json

import server.testgenerator as testgenerator
import server.bridge as bridge
from utils import sort_priority, time_units_converter, memory_units_converter


def get_gateway(conf, logger, work_dir):
    """
    Check which implementation of Session object to choose to get tasks

    :param conf: Configuration dictionary.
    :param logger: Logger object.
    :param work_dir: Path to the working directory.
    :return: Return object of the implementation of Session abstract class.
    """
    if "debug with testgenerator" in conf["scheduler"] and conf["scheduler"]["debug with testgenerator"]:
        return testgenerator.Server(logger, conf["testgenerator"], work_dir)
    else:
        return bridge.Server(logger, conf["Klever Bridge"], work_dir)


class SchedulerException(RuntimeError):
    """Exception is used to determine when task or job fails but not scheduler."""
    pass


class Runner:
    """Class provide general scheduler API."""

    @staticmethod
    def scheduler_type():
        """Return type of the scheduler: 'VerifierCloud' or 'Klever'."""
        return "Klever"

    def __init__(self, conf, logger, work_dir, server):
        """
        Get configuration and prepare working directory.

        :param conf: Dictionary with relevant configuration.
        :param logger: Logger object.
        :param work_dir: PAth to the working directory.
        :param server: Session object.
        """
        self.conf = conf
        self.logger = logger
        self.work_dir = work_dir
        self.server = server
        self.init_scheduler()

    def job_is_solving(self, identifier):
        raise NotImplementedError

    def task_is_solving(self, identifier):
        raise NotImplementedError

    def init_scheduler(self):
        """
        Initialize scheduler completely. This method should be called both at constructing stage and scheduler
        reinitialization. Thus, all object attribute should be cleaned up and set as it is a newly created object.
        """
        return

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

    def prepare_task(self, identifier, description):
        """
        Prepare a working directory before starting the solution.

        :param identifier: Verification task identifier.
        :param description: Dictionary with task description.
        :raise SchedulerException: If a task cannot be scheduled or preparation failed.
        """
        return

    def prepare_job(self, identifier, configuration):
        """
        Prepare a working directory before starting the solution.

        :param identifier: Verification task identifier.
        :param configuration: Job configuration.
        :raise SchedulerException: If a job cannot be scheduled or preparation failed.
        """
        return

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

    def solve_job(self, identifier, configuration):
        """
        Solve given verification job.

        :param identifier: Job identifier.
        :param configuration: Job configuration.
        :return: Return Future object.
        """
        return

    def flush(self):
        """Start solution explicitly of all recently submitted tasks."""

    def process_task_result(self, identifier, future):
        """
        Process result and send results to the server.

        :param identifier: Task identifier string.
        :param future: Future object.
        :return: status of the task after solution: FINISHED.
        :raise SchedulerException: in case of ERROR status.
        """
        return

    def process_job_result(self, identifier, future):
        """
        Process future object status and send results to the server.

        :param identifier: Job identifier string.
        :param future: Future object.
        :return: status of the job after solution: FINISHED.
        :raise SchedulerException: in case of ERROR status.
        """
        return

    def cancel_job(self, identifier, future, after_term=False):
        """
        Stop the job solution.

        :param identifier: Verification task ID.
        :param future: Future object.
        :param after_term: Flag that signals that we already got a termination signal.
        :return: Status of the task after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        :raise SchedulerException: In case of exception occured in future task.
        """
        return

    def cancel_task(self, identifier, future, after_term=False):
        """
        Stop the task solution.

        :param identifier: Verification task ID.
        :param future: Future object.
        :param after_term: Flag that signals that we already got a termination signal.
        :return: Status of the task after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        :raise SchedulerException: In case of exception occured in future task.
        """
        return

    def terminate(self):
        """
        Abort solution of all running tasks and any other actions before termination.
        """
        # stop jobs
        for job_id in [job_id for job_id in self.__jobs if self.__jobs[job_id]["status"]
                       in ["PENDING", "PROCESSING"]]:
            if "future" in self.__jobs[job_id]:
                self.__jobs[job_id]["future"].cancel()
            self.__process_future(self.cancel_job, self.__jobs[job_id], job_id, True)
        # Stop tasks
        for task_id in [task_id for task_id in self.__tasks
                        if self.__tasks[task_id]["status"] in ["PENDING", "PROCESSING"]]:
            if "future" in self.__tasks[task_id]:
                self.__tasks[task_id]["future"].cancel()
            self.__process_future(self.cancel_task, self.__tasks[task_id], task_id, True)

    def update_nodes(self, wait_controller=False):
        """
        Update statuses and configurations of available nodes and push them to the server.

        :param wait_controller: Ignore KV fails until it become working.
        :return: Return True if nothing has changes.
        """
        return True

    def update_tools(self):
        """
        Generate a dictionary with available verification tools and push it to the server.
        """
        return

    def cancel_job_tasks(self, job_id):
        """
        Cancel all running and pending tasks for given job id.

        :param job_id: Job identifier string.
        :raise SchedulerException: Raised this in case of an exception occured in the future task.
        """

        for task_id in [task_id for task_id in self.__tasks
                        if self.__tasks[task_id]["status"] in ["PENDING", "PROCESSING"] and
                        self.__tasks[task_id]["description"]["job id"] == job_id]:
            self.__process_future(self.cancel_task, self.__tasks[task_id], task_id)

    def __process_future(self, handler, item, identifier, *args):
        """
        Perform given method for given future object of solving job or task. It can be solving, canceling or anything
        else. It catches SchedulerException and update status to ERROR or in case of success set a new status provided
        by called handler.

        :param handler: Handler to do something with the job or task. It receives an identifier and future argument as
                        an input and returns new status.
        :param item: It is a value from either self.__tasks or self.__jobs collection.
        :param args: Additional arguments to handler.
        :param identifier: Identifier of a job or a task.
        """
        try:
            item["status"] = handler(identifier, item["future"] if "future" in item else None, *args)
            self.logger.debug("Task {} new status is {}".format(identifier, item["status"]))
            if item["status"] not in ["FINISHED", "ERROR"]:
                raise ValueError("Scheduler got non-finished status {} for finished task {}".
                                 format(item["status"], identifier))
        except SchedulerException as err:
            self.logger.error("Cannot process results of task {}: {}".format(identifier, err))
            item["status"] = "ERROR"
            item["error"] = err

    def __attempts(self, handler, attempts, action, args):
        """
        Just performs N attempts of calling given handler until no exceptions arise. All exceptions are ignored.

        :param handler: Given handler method.
        :param attempts: Integer.
        :param action: String name of the action for self.logger.
        :param args: Arguments for the handler.
        :return: Result returned by the handler.
        """
        result = None
        error = None
        while attempts > 0:
            try:
                self.logger.info("Try to {}".format(action))
                result = handler(*args)
                break
            # todo: ignore particular exceptions
            except Exception as err:
                self.logger.error("Failed to {}: {}".format(action, err))
                time.sleep(30)
                attempts -= 1
                error = err
        if attempts == 0 and error:
            raise SchedulerException(error)

        return result
