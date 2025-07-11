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
import math
from klever.scheduler.schedulers import SchedulerException


def incmean(prevmean, n, x):
    """Calculate incremental mean"""
    newmean = prevmean + int(round((x - prevmean) / n))
    return newmean


def incsum(prevsum, prevmean, mean, x):
    """Calculate incremental sum of square deviations"""
    newsum = prevsum + abs((x - prevmean) * (x - mean))
    return newsum


def devn(cursum, n):
    """Calculate incremental standard deviation"""
    deviation = int(round(math.sqrt(cursum / n)))
    return deviation


class Runner:
    """Class provide general scheduler API."""

    accept_jobs = True
    accept_tag = 'Klever'

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

    @staticmethod
    def scheduler_type():
        """Return type of the scheduler: 'VerifierCloud' or 'Klever'."""
        raise NotImplementedError

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
        :return: List with identifiers of pending tasks to launch and list with identifiers of jobs to launch.
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
        :return: True if it is possible to run the task and False otherwise
        """
        try:
            # Add missing restrictions
            return self._prepare_task(identifier, item["description"])
        except SchedulerException as err:
            msg = "Cannot prepare task {!r} for submission: {!r}".format(identifier, str(err))
            self.logger.warning(msg)
            item["status"] = "ERROR"
            item["error"] = msg
            return False

    def _prepare_task(self, identifier, description):  # pylint:disable=unused-argument
        """
        Prepare a working directory before starting the solution.

        :param identifier: Verification task identifier.
        :param description: Dictionary with task description.
        :raise SchedulerException: If a task cannot be scheduled or preparation failed.
        :return: True if it is possible to run the task and False otherwise
        """
        # Runners should implement the method
        return True

    def prepare_job(self, identifier, item):
        """
        Prepare job before the solution. This method is public and cannot raise any unexpected exceptions and can do
        rescheduling.

        :param identifier: Verification job identifier.
        :param item: Dictionary with job description.
        :return: True if it is possible to run the task and False otherwise
        """
        # Prepare jobs before launching
        self.logger.debug("Prepare new job {} before launching".format(identifier))
        try:
            return self._prepare_job(identifier, item["configuration"])
        except SchedulerException as err:
            msg = "Cannot prepare job {!r} for submission: {!r}".format(identifier, str(err))
            self.logger.warning(msg)
            item["status"] = "ERROR"
            item["error"] = msg
            return False

    def _prepare_job(self, identifier, configuration):  # pylint:disable=unused-argument
        """
        Prepare a working directory before starting the solution.

        :param identifier: Verification job identifier.
        :param configuration: Job configuration.
        :raise SchedulerException: If a job cannot be scheduled or preparation failed.
        """
        return True

    def solve_task(self, identifier, item):
        """
        Solve the task. This method is public and cannot raise any unexpected exceptions and can do rescheduling.

        :param identifier: Verification task identifier.
        :param item: Verification task description dictionary.
        :return: Bool.
        """
        try:
            # Do this again before running to maybe reduce limitations.
            item["future"] = self._solve_task(identifier, item["description"], item["description"].get("login"),
                                              item["description"].get("password"))
            item["status"] = "PROCESSING"
            return True
        except SchedulerException as err:
            item.setdefault("attempts", 0)
            item["attempts"] += 1
            msg = "Cannot solve task {}: {!r}".format(identifier, str(err))
            self.logger.warning(msg)

            if item["attempts"] > 2:
                item.update({"status": "ERROR", "error": msg})
                return False
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
        :param item: Job description.
        :return: Bool.
        """
        try:
            item["future"] = self._solve_job(identifier, item)
            return True
        except SchedulerException as err:
            item.setdefault("attempts", 0)
            item["attempts"] += 1
            msg = "Cannot solve job {}: {!r}".format(identifier, str(err))
            self.logger.warning(msg)

            if item["attempts"] > 2:
                item.update({"status": "ERROR", "error": msg})
                return False
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

    def _is_done(self, item):
        """
        Checks if the job or task done

        :param item: verification dictionary.
        :return: bool result and exit code.
        """
        # Runners must implement the method
        raise NotImplementedError

    def process_task_result(self, identifier, item):
        """
        Process result and send results to the server.

        :param identifier: Task identifier string.
        :param item: Verification task description dictionary.
        :return: Bool if status of the job has changed.
        """
        done, result = self._is_done(item)
        if done:
            try:
                item.pop('error', None)
                item["status"], item['solution'] = self._process_task_result(identifier, result, item["description"])
                self.logger.debug("Task {} new status is {!r}".format(identifier, item["status"]))
                assert item["status"] in ["FINISHED", "ERROR"]
            except SchedulerException as err:
                msg = "Solution of task {} failed: {!r}".format(identifier, str(err))
                self.logger.warning(msg)
                item.update({"status": "ERROR", "error": msg})
            finally:
                del item["future"]
            return True

        return False

    def _process_task_result(self, identifier, result, description):
        """
        Process result and send results to the server.

        :param identifier: Task identifier string.
        :param result: exit code.
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
        :param item: Verification job description dictionary.
        :param task_items: Verification tasks description to cancel them if necessary.
        :return: Bool if status of the job has changed.
        """
        done, result = self._is_done(item)
        if done:
            try:
                item.pop('error', None)
                item["status"] = self._process_job_result(identifier, result)
                self.logger.debug("Job {} new status is {!r}".format(identifier, item["status"]))
                assert item["status"] in ["FINISHED", "ERROR"]
            except SchedulerException as err:
                msg = "Solution of job {} failed: {!r}".format(identifier, str(err))
                self.logger.warning(msg)
                item.update({"status": "ERROR", "error": msg})

                # Cancel tasks
                for task in task_items:
                    self.cancel_task(task["id"], task)
            finally:
                del item["future"]
            return True

        return False

    def _process_job_result(self, identifier, result):
        """
        Process future object status and send results to the server.

        :param identifier: Job identifier string.
        :param result: exit code.
        :return: status of the job after solution: FINISHED.
        :raise SchedulerException: in case of ERROR status.
        """
        # Runners must implement the method
        raise NotImplementedError

    def _cancel_solution(self, process, identifier, mode='task'):
        """
        Stop the solution.

        :param process: process object.
        :param identifier: Verification job ID.
        :return: Status of the task after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        :raise SchedulerException: In case of exception occurred in future task.
        """
        # Runners must implement the method or cancel_job/task directly
        raise NotImplementedError

    def _is_cancelable(self, identifier, item, mode='task'):
        """
        Checks if the solution can be canceled

        :param item: Verification job description dictionary.
        :param identifier: Verification job ID.
        :return: process object if cancelable or None
        :raise SchedulerException: In case of exception occurred in future task.
        """
        # Runners must implement the method or cancel_job/task directly
        raise NotImplementedError

    def cancel_job(self, identifier, item, task_items):
        """
        Stop the job solution.

        :param identifier: Job identifier string.
        :param item: Verification job description dictionary.
        :param task_items: Verification tasks description to cancel them if necessary.
        """
        try:
            process = self._is_cancelable(identifier, item, 'job')
            if process:
                item["status"] = self._cancel_job(process, identifier)
                assert item["status"] in ["FINISHED", "ERROR"]
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

    def _cancel_job(self, process, identifier):
        """
        Stop the job solution.

        :param process: job process.
        :param identifier: Verification job ID.
        :return: Status of the task after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        :raise SchedulerException: In case of exception occurred in future task.
        """
        return self._cancel_solution(process, identifier, mode='job')

    def cancel_task(self, identifier, item):
        """
        Stop the task solution.

        :param identifier: Verification task ID.
        :param item: Task description.
        """
        try:
            process = self._is_cancelable(identifier, item, 'task')
            if process:
                item["status"], _ = self._cancel_task(process, identifier)
                self.logger.debug("Cancelled task {} finished with status: {!r}".format(identifier, item["status"]))
                assert item["status"] in ["FINISHED", "ERROR"]
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

    def _cancel_task(self, process, identifier):
        """
        Stop the task solution.

        :param process: task process.
        :param identifier: Verification task ID.
        :return: Status of the task after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        :raise SchedulerException: In case of exception occurred in future task.
        """
        return self._cancel_solution(process, identifier, mode='job')

    def add_job_progress(self, identifier, item, progress):  # pylint:disable=unused-argument
        """
        Save information about the progress if necessary.

        :param identifier: Job identifier string.
        :param item: Verification job description dictionary.
        :param progress: Information about the job progress.
        """
        return

    def terminate(self):
        """Abort solution of all running tasks and any other actions before termination."""
        return

    def update_nodes(self, wait_controller=False):  # pylint:disable=unused-argument
        """
        Update statuses and configurations of available nodes and push them to the server.

        :param wait_controller: Ignore KV fails until it become working.
        :return: Return True if nothing has changes.
        """
        return True

    def update_tools(self):
        """Generate a dictionary with available verification tools and push it to the server."""
        return
