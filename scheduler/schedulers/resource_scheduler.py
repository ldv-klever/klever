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
from utils import higher_priority, sort_priority


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
        self.__jobs_config = {}
        self.__tasks_config = {}

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

    def schedule(self, pending_tasks, pending_jobs):
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
        running_jobs = self.__processing_jobs
        for job, node in running_jobs:
            if higher_priority(self.__jobs_config[job]['configuration']['priority'], highest_priority, strictly=True):
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

    def claim_resources(self, identifier, conf, node, job=False):
        if job and identifier in self.__processing_jobs:
            raise KeyError("Verification job {!r} should be already running")
        elif identifier in self.__processing_tasks:
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
        self.__system_status[node][tag].append(identifier)

    def release_resources(self, identifier, node, job=False, KeepDisk=0):
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

        # Remove running task or job and delete config of task or job
        del collection[identifier]
        self.__system_status[node][tag].remove(identifier)

        if KeepDisk:
            diff = self.__system_status[node]["available disk memory"] - \
                   self.__system_status[node]["reserved disk memory"]
            if KeepDisk > diff:
                raise ValueError('Cannot reserve amount of disk memory {} which is higher than rest amount {} at node '
                                 '{}'.format(KeepDisk, diff, node))

            self.__system_status[node]["reserved disk memory"] += KeepDisk

    @property
    def __processing_jobs(self):
        jobs = []
        for node in self.__system_status:
            for job in self.__system_status[node]["running verification jobs"]:
                jobs.append([job, node])

        return jobs

    @property
    def __processing_tasks(self):
        tasks = []
        for node in self.__system_status:
            for task in self.__system_status[node]["running verification tasks"]:
                tasks.append([task, node])

        return tasks

    @property
    def active_nodes(self):
        return [n for n in self.__system_status.keys() if self.__system_status[n]['status'] != 'DISCONNECTED']

    def node_info(self, node):
        return copy.deepcopy(self.__system_status[node])

    def __schedule_job(self, job):
        # Ranking of available resources
        nodes = self.__nodes_ranking(self.__system_status, job['configuration']['resource limits'])

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
        nodes = self.__nodes_ranking(self.__system_status, task['description']['resource limits'])
        if len(nodes) > 0:
            return nodes[0]
        else:
            return None

    def __check_invariant(self, job=None):
        def yield_max_task(given_model, jobs):
            # Get all tasks restrictions
            restrictions = [j[1]['configuration']['task resource limits'] for j in jobs
                            if not j[1]['configuration']['task resource limits']['CPU model'] or
                            not cpu_model or
                            (cpu_model and j[1]['configuration']['task resource limits']['CPU model'] == given_model)]

            # For each parameter determine max
            restriction = {
                'CPU model': given_model
            }
            for r in ["number of CPU cores", "memory size", "disk memory size"]:
                m = max(restrictions, key=lambda e: e[r])
                restriction[r] = m[r]

            return restriction

        def check_invariant_for_jobs(jobs_list):
            # Copy system status to calculatepotentially available resources
            par = copy.deepcopy(self.__system_status)

            # Free there all task resources but reserve all max task resources
            for task, node in self.__processing_tasks:
                self.__release_resources(par, self.__tasks_config[task]['resource limits'], node)
            # Free resources of jobs that are not in given list
            for j, node in (j for j in self.__processing_jobs if j not in [e[0] for e in jobs_list]):
                self.__release_resources(par, self.__jobs_config[j], node)

            # Collect maximum task restrictions for each CPU model cpecified for tasks
            required_cpu_models = \
                sorted({j[1]['configuration']['task resource limits']['CPU model'] for j in jobs_list})
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

            sysinfo, cpu_model, mx_task = check_invariant_for_jobs(jobs)
            if cpu_model and mx_task and job:
                # invariant is violated, try to determine jobs to cancel
                # Sort jibs by priority
                cancel = []
                jobs = sorted(jobs, key=lambda x: sort_priority(x[1]['priority']))
                while cpu_model and mx_task and len(jobs) > 0:
                    # First try to cancel job with given CPU model and max requirements
                    suitable = \
                        [j for j in jobs if
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
            elif cpu_model and mx_task:
                return False, None

            # Invariant is preserved, return ranking for the given job
            if job:
                ranking = self.__nodes_ranking(sysinfo, job["configuration"]["resource limits"], job=True)
                return True, ranking
            else:
                return True, None

        else:
            return True, None

    def __nodes_ranking(self, system_status, restriction, job=True):
        suitable = [n for n in system_status.keys() if self.__fulfill_requirement(system_status[n], restriction, job)]
        return sorted(suitable, key=lambda x: self.__free_resources(system_status[x]))

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

        if cpu_number >= restriction["number of CPU cores"] and ram_memory >= restriction["memory size"] and \
                disk_memory >= restriction["disk memory size"]:
            return True
        else:
            return False

    @staticmethod
    def __reserve_resources(system_status, amount, node=None):
        if node not in system_status:
            raise KeyError("There is no node {!r} in the system".format(node))

        # Minus resources
        for st, vt, at in [["reserved CPU number", "number of CPU cores", "available CPU number"],
                           ["reserved RAM memory", "memory size", "available RAM memory"],
                           ["reserved disk memory", "disk memory size", "available disk memory"]]:
            system_status[node][st] += amount[vt]
            if system_status[node][st] > system_status[node][at]:
                raise ValueError("{}, equal to {}, cannot be more than {} which is {}".
                                 format(st.capitalize(), system_status[node][st], at, system_status[node][at]))

        return

    @staticmethod
    def __release_resources(system_status, amount, node):
        if node not in system_status:
            raise KeyError("There is no node {!r} in the system".format(node))

        # Plus resources
        for st, vt, at in [["reserved CPU number", "number of CPU cores", "available CPU number"],
                           ["reserved RAM memory", "memory size", "available RAM memory"],
                           ["reserved disk memory", "disk memory size", "available disk memory"]]:
            system_status[node][st] -= amount[vt]
            if system_status[node][st] < 0:
                raise ValueError("{} cannot be negative {}".
                                 format(st.capitalize(), system_status[node][st]))

        return

    @staticmethod
    def __free_resources(conf):
        def f(x):
            return x if x > 0 else 0

        cpu_number = conf["available CPU number"] - conf["reserved CPU number"]
        ram_memory = conf["available RAM memory"] - conf["reserved RAM memory"]
        disk_memory = conf["available disk memory"] - conf["reserved disk memory"]

        return [f(cpu_number), f(ram_memory), f(disk_memory)]

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
