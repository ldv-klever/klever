__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'

import logging
import os
import shutil
import json
import concurrent.futures
import subprocess
import requests
import consulate

import Cloud.schedulers as schedulers


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
        if "process pool" in self.conf["scheduler"] and self.conf["scheduler"]["process pool"]:
            self.__pool = concurrent.futures.ProcessPoolExecutor(max_processes)
        else:
            self.__pool = concurrent.futures.ThreadPoolExecutor(max_processes)

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
        if limits["memory size"] <= (self.__ram_memory - self.__reserved_ram_memory):
            self.__reserved[identifier] = limits
            self.__reserved_ram_memory += limits["memory size"]
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
        pass

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
        if configuration["resource limits"]["memory size"] >= self.__ram_memory:
            raise schedulers.SchedulerException(
                "Node does not have {} bytes of RAM memory for job {}, has only {} bytes".
                format(configuration["resource limits"]["memory size"]), identifier, self.__ram_memory)
        # TODO: Disk space check

    def solve_task(self, identifier, description, user, password):
        pass

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
            "password": self.conf["Omega"]["password"]
        }
        psi_conf["working directory"] = "psi-work-dir"
        self.__reserved[identifier]["configuration"] = psi_conf

        client_conf = self.__job_conf_prototype.copy()
        job_work_dir = os.path.join(self.work_dir, "jobs", identifier)
        logging.debug("Use working directory {} for job {}".format(job_work_dir, identifier))
        client_conf["common"]["work dir"] = job_work_dir
        client_conf["psi configuration"] = self.__reserved[identifier]["configuration"]
        client_conf["resource limits"] = configuration["resource limits"]

        # Prepare command
        client_bin = os.path.abspath(os.path.join(os.path.dirname(__file__), "../bin/scheduler-client.py"))
        args = [client_bin, "JOB", json.dumps(client_conf)]
        logging.debug("Start job: {}".format(str(args)))

        return self.__pool.submit(subprocess.call, args)

    def flush(self):
        """Start solution explicitly of all recently submitted tasks."""
        super(Scheduler, self).flush()

    def process_task_result(self, identifier, result):
        pass

    def process_job_result(self, identifier, future):
        """
        Process result and send results to the server.
        :param identifier: Job identifier.
        :param future: Future object.
        :return: Status of the job after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        """
        # Job finished and resources should be marked as released
        self.__reserved_ram_memory -= self.__reserved[identifier]["memory size"]
        self.__running_jobs -= 1
        del self.__reserved[identifier]

        if "keep work dir" not in self.conf["scheduler"] or not self.conf["scheduler"]["keep work dir"]:
            job_work_dir = os.path.join(self.work_dir, "jobs", identifier)
            logging.debug("Clean job work dir {} for {}".format(job_work_dir, identifier))
            shutil.rmtree(job_work_dir)

        try:
            result = future.result()
            if result == 0:
                return "FINISHED"
            else:
                error_msg = "Job finished with non-zero exit code: {}".format(result)
                raise schedulers.SchedulerException(error_msg)
        except Exception as err:
            error_msg = "Job {} terminated with an exception: {}".format(identifier, err)
            logging.warning(error_msg)
            raise schedulers.SchedulerException(error_msg)

    def cancel_task(self, identifier):
        pass

    def cancel_job(self, identifier):
        """
        Stop task solution.
        :param identifier: Verification task ID.
        """
        super(Scheduler, self).cancel_job(identifier)

        logging.debug("Mark resources reserved for job {} as free".format(identifier))
        self.__reserved_ram_memory -= self.__reserved[identifier]["memory size"]
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
        super(Scheduler, self).terminate()

        # Be sure that workers are killed
        self.__pool.shutdown()

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
        pass


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'

