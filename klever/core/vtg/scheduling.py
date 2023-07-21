#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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

import time

from klever.core.utils import read_max_resource_limitations, time_units_converter


class Governer:

    def __init__(self, conf, logger, precessing):
        self.conf = conf
        self.logger = logger
        self.processing = precessing

        # Stores current execution status
        self._problematic = {}
        # Stores limitations for running and timeout tasks
        self._issued_limits = {}
        # Total number of tasks
        self._total_tasks = None
        self._unique_tasks = 0
        # Number of successfully(!) solved tasks for which resource calculation statistics is available
        self._solved = 0
        # Indicator that rescheduling is possible
        self._rescheduling = False

        # Read maximum limitations
        self._qos_limit = read_max_resource_limitations(logger, conf)

        # If options with wall limit are given we will try to improve timeout results
        if self.conf.get('wall time limit'):
            self.logger.debug("We will have probably extra time to solve timeout tasks")
            self._walllimit = time.time() + time_units_converter(self.conf['wall time limit'])[0]
            self._minstep = self.conf.get('min increased limit', 1.5)
            self.logger.debug("Minimal time limit increasing step is {}%".format(int(round(self._minstep * 100))))
        else:
            self.logger.debug("We will not have extra time to solve timeout tasks")
            self._walllimit = None

        # Data for interval calculation with statistical values
        self._statistics = {}

    @property
    def limitation_tasks(self):
        """Iterate over all tracking tasks."""
        for task in list(self._problematic.keys()):
            yield self._issued_limits[task], task

    @property
    def rescheduling(self):
        """Check that all rest tasks are limits"""
        # Check that there is no any task that is not finished and it is not timeout or out of mem
        if self._rescheduling:
            return True
        if isinstance(self._total_tasks, int) and self._unique_tasks == self._total_tasks:
            self._rescheduling = True
            return True

        return False

    def is_there(self, task):
        """Check that task is tracked as a limit."""
        return task in self._problematic

    def is_running(self, task):
        return self._problematic[task]['running']

    def do_rescheduling(self, task):
        """Check that we right now can reschedule this task if it is a timeout or memory limit."""
        if self.is_there(task) and not self._problematic[task]['running']:
            element = self._is_there_or_init(task)
            assert not element['running']

            limitation = self._issued_limits[task]
            self.logger.debug(f"Going to increase CPU time limitations for {task}")
            if self.rescheduling and self._qos_limit.get('CPU time', 0) > 0:
                have_time = self._have_time(limitation)
                if have_time > 0:
                    factor = self._increasing_factor
                    new_limit = int(round(limitation['CPU time'] * factor))
                    limitation.update({'CPU time': new_limit})
                    new_wall_limit = 0  # For logging message
                    if limitation.get('wall time', 0) > 0:
                        new_wall_limit = int(round(((limitation['wall time'] / limitation['CPU time']) * new_limit)))
                        limitation.update({'wall time': new_wall_limit})
                    self.logger.debug(f"Reschedule {task} with increased CPU and wall time limit: {new_limit}, "
                                      f"{new_wall_limit}")
                    return element['attempt']
            self.logger.debug(f"We cannot now run {task}")
        return False

    def resource_limitations(self, task):
        """
        Issue a resource limitation for the task. If it is a timeout then previous method should already modify and
        increase the limitations.
        """
        # First set QoS limit
        limits = {}
        limits.update(self._qos_limit)

        # Check do we have some statistics already
        if self.is_there(task):
            element = self._is_there_or_init(task)
            limits = self._issued_limits[task]
            element['running'] = True
            element['attempt'] += 1
            self.logger.debug(f"Issue an increased limitation for {task}")
        else:
            self._unique_tasks += 1

        self._issued_limits[task] = limits
        return limits

    def add_solution(self, task, status_info=None):
        """Save solution and return is this solution is final or not"""
        # Check that it is an error from scheduler
        if self._walllimit and status_info:
            _, _, limit_reason = status_info
            self.logger.debug(f"Task {task} finished")
            self._solved += 1

            if limit_reason in ('OUT OF MEMORY', 'TIMEOUT'):
                self.logger.debug(f"Task {task} has been terminated due to limit")
                element = self._is_there_or_init(task)
                element['status'] = limit_reason
                element['running'] = False
                # We need to check can we solve it again later
                return False
            if self.is_there(task):
                # Ok ,we solved this timelimit or memory limit
                del self._problematic[task]
                del self._issued_limits[task]
            else:
                del self._issued_limits[task]
        else:
            self.logger.debug(f"Task {task} failed or we have no extra time")
            if self.is_there(task):
                del self._problematic[task]
            del self._issued_limits[task]

        return True

    def set_total_tasks(self, number):
        """When total number of tasks becomes known save it to the corresponding attribute"""
        self.logger.debug("Total number of tasks will be {}".format(number))
        self._total_tasks = number

    @property
    def _increasing_factor(self):
        """Estimate can we increase timelimit for timeout more that a user recommended."""
        min_time = sum((l['CPU time'] for l, t in self.limitation_tasks if not self._problematic[t]['running']))
        increased_time = int(min_time * self._minstep)
        have_time = self._have_time()
        if increased_time >= have_time:
            return self._minstep

        return have_time / min_time

    def _is_there_or_init(self, task):
        """Check that task is tracked as a time limit or otherwise start tracking it."""
        return self._problematic.setdefault(task, {'status': None, 'running': False, 'attempt': 1})

    def _have_time(self, limitation=None):
        """
        Check that we have time to solve timelimits. Note that this is not show that the time to solve them is
        actually is. We just check that if wall limitation for a job is given it is not come still.
        """
        if self._walllimit:
            rest = self._walllimit - time.time()
            if rest > 0 and ((limitation and rest > int(limitation['CPU time'] * self._minstep)) or (not limitation)):
                self.logger.debug("We have for solution of timeouts {}s".format(int(rest)))
                return int(rest)
        self.logger.debug("We have no extra time to solve timeouts")
        return 0
