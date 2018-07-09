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

from core.utils import read_max_resource_limitations


class Balancer:

    def __init__(self, conf, logger, precessing, problem_tasks):
        self.processing = precessing
        self.interrupted = problem_tasks
        self.conf = conf
        self.logger = logger
        self.qos_limit = read_max_resource_limitations(logger, conf)

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

    def add_solution(self, vobject, rule_class, rule_name, status_info):
        return True

    def need_rescheduling(self, vobject, rule_class, rule):
        return False

    def neednot_rescheduling(self, vobject, rule_class, rule):
        return False

    def resource_limitations(self, vobject, rule_class, rule):
        return self.qos_limit
