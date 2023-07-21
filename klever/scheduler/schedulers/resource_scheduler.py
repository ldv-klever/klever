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

import json
import copy
import time
import requests

from klever.scheduler.schedulers.global_config import get_workers_cpu_cores
from klever.scheduler.utils import higher_priority, sort_priority, memory_units_converter
from klever.scheduler.schedulers import SchedulerException
from klever.scheduler.utils import consul


class ResourceManager:
    """
    The class is in charge of resource management. It tracks all resources of the system consisting of several
    nodes running the scheduler controller. It provides means for other schedulers to calculate resources,
    reserve resources, checking whether it possible to run a job or task and even choosing appropriate nodes for it.
    It requests data from the scheduler controller and submits the current system workload to Bridge. It does not do
    any specific actions to prepare, start or cancel jobs or tasks.
    """

    def __init__(self, logger, max_jobs=1, pool_size=8, is_adjust_pool_size=False):
        """
        Initialize the manager of resources.

        :param max_jobs: The maximum number of running jobs with the same or higher priority.
        :param pool_size: The total number of running tasks if it is limited.
        """
        self.__logger = logger
        self.__max_running_jobs = max_jobs
        self.__system_status = {}
        self.__cached_system_status = None
        self.__jobs_config = {}
        self.__tasks_config = {}
        self.__max_tasks = pool_size
        self.__is_adjust_pool_size = is_adjust_pool_size
        self.__last_limitation_error = []

        self.__logger.info("Resource manager is live now with max running jobs limitation is {}".format(max_jobs))

    def update_system_status(self, address, wait_controller=False):
        """
        Get an information about connected nodes from a scheduler controller. If a user reduces an amount of available
        resources the method checks the invariant and reports jobs and tasks to cancel to prevent scheduling deadlocks.

        :param address: Controllers address to make the request.
        :param wait_controller: Wait until controller initializes its KV storage.
        :raise ValueError: If the request to controller fails then raise the exception.
        :return: [list of identifiers of jobs to cancel], [list of identifiers of tasks to cancel].
        """
        def request(kv_url):
            try:
                r = requests.get(kv_url, timeout=10)
            except requests.exceptions.Timeout as exp:
                raise ValueError("Timeout while requesting {}".format(kv_url)) from exp
            if not r.ok:
                raise ValueError("Cannot get list of connected nodes requesting {} (got status code: {} due to: {})".
                                 format(kv_url, r.status_code, r.reason))
            nds = r.json()
            nds = [data["Node"] for data in nds]

            # test
            if len(nds) == 0:
                raise KeyError("Expect at least one working node to operate")

            return nds

        url = address + "/v1/catalog/nodes"
        nodes = []
        if wait_controller:
            done = False
            while not done:
                try:
                    nodes = request(url)
                    done = True
                except (requests.exceptions.ConnectionError, KeyError, ValueError):
                    time.sleep(10)
        else:
            nodes = request(url)

        consul_client = consul.Session()

        cancel_jobs = []
        cancel_tasks = []
        for node in nodes:
            response = consul_client.kv_get("states/" + node)
            if not response:
                self.__logger.warning(f"Node {node} was not connected yet.")
                continue

            node_status = json.loads(response)

            # Get dictionary and compare it with existing one
            if node in self.__system_status and self.__system_status[node]["status"] != "DISCONNECTED":
                if self.__system_status[node]["available for jobs"] and not node_status["available for jobs"]:
                    self.__logger.warning("Cancel jobs: {}".
                                          format(str(self.__system_status[node]["running verification jobs"])))
                    cancel_jobs.extend(self.__system_status[node]["running verification jobs"])
                self.__system_status[node]["available for jobs"] = node_status["available for jobs"]

                if self.__system_status[node]["available for tasks"] and not node_status["available for tasks"]:
                    cancel_tasks.extend(self.__system_status[node]["running verification tasks"])
                self.__system_status[node]["available for tasks"] = node_status["available for tasks"]

                if self.__system_status[node]["available CPU number"] <= node_status["available CPU number"] or \
                        self.__system_status[node]["available RAM memory"] <= node_status["available RAM memory"] or \
                        self.__system_status[node]["available disk memory"] <= node_status["available disk memory"]:
                    verdict, data = self.__check_invariant()
                    if not verdict:
                        self.__logger.warning("Deadlock can happen after amount of resources available at {!r} reduced"
                                              ", cancelling running tasks and jobs there".format(node))
                        # Remove jobs
                        self.__logger.warning("Cancel jobs: {}".format(str(data)))
                        cancel_jobs.extend(data)
                self.__system_status[node]["available CPU number"] = node_status["available CPU number"]
                self.__system_status[node]["available RAM memory"] = node_status["available RAM memory"]
                self.__system_status[node]["available disk memory"] = node_status["available disk memory"]
            else:
                self.__system_status[node] = node_status
                self.__system_status[node]["status"] = "HEALTHY"
                self.__system_status[node]["reserved CPU number"] = 0
                self.__system_status[node]["reserved RAM memory"] = 0
                self.__system_status[node]["reserved disk memory"] = 0
                self.__system_status[node]["running verification jobs"] = []
                self.__system_status[node]["running verification tasks"] = []

        # Check disconnected nodes
        for missing in (n for n in self.__system_status if n not in nodes):
            self.__logger.warning("Seems that node {!r} is disconnected, cancel all running tasks and jobs there"
                                  .format(missing))
            self.__logger.warning('Node {!r} is disconnected. Cancel tasks and jobs: {} and {}'.
                                  format(missing, str(self.__system_status[missing]["running verification jobs"]),
                                         str(self.__system_status[missing]["running verification tasks"])))
            cancel_jobs.extend(self.__system_status[missing]["running verification jobs"])
            cancel_tasks.extend(self.__system_status[missing]["running verification tasks"])
            self.__system_status[missing]["status"] = "DISCONNECTED"

        # Check ailing status
        for name, node in [[n, stat] for n, stat in self.__system_status.items()
                           if stat["status"] != "DISCONNECTED"]:
            if node["reserved CPU number"] > node["available CPU number"] or \
                    node["reserved RAM memory"] > node["available RAM memory"] or \
                    node["reserved disk memory"] > node["available disk memory"]:
                self.__logger.warning("Node {!r} is ailing since too many resources reserved!".format(name))
                node["status"] = "AILING"
            else:
                node["status"] = "HEALTHY"

        return cancel_jobs, cancel_tasks

    def set_pool_limit(self, number: int):
        """
        Restrict the number of running tasks and jobs simultaneously.

        :param number: int
        :return: None
        """
        self.__max_tasks = number

    def submit_status(self, server):
        """
        Calculate an available configuration of all nodes, nodes with particular configuration and the current workload,
        and send it all to Bridge. Does not send any data if nothing has been changed from the previous dispatch.

        :param server: {'node name': {node status}} - the system status.
        :return: True if status has been submitted to Bridge and False if nothing to sent.
        """
        def equal(name1, name2, parameter):
            """Compare nodes parameters"""
            return self.__system_status[name1][parameter] == self.__system_status[name2][parameter]

        # Collect configurations
        configurations = []
        node_pool = list(self.__system_status.keys())
        while len(node_pool) > 0:
            primer = node_pool.pop()

            # Collect all such nodes
            nodes = [primer]
            for suits in (s for s in node_pool if equal(s, primer, "CPU model") and
                          equal(s, primer, "available CPU number") and equal(s, primer, "available disk memory")):
                nodes.append(suits)
                node_pool.remove(suits)

            # Add configuration
            conf = {
                "cpu_model": self.__system_status[primer]["CPU model"],
                "cpu_number": self.__system_status[primer]["available CPU number"],
                "ram_memory": int(self.__system_status[primer]["available RAM memory"] / 10**9),
                "disk_memory": int(self.__system_status[primer]["available disk memory"] / 10**9),
                "nodes": [{
                    "hostname": n,
                    "status": self.__system_status[n]["status"],
                    "workload": {
                        "reserved_cpu_number": self.__system_status[n]["reserved CPU number"],
                        "reserved_ram_memory": int(self.__system_status[n]["reserved RAM memory"] / 10**9),
                        "reserved_disk_memory": int(self.__system_status[n]["reserved disk memory"] / 10**9),
                        "running_verification_jobs": len(self.__system_status[n]["running verification jobs"]),
                        "running_verification_tasks": len(self.__system_status[n]["running verification tasks"]),
                        "available_for_jobs": self.__system_status[n]["available for jobs"],
                        "available_for_tasks": self.__system_status[n]["available for tasks"]
                    }
                } for n in nodes]
            }
            configurations.append(conf)

        # Submit nodes
        if not self.__cached_system_status or self.__cached_system_status != str(configurations):
            self.__logger.info("Submit information about the workload to Bridge")
            self.__cached_system_status = str(configurations)
            server.submit_nodes(configurations)
            return True

        return False

    def schedule(self, pending_tasks, pending_jobs):
        """
        Get two sorted by priorities lists of pending tasks and jobs and determine which can be started now and at which
        nodes.

        :param pending_tasks: A list of dictionaries with the description for pending tasks sorted increasing the
                              priority.
        :param pending_jobs: A list of dictionaries with configuration for pending jobs sorted increasing the priority.
        :return: [{task desc}, "node name"], [{job desc}, "node name"] - lists of runnable pending tasks and jobs.
        """
        def schedule_jobs(jobs):
            while len(jobs) > 0 and len(running_jobs) + len(jobs_to_run) < self.__max_running_jobs:
                candidate = jobs.pop()

                if candidate not in (j[0] for j in jobs_to_run):
                    n = self.__schedule_job(candidate, status=status)
                    if n:
                        jobs_to_run.append([candidate, n])
                        # Remove these resources from status
                        self.__reserve_resources(status, candidate['configuration']['resource limits'], n)

        jobs_to_run = []
        tasks_to_run = []

        # Prepare copy of current system status
        status = self.__create_system_status(delete_jobs=False, delete_tasks=False)

        # Check high priority running jobs
        highest_priority = 'IDLE'
        running_jobs = self.__processing_jobs
        for job, node in running_jobs:
            if higher_priority(self.__jobs_config[job]['configuration']['priority'], highest_priority, strictly=True):
                highest_priority = self.__jobs_config[job]['configuration']['priority']

        # Filter jobs that have a higher priority than the current highest priority
        filtered_jobs = [j for j in pending_jobs if higher_priority(j['configuration']['priority'], highest_priority,
                                                                    True)]
        schedule_jobs(filtered_jobs)

        # Schedule all possible tasks
        processing_tasks = self.__processing_tasks
        for task in reversed(pending_tasks):
            if self.__is_adjust_pool_size:
                cur_max_tasks = self.__max_tasks - get_workers_cpu_cores()
            else:
                cur_max_tasks = self.__max_tasks
            if len(processing_tasks) + len(tasks_to_run) >= cur_max_tasks:
                self.__logger.debug(f'We cannot run more tasks since the pool limit {cur_max_tasks} is exceeded')
                break
            node = self.__schedule_task(task, status=status)
            if node:
                tasks_to_run.append([task, node])
                # Remove these resources from status
                self.__reserve_resources(status, task['description']['resource limits'], node)

        # Filter jobs that have the same or a higher priority than the current highest priority
        filtered_jobs = [j for j in pending_jobs if higher_priority(j['configuration']['priority'], highest_priority)]
        schedule_jobs(filtered_jobs)

        return tasks_to_run, jobs_to_run

    def __user_friendly_memory_resources(self, unit, value, available_value, reserved_value):
        """
        Obtain more user-friendly representation (GB instead of B) for memory resources.

        :param unit: Resource unit.
        :param value: Claimed/freed value.
        :param available_value: Available value.
        :param reserved_value: Reserved value.
        :return: Converted values and resource unit.
        """
        if unit == 'B':
            value = memory_units_converter(value, 'GB')[0]
            available_value = memory_units_converter(available_value, 'GB')[0]
            reserved_value = memory_units_converter(reserved_value, 'GB')[0]
            unit = 'GB'

        return value, available_value, reserved_value, unit

    def claim_resources(self, identifier, conf, node, job=False):
        """
        Reserve the resources for given task or job in the system. Call the method when you are about to run the job or
        task and if 'schedule' method allowed it.

        :param identifier: An identifier of given job or task.
        :param conf: A dictionary with the job configuration or task description.
        :param node: A node name string.
        :param job: True if it is a job and False if it is a task.
        :raise KeyError: if job or task is running and its identifier is found in a list of running jobs or tasks.
        """
        if job and identifier in self.__processing_jobs:
            raise KeyError("Verification job {!r} should be already running")
        if not job and identifier in self.__processing_tasks:
            raise KeyError("Verification task {!r} should be already running")

        if job:
            self.__jobs_config[identifier] = conf
            tag = "running verification jobs"
            conf = conf['configuration']['resource limits']
        else:
            self.__tasks_config[identifier] = conf
            tag = "running verification tasks"
            conf = conf['resource limits']

        self.__reserve_resources(self.__system_status, conf, node)
        name = 'job' if job else 'task'
        self.__logger.debug(f"Reserve resources to run a new {name}")
        for reserved, value, available, unit in self.__iterate_over_resources():
            if conf[value]:
                claimed_value, available_value, reserved_value, unit = \
                    self.__user_friendly_memory_resources(unit, conf[value], self.__system_status[node][available],
                                                          self.__system_status[node][reserved])
                self.__logger.debug(
                    f"Node {node}: claim {claimed_value}{unit} of {available} {available_value}{unit}"
                    f" and have totally reserved {reserved_value}{unit}")
        self.__system_status[node][tag].append(identifier)
        self.__logger.debug(f"Now have running totally {len(self.__system_status[node][tag])} {name}s")

    def release_resources(self, identifier, node, job=False, keep_disk=0):
        """
        Paired method with claim_resources. Call it if the task or job solution is finished and reserved resources
        should become available again.

        :param identifier: An identifier of the given job or task.
        :param node: A node name string.
        :param job: True if it is a job and False if it is a task.
        :param keep_disk: An amount of a disk memory in bytes to reserve forever if the working directory is saved.
        """
        if job:
            collection = self.__jobs_config
            tag = "running verification jobs"
            conf = collection[identifier]['configuration']['resource limits']
        else:
            collection = self.__tasks_config
            tag = "running verification tasks"
            conf = collection[identifier]['resource limits']

        # Check that it is actually running on the node
        if identifier not in collection or identifier not in self.__system_status[node][tag]:
            raise KeyError("Cannot find {!r} together with {} at node {!r}".format(identifier, tag, node))

        # Minus resources
        self.__release_resources(self.__system_status, conf, node)
        name = 'job' if job else 'task'
        self.__logger.debug(f"Free resources after solution of a {name}")
        for reserved, value, available, unit in self.__iterate_over_resources():
            if conf[value]:
                freed_value, available_value, reserved_value, unit = \
                    self.__user_friendly_memory_resources(unit, conf[value], self.__system_status[node][available],
                                                          self.__system_status[node][reserved])
                self.__logger.debug(
                    f"Node {node}: freed {freed_value}{unit} of {available} {available_value}{unit}"
                    f" and have totally reserved now {reserved_value}{unit}")

        # Remove running task or job and delete config of task or job
        del collection[identifier]
        self.__system_status[node][tag].remove(identifier)
        self.__logger.debug(f"Now have running totally {len(self.__system_status[node][tag])} {name}s")
        if keep_disk:
            diff = self.__system_status[node]["available disk memory"] - \
                   self.__system_status[node]["reserved disk memory"]
            if keep_disk > diff:
                raise ValueError('Cannot reserve amount of disk memory {} which is higher than rest amount {} at node '
                                 '{}'.format(keep_disk, diff, node))

            self.__system_status[node]["reserved disk memory"] += keep_disk

    def check_resources(self, conf, job=False):
        """
        Provide configuration of a job or description of a task to check that the system has enough resources to
        reserve.

        :param conf: A dictionary with a job configuration or task description.
        :param job: True if it is a job and False if it is a task.
        :return: True if all is right and job or task will not be pending forever.
        :raise SchedulerException: Raised if the system cannot handle the job or task.
        """
        if job:
            self.__logger.debug("Check the resource limits of pending job {!r}".format(conf['identifier']))
            restrictions = conf['resource limits']
        else:
            if conf['job id'] not in self.__jobs_config:
                raise SchedulerException("Job {!r} should be running as task {!r} is generated by it".
                                         format(conf['job id'], conf['id']))

            # Resources for tasks from the job config
            job_resources = self.__jobs_config[conf['job id']]['configuration']['task resource limits']
            # Resources for the task given with the task description
            task_resources = conf['resource limits']
            for restriction in ["number of CPU cores", "memory size", "disk memory size"]:
                if job_resources[restriction] < task_resources[restriction]:
                    raise SchedulerException("Task cannot have {!r} {!r} more than given with a job: {!r}".
                                             format(restriction, task_resources[restriction],
                                                    job_resources[restriction]))

            # Check CPU model
            if task_resources['CPU model'] != job_resources['CPU model']:
                raise SchedulerException("Task cannot have CPU model {!r} different from one given with a job: {!r}".
                                         format(task_resources['CPU model'],
                                                job_resources['CPU model']))

            restrictions = task_resources

        # Create empty system status
        status = self.__create_system_status(delete_tasks=True, delete_jobs=True)
        nodes = self.__nodes_ranking(status, restrictions)

        msg = self.__make_limitation_error(
            self.__free_resources(list(status.values())[-1]),
            restrictions if job else self.__jobs_config[conf['job id']]['configuration']['resource limits'],
            conf['task resource limits'] if job else restrictions)

        if len(nodes) > 0:
            if job and conf['task scheduler'] != 'VerifierCloud':
                task_restrictions = conf['task resource limits']
                self.__reserve_resources(status, restrictions, nodes[0])
                nodes = self.__nodes_ranking(status, task_restrictions)
                if len(nodes) > 0:
                    return True
                self.__raise_limitation_error(msg)
        else:
            self.__raise_limitation_error(msg)
        return False

    def node_info(self, node):
        """
        Return the status of particular node. It will be a copy of the particular object from the system status.
        It prevents any modifications of the system status outside of the manager.

        :param node: A node name string.
        :return: A dictionary with node status.
        """
        return copy.deepcopy(self.__system_status[node])

    @property
    def active_nodes(self):
        """
        Returns a list of node names that currently connected to the system.

        :return: A list with node names.
        """
        return [n for n, stat in self.__system_status.items() if stat['status'] != 'DISCONNECTED']

    def __make_limitation_error(self, resources, job_restrictions, task_restrictions):
        cpus, memory, disk = resources
        error_block = {
            "number of CPU cores": f'available {cpus} of CPU cores but requested'
                                   f' {job_restrictions["number of CPU cores"]} for the job '
                                   f'and {task_restrictions["number of CPU cores"]} for a task',
            "memory size": "available {} of memory but requested {} for the"
                           " job and {} for a task".format(
                                memory_units_converter(memory, outunit='GB')[-1],
                                memory_units_converter(job_restrictions["memory size"], outunit='GB')[-1],
                                memory_units_converter(task_restrictions["memory size"], outunit='GB')[-1]),
            "disk memory size": "available {} of disk memory but requested {} for the"
                                " job and {} for a task".format(
                                    memory_units_converter(disk, outunit='GB')[-1],
                                    memory_units_converter(job_restrictions["disk memory size"], outunit='GB')[-1],
                                    memory_units_converter(task_restrictions["disk memory size"], outunit='GB')[-1])
        }
        return error_block

    def __raise_limitation_error(self, msg):
        if self.__last_limitation_error:
            error = [msg[kind] for kind in self.__last_limitation_error]
            error = ', '.join(error)
            raise SchedulerException(error)

    @property
    def __processing_jobs(self):
        """
        Collect identifiers of all processing jobs.

        :return: A list of running jobs identifiers.
        """
        jobs = []
        for node, stat in self.__system_status.items():
            for job in stat["running verification jobs"]:
                jobs.append([job, node])

        return jobs

    @property
    def __processing_tasks(self):
        """
        Collect identifiers of all processing tasks.

        :return: A list of running tasks identifiers.
        """
        tasks = []
        for node, stat in self.__system_status.items():
            for task in stat["running verification tasks"]:
                tasks.append([task, node])

        return tasks

    def __schedule_job(self, job, status=None):
        """
        Check whether provided job can be started in the system.

        :param job: A job configuration dictionary.
        :param status: A custom status dictionary and if it the manager's system status should not be used.
        :return: A node name where the job can be started or None if there is no such node.
        """
        # Available resources
        if not status:
            status = self.__system_status

        nodes = self.__nodes_ranking(status, job['configuration']['resource limits'])

        # Ranking of theoretically available resources
        if len(nodes) > 0:
            success, inv_nodes = self.__check_invariant(job)
            if success:
                # On base of new rankings choose a node
                suits = [n for n in nodes if n in inv_nodes]
                if len(suits) > 0:
                    return suits[0]

        return None

    def __schedule_task(self, task, status=None):
        """
        Check whether provided task can be started in the system.

        :param task: A task description dictionary.
        :param status: A custom status dictionary and if it the manager's system status should not be used.
        :return: A node name where the task can be started or None if there is no such node.
        """
        # Available resources
        if not status:
            status = self.__system_status

        # Ranking of available resources
        nodes = self.__nodes_ranking(status, task['description']['resource limits'])
        if len(nodes) > 0:
            return nodes[0]

        return None

    def __check_invariant(self, job=None):
        """
        Check that the invariant is preserved in the system and no deadlocks will happen. If a job is provided check
        the same thing but under the assumption that the job is running.

        :param job: A job configuration dictionary or None.
        :return: True, None - the invariant is preserved (job is not given).
                 True, [nodes at which the job can be started] - the invariant is preserved (job given). The list is
                                                                 sorted reducing workload.
                 False [job identifiers to cancel] - the invariant is not preserved (job is not given).
                 False, None - the invariant is not preserved (job is given).
        """
        def yield_max_task(given_model, jbs):
            # Get all tasks restrictions
            restrictions = [j[1]['configuration']['task resource limits'] for j in jbs
                            if j[1]['configuration']['task scheduler'] != 'VerifierCloud' and
                            (not j[1]['configuration']['task resource limits']['CPU model'] or
                             not cpu_model or
                             (cpu_model and j[1]['configuration']['task resource limits']['CPU model'] == given_model))]

            # For each parameter determine max
            if len(restrictions) > 0:
                restriction = {
                    'CPU model': given_model
                }
                for r in ["number of CPU cores", "memory size", "disk memory size"]:
                    m = max(restrictions, key=lambda e: e[r]) # pylint: disable=cell-var-from-loop
                    restriction[r] = m[r]
            else:
                restriction = {
                    'CPU model': given_model,
                    "number of CPU cores": 0,
                    "memory size": 0,
                    "disk memory size": 0
                }

            return restriction

        def check_invariant_for_jobs(jobs_list):
            par = self.__create_system_status(delete_jobs=True, delete_tasks=True, keep_jobs=[j[0] for j in jobs_list])

            # Collect maximum task restrictions for each CPU model specified for tasks
            required_cpu_models = \
                sorted({j[1]['configuration']['task resource limits']['CPU model'] for j in jobs_list
                        if j[1]['configuration']['task scheduler'] != 'VerifierCloud'})
            for model in required_cpu_models:
                mx = yield_max_task(model, jobs_list)

                r = self.__nodes_ranking(par, mx, job=False)
                if len(r) > 0:
                    self.__reserve_resources(par, mx, r[0])
                else:
                    # Invariant is violated
                    return par, model, mx

            # Invariant is preserved
            return par, None, None

        jobs = self.__processing_jobs
        jobs = [[j, self.__jobs_config[j[0]]] for j in jobs] if not job else \
               [[j, self.__jobs_config[j[0]]] for j in jobs] + [[job['id'], job]]

        if len(jobs) > 0:
            # Now check the invariant
            # self.__logger.debug("Going to check that deadlock are impossible" if not job else
            #                     "Going to check that job {!r} does not introduce deadlocks".format(job['id']))

            sysinfo, cpu_model, mx_task = check_invariant_for_jobs(jobs)
            if cpu_model and mx_task and job:
                # invariant is violated, try to determine jobs to cancel
                # Sort jibs by priority
                cancel = []
                jobs = sorted(jobs, key=lambda x: sort_priority(x[1]['priority']))
                while cpu_model and mx_task and len(jobs) > 0:
                    # First try to cancel job with given CPU model and max requirements
                    suitable = \
                        [j for j in jobs if j[1]['configuration']['task scheduler'] != 'VerifierCloud' and
                         (not cpu_model or j[1]['configuration']['task resource limits']['CPU model'] == cpu_model) and
                         (j[1]['configuration']['task resource limits']['memory size'] >= mx_task['memory size'] or
                          j[1]['configuration']['task resource limits']['disk memory size'] >=
                          mx_task['disk memory size'] or
                          j[1]['configuration']['task resource limits']['number of CPU cores'] >=
                             mx_task['number of CPU cores'])]

                    if len(suitable) == 0:
                        raise ValueError("Cannot determine job with CPU model {!r} given for tasks to cancel".
                                         format(cpu_model))

                    candidate = suitable.pop()
                    cancel.append(candidate[0])
                    jobs.remove(candidate)
                    sysinfo, cpu_model, mx_task = check_invariant_for_jobs(jobs)

                return False, cancel
            if cpu_model and mx_task:
                return False, None

            # Invariant is preserved, return ranking for the given job
            if job:
                ranking = self.__nodes_ranking(sysinfo, job["configuration"]["resource limits"], job=True)
                return True, ranking

        return True, None

    def __create_system_status(self, delete_jobs=True, delete_tasks=True, keep_jobs=None, keep_tasks=None):
        """
        Copy current system status and if necessary do not reserve resources for running jobs and tasks.

        :param delete_jobs: If True release resources claimed for running jobs in the copy of system status.
        :param delete_tasks: if True release resources claimed for running tasks in the copy of system status.
        :param keep_jobs: [job identifiers] - do not release resources claimed by particular running jobs in the copy
                          of system status.
        :param keep_tasks: [task identifiers] - do not release resources claimed by particular running tasks in the
                           copy of system status.
        :return: The copy of system status that can be modified anyhow.
        """

        def release_all_tasks(s, kt=None):
            if not kt:
                kt = []

            # Free resources of tasks that are not in given list
            for j, node in (t for t in self.__processing_tasks if t not in kt):
                self.__release_resources(s, self.__tasks_config[j]['resource limits'], node)

        def release_all_jobs(s, kj=None):
            if not kj:
                kj = []

            # Free resources of jobs that are not in given list
            for j, node in (j for j in self.__processing_jobs if j not in kj):
                self.__release_resources(s, self.__jobs_config[j]['configuration']['resource limits'], node)

        # Copy system status to calculate potentially available resources
        status = copy.deepcopy(self.__system_status)

        # Free there all task resources but reserve all max task resources
        if not keep_tasks:
            keep_tasks = []
        if delete_tasks:
            release_all_tasks(status, keep_tasks)

        if not keep_jobs:
            keep_jobs = []
        if delete_jobs:
            release_all_jobs(status, keep_jobs)

        return status

    def __nodes_ranking(self, system_status, restriction, job=True):
        """
        Get restrictions and return list of nodes where such amount of resources can be reserved. Nodes are sorted
        reducing workload.

        :param system_status: A dictionary with system status.
        :param restriction: A dictionary with the resource restrictions.
        :param job: True if it is a job and False if it is a task.
        :return: A list of node names sorted reducing the workload.
        """
        suitable = [n for n in system_status.keys() if self.__fulfill_requirement(system_status[n], restriction, job)]
        return sorted(suitable, key=lambda x: self.__free_resources(system_status[x]))

    def __fulfill_requirement(self, node, restriction, job=True):
        """
        Check that given node has enough resources to run job or task according to given restrictions.

        :param node: A node name.
        :param restriction: A dictionary with the restrictions.
        :param job: True if it is a job and False if it is a task.
        :return: True if the node has enough free resources and False otherwise.
        """

        # Check condition
        if job and not node['available for jobs']:
            return False
        if not job and not node['available for tasks']:
            return False

        # Check CPU model
        if restriction['CPU model'] and restriction['CPU model'] != node['CPU model']:
            return False

        # Check rest resources
        cpu_number, ram_memory, disk_memory = self.__free_resources(node)
        cpu_number_limit, memory_size_limit, disk_memory_size_limit = \
            restriction["number of CPU cores"], restriction["memory size"], restriction["disk memory size"]

        if cpu_number >= cpu_number_limit and ram_memory >= memory_size_limit and \
                disk_memory >= disk_memory_size_limit:
            return True

        self.__last_limitation_error = []
        if cpu_number < restriction["number of CPU cores"]:
            self.__last_limitation_error.append('number of CPU cores')
        if ram_memory < restriction["memory size"]:
            self.__last_limitation_error.append('memory size')
        if disk_memory < restriction["disk memory size"]:
            self.__last_limitation_error.append('disk memory size')
        return False

    def __reserve_resources(self, system_status, amount, node=None):
        """
        Reserve given amount of resources in given system status.

        :param system_status: A system status dictionary.
        :param amount: A dictionary with resource restrictions.
        :param node: Particular node name.
        """
        if node not in system_status:
            raise KeyError("There is no node {!r} in the system".format(node))

        # Minus resources
        for reserved, value, available, _ in self.__iterate_over_resources():
            system_status[node][reserved] += amount[value]
            if system_status[node][reserved] > system_status[node][available]:
                raise ValueError(f"{reserved.capitalize()}, equal to {system_status[node][reserved]}, cannot be more "
                                 f"than {available} which is {system_status[node][available]}")

    def __release_resources(self, system_status, amount, node):
        """
        Release a reserved amount of resources in given system status.

        :param system_status: A dictionary with the system status.
        :param amount: A dictionary with the resource limits.
        :param node: A particular node name.
        """
        if node not in system_status:
            raise KeyError("There is no node {!r} in the system".format(node))

        # Plus resources
        for reserved, value, _, _ in self.__iterate_over_resources():
            system_status[node][reserved] -= amount[value]
            if system_status[node][reserved] < 0:
                raise ValueError(f"{reserved.capitalize()} cannot be negative {system_status[node][reserved]}")

    @staticmethod
    def __iterate_over_resources():
        for st, vt, at, unit in [["reserved CPU number", "number of CPU cores", "available CPU number", " Cores"],
                                 ["reserved RAM memory", "memory size", "available RAM memory", "B"],
                                 ["reserved disk memory", "disk memory size", "available disk memory", "B"]]:
            yield st, vt, at, unit

    @staticmethod
    def __free_resources(conf):
        """
        Calculate the amount of free resources for given node.

        :param conf: A node configuration.
        :return: [available CPU cores number, available RAM memory, available disk space].
        """
        def f(x):
            return x if x > 0 else 0

        cpu_number = conf["available CPU number"] - conf["reserved CPU number"]
        ram_memory = conf["available RAM memory"] - conf["reserved RAM memory"]
        disk_memory = conf["available disk memory"] - conf["reserved disk memory"]

        return [f(cpu_number), f(ram_memory), f(disk_memory)]
