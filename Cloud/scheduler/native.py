__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'

import logging
import os
import shutil
import time
import Cloud.scheduler as scheduler
import Cloud.client.executils as executils
import requests
import json
import consulate
import re

class Scheduler(scheduler.SchedulerExchange):
    """
    Implement scheduler which is used to run tasks and jobs on the system locally.
    """
    __kv_url = None
    __node_name = None
    __cpu_model = None
    __cpu_cores = None
    __ram_memory = None
    __disk_memory = None
    __disk_memory = None

    def launch(self):
        """Start scheduler loop."""

        if "controller address" not in self.conf:
            raise KeyError("Provide configuration property 'scheduler''controller address'")
        self.__kv_url = self.conf["controller address"]

        # Check first time node
        self._update_nodes()

        # TODO: Check existence of verifier scripts

        # TODO: Add benchexec scripts

        # Add path to benchexec directory
        #bexec_loc = self.conf["BenchExec location"]
        #logging.debug("Add to PATH location {0}".format(bexec_loc))
        #sys.path.append(bexec_loc)

        return super(Scheduler, self).launch()

    def scheduler_type(self):
        """Return type of the scheduler: 'VerifierCloud' or 'Klever'."""
        return "Klever"

    def _schedule(self, pending, processing, sorter):
        """
        Get list of new tasks which can be launched during current scheduler iteration.
        :param pending: List with all pending tasks.
        :param processing: List with currently ongoing tasks.
        :param sorter: Function which can by used for sorting tasks according to their priorities.
        :return: List with identifiers of pending tasks to launch.
        """
        if "max concurrent tasks" in self.conf and self.conf["max concurrent tasks"]:
            if len(processing) < self.conf["max concurrent tasks"]:
                diff = self.conf["max concurrent tasks"] - len(processing)
                if diff <= len(pending):
                    new = pending[0:diff]
                else:
                    new = pending
            else:
                new = []
        else:
            new = pending

        return new

    def _prepare_task(self, identifier, description):
        """
        Prepare working directory before starting solution.
        :param identifier: Verification task identifier.
        :param description: Dictionary with task description.
        """
        # Check feasibility of resource limitations
        logging.debug("Check that task {} has feasible resource limitations".format(identifier))
        if description["resource limits"]["CPU model"] != self.__cpu_model:
            raise ValueError("Computer has {} CPU model but task {} asks for {}".
                             format(self.__cpu_model, identifier, description["resource limits"]["CPU model"]))
        if description["resource limits"]["CPU number"] > self.__cpu_cores:
            raise ValueError("Computer has {} cores but task {} asks for {}".
                             format(self.__cpu_cores, identifier, description["resource limits"]["CPU number"]))
        if description["resource limits"]["RAM memory"] > self.__ram_memory:
            raise ValueError("Computer has {} bytes of RAM but task {} asks for {}".
                             format(self.__ram_memory, identifier, description["resource limits"]["RAM memory"]))
        if description["resource limits"]["RAM memory"] > self.__disk_memory:
            raise ValueError("Computer has {} bytes of disk space but task {} asks for {}".
                             format(self.__disk_memory, identifier, description["resource limits"]["RAM memory"]))

        # Check verification tool
        logging.debug("Check verifier {} of the version {} in the list of supported tools".
                      format(description["verifier"]["name"], format(description["verifier"]["version"])))
        if description["verifier"]["name"] not in self.__verifiers:
            raise ValueError("Scheduler has not verifier {} in the list of supported tools".
                             format(description["verifier"]["name"]))
        else:
            if description["verifier"]["version"] not in self.__verifiers[description["verifier"]["name"]]:
                raise ValueError("Scheduler has not version {} of the verifier {} in the list of supported tools".
                                 format(description["verifier"]["version"], description["verifier"]["name"]))

        # Prepare working directory
        task_work_dir = os.path.join(self.work_dir, "client-workdirs", identifier)
        logging.debug("Make directory for the task to solve {0}".format(task_work_dir))
        os.makedirs(task_work_dir, exist_ok=True)

    def _prepare_job(self, identifier, configuration):
        """
        Prepare working directory before starting solution.
        :param identifier: Verification task identifier.
        :param configuration: Job configuration.
        """
        return

    def _solve_task(self, identifier, description, user, password):
        """
        Solve given verification task.
        :param identifier: Verification task identifier.
        :param description: Verification task description dictionary.
        :param user: User name.
        :param password: Password.
        :return: Return Future object.
        """
        # TODO: Add more exceptions handling to make code more reliable

        # Prepare command to submit
        logging.debug("Prepare arguments of the task {}".format(identifier))
        task_data_dir = os.path.join(self.work_dir, "tasks", identifier, "data")
        run = Run(task_data_dir, description, user, password)
        branch, revision = run.version
        if branch == "":
            logging.warning("Branch has not given for the task {}".format(identifier))
            branch = None
        if revision == "":
            logging.warning("Revision has not given for the task {}".format(identifier))
            revision = None

        # Submit command
        logging.info("Submit the task {0}".format(identifier))
        return self.wi.submit(run=run,
                              limits=run.limits,
                              cpu_model=run.cpu_model,
                              result_files_pattern=None,
                              priority=run.priority,
                              user_pwd=run.user_pwd,
                              svn_branch=branch,
                              svn_revision=revision)

    def _solve_job(self, configuration):
        """
        Solve given verification task.
        :param identifier: Job identifier.
        :param configuration: Job configuration.
        :return: Return Future object.
        """
        return

    def _flush(self):
        """Start solution explicitly of all recently submitted tasks."""
        self.wi.flush_runs()

    def _process_task_result(self, identifier, result):
        """
        Process result and send results to the verification gateway.
        :param identifier:
        :return: Status of the task after solution: FINISHED or ERROR.
        """
        task_work_dir = os.path.join(self.work_dir, "tasks", identifier)
        solution_file = os.path.join(task_work_dir, "solution.zip")
        logging.debug("Save solution to the disk as {}".format(solution_file))
        if result:
            with open(solution_file, 'wb') as sa:
                sa.write(result)
        else:
            logging.warning("Task has been finished but no data has been received for the task {}".
                            format(identifier))
            return "ERROR"

        # Unpack results
        task_solution_dir = os.path.join(task_work_dir, "solution")
        logging.debug("Make directory for the solution to extract {0}".format(task_solution_dir))
        os.makedirs(task_solution_dir, exist_ok=True)
        logging.debug("Extract results from {} to {}".format(solution_file, task_solution_dir))
        shutil.unpack_archive(solution_file, task_solution_dir)

        # Process results and convert RunExec output to result description
        solution_description = os.path.join(task_solution_dir, "verification task decision result.json")
        logging.debug("Get solution description from {}".format(solution_description))
        try:
            solution_identifier, solution_description = \
                executils.extract_description(task_solution_dir, solution_description)
            logging.debug("Successfully extracted solution {} for task {}".format(solution_identifier, identifier))
        except Exception as err:
            logging.warning("Cannot extract results from a solution: {}".format(err))
            raise err

        # Make archive
        solution_archive = os.path.join(task_work_dir, "solution")
        logging.debug("Make archive {} with a solution of the task {}.tar.gz".format(solution_archive, identifier))
        shutil.make_archive(solution_archive, 'gztar', task_solution_dir)
        solution_archive += ".tar.gz"

        # Push result
        logging.debug("Upload solution archive {} of the task {} to the verification gateway".format(solution_archive,
                                                                                                     identifier))
        self.server.submit_solution(identifier, solution_archive, solution_description)

        # Remove task directory
        shutil.rmtree(task_work_dir)

        logging.debug("Task {} has been processed successfully".format(identifier))
        return "FINISHED"

    def _process_job_result(self, identifier, result):
        """
        Process result and send results to the server.
        :param identifier:
        :return: Status of the task after solution: FINISHED or ERROR.
        """
        return

    def _cancel_task(self, identifier):
        """
        Stop task solution.
        :param identifier: Verification task ID.
        """
        logging.debug("Cancel task {}".format(identifier))
        super(Scheduler, self)._cancel_task(identifier)
        task_work_dir = os.path.join(self.work_dir, "tasks", identifier)
        shutil.rmtree(task_work_dir)

    def _cancel_job(self, identifier):
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

    def _terminate(self):
        """
        Abort solution of all running tasks and any other actions before
        termination.
        """
        logging.info("Terminate all runs")
        return self.wi.shutdown()

    def _update_nodes(self):
        """
        Update statuses and configurations of available nodes.
        :return: Return True if nothing has changes
        """
        # Determine node name
        url = self.__kv_url + "/v1/catalog/nodes"
        response = requests.get(url)
        if not response.ok:
            raise "Cannot get list of connected nodes requesting {} (got status code: {} due to: {})".\
                format(url, response.status_code, response.reason)
        nodes = response.json()
        if len(nodes) != 1:
            raise ValueError("Native scheduler expects always 1 node to be connected, but got {}". format(len(nodes)))
        self.__node_name = nodes[0]["Node"]

        # Fetch node configuration
        url = self.__kv_url + "/v1/kv/states/" + self.__node_name
        session = consulate.Consul()
        string = session.kv["states/" + self.__node_name]
        node_status = json.loads(string)

        # Fill available resources
        if self.__cpu_model != node_status["CPU model"] or \
           self.__cpu_cores != node_status["available CPU number"] or \
           self.__ram_memory != node_status["available RAM memory"] or \
           self.__disk_memory != node_status["available disk memory"]:
            self.__cpu_model = node_status["CPU model"]
            self.__cpu_cores = node_status["available CPU number"]
            self.__ram_memory = node_status["available RAM memory"]
            self.__disk_memory = node_status["available disk memory"]
            return False
        return True

    def _update_tools(self):
        """
        Generate dictionary with verification tools available.
        :return: Dictionary with available verification tools.
        """
        while True:
            logging.debug("Send tools info to the verification gateway")
            # TODO: Implement collecting of working revisions
            self.server.submit_tools([])
            time.sleep(period)


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'

