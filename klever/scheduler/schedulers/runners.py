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
import klever.scheduler.utils as utils
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
        #utils.kv_clear_solutions(self.logger, self.scheduler_type())

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

    def _prepare_task(self, identifier, description):
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

    def _prepare_job(self, identifier, configuration):
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

    def process_task_result(self, identifier, item):
        """
        Process result and send results to the server.

        :param identifier: Task identifier string.
        :param item: Verification task description dictionary.
        :return: Bool if status of the job has changed.
        """
        if item["future"].done():
            try:
                item.pop('error', None)
                item["status"] = self._process_task_result(identifier, item["future"], item["description"])
                self.logger.debug("Task {} new status is {!r}".format(identifier, item["status"]))
                assert item["status"] in ["FINISHED", "ERROR"]
            except SchedulerException as err:
                msg = "Task failed {}: {!r}".format(identifier, err)
                self.logger.warning(msg)
                item.update({"status": "ERROR", "error": msg})
            finally:
                utils.kv_clear_solutions(self.logger, self.scheduler_type(), identifier)
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
        :param item: Verification job description dictionary.
        :param task_items: Verification tasks description to cancel them if necessary.
        :return: Bool if status of the job has changed.
        """
        if item.get("future") and item["future"].done():
            try:
                item.pop('error', None)
                item["status"] = self._process_job_result(identifier, item["future"])
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

        :param identifier: Job identifier string.
        :param item: Verification job description dictionary.
        :param task_items: Verification tasks description to cancel them if necessary.
        """
        try:
            if item.get("future") and not item["future"].cancel():
                item["status"] = self._cancel_job(identifier, item["future"])
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

    def _cancel_job(self, identifier, future):
        """
        Stop the job solution.

        :param identifier: Verification job ID.
        :param future: Future object.
        :return: Status of the task after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        :raise SchedulerException: In case of exception occurred in future task.
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
            if item.get("future") and not item["future"].cancel():
                item["status"] = self._cancel_task(identifier, item["future"])
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

    def _cancel_task(self, identifier, future):
        """
        Stop the task solution.

        :param identifier: Verification task ID.
        :param future: Future object.
        :return: Status of the task after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        :raise SchedulerException: In case of exception occurred in future task.
        """
        # Runners must implement the method
        raise NotImplementedError

    def add_job_progress(self, identifier, item, progress):
        """
        Save information about the progress if necessary.

        :param identifier: Job identifier string.
        :param item: Verification job description dictionary.
        :param progress: Information about the job progress.
        """
        return

    def terminate(self):
        """Abort solution of all running tasks and any other actions before termination."""
        utils.kv_clear_solutions(self.logger, self.scheduler_type())
        return

    def update_nodes(self, wait_controller=False):
        """
        Update statuses and configurations of available nodes and push them to the server.

        :param wait_controller: Ignore KV fails until it become working.
        :return: Return True if nothing has changes.
        """
        return True

    def update_tools(self):
        """Generate a dictionary with available verification tools and push it to the server."""
        return


class SpeculativeSimple(Runner):
    """This runner collects statistics and adjust memory limits to run more tasks."""

    def init(self):
        """
        Initialize scheduler completely. This method should be called both at constructing stage and scheduler
        reinitialization. Thus, all object attribute should be cleaned up and set as it is a newly created object.
        """
        super(SpeculativeSimple, self).init()
        # Timeout tasks
        self._problematic = dict()
        # Data about job tasks
        self._jdata = dict()

    def prepare_task(self, identifier, item):
        """
        Prepare the task before rescheduling. This method is public and cannot raise any unexpected exceptions and can
        do rescheduling. This method is public and cannot raise any unexpected exceptions and can do
        rescheduling.

        :param identifier: Verification task identifier.
        :param item: Dictionary with task description.
        """
        message = None
        if item["description"]["job id"] in self._jdata:
            message = self._estimate_resource_limitations(item, identifier)
        super(SpeculativeSimple, self).prepare_task(identifier, item)
        return message

    def solve_job(self, identifier, item):
        """
        Solve given verification job. This method is public and cannot raise any unexpected exceptions and can do
        rescheduling.

        :param identifier: Job identifier.
        :param item: Job description.
        :return: Bool.
        """
        successful = super(SpeculativeSimple, self).solve_job(identifier, item)
        if successful:
            jd = self._track_job(identifier)
            jd["QoS limit"] = dict(item['configuration']['task resource limits'])
        return successful

    def process_task_result(self, identifier, item):
        """
        Process result and send results to the server.

        :param identifier: Task identifier string.
        :param item: Verification task description dictionary.
        :return: Bool if status of the job has changed.
        """
        # Get solution in advance before it is cleaned
        if item["future"].done():
            solution = utils.kv_get_solution(self.logger, self.scheduler_type(), identifier)
        else:
            solution = False
        status = super(SpeculativeSimple, self).process_task_result(identifier, item)
        if status and solution:
            solved = self._add_solution(item["description"]["job id"], item["description"]["solution class"],
                                        identifier, solution)
            if not solved:
                # We need to prepare task again to set new resource limitations to configuration files and solve it
                # once again
                self.prepare_task(identifier, item)
                self.logger.info("Reschedule task {} of category {!r} due to underapproximated memory limit".
                                 format(identifier, item["description"]["solution class"]))
                item["status"] = "PENDING"
                item["rescheduled"] = True
        elif status and not solution:
            self.logger.info('Missing decision results for task {}:{}'.
                             format(item["description"]["solution class"], identifier))
            self._del_task(item["description"]["job id"], item["description"]["solution class"], identifier)
        return status

    def process_job_result(self, identifier, item, task_items):
        """
        Process future object status and send results to the server.

        :param identifier: Job identifier string.
        :param item: Verification job description dictionary.
        :param task_items: Verification tasks description to cancel them if necessary.
        :return: Bool if status of the job has changed.
        """
        status = super(SpeculativeSimple, self).process_job_result(identifier, item, task_items)
        if status:
            # Add log and asserts
            jd = self._track_job(identifier)
            if sum([len([jd["limits"][att]["tasks"] for att in jd["limits"]])]) > 0:
                self.logger.debug("Job {} max task number was given as {} and solved successfully {}".
                                  format(identifier, jd.get("total tasks", 0), jd.get("solved", 0)))
                for att, attd in ((a, d) for a, d in jd["limits"].items() if d.get('statistics') is not None):
                    self.logger.info(
                        '\n\t'.join([
                            "Task category {!r} statistics:".format(att),
                            "solved: {}".format(attd["statistics"].get("number", 0)),
                            "memory consumption deviation: {}GB".format(
                                utils.memory_units_converter(attd["statistics"].get("mean mem", 0), 'GB')[0]),
                            "mean memory consumption: {}GB".format(
                                utils.memory_units_converter(attd["statistics"].get("memdev", 0), 'GB')[0]),
                            "mean CPU time consumption: {}s".format(
                                int(attd["statistics"].get("mean time", 0))),
                            "CPU time consumption deviation: {}s".format(
                                int(attd["statistics"].get("timedev", 0)))
                        ])
                    )

            self.del_job(identifier)
        return status

    def cancel_job(self, identifier, item, task_items):
        """
        Stop the job solution.

        :param identifier: Verification job ID.
        :param item: Verification job description dictionary.
        :param task_items: Verification tasks description to cancel them if necessary.
        """
        super(SpeculativeSimple, self).cancel_job(identifier, item, task_items)
        self.del_job(identifier)

    def cancel_task(self, identifier, item):
        """
        Stop the task solution.

        :param identifier: Verification task ID.
        :param item: Task description.
        """
        super(SpeculativeSimple, self).cancel_task(identifier, item)
        if self._is_there(item["description"]["job id"], item["description"]["solution class"], identifier):
            self._del_task(item["description"]["job id"], item["description"]["solution class"], identifier)

    def terminate(self):
        """Abort solution of all running tasks and any other actions before termination."""
        super(SpeculativeSimple, self).terminate()
        # Clean data
        self._problematic = dict()
        self._jdata = dict()

    def add_job_progress(self, identifier, item, progress):
        """
        Save information about the progress if necessary.

        :param identifier: Job identifier string.
        :param item: Verification job description dictionary.
        :param progress: Information about the job progress.
        """
        super(SpeculativeSimple, self).add_job_progress(identifier, item, progress)
        if progress.get('total_ts'):
            jd = self._track_job(identifier)
            jd['total tasks'] = progress['total_ts']

    def _is_there(self, job_identifier, attribute, identifier):
        """
        Check that the task if already tracked as a time or memory limit.

        :param job_identifier: Job identifier.
        :param attribute: Attribute given to the job to classify it.
        :param identifier: Identifier of the task.
        :return: True if it is a known limit task.
        """

        if job_identifier in self._jdata and attribute in self._jdata[job_identifier]["limits"] and \
                identifier in self._jdata[job_identifier]["limits"][attribute]["tasks"] and \
                self._jdata[job_identifier]["limits"][attribute]["tasks"][identifier]["status"] in \
                ('OUT OF MEMORY', 'TIMEOUT', 'OUT OF JAVA MEMORY', 'TIMEOUT (OUT OF JAVA MEMORY)'):
            return True
        return False

    def _is_there_or_init(self, job_identifier, attribute, identifier):
        """
        Check that the task if already tracked as a time or memory limit. If not create a new description for the task
        as it is a limit.

        :param job_identifier: Job identifier.
        :param attribute: Attribute given to the job to classify it.
        :param identifier: Identifier of the task.
        :return: Description of the task.
        """
        jd = self._track_job(job_identifier)
        attd = jd["limits"].setdefault(attribute,
                                       {
                                           "tasks": dict(),
                                           "statistics": None
                                       })
        task = attd["tasks"].setdefault(identifier, {"limitation": dict(), "status": None})
        return task

    def _del_task(self, job_identifier, attribute, identifier):
        """
        Delete task. This means that it is either solved or failed.

        :param job_identifier: Job identifier.
        :param attribute: Attribute given to the job to classify it.
        :param identifier: Identifier of the task.
        :return: None
        """
        job = self._track_job(job_identifier)
        if attribute in job["limits"]:
            del job["limits"][attribute]["tasks"][identifier]

    def _track_job(self, job_identifier):
        """
        Start tracking the job.

        :param job_identifier: Job identifier.
        :return: Job solutions description.
        """
        return self._jdata.setdefault(job_identifier,
                                      {
                                          "limits": dict(),
                                          "total tasks": None,
                                          "QoS limit": None,
                                          "solved": 0
                                      })

    def del_job(self, job_identifier):
        """
        Stop tracking the job.

        :param job_identifier: job identifier.
        :return: None
        """
        if job_identifier in self._jdata:
            del self._jdata[job_identifier]

    def _estimate_resource_limitations(self, item, identifier):
        """
        :param item: Description of the task.
        :param identifier: Task identifier.
        :return: New resource limitations.
        """
        job_identifier = item["description"]["job id"]
        attribute = item["description"]["solution class"]
        job_limitations = item["description"]["resource limits"]
        message = "Set job limit for task {}: ".format(identifier)

        # First set QoS limit
        job = self._track_job(job_identifier)
        qos = job.get("QoS limit")
        assert qos is not None
        assert job_limitations is not None

        # Start tracking the element
        element = self._is_there_or_init(job_identifier, attribute, identifier)
        limits = dict(job_limitations)

        # Check do we have some statistics already
        speculative = False

        if limits.get('memory size', 0) <= 0:
            message += 'There is no memory size limitation at solving task {}.'
        elif limits.get('CPU time') and limits['CPU time'] > qos['CPU time']:
            message += 'There is no memory size limitation at solving task {}.'
        elif self._is_there(job_identifier, attribute, identifier):
            limits = dict(qos)
            message = 'Set QoS limit for the task {}'.format(identifier)
        elif not job.get("total tasks", None) or job.get("solved", 0) <= (0.05 * job.get("total tasks", 0)):
            message += 'We have not enough solved tasks (5%) to yield speculative limit'
        elif not job["limits"][attribute]["statistics"] or job["limits"][attribute]["statistics"]["number"] <= 5:
            message += 'We have not solved at least 5 tasks to estimate average consumption'
        else:
            statistics = job["limits"][attribute]["statistics"]
            if int(statistics['mean mem']) < 0:
                raise ValueError('Mean memory is negative: {}'.format(int(statistics['mean mem'])))
            if int(statistics['memdev']) < 0:
                raise ValueError('Memory deviation is negative: {}'.format(int(statistics['memdev'])))
            limits['memory size'] = int(statistics['mean mem']) + 2 * int(statistics['memdev'])
            if limits['memory size'] < qos['memory size']:
                message = "Try running task {} with a speculative limitation {}B".\
                          format(identifier, limits['memory size'])
                speculative = True
            else:
                message += "Estimation {}B is too high.".format(limits['memory size'])
                limits = dict(job_limitations)

        element["limitation"] = limits
        item["description"]["resource limits"] = limits
        item["description"]["speculative"] = speculative
        return message

    def _add_statisitcs(self, job, attribute, resources):
        """
        Add statistics collected after task solution.

        :param job: Description dictionary of the job.
        :param attribute: Attribute given to the job to classify it.
        :param resources: Dictionary with resource consumption data.
        :return: None
        """
        if not job["limits"][attribute]["statistics"]:
            job["limits"][attribute]["statistics"] = {
                'mean mem': resources['memory size'],
                'memsum': 0,
                'memdev': 0,
                'mean time': resources['CPU time'] / 1000,
                'timesum': 0,
                'timedev': 0,
                'number': 1
            }
        else:
            statistics = job["limits"][attribute]["statistics"]
            statistics['number'] += 1
            # First save data for CPU
            newmean = incmean(statistics['mean time'], statistics['number'], resources['CPU time'] / 1000)
            newsum = incsum(statistics['timesum'], statistics['mean time'], newmean, resources['CPU time'] / 1000)
            timedev = devn(newsum, statistics['number'])
            statistics.update({'mean time': newmean, 'timesum': newsum, 'timedev': timedev})

            # Then memory
            newmean = incmean(statistics['mean mem'], statistics['number'], resources['memory size'])
            newsum = incsum(statistics['memsum'], statistics['mean mem'], newmean, resources['memory size'])
            memdev = devn(newsum, statistics['number'])
            statistics.update({'mean mem': newmean, 'memsum': newsum, 'memdev': memdev})

    def _add_solution(self, job_identifier, attribute, identifier, solution):

        """
        Save solution and return is this solution is final or not.

        :param job_identifier: Job identifier.
        :param attribute: Attribute given to the job to classify it.
        :param identifier: Identifier of the task.
        :param solution: Data from the task solution.
        :return: True if task is solved.
        """
        status = solution["status"]
        resources = solution["resources"]
        job = self._track_job(job_identifier)
        element = self._is_there_or_init(job_identifier, attribute, identifier)
        element["status"] = status

        # Check that it is an error from scheduler
        self.logger.info("Task {}:{} finished with status".format(attribute, identifier, status))
        if resources:
            job["solved"] += 1
            self.logger.debug(
                "Task {} from category {!r} solved with status {!r} and required {}B of memory and {}s of CPU time".
                format(identifier, attribute, status, resources['memory size'], int(resources['CPU time'] / 1000)))

            if solution['uploaded']:
                self._del_task(job_identifier, attribute, identifier)
                self._add_statisitcs(job, attribute, resources)
                self.logger.info("Accept task {}".format(identifier))
                return True
            else:
                self.logger.info("Do not accept timeout task {} with status {!r}".
                                 format(identifier, status))
                return False
        else:
            self._del_task(job_identifier, attribute, identifier)
            return True


class Speculative(SpeculativeSimple):

    def _add_statisitcs(self, job, attribute, resources):
        """
        Add statistics collected after task solution.

        :param job: Description dictionary of the job.
        :param attribute: Attribute given to the job to classify it.
        :param resources: Dictionary with resource consumption data.
        :return: None
        """

        def inc_wighted_mean(totalsumm, totaltime):
            """Calculate incremental mean"""
            return round(totalsumm/totaltime)

        if not job["limits"][attribute]["statistics"]:
            job["limits"][attribute]["statistics"] = {
                'mean mem': 0,
                'memsum': 0,
                'memdevsum': 0,
                'memdev': 0,
                'mean time': 0,
                'timedevsum': 0,
                'timesum': 0,
                'timedev': 0,
                'number': 0,
            }

        statistics = job["limits"][attribute]["statistics"]
        statistics['number'] += 1
        statistics['timesum'] += (resources['CPU time'] / 1000)

        # First save data for CPU
        newmean = incmean(statistics['mean time'], statistics['number'], resources['CPU time'] / 1000)
        newsum = incsum(statistics['timedevsum'], statistics['mean time'], newmean, resources['CPU time'] / 1000)
        if newsum != 0:
            timedev = devn(newsum, statistics['number'])
        else:
            timedev = 0
        statistics.update({'mean time': newmean, 'timedevsum': newsum, 'timedev': timedev})
        self.logger.debug("Current mean CPU time: {}s, current CPU time deviation: {}s".
                          format(round(newmean), round(timedev)))

        # Then memory
        statistics['memsum'] = round(resources['memory size'] * resources['CPU time'] / 1000)
        newmean = inc_wighted_mean(statistics['memsum'], statistics['timesum'])
        newsum = incsum(statistics['memdevsum'], statistics['mean mem'], newmean, resources['memory size'])
        if newsum != 0:
            memdev = devn(newsum, statistics['number'])
        else:
            memdev = 0
        statistics.update({'mean mem': newmean, 'memdevsum': newsum, 'memdev': memdev})
        self.logger.debug("Current mean RAM: {}GB, current RAM deviation: {}GB".format(
            utils.memory_units_converter(round(newmean), 'GB')[0],
            utils.memory_units_converter(round(memdev), 'GB')[0]))
