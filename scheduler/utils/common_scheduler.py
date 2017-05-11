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
import requests
import consulate
import json
import copy
from utils import higher_priority


class InvariantException(RuntimeError):
    """
    Exception is used to determine when deadlock is possible or not
    (Invariant is not satisfied or satidfied correspondingly).
    """
    pass


class ResourceManager:

    def __init__(self, logger, max_jobs=1):
        """
        Initiaize abstract scheduler that allows to track resources and do planning but ignores any resl statuses of
        verification jobs and tasks. It also does not run or stop solution of jobs and tasks.

        :param max_jobs: Maximum number of running jobs of the same or higher priority.
        """
        self.__logger = logger
        self.__max_running_jobs = max_jobs
        self.__system_status = {}
        self.__cached_system_status = None
        # {identifier -> {job resources}, {task resources}, priority}
        self.__jobs_config = {}

    def request_from_consul(self, address):
        self.__logger.debug("Try to receive information about resources from controller")
        url = address + "/v1/catalog/nodes"
        response = requests.get(url)
        if not response.ok:
            raise "Cannot get list of connected nodes requesting {} (got status code: {} due to: {})". \
                format(url, response.status_code, response.reason)
        nodes = response.json()
        nodes = [data["Node"] for data in nodes]

        # Fetch node configuration
        session = consulate.Consul()
        cancel_jobs = []
        cancel_tasks = []
        for node in nodes:
            string = session.kv["states/" + node]
            node_status = json.loads(string)

            # Get dictionary and compare it with existing one
            if node in self.__system_status and self.__system_status[node]["status"] != "DISCONNECTED":
                if self.__system_status[node]["available for jobs"] and not node_status["available for jobs"]:
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
            cancel_jobs.extend(self.__system_status[missing]["running verification jobs"])
            cancel_tasks.extend(self.__system_status[missing]["running verification tasks"])
            self.__system_status[missing]["status"] = "DISCONNECTED"

        # Check ailing status
        for name, node in [[n, self.__system_status[n]] for n in self.__system_status
                           if self.__system_status[n]["status"] != "DISCONNECTED"]:
            if node["reserved CPU number"] > node["available CPU number"] or \
                    node["reserved RAM memory"] > node["available RAM memory"] or \
                    node["reserved disk memory"] > node["available disk memory"]:
                self.__logger.warning("Node {!r} is ailing since too many resources reserved!".format(name))
                node["status"] = "AILING"
            else:
                node["status"] = "HEALTHY"

        return cancel_jobs, cancel_tasks

    def submit_status(self, server):
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
                "CPU model": self.__system_status[primer]["CPU model"],
                "CPU number": self.__system_status[primer]["available CPU number"],
                "RAM memory": self.__system_status[primer]["available RAM memory"],
                "disk memory": self.__system_status[primer]["available disk memory"],
                "nodes": {
                    n: {
                        "status": self.__system_status[n]["status"],
                        "workload": {
                            "reserved CPU number": self.__system_status[n]["reserved CPU number"],
                            "reserved RAM memory": self.__system_status[n]["reserved RAM memory"],
                            "reserved disk memory": self.__system_status[n]["reserved disk memory"],
                            "running verification jobs": len(self.__system_status[n]["running verification jobs"]),
                            "running verification tasks": len(self.__system_status[n]["running verification tasks"]),
                            "available for jobs": self.__system_status[n]["available for jobs"],
                            "available for tasks": self.__system_status[n]["available for tasks"]
                        }
                    } for n in nodes
                }
            }
            configurations.append(conf)

        # Submit nodes
        if not self.__cached_system_status or self.__cached_system_status != str(configurations):
            self.__cached_system_status = str(configurations)
            server.submit_nodes(configurations)
            return True

        return False

    def schedule(self, pending_jobs, pending_tasks):
        def schedule_jobs(jobs):
            while len(jobs) > 0 and len(running_jobs) + len(jobs_to_run) <= self.__max_running_jobs:
                candidate = jobs.pop()

                n = self.__schedule_job(candidate)
                if n:
                    jobs_to_run.append([candidate, n])

        jobs_to_run = []
        tasks_to_run = []

        # Check high priority running jobs
        highest_priority = 'IDLE'
        running_jobs = self.__processing_jobs()
        for job, node in running_jobs:
            if higher_priority(self.__jobs_config[job]['priority'], highest_priority, strictly=True):
                highest_priority = self.__jobs_config[job]['priority']

        # Filter jobs that have a higher priority than the current highest priority
        filtered_jobs = [j for j in pending_jobs if higher_priority(j['configuration']['priority'], highest_priority,
                                                                    True)]
        schedule_jobs(filtered_jobs)

        # Schedule all posible tasks
        for task in pending_tasks:
            node = self.__schedule_task(task)
            if node:
                tasks_to_run.append([task, node])

        # Filter jobs that have the same or a higher priority than the current highest priority
        filtered_jobs = [j for j in pending_jobs if higher_priority(j['configuration']['priority'], highest_priority)]
        schedule_jobs(filtered_jobs)

        return tasks_to_run, jobs_to_run

    def claim_resources(self, avialable, identifier, job=False):
        # todo: get actial resources
        # todo: get information about job or task by an identifier and job key
        # todo: claim resources
        # todo: save that it is runnning there
        # return True
        raise NotImplementedError

    def release_resources(self, identifier, job=False, KeepDisk=0):
        # todo: get actual resources
        # todo: get information about job or task by an identifier and job key
        # todo: check that it is actually running on the node
        # todo: minus resources
        # todo: remove running task or job and delete config of task or job
        # todo: if KeepDisk
        # todo: plus back keepDisk space and check invariant
        # return True
        raise NotImplementedError

    def __schedule_job(self, job):
        # Ranking of available resources
        nodes = self.__nodes_ranking(self.__system_status, job)

        # Ranking of theoretically available resources
        if len(nodes) > 0:
            success, inv_nodes = self.__check_invariant(job)
            if success:
                # On base of new rankings choose a node
                suits = [n for n in nodes if n in inv_nodes]
                if len(suits) > 0:
                    return suits[0]

        return None

    def __schedule_task(self, task):
        # Ranking of available resources
        nodes = self.__nodes_ranking(self.__system_status, task)
        if len(nodes) > 0:
            return nodes[0]
        else:
            return None

    def __check_invariant(self, job=None):
        jobs = self.__processing_jobs()
        jobs = [self.__jobs_config[j[0]] for j in jobs] if not job else \
               [self.__jobs_config[j[0]] for j in jobs] + job

        if len(jobs) > 0:
            # Now check the invariant

            # Collect maximum task restrictions for each CPU model cpecified for tasks
            required_cpu_models = sorted({j['task resource limits']['CPU model'] for j in jobs})
            max_tasks = []
            for model in required_cpu_models:
                mx = self.__yield_max_task(model, job)
                max_tasks.append(mx)

            # Copy system status to calculatepotentially available resources
            par = copy.deepcopy(self.__system_status)

            # todo Free there all task resources but reserve all max task resources
            #for task, node in __processing_tasks

            # todo: make ranking of potentially available resources and reserve max task resources
            # todo: if all is fine return the last obtain ranking and resources
            # todo: if it is violated with provided job provide None
            # todo: if it is violated without provided job raise an Exception
            # todo: if it is not violated with provided job provide nodes ranking where job can be started
            # return True, ranking if job
            #        True, None if not job
            #        False, [cancel jobs] including job if it violates invariant
        else:
            return True, None

    def __nodes_ranking(self, system_status, restriction, job=True):
        suitable = [n for n in system_status.keys() if self.__fulfill_requirement(system_status[n], restriction, job)]
        return sorted(suitable, self.__free_resources)

    def __yield_max_task(self, cpu_model, job=None):
        # Choose all jobs
        jobs = self.__processing_jobs()
        jobs = [self.__jobs_config[j[0]] for j in jobs] if not job else \
               [self.__jobs_config[j[0]] for j in jobs] + job

        # Get all tasks restrictions
        restrictions = [j['task resource limits'] for j in jobs if not j['task resource limits']['CPU model'] or
                        not cpu_model or (cpu_model and j['task resource limits']['CPU model'] == cpu_model)]

        # For each parameter determine max
        restriction = {
            'CPU model': cpu_model
        }
        for r in ["number of CPU cores", "memory size", "disk memory size"]:
            m = max(restrictions, key=lambda e: e[r])
            restriction[r] = m

        return restriction

    def __reserve_resources(self, system_status, amount, node=None):
        # todo: get dictionary with all nodes and required amount
        # todo: filter out nodes
        # todo: minus resources
        # todo: return chosen node
        # return True
        raise NotImplementedError

    def __release_resources(self, system_status, amount, node):
        # todo: get dictionary with all nodes and required amount
        # todo: filter out nodes
        # todo: plus resources
        # todo: return chosen node
        # return True
        raise NotImplementedError

    def __processing_jobs(self):
        jobs = []
        for node in self.__system_status:
            for job in self.__system_status[node]["running verification jobs"]:
                jobs.append([job, node])

        return jobs

    def __processing_tasks(self):
        tasks = []
        for node in self.__system_status:
            for task in self.__system_status[node]["running verification tasks"]:
                tasks.append([task, node])

        return tasks

    @staticmethod
    def __fulfill_requirement(self, node, restriction, job=True):
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

        if cpu_number >= restriction["memory size"] and ram_memory >= restriction["number of CPU cores"] and \
                disk_memory >= restriction["disk memory size"]:
            return True
        else:
            return False

    @staticmethod
    def __free_resources(self, conf):
        cpu_number = conf["available CPU number"] - conf["reserved CPU number"]
        ram_memory = conf["available RAM memory"] - conf["reserved RAM memory"]
        disk_memory = conf["available disk memory"] - conf["reserved disk memory"]

        f = lambda x: x if x > 0 else 0
        return [f(cpu_number), f(ram_memory), f(disk_memory)]

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'