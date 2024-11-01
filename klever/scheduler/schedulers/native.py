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

import concurrent.futures
import json
import multiprocessing
import os
import re
import shutil
import signal
import time

from klever.scheduler import schedulers
from klever.scheduler.schedulers import runners, resource_scheduler
from klever.scheduler import utils
from klever.scheduler.client import run_benchexec


class Native(runners.TryLessMemoryRunner):
    """
    Implement the scheduler which is used to run tasks and jobs on this system locally.
    """
    _kv_url = None
    _node_name = None
    _cpu_cores = None
    _pool = None
    _job_conf_prototype = {}
    _reserved = {"jobs": {}, "tasks": {}}
    _job_processes = {}
    _task_processes = {}
    __cached_tools_data = None
    __cached_nodes_data = None
    NODE_INIT_MAX_RETRIES = 50
    NODE_INIT_WAIT_INTERVAL = 1  # in sec

    @staticmethod
    def scheduler_type():
        """Return type of the scheduler: 'VerifierCloud' or 'Klever'."""
        return "Klever"

    def __init__(self, conf, logger, work_dir, server):
        """Do native scheduler specific initialization"""
        super().__init__(conf, logger, work_dir, server)
        self._job_conf_prototype = None
        self._pool = None
        self._process_starter = run_benchexec
        self._manager = None
        self._log_file = 'info.log'

    def init(self):
        """
        Initialize scheduler completely. This method should be called both at constructing stage and scheduler
        reinitialization. Thus, all object attribute should be cleaned up and set as it is a newly created object.
        """
        super().init()
        if "job client configuration" not in self.conf["scheduler"]:
            raise KeyError("Provide configuration property 'scheduler''job client configuration' as path to json file")
        if "controller address" not in self.conf["scheduler"]:
            raise KeyError("Provide configuration property 'scheduler''controller address'")

        # Import job configuration prototype
        with open(self.conf["scheduler"]["job client configuration"], encoding="utf-8") as fh:
            self._job_conf_prototype = json.loads(fh.read())
        # Try to get configuration just to be sure that it exists
        self._get_task_configuration()

        if "Klever Bridge" not in self._job_conf_prototype:
            self.logger.debug("Add Klever Bridge settings to client job configuration")
            self._job_conf_prototype["Klever Bridge"] = self.conf["Klever Bridge"]
        else:
            self.logger.debug("Use provided in configuration prototype Klever Bridge settings for jobs")
        if "common" not in self._job_conf_prototype:
            self.logger.debug("Use the same 'common' options for jobs which is used for the scheduler")
        else:
            self.logger.debug("Use provided in configuration prototype 'common' settings for jobs")

        # Check node first time
        m_type = self.conf["scheduler"].get("manager", 'local')
        if m_type == 'consul':
            address = self.conf["scheduler"]["controller address"]
            self._manager = resource_scheduler.ConsulResourceManager(
                self.logger,
                address,
                max_jobs=self.conf["scheduler"].get("concurrent jobs", 1),
                is_adjust_pool_size=self.conf["scheduler"].get("limit max tasks based on plugins load", False),
            )
        elif m_type == 'local':
            self._manager = resource_scheduler.ResourceManager(
                self.logger,
                max_jobs=self.conf["scheduler"].get("concurrent jobs", 1),
                is_adjust_pool_size=self.conf["scheduler"].get("limit max tasks based on plugins load", False),
                node_conf=self.conf.get("node configuration", None)
            )
        else:
            raise KeyError(f"Unknown manager type: {m_type}")

        node_init_retries = 0
        while True:
            self.update_nodes(self.conf["scheduler"].get("wait controller initialization", False))
            nodes = self._manager.active_nodes
            if len(nodes) == 1:
                break

            node_init_retries += 1
            if node_init_retries >= self.NODE_INIT_MAX_RETRIES:
                raise ValueError(f'Node was not initialised after {node_init_retries} retries')
            self.logger.warning(f"Node was not initialized. Wait for {self.NODE_INIT_WAIT_INTERVAL}s")
            time.sleep(self.NODE_INIT_WAIT_INTERVAL)

        self._node_name = nodes[0]
        data = self._manager.node_info(self._node_name)
        self._cpu_cores = data["CPU number"]

        # init process pull
        if "processes" not in self.conf["scheduler"]:
            raise KeyError("Provide configuration property 'scheduler''processes' to set "
                           "available number of parallel processes")

        if "disable CPU cores account" in self.conf["scheduler"] and \
                self.conf["scheduler"]["disable CPU cores account"]:
            max_processes = self.conf["scheduler"]["processes"]
            if isinstance(max_processes, float):
                data = utils.extract_cpu_cores_info()
                # Evaluate as a number of virtual cores. Allow 2 processes at least that hits when there is the only
                # CPU core.
                max_processes = max(2, int(max_processes * sum((len(item) for a, item in data.items()))))
        else:
            max_processes = self.conf["scheduler"]["processes"]
            if isinstance(max_processes, float):
                max_processes = max(2, int(max_processes * self._cpu_cores))
        if max_processes < 2:
            raise KeyError(f"The number of parallel processes should be greater than 2 ({max_processes} is given)")

        # Limit the total number of running jobs and tasks by the number of executors in the pool
        self._manager.set_pool_limit(max_processes)

        self.logger.info(f"Initialize pool with {max_processes} processes to run tasks and jobs")
        if self.conf["scheduler"].get("process pool"):
            self._pool = concurrent.futures.ProcessPoolExecutor(max_processes)
        else:
            self._pool = concurrent.futures.ThreadPoolExecutor(max_processes)

    def schedule(self, pending_tasks, pending_jobs):
        """
        Get a list of new tasks which can be launched during current scheduler iteration. All pending jobs and tasks
        should be sorted reducing the priority to the end. Each task and job in arguments are dictionaries with full
        configuration or description.

        :param pending_tasks: List with all pending tasks.
        :param pending_jobs: List with all pending jobs.
        :return: List with identifiers of pending tasks to launch and list with identifiers of jobs to launch.
        """
        # Use resource manager to determine which jobs or task we can run t the moment.
        new_tasks, new_jobs = self._manager.schedule(pending_tasks, pending_jobs)
        return [t[0]['id'] for t in new_tasks], [j[0]['id'] for j in new_jobs]

    def terminate(self):
        """
        Abort solution of all running tasks and any other actions before termination.
        """
        # Submit an empty configuration
        self.logger.debug("Submit an empty configuration list before shutting down")
        configurations = []
        self.server.submit_nodes(configurations, looping=True)

        # Terminate
        super().terminate()

        # Be sure that workers are killed
        self._pool.shutdown(wait=False)

    def update_nodes(self, wait_controller=False):
        """
        Update statuses and configurations of available nodes and push them to the server.

        :param wait_controller: Ignore KV fails until it become working.
        :return: Return True if nothing has changes.
        """
        # todo: Need refactoring!
        # Use resource manager to manage resources
        cancel_jobs, cancel_tasks = self._manager.update_system_status(wait_controller)
        # todo: how to provide jobs or tasks to cancel?
        if len(cancel_tasks) > 0 or len(cancel_jobs) > 0:
            self.logger.warning("Need to cancel jobs {} and tasks {} to avoid deadlocks, since resources has been "
                                "decreased".format(str(cancel_jobs), str(cancel_tasks)))
        return self._manager.submit_status(self.server)

    def update_tools(self):
        """
        Generate a dictionary with available verification tools and push it to the server.
        """
        # todo: Need refactoring!
        data = self._get_task_configuration()
        if not self.__cached_tools_data or str(data) != self.__cached_tools_data:
            self.__cached_tools_data = str(data)
            verification_tools = data['client']['verification tools']

            # Submit tools
            self.server.submit_tools(verification_tools)

    def _solve_task(self, identifier, description, user, password):
        """
        Solve given verification task.

        :param identifier: Verification task identifier.
        :param description: Verification task description dictionary.
        :param user: User name.
        :param password: Password.
        :return: Return Future object.
        """
        self.logger.debug("Start solution of task {!r}".format(identifier))
        self._prepare_solution(identifier, description, mode='task')
        self._manager.claim_resources(identifier, description, self._node_name, job=False)
        return self._pool.submit(self._execute, self._log_file, self._task_processes[identifier])

    def _solve_job(self, identifier, configuration):
        """
        Solve given verification job.

        :param identifier: Job identifier.
        :param configuration: Job configuration.
        :return: Return Future object.
        """
        self.logger.debug("Start solution of job {!r}".format(identifier))
        self._prepare_solution(identifier, configuration['configuration'], mode='job')
        self._manager.claim_resources(identifier, configuration, self._node_name, job=True)
        return self._pool.submit(self._execute, self._log_file, self._job_processes[identifier])

    def _process_task_result(self, identifier, future, description):
        """
        Process result and send results to the server.

        :param identifier: Task identifier string.
        :param future: Future object.
        :param description: Verification task description dictionary.
        :return: status of the task after solution: FINISHED.
        :raise SchedulerException: in case of ERROR status.
        """
        return self._check_solution(identifier, future, mode='task')

    def _process_job_result(self, identifier, future):
        """
        Process future object status and send results to the server.

        :param identifier: Job identifier string.
        :param future: Future object.
        :return: status of the job after solution: FINISHED.
        :raise SchedulerException: in case of ERROR status.
        """
        return self._check_solution(identifier, future, mode='job')

    def _cancel_job(self, identifier, future):
        """
        Stop the job solution.

        :param identifier: Verification task ID.
        :param future: Future object.
        :return: Status of the task after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        :raise SchedulerException: In case of exception occurred in future task.
        """
        return self._cancel_solution(identifier, future, mode='job')

    def _cancel_task(self, identifier, future):
        """
        Stop the task solution.

        :param identifier: Verification task ID.
        :param future: Future object.
        :return: Status of the task after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        :raise SchedulerException: In case of exception occurred in future task.
        """
        return self._cancel_solution(identifier, future, mode='task')

    def _prepare_task(self, identifier, description):
        self._manager.check_resources(description, job=False)
        return True

    def _prepare_job(self, identifier, configuration):
        self._manager.check_resources(configuration, job=True)
        return True

    def _prepare_solution(self, identifier, configuration, mode='task'):
        """
        Generate a working directory, configuration files and multiprocessing Process object to be ready to just run it.

        :param identifier: Job or task identifier.
        :param configuration: A dictionary with a configuration or description.
        :param mode: 'task' or 'job'.
        :raise SchedulerException: Raised if the preparation fails and task or job cannot be scheduled.
        """
        self.logger.info("Going to prepare execution of the {} {}".format(mode, identifier))
        node_status = self._manager.node_info(self._node_name)

        if mode == 'task':
            subdir = 'tasks'
            client_conf = self._get_task_configuration()
            self._manager.check_resources(configuration, job=False)
            if 'task files' in configuration:
                client_conf["task files"] = configuration['task files']
        else:
            subdir = 'jobs'
            client_conf = self._job_conf_prototype.copy()
            self._manager.check_resources(configuration, job=True)

        self._create_work_dir(subdir, identifier)
        work_dir = os.path.join(self.work_dir, subdir, identifier)
        self._reserved[subdir][identifier] = {}

        client_conf["Klever Bridge"] = self.conf["Klever Bridge"]
        client_conf["identifier"] = identifier
        client_conf["resource limits"] = configuration["resource limits"]
        client_conf["resource limits"]["CPU cores"] = \
            self._get_virtual_cores(int(node_status["available CPU number"]),
                                    int(node_status["reserved CPU number"]),
                                    int(configuration["resource limits"]["number of CPU cores"]))

        if mode == 'task':
            client_conf["common"]["working directory"] = work_dir
            for name in ("verifier", "upload verifier input files"):
                client_conf[name] = configuration[name]

            # Speculative flag
            if configuration.get('speculative'):
                client_conf["speculative"] = True

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

        else:
            klever_core_conf = configuration.copy()
            klever_core_conf["Klever Bridge"] = self.conf["Klever Bridge"]
            klever_core_conf["working directory"] = "klever-core-work-dir"
            self._reserved["jobs"][identifier]["configuration"] = klever_core_conf
            client_conf["common"]["working directory"] = work_dir
            client_conf["Klever Core conf"] = self._reserved["jobs"][identifier]["configuration"]

            if len(client_conf["resource limits"]["CPU cores"]) == 0:
                data = utils.extract_cpu_cores_info()
                client_conf["Klever Core conf"]["task resource limits"]["CPU Virtual cores"] = \
                    sum((len(item) for a, item in data.items()))
            else:
                client_conf["Klever Core conf"]["task resource limits"]["CPU Virtual cores"] = \
                    len(client_conf["resource limits"]["CPU cores"])

            # Save Klever Core configuration to default configuration file
            with open(os.path.join(work_dir, "core.json"), "w", encoding="utf-8") as fh:
                json.dump(client_conf["Klever Core conf"], fh, ensure_ascii=False, sort_keys=True, indent=4)

        process = multiprocessing.Process(None, self._process_starter, identifier, [mode, client_conf])

        if mode == 'task':
            self._task_processes[identifier] = process
        else:
            self._job_processes[identifier] = process

    def _check_solution(self, identifier, future, mode='task'):
        """
        Process results of the task or job solution.

        :param identifier: A job or task identifier.
        :param future: A future object.
        :return: Status after solution: FINISHED.
        :raise SchedulerException: Raised if an exception occurred during the solution or if results are inconsistent.
        """
        self.logger.info(f"Going to check execution of the {mode} {identifier}")
        return self._postprocess_solution(identifier, future, mode)

    def _cancel_solution(self, identifier, future, mode='task'):
        """
        Terminate process solving a process or a task, mark resources as released, clean working directory.

        :param identifier: Identifier of a job or a task.
        :param future: Future object.
        :param mode: 'task' or 'job'.
        :return: Status of the task after solution: FINISHED. Rise SchedulerException in case of ERROR status.
        :raise SchedulerException: raise if an exception occurred during solution or results are inconsistent.
        """
        self.logger.info("Going to cancel execution of the {} {}".format(mode, identifier))
        if mode == 'task':
            process = self._task_processes.get(identifier, None)
        else:
            process = self._job_processes.get(identifier, None)
        if process and process.pid:
            try:
                # If the user really sent SIGINT then all children got it anyway and we must just wait.
                # If the user pressed a button in Bridge then we have to trigger signal manually.
                os.kill(process.pid, signal.SIGTERM)
                process.join()
            except Exception as err:  # pylint:disable=broad-exception-caught
                self.logger.warning('Cannot terminate process {}: {}'.format(process.pid, err))
        return self._postprocess_solution(identifier, future, mode, True)

    def _postprocess_solution(self, identifier, future, mode, fault_tolerant=False):
        """
        Mark resources as released, clean the working directory.

        :param identifier: A job or task identifier
        :param mode: 'task' or 'job'.
        :param fault_tolerant: in case of cancel results are inconsistent, do not raise an exception in this case.
        :raise SchedulerException: Raised if an exception occurred during the solution or if results are inconsistent.
        """
        if mode == 'task':
            subdir = 'tasks'
            if identifier in self._task_processes:
                del self._task_processes[identifier]
        else:
            subdir = 'jobs'
            if identifier in self._job_processes:
                del self._job_processes[identifier]
        # Mark resources as released
        del self._reserved[subdir][identifier]

        # Include logs into total scheduler logs
        work_dir = os.path.join(self.work_dir, subdir, identifier)

        # Release resources
        if "keep working directory" in self.conf["scheduler"] and self.conf["scheduler"]["keep working directory"] and \
                os.path.isdir(work_dir):
            reserved_space = utils.dir_size(work_dir)
        else:
            reserved_space = 0

        self.logger.debug('Yielding result of a future object of {} {}'.format(mode, identifier))
        # Track just last error
        error_msg = None
        task_results = None
        try:
            if future:
                self._manager.release_resources(identifier, self._node_name, mode == 'job',
                                                reserved_space)

                result = future.result()
                self.logger.info(f'Future processor of {mode} {identifier} returned {result}')

                termination_reason_file = "{}/termination-reason.txt".format(work_dir)
                if os.path.isfile(termination_reason_file):
                    with open(termination_reason_file, mode='r', encoding="utf-8") as fp:
                        termination_reason = fp.read()
                        raise schedulers.SchedulerException(termination_reason)

                if mode == 'task':
                    results_file = os.path.join(work_dir, "decision results.json")
                    self.logger.debug("Read decision results from the disk: {}".format(os.path.abspath(results_file)))
                    if not os.path.isfile(results_file):
                        error_msg = "Results file ({}) is not found".format(results_file)
                    else:
                        with open(results_file, encoding="utf-8") as fp:
                            task_results = json.loads(fp.read())

                logfile = "{}/client-log.log".format(work_dir)
                if os.path.isfile(logfile):
                    with open(logfile, mode='r', encoding="utf-8") as f:
                        self.logger.debug("Scheduler client log:\n\n{}".format(f.read()))
                else:
                    self.logger.warning("Cannot find Scheduler client file with logs: {!r}".format(logfile))

                errors_file = "{}/client-critical.log".format(work_dir)
                if os.path.isfile(errors_file):
                    with open(errors_file, mode='r', encoding="utf-8") as f:
                        errors = [l.strip() for l in f.readlines()]

                    for msg in list(errors):
                        if not msg:
                            continue

                        match = re.search(r'WARNING - (.*)', msg)
                        if not match:
                            continue
                        if self.conf["scheduler"].get("ignore BenchExec warnings") is True or \
                                (isinstance(self.conf["scheduler"].get("ignore BenchExec warnings"), list) and
                                 any(True for t in self.conf["scheduler"].get("ignore BenchExec warnings") if
                                     t in msg)):
                            continue
                        if re.search(r'benchexec(.*) outputted to STDERR', msg):
                            continue
                        error_msg = msg

                if not error_msg:
                    try:
                        result = int(result)
                    except ValueError:
                        error_msg = f'Cannot cast {result} to integer'
                    else:
                        if result != 0:
                            error_msg = "Exited with exit code: {}".format(result)

                if error_msg and not fault_tolerant:
                    raise schedulers.SchedulerException(error_msg + " (please, inspect unknown reports and logs)")
                if error_msg:
                    self.logger.warning(error_msg)
            else:
                self.logger.debug("Seems that {} {} has not been started".format(mode, identifier))
        finally:
            # Clean working directory
            if "keep working directory" not in self.conf["scheduler"] or \
                    not self.conf["scheduler"]["keep working directory"]:
                self.logger.debug("Clean task working directory {} for {}".format(work_dir, identifier))
                shutil.rmtree(work_dir)

        if mode == 'task':
            if task_results:
                return "FINISHED", task_results
            return "ERROR", None

        return "FINISHED"

    @staticmethod
    def _execute(logfile, process):
        """
        Common implementation for running of a multiprocessing process and for waiting until it terminates.

        :param process: multiprocessing.Process object.
        :raise SchedulerException: Raised if process cannot be executed or if its exit code cannot be determined.
        """

        def log(msg):
            """This avoids killing problem of logging loggers."""
            if os.path.isfile(logfile):
                with open(logfile, 'a') as fp:
                    print(msg, file=fp)
            else:
                print(msg)

        log("Future task {!r}: Going to start a new process which will start native scheduler client".
            format(process.name))
        process.start()
        log("Future task {!r}: get pid of the started process.".format(process.name))
        if process.pid:
            log("Future task {!r}: the pid is {!r}.".format(process.name, process.pid))
            while process.is_alive():
                j = process.join(5)
                if j is not None:
                    break
            log("Future task {!r}: join method returned {!r}.".format(process.name, str(j)))
            log("Future task {!r}: process {!r} joined, going to check its exit code".
                format(process.name, process.pid))
            ec = process.exitcode
            log("Future task {!r}: exit code of the process {!r} is {!r}".format(process.name, process.pid, str(ec)))
            if ec is not None:
                return str(ec)

            error_msg = 'Cannot determine exit code of process {!r}'.format(process.pid)
            raise schedulers.SchedulerException(error_msg)

        raise schedulers.SchedulerException("Cannot launch process to run a job or a task")

    def _create_work_dir(self, entities, identifier):
        """
        Create the working directory for a job or a task.

        :param entities: Internal subdirectory name string.
        :param identifier: A job or task identifier string.
        """
        work_dir = os.path.join(self.work_dir, entities, identifier)
        if os.path.isdir(work_dir):
            self.logger.debug("Remove former working directory {}/{}".format(entities, identifier))
            shutil.rmtree(work_dir)

        self.logger.debug("Create working directory {}/{}".format(entities, identifier))
        os.makedirs(work_dir)

    def _get_task_configuration(self):
        """
        Read the scheduler task configuration JSON file to keep it updated.

        :return: Dictionary with the updated configuration.
        """
        name = self.conf["scheduler"]["task client configuration"]
        with open(name, encoding="utf-8") as fh:
            data = json.loads(fh.read())

        # Do checks
        if "client" not in data:
            raise KeyError("Specify 'client' object at task client configuration {!r}".format(name))
        if "verification tools" not in data["client"] or len(data["client"]["verification tools"]) == 0:
            raise KeyError("Specify paths to verification tools installed as 'client''verification tools' object at "
                           "task client configuration {!r}".format(name))
        for tool in data["client"]["verification tools"]:
            if len(data["client"]["verification tools"].keys()) == 0:
                raise KeyError("Specify versions and paths to them for installed verification tool {!r} at "
                               "'client''verification tools' object at task client configuration".format(tool))

            for version in data["client"]["verification tools"][tool]:
                if not os.path.isdir(data["client"]["verification tools"][tool][version]):
                    raise ValueError("Cannot find script {!r} for verifier {!r} of the version {!r}".
                                     format(data["client"]["verification tools"][tool][version], tool, version))

        return data

    @staticmethod
    def _get_virtual_cores(available, reserved, required):
        # First get system info
        si = utils.extract_cpu_cores_info()

        # Get keys
        pcores = sorted(si.keys())

        if available > len(pcores):
            raise ValueError('Host system has {} cores but expect {}'.format(len(pcores), available))

        cores = []
        for vcores in (si[pc] for pc in pcores[available - reserved - required:available - reserved]):
            cores.extend(vcores)

        return cores
