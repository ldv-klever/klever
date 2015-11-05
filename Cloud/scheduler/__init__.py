import abc
import concurrent.futures
import logging
import os
import shutil
import time


class SchedulerExchange(metaclass=abc.ABCMeta):
    """Class provide general scheduler API."""

    __tasks = {}
    __nodes = None
    __tools = None
    __iteration_timeout = 1

    def __init__(self, conf, work_dir, gw):
        """
        Get configuration and prepare working directory.
        :param conf: Dictionary with relevant configuration.
        :param work_dir: PAth to the working directory.
        :param gw: Verification gateway object.
        """
        self.conf = conf
        self.work_dir = work_dir
        self.gw = gw

        # Check configuration completeness
        logging.debug("Check whether configuration contains all necessary data")
        if "user" not in self.conf:
            raise KeyError("Please provide scheduler username 'user' to authorize at verification gateway")
        elif "password" not in self.conf:
            raise KeyError("Please provide scheduler password 'password' to authorize at verification gateway")
        elif "task timeout" not in self.conf:
            raise KeyError("Please provide 'task timeout' within the configuration in seconds")
        elif "tools and nodes update period" not in self.conf:
            raise KeyError("Please provide 'tools and nodes update period' configuration option in seconds")
        elif "require login" not in conf:
            logging.warning("Suppose that users may not provide login")
            conf["require login"] = True

        # Initialize gateway interaction
        gw.auth(self.conf["user"], self.conf["password"])
        gw.register(self.conf["name"], self.conf["require login"])

        # Clean working directory
        if os.path.isdir(work_dir):
            logging.info("Clean scheduler working directory {}".format(work_dir))
            shutil.rmtree(work_dir)
        os.makedirs(work_dir, exist_ok=True)

        if "iteration_timeout" in self.conf:
            self.__iteration_timeout = self.conf["iteration_timeout"]

        logging.info("Scheduler initialization has been successful")

    @abc.abstractmethod
    def launch(self):
        """Start scheduler loop."""
        logging.info("Start monitoring tools and nodes")
        executor = concurrent.futures.ThreadPoolExecutor(2)
        nodes_future = executor.submit(self._nodes, int(self.conf["tools and nodes update period"]))
        tools_future = executor.submit(self._tools, int(self.conf["tools and nodes update period"]))

        logging.info("Start monitoring verification tasks")
        try:
            while True:
                logging.info("Start scheduling iteration with statuses exchange with the verification gateway")
                pending_tasks = [task_id for task_id in self.__tasks if "status" in self.__tasks[task_id] and
                                 self.__tasks[task_id]["status"] == "PENDING"]
                processing_tasks = [task_id for task_id in self.__tasks if "status" in self.__tasks[task_id] and
                                    self.__tasks[task_id]["status"] == "PROCESSING"]
                finished_tasks = [task_id for task_id in self.__tasks if "status" in self.__tasks[task_id] and
                                  self.__tasks[task_id]["status"] == "FINISHED"]
                unknown_tasks = [task_id for task_id in self.__tasks if "status" in self.__tasks[task_id] and
                                 self.__tasks[task_id]["status"] == "UNKNOWN"]
                error_tasks = [task_id for task_id in self.__tasks if "status" in self.__tasks[task_id] and
                               self.__tasks[task_id]["status"] == "ERROR"]
                scheduler_state = {
                    "tasks": {
                        "pending": pending_tasks,
                        "processing": processing_tasks,
                        "finished": finished_tasks,
                        "unknown": unknown_tasks,
                        "error": error_tasks
                    }
                }
                logging.info("Scheduler has {} pending, {} processing, {} finished, {} unknown and {} error tasks".
                             format(len(pending_tasks), len(processing_tasks), len(finished_tasks), len(unknown_tasks),
                                    len(error_tasks)))
                gateway_state = self.gw.exchange_tasks(scheduler_state)

                # Start solution of new tasks
                logging.debug("Determine new tasks to solve")
                new_tasks = set(gateway_state["tasks"]["pending"]) - set(pending_tasks + processing_tasks)
                # TODO: Implement gradual tasks submissions
                for task in new_tasks:
                    if self.conf["require authorization"]:
                        user = gateway_state["users"][gateway_state["task descriptions"][task]["user"]]["user"]
                        password = gateway_state["users"][gateway_state["task descriptions"][task]["user"]]["password"]
                    else:
                        user = None
                        password = None

                    self._prepare_task(task)
                    try:
                        future = self._solve_task(task, gateway_state["task descriptions"][task]["description"], user,
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

                # Remove finished tasks before updating statuses
                logging.debug("Remove tasks with statuses FINISHED, ERROR or UNKNOWN")
                deleted = [task_id for task_id in set(finished_tasks + unknown_tasks + error_tasks)]
                for task_id in deleted:
                    del self.__tasks[task_id]
                logging.info("Total {} tasks has been deleted".format(len(deleted)))

                # Cancel tasks
                logging.debug("Stop solution of cancelled tasks")
                cancel_tasks = set(pending_tasks + processing_tasks) - set(gateway_state["tasks"]["pending"] +
                                                                           gateway_state["tasks"]["processing"])
                for task in cancel_tasks:
                    self.__tasks[task]["future"].cancel()
                    self.__tasks[task]["status"] = "UNKNOWN"
                    self._cancel_task(task)
                logging.info("Total {} tasks have been cancelled".format(len(cancel_tasks)))

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
                if not nodes_future.running():
                    raise nodes_future.exception()
                elif not tools_future.running():
                    raise tools_future.exception()

                logging.debug("Scheduler iteration has finished")
                time.sleep(self.__iteration_timeout)
        except KeyboardInterrupt:
            logging.error("Scheduler execution is interrupted, cancel all running threads")
            nodes_future.cancel()
            tools_future.cancel()
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
