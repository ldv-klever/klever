import abc
import concurrent.futures
import logging
import os
import shutil
import time


class SchedulerExchange(metaclass=abc.ABCMeta):
    """Class provide general scheduler API."""

    __tasks = {}
    __jobs = {}
    __nodes = None
    __tools = None
    __iteration_timeout = 1

    def __init__(self, conf, work_dir, server):
        """
        Get configuration and prepare working directory.
        :param conf: Dictionary with relevant configuration.
        :param work_dir: PAth to the working directory.
        :param server: Session object.
        """
        self.conf = conf
        self.work_dir = work_dir
        self.server = server

        # Check configuration completeness
        logging.debug("Check whether configuration contains all necessary data")
        if "tools and nodes update period" not in self.conf:
            raise KeyError("Please provide 'scheduler''tools and nodes update period' configuration option in seconds")

        # Initialize interaction
        server.register(self.scheduler_type())

        # Clean working directory
        if os.path.isdir(work_dir):
            logging.info("Clean scheduler working directory {}".format(work_dir))
            shutil.rmtree(work_dir)
        os.makedirs(work_dir, exist_ok=True)

        if "iteration_timeout" in self.conf:
            self.__iteration_timeout = self.conf["iteration_timeout"]

        logging.info("Scheduler initialization has been successful")

    @abc.abstractproperty
    def scheduler_type(self):
        """Return type of the scheduler: 'VerifierCloud' or 'Klever'."""
        return "Klever"

    @abc.abstractmethod
    def launch(self):
        """Start scheduler loop."""
        logging.info("Start scheduler loop")
        try:
            while True:
                # Prepare scheduler state
                logging.info("Start scheduling iteration with statuses exchange with the verification gateway")
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
                    "jobs": {
                        "pending": [job_id for job_id in self.__tasks if "status" in self.__tasks[job_id] and
                                 self.__jobs[job_id]["status"] == "PENDING"],
                        "processing": [job_id for job_id in self.__tasks if "status" in self.__tasks[job_id] and
                                 self.__jobs[job_id]["status"] == "PROCESSING"],
                        "finished": [job_id for job_id in self.__tasks if "status" in self.__tasks[job_id] and
                                 self.__jobs[job_id]["status"] == "FINISHED"],
                        "error": [job_id for job_id in self.__tasks if "status" in self.__tasks[job_id] and
                                 self.__jobs[job_id]["status"] == "ERROR"]
                    },
                    "task errors": {},
                    "job errors": {}
                }
                logging.info("Scheduler has {} pending, {} processing, {} finished and {} error tasks".
                             format(len(scheduler_state["tasks"]["pending"]),
                                    len(scheduler_state["tasks"]["processing"]),
                                    len(scheduler_state["tasks"]["finished"]),
                                    len(scheduler_state["tasks"]["error"])))
                logging.info("Scheduler has {} pending, {} processing, {} finished and {} error jobs".
                             format(len(scheduler_state["jobs"]["pending"]),
                                    len(scheduler_state["jobs"]["processing"]),
                                    len(scheduler_state["jobs"]["finished"]),
                                    len(scheduler_state["jobs"]["error"])))

                logging.debug("Add task error descriptions")
                for id in scheduler_state["tasks"]["error"]:
                    scheduler_state["task errors"][id] = self.__tasks[id]["error"]

                logging.debug("Add job error descriptions")
                for id in scheduler_state["jobs"]["error"]:
                    scheduler_state["task errors"][id] = self.__jobs[id]["error"]

                # Submit scheduler state and receive server state
                server_state = self.server.exchange_tasks(scheduler_state)

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
                    del self.__tasks[job_id]
                logging.info("Total {} jobs has been deleted".format(len(deleted)))

                # Cancel tasks
                cancel_tasks = [task_id for task_id in set(scheduler_state["tasks"]["pending"] +
                                                           scheduler_state["tasks"]["processing"]) if task_id not in
                                set(server_state["tasks"]["pending"] + scheduler_state["tasks"]["processing"])]
                for task in cancel_tasks:
                    self.__tasks[task]["future"].cancel()
                    self._cancel_task(task)
                    del self.__tasks[task]
                logging.info("Total {} tasks have been cancelled".format(len(cancel_tasks)))

                # Cancel jobs
                cancelled_jobs = [job_id for job_id in set(scheduler_state["jobs"]["pending"] +
                                                         scheduler_state["jobs"]["processing"]) if job_id not in
                                server_state["jobs"]["cancelled"]]
                for job in cancelled_jobs:
                    self.__tasks[job]["future"].cancel()
                    self._cancel_task(job)
                    del self.__tasks[job]
                logging.info("Total {} jobs have been cancelled".format(len(cancelled_jobs)))

                # Add new pending tasks
                new_tasks = [task_id for task_id in server_state["tasks"]["pending"] if task_id not in self.__tasks]
                for task in new_tasks:
                    self.__tasks[task] = {"status": "PENDING"}
                    
                # Add new pending jobs
                new_jobs = [job_id for job_id in server_state["jobs"]["pending"] if job_id not in self.__jobs]
                for job in new_jobs:
                    self.__jobs[job] = {"status": "PENDING"}

                # Wait there until all threads are terminated
                if "debug each iteration" in self.conf and self.conf["debug each iteration"]:
                    wait_list = [self.__tasks[task_id]["future"] for task_id in self.__tasks if "future" in
                                 self.__tasks[task_id]]
                    if "iteration timeout" not in self.conf:
                        logging.debug("Wait for termination of {} tasks".format(len(wait_list)))
                        concurrent.futures.wait(wait_list, timeout=None, return_when="ALL_COMPLETED")
                    else:
                        logging.debug("Wait {} seconds for termination of {} tasks".
                                      format(self.conf["iteration timeout"], len(wait_list)))
                        concurrent.futures.wait(wait_list, timeout=self.conf["iteration timeout"],
                                                return_when="ALL_COMPLETED")

                # Update statuses
                for task in [task for task in self.__tasks if self.__tasks[task]["status"] == "PROCESSING" and
                             self.__tasks[task]["future"].done()]:
                    try:
                        data = self.__tasks[task]["future"].result()
                        status = self._process_result(task, data)
                    except Exception as exc:
                        self._terminate()
                        raise RuntimeError("Failed to process task {}: {}".format(task, exc))

                    if status not in ["FINISHED", "UNKNOWN", "ERROR"]:
                        raise ValueError("Cannot get solution status after termination for task {}".format(task))
                    self.__tasks[task]["status"] = status

                # Check nodes and tools healthy
                logging.debug("Check nodes and tools threads healthiness")
                # TODO: Submit nodes and verification tools statuses

                # Start solution of new tasks
                logging.debug("Determine tasks to solve")
                # TODO: Implement gradual tasks submissions

                for task in [task_id for task_id in self.__tasks if self.__tasks[task_id]["status"] == "PENDING"]:
                    if self.conf["require authorization"]:
                        user = server_state["users"][server_state["task descriptions"][task]["user"]]["user"]
                        password = server_state["users"][server_state["task descriptions"][task]["user"]]["password"]
                    else:
                        user = None
                        password = None

                    self._prepare_task(task)
                    try:
                        future = self._solve_task(task, server_state["task descriptions"][task]["description"], user,
                                                  password)
                        self.__tasks[task] = {
                            "future": future,
                            "status": "PROCESSING"
                        }
                    except Exception as err:
                        logging.error("Cannot submit task {}: {}".format(task, err))
                        self.__tasks[task] = {
                            "status": "ERROR"
                        }
                logging.info("Total {} tasks have been started".format(len(new_tasks)))

                # Flushing tasks
                logging.debug("Flush submitted tasks if necessary")
                self._flush()

                logging.debug("Scheduler iteration has finished")
                time.sleep(self.__iteration_timeout)
        except KeyboardInterrupt:
            logging.error("Scheduler execution is interrupted, cancel all running threads")
            self._terminate()

    @abc.abstractmethod
    def _prepare_task(self, identifier):
        """
        Prepare working directory before starting solution.
        :param identifier: Verification task identifier.
        """
        return

    @abc.abstractmethod
    def _solve_task(self, identifier, description, user, password):
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
    def _flush(self):
        """Start solution explicitly of all recently submitted tasks."""

    @abc.abstractmethod
    def _process_result(self, identifier, result):
        """
        Process result and send results to the verification gateway.
        :param identifier:
        :return: Status of the task after solution: FINISHED, UNKNOWN or ERROR.
        """

    @abc.abstractmethod
    def _cancel_task(self, identifier):
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
    def _terminate(self):
        """
        Abort solution of all running tasks and any other actions before
        termination.
        """
        # TODO: Stop nodes and tools threads
        return

    @abc.abstractmethod
    def _nodes(self, period):
        """
        Update statuses and configurations of available nodes.
        :param period: Time in seconds between each update request.
        :return: Dictionary with configurations and statuses of nodes.
        """
        return

    @abc.abstractmethod
    def _tools(self, period):
        """
        Generate dictionary with verification tools available.
        :param period: Time in seconds between each update request.
        :return: Dictionary with available verification tools.
        """
        return

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
