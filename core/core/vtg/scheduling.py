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

import time

from core.utils import read_max_resource_limitations, time_units_converter


class Balancer:

    def __init__(self, conf, logger, precessing):
        self.conf = conf
        self.logger = logger
        self.processing = precessing

        # Stores current execution status
        self._problematic = dict()
        # Stores limitations for running and timeout tasks
        self._issued_limits = dict()
        # Total number of tasks
        self._total_tasks = None
        # Number of successfully(!) solved tasks for which resource caclulation statistics is available
        self._solved = 0

        # Read maximum limitations
        self._qos_limit = read_max_resource_limitations(logger, conf)

        # If options with wall limit are given we will try to improve timeout results
        if self.conf.get('wall time limit'):
            self.logger.debug("We will have probably extra time to solve timeout tasks")
            self._walllimit = time.time() + time_units_converter(self.conf['wall time limit'])[0]
            self._minstep = self.conf.get('min increaded limit', 1.2)
            self.logger.debug("Minimal time limit increasing step is {}%".format(int(round(self._minstep * 100))))
        else:
            self.logger.debug("We will not have extra time to solve timeout tasks")
            self._walllimit = None

        # Data for interval calculation with statistical values
        self._statistics = dict()

    @property
    def limitation_tasks(self):
        """Iterate over all tracking tasks."""
        for vo, classes in self._problematic.items():
            for rules in classes.values():
                for rule, task in rules.items():
                    yield (self._issued_limits[vo][rule], task)

    @property
    def rescheduling(self):
        """Check that all rest tasks are limits"""
        # Check that there is no any task that is not finished and it is not timeout or out of mem
        for vo, ruleclasses in self.processing.items():
            if vo not in self._problematic:
                return False
            else:
                for rc, rules in ruleclasses.items():
                    if rc not in self._problematic[vo]:
                        return False
                    else:
                        if set(rules.keys()).difference(set(self._problematic[vo][rc].keys())):
                            return False
        return True

    def is_there(self, vobject, rule_class, rule_name):
        """Check that task is tracked as a limit."""
        if self._problematic.get(vobject) and self._problematic[vobject].get(rule_class) and \
                self._problematic[vobject][rule_class].get(rule_name):
            return True
        return False

    def do_rescheduling(self, vobject, rule_class, rule_name):
        """Check that we rihgt now can reschedule this task if it is a timeout or memory limit."""
        if self.is_there(vobject, rule_class, rule_name) and \
                not self._problematic[vobject][rule_class][rule_name]['running']:
            element = self._is_there_or_init(vobject, rule_class, rule_name)
            assert not element['running']

            limitation = self._issued_limits[vobject][rule_name]
            self.logger.debug("Going to increass CPU time limitations for {}:{}".format(vobject, rule_name))
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
                    self.logger.debug("Reschedule {}:{} with increased CPU and wall time limit: {}, {}".
                                      format(vobject, rule_name, new_limit, new_wall_limit))
                    return element['attempt']
            self.logger.debug("We cannot now run {}:{}".format(vobject, rule_name))
        return False

    def need_rescheduling(self, vobject, rule_class, rule_name):
        """
        Check that in general this task need rescheduling but such rescheduling can be either done now or postponed.
        """
        if self.is_there(vobject, rule_class, rule_name):
            element = self._is_there_or_init(vobject, rule_class, rule_name)
            if not element["running"]:
                issued_limit = self._issued_limits[vobject][rule_name]
                if self._have_time(issued_limit) and self._qos_limit.get('CPU time', 0) > 0:
                    self.logger.info("Task {}:{} will be solved again".format(vobject, rule_name))
                    return True
            else:
                self.logger.info("Task {}:{} is still running".format(vobject, rule_name))
                return True
        return False

    def resource_limitations(self, vobject, rule_class, rule_name):
        """
        Issue a resource limitation for the task. If it is a timeout then previous method should already modify and
        increase the limitations.
        """

        # First set QoS limit
        limits = dict()
        limits.update(self._qos_limit)

        # Check do we have some statistics already
        if self.is_there(vobject, rule_class, rule_name):
            element = self._is_there_or_init(vobject, rule_class, rule_name)
            limits = self._issued_limits[vobject][rule_name]
            element['running'] = True
            element['attempt'] += 1
            self.logger.debug("Issue an increased limitation for {}:{}".format(vobject, rule_name))

        self._add_limit(vobject, rule_name, limits)
        return limits

    def add_solution(self, vobject, rule_class, rule_name, status_info):
        """Save solution and return is this solution is final or not"""
        status, resources, limit_reason = status_info

        # Check that it is an error from scheduler
        if resources:
            self.logger.debug("Task {}:{} finished".format(vobject, rule_name))
            self._solved += 1

            if limit_reason in ('OUT OF MEMORY', 'TIMEOUT'):
                self.logger.debug("Task {}:{} has been terminated due to limit".format(vobject, rule_name))
                element = self._is_there_or_init(vobject, rule_class, rule_name)
                element['status'] = limit_reason
                element['running'] = False
                # We need to check can we solve it again later
                return False
            elif self.is_there(vobject, rule_class, rule_name):
                # Ok ,we solved this timelimit or memory limit
                self._del_run(vobject, rule_class, rule_name)
                self._remove_limit(vobject, rule_name)
            else:
                self._remove_limit(vobject, rule_name)
        else:
            self.logger.debug("Task {}:{} failed".format(vobject, rule_name))
            if self.is_there(vobject, rule_class, rule_name):
                self._del_run(vobject, rule_class, rule_name)
            self._remove_limit(vobject, rule_name)

        return True

    def set_total_tasks(self, number):
        """When total number of tasks becomes known save it to the corresponding attribute"""
        self.logger.debug("Total number of tasks will be {}".format(number))
        self._total_tasks = number

    @property
    def _increasing_factor(self):
        """Estimate can we increase timelimit for timeout more that a user recommended."""
        min_time = sum((l['CPU time'] for l, t in self.limitation_tasks if not t['running']))
        increased_time = int(min_time * self._minstep)
        have_time = self._have_time()
        if increased_time >= have_time:
            return self._minstep
        else:
            return have_time / min_time

    def _add_limit(self, vobject, rule_name, limit):
        """Save resource limitation for a task."""
        rules = self._issued_limits.setdefault(vobject, dict())
        rules.update({rule_name: limit})

    def _remove_limit(self, vobject, rule_name):
        """Drop resource limitation for a task."""
        del self._issued_limits[vobject][rule_name]
        if len(self._issued_limits[vobject]) == 0:
            del self._issued_limits[vobject]

    def _is_there_or_init(self, vobject, rule_class, rule_name):
        """Check that task is tracked as a time limit or otherwise start tracking it."""
        classes = self._problematic.setdefault(vobject, dict())
        rules = classes.setdefault(rule_class, dict())
        return rules.setdefault(rule_name, {'status': None, 'running': False, 'attempt': 1})

    def _del_run(self, vobject, rule_class, rule_name):
        """Stop tracking error or limit task."""
        del self._problematic[vobject][rule_class][rule_name]
        if len(self._problematic[vobject][rule_class]) == 0:
            del self._problematic[vobject][rule_class]
        if len(self._problematic[vobject]) == 0:
            del self._problematic[vobject]

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
