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

from klever.scheduler.schedulers import resource_scheduler
from klever.scheduler import utils
from klever.scheduler.schedulers.native import BaseNativeRunner


class Docker(BaseNativeRunner):
    """
    Implement the scheduler which is used to run tasks and jobs on this system locally.
    """
    _process = None

    def init(self):
        """
        Initialize scheduler completely. This method should be called both at constructing stage and scheduler
        reinitialization. Thus, all object attribute should be cleaned up and set as it is a newly created object.
        """
        super().init()
        # Check node first time
        self._manager = resource_scheduler.DockerResourceManager(
            self.logger,
            max_jobs=self.conf["scheduler"].get("concurrent jobs", 1),
            is_adjust_pool_size=self.conf["scheduler"].get("limit max tasks based on plugins load", False),
            node_conf=self.conf.get("node configuration", None)
        )

        node_conf = utils.prepare_node_info(self.conf.get("node configuration", None))
        self._node_name = node_conf['node name']

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
        return self._process

    def _solve_job(self, identifier, configuration):
        """
        Solve given verification job.

        :param identifier: Job identifier.
        :param configuration: Job configuration.
        :return: Return Future object.
        """
        self.logger.debug("Start solution of job {!r}".format(identifier))
        self._prepare_solution(identifier, configuration['configuration'], mode='job')
        return self._process

    def _is_done(self, item):
        done = self._process and self._process.exitcode is not None
        result = self._process.exitcode if done else None
        return done, result

    def _is_cancelable(self, identifier, item, mode='task'):
        if self._process:
            self._process.terminate()
            return self._process
        return None

    def _prepare_solution(self, identifier, configuration, mode='task'):
        """
        Generate a working directory, configuration files and multiprocessing Process object to be ready to just run it.

        :param identifier: Job or task identifier.
        :param configuration: A dictionary with a configuration or description.
        :param mode: 'task' or 'job'.
        :raise SchedulerException: Raised if the preparation fails and task or job cannot be scheduled.
        """
        self._process = super()._prepare_solution(identifier, configuration, mode)
        self._process.start()
