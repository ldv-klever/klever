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

import utils
from schedulers import SchedulerException


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
        self.init()
        utils.clear_resources(self.logger)

    def is_solving(self, item):
        """
        Check that task or job has been started.

        :param item: Dictionary.
        :return: Bool
        """
        return 'future' in item

    def init(self):
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
        # Runners must implement the method
        raise NotImplementedError

    def prepare_task(self, identifier, item):
        """
        Prepare the task before rescheduling. This method is public and cannot raise any unexpected exceptions and can
        do rescheduling. This method is public and cannot raise any unexpected exceptions and can do
        rescheduling.

        :param identifier: Verification task identifier.
        :param item: Dictionary with task description.
        """
        self.logger.debug("Prepare new task {} before launching".format(identifier))
        try:
            # Add missing restrictions
            self._prepare_task(identifier, item["description"])
        except SchedulerException as err:
            self.logger.error("Cannot prepare task {} for submission: {!r}".format(identifier, err))
            item["status"] = "ERROR"
            item["error"] = err

    def _prepare_task(self, identifier, description):
        """
        Prepare a working directory before starting the solution.

        :param identifier: Verification task identifier.
        :param description: Dictionary with task description.
        :raise SchedulerException: If a task cannot be scheduled or preparation failed.
        """
        # Runners must implement the method
        raise NotImplementedError

    def prepare_job(self, identifier, item):
        """
        Prepare job before the solution. This method is public and cannot raise any unexpected exceptions and can do
        rescheduling.

        :param identifier: Verification job identifier.
        :param item: Dictionary with job description.
        """
        # Prepare jobs before launching
        self.logger.debug("Prepare new job {} before launching".format(identifier))
        try:
            self._prepare_job(identifier, item["configuration"])
        except SchedulerException as err:
            self.logger.error("Cannot prepare job {} for submission: {!r}".format(identifier, err))
            item["status"] = "ERROR"
            item["error"] = err

    def _prepare_job(self, identifier, configuration):
        """
        Prepare a working directory before starting the solution.

        :param identifier: Verification task identifier.
        :param configuration: Job configuration.
        :raise SchedulerException: If a job cannot be scheduled or preparation failed.
        """
        # Runners must implement the method
        raise NotImplementedError

    def solve_task(self, identifier, item):
        """
        Solve the task. This method is public and cannot raise any unexpected exceptions and can do rescheduling.

        :param identifier: Verification task identifier.
        :param item: Verification task description dictionary.
        :return: Bool.
        """
        try:
            item["future"] = self._solve_task(identifier, item["description"], item["user"], item["password"])
            item["status"] = "PROCESSING"
            return True
        except SchedulerException as err:
            item.setdefault("attempts", 0)
            item["attempts"] += 1

            if item["attempts"] > 2:
                msg = "Cannot solve task {}: {!r}".format(identifier, err)
                self.logger.warning(msg)
                item.update({"status": "ERROR", "error": msg})
                return True
            return False

    def _solve_task(self, identifier, description, user, password):
        """
        Solve given verification task.

        :param identifier: Verification task identifier.
        :param description: Verification task description dictionary.
        :param user: User name.
        :param password: Password.
        :return: Return Future object.
        """
        # Runners must implement the method
        raise NotImplementedError

    def solve_job(self, identifier, item):
        """
        Solve given verification job. This method is public and cannot raise any unexpected exceptions and can do
        rescheduling.

        :param identifier: Job identifier.
        :param item: Job descitption.
        :return: Bool.
        """
        try:
            item["future"] = self._solve_job(identifier, item)
        except SchedulerException as err:
            item.setdefault("attempts", 0)
            item["attempts"] += 1

            if item["attempts"] > 2:
                msg = "Cannot solve job {}: {!r}".format(identifier, err)
                self.logger.warning(msg)
                item.update({"status": "ERROR", "error": msg})
                return True
            return False

    def _solve_job(self, identifier, configuration):
        """
        Solve given verification job.

        :param identifier: Job identifier.
        :param configuration: Job configuration.
        :return: Return Future object.
        """
        # Runners must implement the method
        raise NotImplementedError

    def flush(self):
        """Start solution explicitly of all recently submitted tasks."""
        return

    def process_task_result(self, identifier, item):
        """
        Process result and send results to the server.

        :param identifier: Task identifier string.
        :param item: Verification task description dictionary.
        :return: Bool if status of the job has changed.
        """
        if item["future"].done():
            try:
                item["status"] = self._process_task_result(identifier, item["future"], item["description"])
                self.logger.debug("Task {} new status is {!r}".format(identifier, item["status"]))
                assert item["status"] not in ["FINISHED", "ERROR"]
            except SchedulerException as err:
                msg = "Task failed {}: {!r}".format(identifier, err)
                self.logger.warning(msg)
                item.update({"status": "ERROR", "error": msg})
            finally:
                utils.clear_resources(self.logger, identifier)
                del item["future"]
                return True
        else:
            return False
    
    def _process_task_result(self, identifier, future, description):
        """
        Process result and send results to the server.

        :param identifier: Task identifier string.
        :param future: Future object.
        :param description: Verification task description dictionary.
        :return: status of the task after solution: FINISHED.
        :raise SchedulerException: in case of ERROR status.
        """
        # Runners must implement the method
        raise NotImplementedError

    def process_job_result(self, identifier, item, task_items):
        """
        Process future object status and send results to the server.

        :param identifier: Job identifier string.
        :param item: Verification task description dictionary.
        :param task_items: Verification tasks description to cancel them if necessary.
        :return: Bool if status of the job has changed.
        """
        if item.get("future", None) and item["future"].done():
            try:
                item["status"] = self._process_job_result(identifier, item["future"])
                self.logger.debug("Job {} new status is {!r}".format(identifier, item["status"]))
                assert item["status"] not in ["FINISHED", "ERROR"]
            except SchedulerException as err:
                msg = "Job failed {}: {!r}".format(identifier, err)
                self.logger.warning(msg)
                item.update({"status": "ERROR", "error": msg})

                # Cancel tasks
                for task in task_items:
                    self.cancel_task(task["id"], task)
            finally:
                del item["future"]
                return True
        else:
            return False

    def _process_job_result(self, identifier, future):
        """
        Process future object status and send results to the server.

        :param identifier: Job identifier string.
        :param future: Future object.
        :return: status of the job after solution: FINISHED.
        :raise SchedulerException: in case of ERROR status.
        """
        # Runners must implement the method
        raise NotImplementedError

    def cancel_job(self, identifier, item, task_items):
        """
        Stop the job solution.

        :param identifier: Verification task ID.
        :param item: Verification task description dictionary.
        :param task_items: Verification tasks description to cancel them if necessary.
        """
        try:
            if item.get("future", False) and not item["future"].cancel():
                item["status"] = self._cancel_job(identifier, item["future"])
                assert item["status"] not in ["FINISHED", "ERROR"]
            else:
                item["status"] = "ERROR"
                item["error"] = "Task has been cancelled before execution"
            self.logger.debug("Job {} new status is {!r}".format(identifier, item["status"]))
        except SchedulerException as err:
            self.logger.error("Job {} has failed: {!r}".format(identifier, err))
            item["status"] = "ERROR"
            item["error"] = err
        finally:
            # Cancel tasks
            for task in task_items:
                self.cancel_task(task["id"], task)
            if "future" in item:
                del item["future"]

    def _cancel_job(self, identifier, future):
        """
        Stop the job solution.

        :param identifier: Verification task ID.
        :param future: Future object.
        :return: Status of the task after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        :raise SchedulerException: In case of exception occured in future task.
        """
        # Runners must implement the method
        raise NotImplementedError

    def cancel_task(self, identifier, item):
        """
        Stop the task solution.

        :param identifier: Verification task ID.
        :param item: Task description.
        """
        try:
            if item.get("future", False) and not item["future"].cancel():
                item["status"] = self._cancel_task(identifier, item["future"])
                assert item["status"] not in ["FINISHED", "ERROR"]
            else:
                item["status"] = "ERROR"
                item["error"] = "Task has been cancelled before execution"
            self.logger.debug("Task {} new status is {!r}".format(identifier, item["status"]))
        except SchedulerException as err:
            self.logger.error("Cannot process results of task {}: {!r}".format(identifier, err))
            item["status"] = "ERROR"
            item["error"] = err
        finally:
            if "future" in item:
                del item["future"]

    def _cancel_task(self, identifier, future):
        """
        Stop the task solution.

        :param identifier: Verification task ID.
        :param future: Future object.
        :return: Status of the task after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        :raise SchedulerException: In case of exception occured in future task.
        """
        # Runners must implement the method
        raise NotImplementedError

    def terminate(self):
        """Abort solution of all running tasks and any other actions before termination."""
        return

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
