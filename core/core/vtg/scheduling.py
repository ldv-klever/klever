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

import math

from core.utils import read_max_resource_limitations


def incmean(prevmean, n, x):
    """Calculate incremental mean"""
    newmean = prevmean + int(round((x - prevmean) / n))
    return newmean


def incsum(prevsum, prevmean, mean, x):
    """Caclulate incremental sum of square deviations"""
    newsum = prevsum + (x - prevmean) * (x - mean)
    return newsum


def devn(cursum, n):
    """Caclulate incremental standart deviation"""
    deviation = int(round(math.sqrt(cursum / n)))
    return deviation


class Balancer:

    def __init__(self, conf, logger, precessing, problem_tasks):
        self.processing = precessing
        self.interrupted = problem_tasks
        self.conf = conf
        self.logger = logger
        self.qos_limit = read_max_resource_limitations(logger, conf)

        # Data for interval calculation
        self.statistics = dict()

    @property
    def rescheduling(self):
        # Check that there is no any task that is not finished and it is not timeout or out of mem
        for vo in self.processing:
            if vo not in self.interrupted:
                return False
            else:
                for rc in self.processing[vo]:
                    if rc not in self.interrupted[vo]:
                        return False
                    else:
                        for rule in self.processing[vo][rc]:
                            if rule not in self.interrupted[vo][rc]:
                                return False

        return True

    def is_there(self, vobject, rule_class, rule_name):
        if vobject in self.processing and rule_class in self.processing[vobject] and rule_name in \
                self.processing[vobject][rule_class]:
            return True
        else:
            return False

    def is_there_or_init(self, vobject, rule_class, rule_name):
        if not self.is_there(vobject, rule_class, rule_name):
            if vobject not in self.processing:
                self.processing[vobject] = {rule_class: {rule_name: {'error': False, 'status': None}}}
            elif rule_class not in self.processing[vobject]:
                self.processing[vobject][rule_class] = {rule_name: {'error': False, 'status': None}}
            else:
                self.processing[vobject][rule_class][rule_name] = {'error': False, 'status': None}
        return self.processing[vobject][rule_class][rule_name]

    def del_run(self, vobject, rule_class, rule_name):
        del self.processing[vobject][rule_class][rule_name]
        if len(self.processing[vobject][rule_class]) == 0:
            del self.processing[vobject][rule_class]
        if len(self.processing[vobject]) == 0:
            del self.processing[vobject]

    def add_solution(self, vobject, rule_class, rule_name, status_info):
        """Save solution and return is this solution is final or not"""
        status, resources, limit_reason = status_info

        # Update statistics
        if status == 'error':
            if self.is_there(vobject, rule_class, rule_name):
                element = self.is_there_or_init(vobject, rule_class, rule_name)
                if element['error']:
                    element['error'] = False
                    if not element['status']:
                        # Delete it if it is not a limitation problem
                        self.del_run(vobject, rule_class, rule_name)
                else:
                    element['error'] = True
                    return False
            else:
                element = self.is_there_or_init(vobject, rule_class, rule_name)
                element['error'] = True
                return False
        else:
            if resources:
                if rule_class not in self.statistics:
                    self.statistics[rule_class] = {
                        'mean mem': resources['memory size'],
                        'memsum': 0,
                        'memdev': 0,
                        'mean time': resources['CPU time'],
                        'timesum': 0,
                        'timedev': 0,
                        'number': 1
                    }
                else:
                    self.statistics['number'] += 1
                    # First CPU
                    newmean = incmean(self.statistics[rule_class]['mean time'], self.statistics[rule_class]['number'],
                                      resources['CPU time'])
                    newsum = incsum(self.statistics[rule_class]['timesum'], self.statistics[rule_class]['mean time'],
                                    newmean, resources['CPU time'])
                    timedev = devn(newsum, self.statistics[rule_class]['number'])
                    self.statistics[rule_class]['mean time'] = newmean
                    self.statistics[rule_class]['timesum'] = newsum
                    self.statistics[rule_class]['timedev'] = timedev

                    # Then memory
                    newmean = incmean(self.statistics[rule_class]['mean mem'], self.statistics[rule_class]['number'],
                                      resources['memory size'])
                    newsum = incsum(self.statistics[rule_class]['memsum'], self.statistics[rule_class]['mean mem'],
                                    newmean, resources['memory size'])
                    timedev = devn(newsum, self.statistics[rule_class]['number'])
                    self.statistics[rule_class]['mean mem'] = newmean
                    self.statistics[rule_class]['memsum'] = newsum
                    self.statistics[rule_class]['memdev'] = timedev

                if limit_reason in ('CPU time exhausted', 'memory exhausted'):
                    element = self.is_there_or_init(vobject, rule_class, rule_name)
                    element['status'] = limit_reason
                    return False
                elif self.is_there(vobject, rule_class, rule_name):
                    # Ok ,we solved this timelimit or memory limit
                    self.del_run(vobject, rule_class, rule_name)

        return True

    def need_rescheduling(self, vobject, rule_class, rule):
        return False

    def neednot_rescheduling(self, vobject, rule_class, rule):
        return False

    def resource_limitations(self, vobject, rule_class, rule):
        return self.qos_limit
