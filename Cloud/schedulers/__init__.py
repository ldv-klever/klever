import abc
import concurrent.futures
import logging
import os
import shutil
import time

import Cloud.requests.testgenerator as testgenerator
import Cloud.requests.omega as omega


def get_gateway(conf, work_dir):
    """
    Check which implementation of Session object to choose to get tasks
    :param conf: Configuration dictionary.
    :param work_dir: Path to the working directory.
    :return: Return object of the implementation of Session abstract class.
    """
    if "debug with testgenerator" in conf["scheduler"] and conf["scheduler"]["debug with testgenerator"]:
        return testgenerator.Server(conf["testgenerator"], work_dir)
    else:
        return omega.Server(conf["Omega"], work_dir)


class SchedulerException(RuntimeError):
    """Exception is used to determine when task or job fails but not scheduler."""
    pass


class SchedulerExchange(metaclass=abc.ABCMeta):
    """Class provide general scheduler API."""

    __tasks = {}
    __jobs = {}
    __nodes = None
    __tools = None
    __iteration_period = 1

    @staticmethod
    @abc.abstractstaticmethod
    def scheduler_type():
        """Return type of the scheduler: 'VerifierCloud' or 'Klever'."""
        return "Klever"

    def __init__(self, conf, work_dir):
        """
        Get configuration and prepare working directory.
        :param conf: Dictionary with relevant configuration.
        :param work_dir: PAth to the working directory.
        :param server: Session object.
        """
        self.conf = conf
        self.work_dir = work_dir
        self.server = get_gateway(conf, os.path.join(work_dir, "requests"))

        # Check configuration completeness
        logging.debug("Check whether configuration contains all necessary data")

        # Initialize interaction
        self.server.register(self.scheduler_type())

        # Clean working directory
        if os.path.isdir(work_dir):
            logging.info("Clean scheduler working directory {}".format(work_dir))
            shutil.rmtree(work_dir)
        os.makedirs(work_dir, exist_ok=True)

        if "iteration_timeout" in self.conf["scheduler"]:
            self.__iteration_period = self.conf["scheduler"]["iteration_timeout"]

        logging.info("Scheduler initialization has been successful")

    def __sort_priority(self, task_id):
        """
        Use the function to sort tasks by their priorities. For higher priority return higher integer.
        :param task_id: Task identifier..
        :return: 3, 2, 1, 0
        """
        priority = self.__tasks[task_id]["priority"]
        if priority == "IDLE":
            return 3
        elif priority == "LOW":
            return 2
        elif priority == "HIGH":
            return 1
        elif priority == "URGENT":
            return 0
        else:
            raise ValueError("Unknown priority: {}".format(priority))

    @abc.abstractmethod
    def launch(self):
        """Start scheduler loop."""
        logging.info("Start scheduler loop")
        try:
            while True:
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
                              self.__jobs[job_id]["status"] == "ERROR"]
                }
                logging.info("Scheduler has {} pending, {} processing, {} finished and {} error jobs".
                             format(len(scheduler_state["jobs"]["pending"]),
                                    len(scheduler_state["jobs"]["processing"]),
                                    len(scheduler_state["jobs"]["finished"]),
                                    len(scheduler_state["jobs"]["error"])))

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
                server_state = self.server.exchange(scheduler_state)

                # Add PENDING tasks
                for task_id in [task_id for task_id in server_state["tasks"]["pending"] if task_id not in self.__tasks]:
                    self.__tasks[task_id] = {
                        "id": task_id,
                        "status": "PENDING",
                        "description": server_state["task descriptions"][task_id]["description"],
                        "priority": server_state["task descriptions"][task_id]["description"]["priority"]
                    }
                    if self.scheduler_type() == "VerifierCloud":
                        self.__tasks[task_id]["user"] = \
                            server_state["task descriptions"][task_id]["scheduler user name"]
                        self.__tasks[task_id]["password"] = \
                            server_state["task descriptions"][task_id]["scheduler password"]
                    else:
                        self.__tasks[task_id]["user"] = None
                        self.__tasks[task_id]["password"] = None

                # Add PENDING jobs
                for job_id in [job_id for job_id in server_state["jobs"]["pending"] if job_id not in self.__jobs]:
                    self.__jobs[job_id] = {
                        "id": job_id,
                        "status": "PENDING",
                        "configuration": server_state["job configurations"][job_id]
                    }

                # Remove finished or error tasks
                logging.debug("Remove tasks with statuses FINISHED and ERROR")
                deleted = set(scheduler_state["tasks"]["finished"] + scheduler_state["tasks"]["error"])
                for task_id in deleted:
                    del self.__tasks[task_id]
                logging.info("Total {} tasks has been deleted".format(len(deleted)))

                # Remove finished or error jobs
                logging.debug("Remove jobs with statuses FINISHED and ERROR")
                deleted = set(scheduler_state["jobs"]["finished"] + scheduler_state["jobs"]["error"])
                for job_id in deleted:
                    del self.__jobs[job_id]
                logging.info("Total {} jobs has been deleted".format(len(deleted)))

                # Cancel tasks
                cancel_tasks = [task_id for task_id in set(scheduler_state["tasks"]["pending"] +
                                                           scheduler_state["tasks"]["processing"]) if task_id not in
                                set(server_state["tasks"]["pending"] + scheduler_state["tasks"]["processing"])]
                for task_id in cancel_tasks:
                    self.__tasks[task_id]["future"].cancel()
                    self.cancel_task(task_id)
                    del self.__tasks[task_id]
                logging.info("Total {} tasks have been cancelled".format(len(cancel_tasks)))

                # Cancel jobs
                cancelled_jobs = [job_id for job_id in set(scheduler_state["jobs"]["pending"] +
                                  scheduler_state["jobs"]["processing"]) if job_id in server_state["jobs"]["cancelled"]]
                for job_id in cancelled_jobs:
                    self.__jobs[job_id]["future"].cancel()
                    self.cancel_job(job_id)
                    del self.__jobs[job_id]
                logging.info("Total {} jobs have been cancelled".format(len(cancelled_jobs)))

                # Update task processing status
                for job_id in server_state["jobs"]["processing"]:
                    if job_id in self.__jobs and self.__jobs[job_id]["status"] == "PENDING":
                        self.__jobs[job_id]["status"] = "PROCESSING"
                    elif job_id not in self.__jobs:
                        logging.warning("Job {} has status PROCESSING but it was not running actually".
                                        format(job_id))
                        self.__jobs[job_id] = {
                            "id": job_id,
                            "status": "ERROR",
                            "error": "Job {} has status PROCESSING but it was not running actually".\
                                     format(job_id)
                        }
                        
                # Update task processing status
                for task_id in server_state["tasks"]["processing"]:
                    if task_id not in self.__tasks:
                        logging.warning("Task{} has status PROCESSING but it was not running actually".
                                        format(job_id))
                        self.__tasks[task_id] = {
                            "id": task_id,
                            "status": "ERROR",
                            "error": "Task {} has status PROCESSING but it was not running actually".\
                                     format(task_id)
                        }

                # Check new pending tasks and prepare them before launching
                # TODO: It is extremely slow in case of VerifierCloud
                for task_id in [task_id for task_id in self.__tasks if self.__tasks[task_id]["status"] == "PENDING"]:
                    try:
                        self.prepare_task(task_id, self.__tasks[task_id]["description"])
                    except SchedulerException as err:
                        logging.error("Cannot prepare task {} for submission: {}".format(task_id, err))
                        self.__tasks[task_id]["status"] = "ERROR"
                        self.__tasks[task_id]["error"] = err

                # Check new pending jobs and prepare them before launching
                for job_id in [job_id for job_id in self.__jobs if self.__jobs[job_id]["status"] == "PENDING"]:
                    try:
                        self.prepare_job(job_id, self.__jobs[job_id]["configuration"])
                    except SchedulerException as err:
                        logging.error("Cannot prepare job {} for submission: {}".format(job_id, err))
                        self.__jobs[job_id]["status"] = "ERROR"
                        self.__jobs[job_id]["error"] = err

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
                for task_id in [task for task in self.__tasks if self.__tasks[task]["status"] == "PROCESSING" and
                             self.__tasks[task]["future"].done()]:
                    try:
                        self.__tasks[task_id]["status"] = self.process_task_result(task_id,
                                                                                   self.__tasks[task_id]["future"])
                    except SchedulerException as err:
                        logging.error("Cannot process results of task {}: {}".format(task_id, err))
                        self.__tasks[task_id]["status"] = "ERROR"
                        self.__tasks[task_id]["error"] = err

                # Update jobs
                for job_id in [job for job in self.__jobs if self.__jobs[job]["status"] == "PROCESSING" and
                               self.__jobs[job]["future"].done()]:
                    try:
                        self.__jobs[job_id]["status"] = self.process_job_result(job_id, self.__jobs[job_id]["future"])
                    except SchedulerException as err:
                        logging.error("Cannot process results of job {}: {}".format(job_id, err))
                        self.__jobs[job_id]["status"] = "ERROR"
                        self.__jobs[job_id]["error"] = err

                # Get actual information about connected nodes
                submit = True
                try:
                    nothing_changed = self.update_nodes()
                except Exception as err:
                    logging.error("Cannot obtain information about the nodes: {}".format(err))
                    submit = False
                    nothing_changed = False

                if not nothing_changed:
                    # TODO: Implement rescheduling current tasks
                    pass

                if submit:
                    # Schedule new tasks
                    logging.info("Start scheduling new tasks")
                    pending_tasks = [self.__tasks[task_id] for task_id in self.__tasks
                               if self.__tasks[task_id]["status"] == "PENDING"]
                    processing_tasks = [self.__tasks[task_id] for task_id in self.__tasks
                               if self.__tasks[task_id]["status"] == "PROCESSING"]
                    pending_jobs = [self.__jobs[job_id] for job_id in self.__jobs
                               if self.__jobs[job_id]["status"] == "PENDING"]
                    processing_jobs = [self.__jobs[job_id] for job_id in self.__jobs
                               if self.__jobs[job_id]["status"] == "PROCESSING"]
                    tasks_to_start, jobs_to_start = self.schedule(pending_tasks, pending_jobs, processing_tasks,
                                                                   processing_jobs, self.__sort_priority)
                    logging.info("Going to start {} new tasks and {} jobs".
                                 format(len(tasks_to_start), len(jobs_to_start)))

                    for job_id in jobs_to_start:
                        future = self.solve_job(job_id, self.__jobs[job_id]["configuration"])
                        logging.info("Submitted job {}".format(job_id))
                        self.__jobs[job_id]["future"] = future

                    for task_id in tasks_to_start:
                        # This check is very helpful for debugging
                        if self.__tasks[task_id]["status"] != "PENDING":
                            raise RuntimeError("Attempt to submit tasks with non-pending status: {}".format(task_id))
                        future = self.solve_task(task_id,
                                                  self.__tasks[task_id]["description"],
                                                  self.__tasks[task_id]["user"],
                                                  self.__tasks[task_id]["password"])
                        logging.info("Submitted task {}".format(task_id))
                        self.__tasks[task_id]["status"] = "PROCESSING"
                        self.__tasks[task_id]["future"] = future

                    # Flushing tasks
                    logging.debug("Flush submitted tasks and jobs if necessary")
                    self.flush()
                else:
                    logging.warning("Do not run any tasks until actual information about the nodes will be obtained")

                logging.debug("Scheduler iteration has finished")
                time.sleep(self.__iteration_period)
        except KeyboardInterrupt:
            logging.error("Scheduler execution is interrupted, cancel all running threads")
            self.terminate()

    @abc.abstractmethod
    def schedule(self, pending_tasks, pending_jobs, processing_tasks, processing_jobs, sorter):
        """
        Get list of new tasks which can be launched during current scheduler iteration.
        :param pending_tasks: List with all pending tasks.
        :param pending_jobs: List with all pending jobs.
        :param processing_tasks: List with currently ongoing tasks.
        :param processing_jobs: List with currently ongoing jobs.
        :param sorter: Function which can by used for sorting tasks according to their priorities.
        :return: List with identifiers of pending tasks to launch and list woth identifiers of jobs to launch.
        """
        return []

    @abc.abstractmethod
    def prepare_task(self, identifier, description):
        """
        Prepare working directory before starting solution.
        :param identifier: Verification task identifier.
        :param description: Dictionary with task description.
        """
        return

    @abc.abstractmethod
    def prepare_job(self, identifier, configuration):
        """
        Prepare working directory before starting solution.
        :param identifier: Verification task identifier.
        :param configuration: Job configuration.
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
        Solve given verification task.
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
        :param identifier:
        :param future: Future object.
        :return: Status of the task after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        """
        return

    @abc.abstractmethod
    def process_job_result(self, identifier, future):
        """
        Process result and send results to the server.
        :param identifier:
        :param future: Future object.
        :return: Status of the job after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        """
        return

    @abc.abstractmethod
    def cancel_job(self, identifier):
        """
        Stop task solution.
        :param identifier: Verification task ID.
        """
        if identifier in self.__jobs and "future" in self.__jobs[identifier] \
                and not self.__jobs[identifier]["future"].done():
            logging.debug("Cancel job '{}'".format(identifier))
            self.__jobs[identifier]["future"].cancel()
        else:
            logging.debug("Job '{}' is not running, so it cannot be canceled".format(identifier))

    @abc.abstractmethod
    def cancel_task(self, identifier):
        """
        Stop task solution.
        :param identifier: Verification task ID.
        """
        if identifier in self.__tasks and "future" in self.__tasks[identifier] \
                and not self.__tasks[identifier]["future"].done():
            logging.debug("Cancel task '{}'".format(identifier))
            self.__tasks[identifier]["future"].cancel()
        else:
            logging.debug("Task '{}' is not running, so it cannot be canceled".format(identifier))

    @abc.abstractmethod
    def terminate(self):
        """
        Abort solution of all running tasks and any other actions before
        termination.
        """
        # Stop tasks
        for task_id in [task_id for task_id in self.__tasks if self.__tasks[task_id]["status"]
                        in ["PENDING", "PROCESSING"]]:
            self.cancel_task(task_id)
        # stop jobs
        for job_id in [job_id for job_id in self.__jobs if self.__jobs[job_id]["status"]
                        in ["PENDING", "PROCESSING"] and "future" in self.__jobs[job_id]]:
            self.cancel_job(job_id)
        exit(137)

    @abc.abstractmethod
    def update_nodes(self):
        """
        Update statuses and configurations of available nodes and
        push it to the server.
        :return: Return True if nothing has changes
        """
        return True

    @abc.abstractmethod
    def update_tools(self):
        """
        Generate dictionary with verification tools available and
        push it to the verification gate.
        """
        return

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'