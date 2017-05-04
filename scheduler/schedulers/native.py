#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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

import logging
import os
import shutil
import json
import concurrent.futures
import multiprocessing
import subprocess
import requests
import consulate
import signal
import sys

import schedulers as schedulers


def executor(timeout, args):
    """
    Function just executes native scheduler client and waits until its termination.

    :param timeout: Check that tool will exit definetly within this period of time.
    :param args: Native scheduler client execution command arguments.
    :return: It exits with the exit code returne by a client.
    """
    # todo: implement proper logging here, since usage of logging.debug lead to hanging of threads dont know why

    # Kill handler
    mypid = os.getpid()
    print('Executor {!r}: establish signal handlers'.format(mypid))
    original_sigint_handler = signal.getsignal(signal.SIGINT)
    original_sigtrm_handler = signal.getsignal(signal.SIGTERM)

    def handler(arg1, arg2):
        print('Somebody wants to kill me ({!r})!'.format(mypid))
        signal.signal(signal.SIGTERM, original_sigtrm_handler)
        signal.signal(signal.SIGINT, original_sigint_handler)
        os.killpg(os.getpgid(prc.pid), signal.SIGTERM)
        os._exit(-1)

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)

    print('Executor {!r}: Start command {!r}'.format(mypid, ' '.join(args)))
    prc = subprocess.Popen(args, preexec_fn=os.setsid)
    print('Executor {!r}: Waiting for termination of {!r}'.format(mypid, ' '.join(args)))
    try:
        prc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        print('Executor {!r}: expired timeout {!r} for command: {!r}'.
              format(mypid, timeout, ' '.join(args)))
        os._exit(-1)

    print('executor {!r}: Finished command: {!r}'.format(mypid, ' '.join(args)))

    # Be sure that process will exit
    os._exit(prc.returncode)


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
    __job_conf_prototype = dict()
    __reserved_ram_memory = 0
    __reserved_disk_memory = 0
    __running_tasks = 0
    __running_jobs = 0
    __reserved = {"jobs": {}, "tasks": {}}
    __job_processes = dict()
    __task_processes = dict()
    __cached_tools_data = None
    __cached_nodes_data = None

    def __init__(self, conf, work_dir):
        """Do native scheduler specific initialization"""
        super(Scheduler, self).__init__(conf, work_dir)

        if "job client configuration" not in self.conf["scheduler"]:
            raise KeyError("Provide configuration property 'scheduler''job client configuration' as path to json file")
        if "controller address" not in self.conf["scheduler"]:
            raise KeyError("Provide configuration property 'scheduler''controller address'")
        self.__kv_url = self.conf["scheduler"]["controller address"]

        # Import job configuration prototype
        with open(self.conf["scheduler"]["job client configuration"], encoding="utf8") as fh:
            self.__job_conf_prototype = json.loads(fh.read())
        # Try to get configuration just to be sure that it exists
        self.__get_task_configuration()

        if "Klever Bridge" not in self.__job_conf_prototype:
            logging.debug("Add Klever Bridge settings to client job configuration")
            self.__job_conf_prototype["Klever Bridge"] = self.conf["Klever Bridge"]
        else:
            logging.debug("Use provided in configuration prototype Klever Bridge settings for jobs")
        if "common" not in self.__job_conf_prototype:
            logging.debug("Use the same 'common' options for jobs which is used for the scheduler")
        else:
            logging.debug("Use provided in configuration prototype 'common' settings for jobs")

        # Check first time node
        self.update_nodes()

        # init process pull
        if "processes" not in self.conf["scheduler"]:
            raise KeyError("Provide configuration property 'scheduler''processes' to set "
                           "available number of parallel processes")
        max_processes = self.conf["scheduler"]["processes"]
        if isinstance(max_processes, float):
            max_processes = int(max_processes * self.__cpu_cores)
        if max_processes < 2:
            raise KeyError(
                "The number of parallel processes should be greater than 2 ({} is given)".format(max_processes))
        logging.info("Initialize pool with {} processes to run tasks and jobs".format(max_processes))
        if "process pool" in self.conf["scheduler"] and self.conf["scheduler"]["process pool"]:
            self.__pool = concurrent.futures.ProcessPoolExecutor(max_processes)
        else:
            self.__pool = concurrent.futures.ThreadPoolExecutor(max_processes)

        # Check client bin
        self.__client_bin = os.path.abspath(os.path.join(os.path.dirname(__file__), "../bin/scheduler-client"))

    @staticmethod
    def scheduler_type():
        """Return type of the scheduler: 'VerifierCloud' or 'Klever'."""
        return "Klever"

    def __try_to_schedule(self, task_or_job, identifier, limits):
        """
        Try to find slot to scheduler task or job with provided limits.
        :param identifier: Identifier of the task or job.
        :param limits: Dictionary with resource limits.
        :return: True if task or job can be scheduled, False - otherwise.
        """
        # TODO: Check disk space also
        if limits["memory size"] <= (self.__ram_memory - self.__reserved_ram_memory):
            if task_or_job == "task":
                self.__reserved["tasks"][identifier] = limits
            else:
                self.__reserved["jobs"][identifier] = limits
            self.__reserved_ram_memory += limits["memory size"]
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
                if self.__try_to_schedule("task", task["id"], task["description"]["resource limits"]):
                    new_tasks.append(task["id"])
                    self.__running_tasks += 1
                    # Plan jobs

        if len(pending_jobs) > 0:
            # Sort to get high priority tasks at the beginning
            for job in [job for job in pending_jobs if job["id"] not in self.__reserved]:
                if self.__try_to_schedule("job", job["id"], job["configuration"]["resource limits"]):
                    new_jobs.append(job["id"])
                    self.__running_jobs += 1

        return new_tasks, new_jobs

    def prepare_task(self, identifier, configuration):
        """
        Prepare working directory with input files before starting a solution.

        :param identifier: Verification task identifier.
        :param configuration: Task configuration.
        """
        self.__prepare_solution(identifier, configuration, mode='task')

    def prepare_job(self, identifier, configuration):
        """
        Prepare working directory with input files before starting a solution.

        :param identifier: Job identifier.
        :param configuration: Job configuration.
        """
        self.__prepare_solution(identifier, configuration, mode='job')

    def solve_task(self, identifier, configuration, user, password):
        """
        Solve given verification task.

        :param identifier: Task identifier.
        :param configuration: Task configuration.
        :param user: Username.
        :param password: Password.
        :return: Return Future object.
        """
        logging.debug("Start solution of task {!r}".format(identifier))
        return self.__pool.submit(self.__execute, self.__task_processes[identifier])

    def solve_job(self, identifier, configuration):
        """
        Solve given verification job.

        :param identifier: Job identifier.
        :param configuration: Job configuration.
        :return: Return Future object.
        """
        logging.debug("Start solution of job {!r}".format(identifier))
        return self.__pool.submit(self.__execute, self.__job_processes[identifier])

    def flush(self):
        """Start solution explicitly of all recently submitted tasks."""
        super(Scheduler, self).flush()

    def process_task_result(self, identifier, future):
        """
        Process task execution result, clean working directory and mark resources as released.

        :param identifier: Job identifier.
        :param future: Future object.
        :return: Status of the job after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        """
        return self.__check_solution(identifier, future, mode='task')

    def process_job_result(self, identifier, future):
        """
        Process job execution result, clean working directory and mark resources as released.

        :param identifier: Job identifier.
        :param future: Future object.
        :return: Status of the job after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        """
        return self.__check_solution(identifier, future, mode='job')

    def cancel_task(self, identifier, future):
        """
        Cancel task and then get result, clean working directory and mark resources as released.

        :param identifier: Task identifier.
        :param future: Future object.
        :return: Status of the job after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        """
        return self.__cancel_solution(identifier, future, mode='task')

    def cancel_job(self, identifier, future):
        """
        Cancel job and then get result, clean working directory and mark resources as released.

        :param identifier: Task identifier.
        :param future: Future object.
        :return: Status of the job after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        """
        return self.__cancel_solution(identifier, future, mode='job')

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
        self.__pool.shutdown(wait=False)

    def update_nodes(self):
        """
        Update statuses and configurations of available nodes.
        :return: Return True if nothing has changes
        """
        # Determine node name
        url = self.__kv_url + "/v1/catalog/nodes"
        response = requests.get(url)
        if not response.ok:
            raise "Cannot get list of connected nodes requesting {} (got status code: {} due to: {})". \
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
                        "reserved RAM memory": self.__reserved_ram_memory,
                        "reserved disk memory": 0,
                        "running verification jobs": self.__running_jobs,
                        "running verification tasks": self.__running_tasks,
                        "available for jobs": node_status["available for jobs"],
                        "available for tasks": node_status["available for tasks"],
                    }
                }
            }
        }]
        if not self.__cached_nodes_data or self.__cached_nodes_data != str(configurations):
            self.__cached_nodes_data = str(configurations)
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
        data = self.__get_task_configuration()
        if not self.__cached_tools_data or str(data) != self.__cached_tools_data:
            self.__cached_tools_data = str(data)
            verification_tools = data['client']['verification tools']

            # Submit tools
            self.server.submit_tools(verification_tools)

    def __prepare_solution(self, identifier, configuration, mode='task'):
        """
        Generate working directory, configuration files and multiprocessing Process object to be ready to just run it.

        :param identifier: Job or task identifier.
        :param configuration: Dictionary.
        :param mode: 'task' or 'job'.
        :return: None
        """
        logging.info("Going to prepare execution of the {} {}".format(mode, identifier))
        self.__check_resource_limits(configuration)
        args = [sys.executable, self.__client_bin]
        if mode == 'task':
            subdir = 'tasks'
            args.append("TASK")
            client_conf = self.__get_task_configuration()
        else:
            subdir = 'jobs'
            args.append("JOB")
            client_conf = self.__job_conf_prototype.copy()

        self.__create_work_dir(subdir, identifier)
        client_conf["Klever Bridge"] = self.conf["Klever Bridge"]
        client_conf["identifier"] = identifier
        work_dir = os.path.join(self.work_dir, subdir, identifier)
        file_name = os.path.join(work_dir, 'client.json')
        args.extend(['--file', file_name])
        self.__reserved[subdir][identifier] = dict()

        if configuration["resource limits"]["CPU time"]:
            # This is emergency timer if something will hang
            timeout = int((configuration["resource limits"]["CPU time"] * 1.5) / 100)
        else:
            timeout = None
        process = multiprocessing.Process(None, executor, identifier, [timeout, args])

        if mode == 'task':
            client_conf["Klever Bridge"] = self.conf["Klever Bridge"]
            client_conf["identifier"] = identifier
            client_conf["common"]["working directory"] = work_dir
            with open(os.path.join(work_dir, "task.json"), "w", encoding="utf8") as fp:
                json.dump(configuration, fp, ensure_ascii=False, sort_keys=True, indent=4)
            for name in ("resource limits", "verifier", "files", "upload input files of static verifiers"):
                client_conf[name] = configuration[name]
            # Property file may not be specified.
            if "property file" in configuration:
                client_conf["property file"] = configuration["property file"]

            # Do verification versions check
            if client_conf['verifier']['name'] not in client_conf['client']['verification tools']:
                raise schedulers.SchedulerException(
                    'Use another verification tool or install and then specify verifier {!r} with its versions at {!r}'.
                    format(client_conf['verifier']['name'], self.conf["scheduler"]["task client configuration"]))
            if 'version' not in client_conf['verifier']:
                raise schedulers.SchedulerException('Cannot find any given {!r} version at at task description'.
                                                    format(client_conf['verifier']['name']))
            if client_conf['verifier']['version'] not in \
                    client_conf['client']['verification tools'][client_conf['verifier']['name']]:
                raise schedulers.SchedulerException(
                    'Use another version of {!r} or install given version {!r} and specify it at scheduler client '
                    'configuration {!r}'.format(client_conf['verifier']['name'], client_conf['verifier']['version'],
                                                self.conf["scheduler"]["task client configuration"]))

            self.__task_processes[identifier] = process
        else:
            klever_core_conf = configuration.copy()
            del klever_core_conf["resource limits"]
            klever_core_conf["Klever Bridge"] = self.conf["Klever Bridge"]
            klever_core_conf["working directory"] = "klever-core-work-dir"
            self.__reserved["jobs"][identifier]["configuration"] = klever_core_conf
            client_conf["common"]["working directory"] = work_dir
            client_conf["Klever Core conf"] = self.__reserved["jobs"][identifier]["configuration"]
            client_conf["resource limits"] = configuration["resource limits"]

            self.__job_processes[identifier] = process

        with open(file_name, 'w', encoding="utf8") as fp:
            json.dump(client_conf, fp, ensure_ascii=False, sort_keys=True, indent=4)

    def __check_solution(self, identifier, future, mode='task'):
        """
        Process results of task or job solution.

        :param identifier: Job or task identifier.
        :param future: Future object.
        :return: Status after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        """
        logging.info("Going to prepare execution of the {} {}".format(mode, identifier))
        return self.__postprocess_solution(identifier, future, mode)

    def __cancel_solution(self, identifier, future, mode='task'):
        """
        Terminate process solving a process or a task, mark resources as released, clean working directory.

        :param identifier: Identifier of a job or a task.
        :param future: Future object.
        :param mode: 'task' or 'job'.
        :return: Status of the task after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        """
        logging.info("Going to cancel execution of the {} {}".format(mode, identifier))
        if mode == 'task':
            process = self.__task_processes[identifier]
        else:
            process = self.__job_processes[identifier]
        if process and process.pid:
            try:
                os.kill(process.pid, signal.SIGTERM)
                logging.debug("Wait till {} {} become terminated".format(mode, identifier))
                process.join()
            except Exception as err:
                logging.warning('Cannot terminate process {}: {}'.format(process.pid, err))
        return self.__postprocess_solution(identifier, future, mode)

    def __postprocess_solution(self, identifier, future, mode):
        """
        Mark resources as released, clean working directory

        :param identifier: Job or task identifier
        :param mode: 'task' or 'job'.
        :return: None
        """
        if mode == 'task':
            subdir = 'tasks'
            self.__running_tasks -= 1
            del self.__task_processes[identifier]
        else:
            subdir = 'jobs'
            self.__running_jobs -= 1
            del self.__job_processes[identifier]
        # Mark resources as released
        self.__reserved_ram_memory -= self.__reserved[subdir][identifier]["memory size"]
        del self.__reserved[subdir][identifier]

        # Include logs into total scheduler logs
        work_dir = os.path.join(self.work_dir, subdir, identifier)

        logging.debug('Yielding result of a future object of {} {}'.format(mode, identifier))
        try:
            result = future.result()
            logfile = "{}/client-log.log".format(work_dir)
            if os.path.isfile(logfile):
                with open(logfile, mode='r', encoding="utf8") as f:
                    logging.debug("Scheduler client log: {}".format(f.read()))
            else:
                raise FileNotFoundError("Cannot find Scheduler client file with logs: {!r}".format(logfile))

            errors_file = "{}/client-critical.log".format(work_dir)
            if os.path.isfile(errors_file):
                with open(errors_file, mode='r', encoding="utf8") as f:
                    errors = f.readlines()
            else:
                errors = []

            if len(errors) > 0:
                error_msg = errors[-1]
            else:
                error_msg = "Execution of {} {} finished with non-zero exit code: {}".format(mode, identifier,
                                                                                             result)
            if len(errors) > 0 or result != 0:
                logging.warning(error_msg)
                raise schedulers.SchedulerException(error_msg)
        except Exception as err:
            error_msg = "Execution of {} {} terminated with an exception: {}".format(mode, identifier, err)
            logging.warning(error_msg)
            raise schedulers.SchedulerException(error_msg)
        finally:
            # Clean working directory
            if "keep working directory" not in self.conf["scheduler"] or \
                    not self.conf["scheduler"]["keep working directory"]:
                logging.debug("Clean task working directory {} for {}".format(work_dir, identifier))
                shutil.rmtree(work_dir)

        return "FINISHED"

    @staticmethod
    def __execute(process):
        """
        Common implementation for running of a multiprocessing process and waiting till its termination.

        :param process: multiprocessing.Process
        :return: None
        """
        logging.debug("Future task {!r}: Going to start a new process which will start native scheduler client".
                      format(process.name))
        process.start()
        logging.debug("Future task {!r}: get pid of the started process.".format(process.name))
        if process.pid:
            logging.debug("Future task {!r}: the pid is {!r}.".format(process.name, process.pid))
            j = process.join()
            logging.debug("Future task {!r}: join method returned {!r}.".format(process.name, str(j)))
            logging.debug("Future task {!r}: process {!r} joined, going to check its exit code".
                          format(process.name, process.pid))
            ec = process.exitcode
            logging.debug("Future task {!r}: exit code of the process {!r} is {!r}".
                          format(process.name, process.pid, str(ec)))
            if ec is not None:
                return ec
            else:
                error_msg = 'Cannot determine exit code of process {!r}'.format(process.pid)
                raise schedulers.SchedulerException(error_msg)
        else:
            raise schedulers.SchedulerException("Cannot launch process to run a job or a task")

    def __check_resource_limits(self, desc):
        """
        Check resource limitations provided with a job or a task configuration to be sure that it can be launched.

        :param desc: Configuration dictionary.
        :return: None
        """
        logging.debug("Check resource limits")

        if desc["resource limits"]["CPU model"] and desc["resource limits"]["CPU model"] != self.__cpu_model:
            raise schedulers.SchedulerException(
                "Host CPU model is not {} (has only {})".
                    format(desc["resource limits"]["CPU model"], self.__cpu_model))

        if desc["resource limits"]["memory size"] > self.__ram_memory:
            raise schedulers.SchedulerException(
                "Host does not have {} bytes of RAM memory (has only {} bytes)".
                    format(desc["resource limits"]["memory size"], self.__ram_memory))

            # TODO: Disk space check
            # TODO: number of CPU cores check

    def __create_work_dir(self, entities, identifier):
        """
        Create working directory for a job or a task.

        :param entities: Internal subdirectory name.
        :param identifier: Job or task identifier string.
        :return: None
        """
        work_dir = os.path.join(self.work_dir, entities, identifier)
        logging.debug("Create working directory {}/{}".format(entities, identifier))
        if "keep working directory" in self.conf["scheduler"] and self.conf["scheduler"]["keep working directory"]:
            os.makedirs(work_dir.encode("utf8"), exist_ok=True)
        else:
            os.makedirs(work_dir.encode("utf8"), exist_ok=False)

    def __get_task_configuration(self):
        """
        Read scheduler task configuration JSON file to keep it updated.

        :return: Dictionary with configuration.
        """
        name = self.conf["scheduler"]["task client configuration"]
        with open(name, encoding="utf8") as fh:
            data = json.loads(fh.read())

        # Do checks
        if "client" not in data:
            raise KeyError("Specify 'client' object at task client configuration {!r}".format(name))
        if "verification tools" not in data["client"] or len(data["client"]["verification tools"]) == 0:
            raise KeyError("Specify pathes to verification tools installed as 'client''verification tools' object at "
                           "task client configuration {!r}".format(name))
        for tool in data["client"]["verification tools"]:
            if len(data["client"]["verification tools"].keys()) == 0:
                raise KeyError("Specify versions and pathes to them for installed verification tool {!r} at "
                               "'client''verification tools' object at task client configuration".format(tool))

            for version in data["client"]["verification tools"][tool]:
                if not os.path.isdir(data["client"]["verification tools"][tool][version]):
                    raise ValueError("Cannot find script {!r} for verifier {!r} of the version {!r}".
                                     format(data["client"]["verification tools"][tool][version], tool, version))

        return data

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
