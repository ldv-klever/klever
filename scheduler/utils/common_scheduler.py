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


class CalculationSystem:

    def __init__(self, max_jobs=1):
        """
        Initiaize abstract scheduler that allows to track resources and do planning but ignores any resl statuses of
        verification jobs and tasks. It also does not run or stop solution of jobs and tasks.

        :param max_jobs: Maximum number of running jobs of the same or higher priority.
        """
        self.__max_running_jobs = max_jobs
        self.__system_status = {}
        # {identifier -> node_name}
        self.__running_jobs = {}
        # {identifier -> node_name}
        self.__running_tasks = {}
        # {identifier -> {job resources}, {task resources}, priority}
        self.__jobs_config = {}

    def update_nodes(self, avialable):
        # todo: get dictionary and compare it with existing one
        # todo: if nodes left report about failed jobs and tasks running there
        # todo: for rest edit amount of avialable resources
        # todo: if resources left less than available do nothing - expect that in case of emmergency user just
        #       reconnect node
        # todo: recalculate invariant - if it is not satisfied: cancel tasjs or jobs
        #return available
        raise NotImplementedError

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

    def __check_invariant(self, job):
        # todo: for each CPU determine max task resources
        # todo: make ranking of potentially available resources and reserve max task resources
        # todo: if all is fine return the last obtain ranking and resources
        # todo: if it is violated with provided job provide None
        # todo: if it is violated without provided job raise an Exception
        # todo: if it is not violated with provided job provide nodes ranking where job can be started
        # return ranking
        raise NotImplementedError

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