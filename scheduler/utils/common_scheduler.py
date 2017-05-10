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
            self.__system_status[missing]["status"] == "DISCONNECTED"

        # Check ailing status
        for name, node in ([n, self.__system_status[n]] for n in self.__system_status
                            if self.__system_status[n]["status"] != "DISCONNECTED"):
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

    def schedule(self, configs, pending_jobs, pending_tasks):
        # todo: Check high priority pending jobs
        # todo: Try to  schedule it
        # todo: Schedule all avialable tasks
        # todo: Try schedule rest jobs until N
        # return run
        raise NotImplementedError

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

    def __schedule_job(self):
        # todo: ranking of available resources
        # todo: ranking of theoretically available resources
        # todo: check invariant
        # todo: on base of new rankings choose a node
        # return node
        raise NotImplementedError

    def __schedule_task(self):
        # todo: ranking of available resources
        # todo: choose the mostly used machine
        # return node
        raise NotImplementedError

    def __check_invariant(self, job=None):
        # todo: for each CPU determine max task resources
        # todo: make ranking of potentially available resources and reserve max task resources
        # todo: if all is fine return the last obtain ranking and resources
        # todo: if it is violated with provided job provide None
        # todo: if it is violated without provided job raise an Exception
        # todo: if it is not violated with provided job provide nodes ranking where job can be started
        # return True, ranking if job
        #        True, None if not job
        #        False, [cancel jobs] including job if it violates invariant
        #raise NotImplementedError
        return True, []

    def __nodes_ranking(self, available, required):
        # todo: sort machines from the mostly used to free avialable
        # todo: exclude machines that do not have enough resources according to requirements
        # return ranking
        raise NotImplementedError

    def __yield_max_task(self, cpu_model):
        # todo: choose all jobs
        # todo: get all tasks restrictions
        # todo: for each parameter determine max
        # todo: provide such dictionary
        # return restrictions
        raise NotImplementedError

    def __reserve_resources(self, avialable, amount, node=None):
        # todo: get dictionary with all nodes and required amount
        # todo: filter out nodes
        # todo: minus resources
        # todo: return chosen node
        # return True
        raise NotImplementedError

    def __release_resources(self, avialable, amount, node):
        # todo: get dictionary with all nodes and required amount
        # todo: filter out nodes
        # todo: plus resources
        # todo: return chosen node
        # return True
        raise NotImplementedError

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'