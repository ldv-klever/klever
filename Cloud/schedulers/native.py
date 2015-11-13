__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'

import logging
import os
import shutil
import time
import json
import concurrent.futures

import requests
import consulate

import Cloud.schedulers as schedulers
import Cloud.client as client


class Scheduler(schedulers.SchedulerExchange):
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
    __pool = None
    __job_conf_prototype = {}
    __reserved_ram_memory = 0
    __reserved_disk_memory = 0
    __running_tasks = 0
    __running_jobs = 0
    __reserved = {}

    def launch(self):
        """Start scheduler loop."""

        if "job client configuration" not in self.conf["scheduler"]:
            raise KeyError("Provide configuration property 'scheduler''job client configuration' as path to json file")
        if "controller address" not in self.conf["scheduler"]:
            raise KeyError("Provide configuration property 'scheduler''controller address'")
        self.__kv_url = self.conf["scheduler"]["controller address"]

        # Import job configuration prototype
        with open(self.conf["scheduler"]["job client configuration"], "r") as fh:
            self.__job_conf_prototype = json.loads(fh.read())
        if "Omega" not in self.__job_conf_prototype:
            logging.debug("Add Omega settings to client job configuration")
            self.__job_conf_prototype["Omega"] = self.conf["Omega"]
        else:
            logging.debug("Use provided in configuration prototype Omega settings for jobs")
        if "common" not in self.__job_conf_prototype:
            logging.debug("Use the same 'common' options for jobs which is used for the scheduler")
        else:
            logging.debug("Use provided in configuration prototype 'common' settings for jobs")

        # Check first time node
        self.update_nodes()

        # init process pull
        if "processes" not in self.conf["scheduler"] or self.conf["scheduler"]["processes"] < 2:
            raise KeyError("Provide configuration property 'scheduler''processes' to set "
                           "available number of parallel processes")
        max_processes = self.conf["scheduler"]["processes"] - 1
        logging.info("Initialize pool with {} processes to run tasks and jobs".format(max_processes))
        self.__pool = concurrent.futures.ProcessPoolExecutor(max_processes)

        # Check existence of verifier scripts
        for tool in self.conf["scheduler"]["verification tools"]:
            for version in self.conf["scheduler"]["verification tools"][tool]:
                if not os.path.isfile(self.conf["scheduler"]["verification tools"][tool][version]):
                    raise ValueError("Cannot find script {} for verifier {} of the version {}".
                                     format(self.conf["scheduler"]["verification tools"][tool][version], tool, version))

        return super(Scheduler, self).launch()

    @staticmethod
    def scheduler_type():
        """Return type of the scheduler: 'VerifierCloud' or 'Klever'."""
        return "Klever"

    def __try_to_schedule(self, identifier, limits):
        """
        Try to find slot to scheduler task or job with provided limits.
        :param identifier: Identifier of the task or job.
        :param limits: Dictionary with resource limits.
        :return: True if task or job can be scheduled, False - otherwise.
        """
        # TODO: Check disk space also
        if limits["max mem size"] <= (self.__ram_memory - self.__reserved_ram_memory):
            self.__reserved[identifier] = limits
            self.__reserved_ram_memory += limits["max mem size"]
            self.__reserved[identifier] = limits
            return True
        else:
            return False

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
        new_tasks = []
        new_jobs = []

        # Plan tasks first
        if len(pending_tasks) > 0:
            # Sort to get high priority tasks at the beginning
            pending_tasks = sorted(pending_tasks, key=sorter)
            for task in pending_tasks:
                if self.__try_to_schedule(task["id"], task["description"]["resource limits"]):
                    new_tasks.append(task["id"])
                    self.__running_tasks += 1

        # Plan jobs
        if len(pending_jobs) > 0:
            # Sort to get high priority tasks at the beginning
            for job in [job for job in pending_jobs if job["id"] not in self.__reserved]:
                if self.__try_to_schedule(job["id"], job["configuration"]["resource limits"]):
                    new_jobs.append(job["id"])
                    self.__running_jobs += 1

        return new_tasks, new_jobs

    def prepare_task(self, identifier, description):
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

    def prepare_job(self, identifier, configuration):
        """
        Prepare working directory before starting solution.
        :param identifier: Verification task identifier.
        :param configuration: Job configuration.
        """
        # Check resource limitiations
        logging.debug("Check resource limitations for the job {}".format(identifier))
        if configuration["resource limits"]["CPU model"] and \
           configuration["resource limits"]["CPU model"] != self.__cpu_model:
            raise schedulers.SchedulerException(
                "There is no node with CPU model {} for job {}, has only {}".
                format(configuration["resource limits"]["CPU model"]), identifier, self.__cpu_model)
        if configuration["resource limits"]["max mem size"] >= self.__ram_memory:
            raise schedulers.SchedulerException(
                "Node does not have {} bytes of RAM memory for job {}, has only {} bytes".
                format(configuration["resource limits"]["max mem size"]), identifier, self.__ram_memory)
        # TODO: Disk space check

    def solve_task(self, identifier, description, user, password):
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

    def solve_job(self, identifier, configuration):
        """
        Solve given verification task.
        :param identifier: Job identifier.
        :param configuration: Job configuration.
        :return: Return Future object.
        """
        logging.info("Going to start execution of the job {}".format(identifier))

        # Create working directory
        job_work_dir = os.path.join(self.work_dir, "jobs", identifier)
        logging.debug("Create working directory {}".format(identifier))
        os.makedirs(job_work_dir)

        # Generate configuration
        psi_conf = configuration.copy()
        del psi_conf["resource limits"]
        psi_conf["Omega"] = {
            "name": self.conf["Omega"]["name"],
            "user": self.conf["Omega"]["user"],
            "passwd": self.conf["Omega"]["password"]
        }
        self.__reserved[identifier]["configuration"] = psi_conf

        client_conf = self.__job_conf_prototype.copy()
        job_work_dir = os.path.join(self.work_dir, "jobs", identifier)
        logging.debug("Use working directory {} for job {}".format(job_work_dir, identifier))
        client_conf["common"]["work dir"] = job_work_dir
        client_conf["psi configuration"] = self.__reserved[identifier]["configuration"]
        client_conf["resource limits"] = configuration["resource limits"]
        json_str = json.dumps(client_conf)
        return self.__pool.submit(client.solve_job, client_conf)

    def flush(self):
        """Start solution explicitly of all recently submitted tasks."""
        super(Scheduler, self).flush()

    def process_task_result(self, identifier, result):
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

    def process_job_result(self, identifier, future):
        """
        Process result and send results to the server.
        :param identifier: Job identifier.
        :param future: Future object.
        :return: Status of the job after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        """
        try:
            result = future.result()
            return "FINISHED"
        except Exception as err:
            error_msg = "Job {} terminated with an exception: {}".format(identifier, err)
            logging.warning(error_msg)
            raise schedulers.SchedulerException(error_msg)

    def cancel_task(self, identifier):
        """
        Stop task solution.
        :param identifier: Verification task ID.
        """
        logging.debug("Cancel task {}".format(identifier))
        super(Scheduler, self).cancel_task(identifier)
        self.__reserved_ram_memory -= self.__reserved[identifier]["max mem size"]
        self.__running_tasks -= 1
        del self.__reserved[identifier]
        
        if "keep work dir" in self.conf["scheduler"] and self.conf["scheduler"]["keep work dir"]:
            return
        task_work_dir = os.path.join(self.work_dir, "tasks", identifier)
        logging.debug("Clean task work dir {} for {}".format(task_work_dir, identifier))
        shutil.rmtree(task_work_dir)

    def cancel_job(self, identifier):
        """
        Stop task solution.
        :param identifier: Verification task ID.
        """
        logging.debug("Cancel job {}".format(identifier))
        super(Scheduler, self).cancel_job(identifier)
        self.__reserved_ram_memory -= self.__reserved[identifier]["max mem size"]
        self.__running_jobs -= 1
        del self.__reserved[identifier]

        if "keep work dir" in self.conf["scheduler"] and self.conf["scheduler"]["keep work dir"]:
            return
        job_work_dir = os.path.join(self.work_dir, "jobs", identifier)
        logging.debug("Clean job work dir {} for {}".format(job_work_dir, identifier))
        shutil.rmtree(job_work_dir)

    def terminate(self):
        """
        Abort solution of all running tasks and any other actions before
        termination.
        """
        # Submit an empty configuration
        logging.debug("Submit an empty configuration list before shutting down")
        configurations = []
        self.server.submit_nodes(configurations)

        # Terminate
        return super(Scheduler, self).terminate()

    def update_nodes(self):
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

        # Submit nodes
        # TODO: Properly set node status
        configurations = [{
            "CPU model": node_status["CPU model"],
            "CPU number": node_status["available CPU number"],
            "RAM memory": node_status["available RAM memory"],
            "disk memory": node_status["available disk memory"],
            "nodes": {
                node_status["node name"]: {
                    "status": "HEALTHY",
                    "workload": {
                        "reserved CPU number": 0,
                        "reserved RAM memory": 0,
                        "reserved disk memory": 0,
                        "running verification jobs": 0,
                        "running verification tasks": 0,
                        "available for jobs": node_status["available for jobs"],
                        "available for tasks": node_status["available for tasks"],
                    }
                }
            }
        }]
        self.server.submit_nodes(configurations)

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

    def update_tools(self):
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

