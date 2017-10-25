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

import abc


class AbstractServer(metaclass=abc.ABCMeta):
    """Start exchange with verification gate."""

    def __init__(self, logger, conf, work_dir):
        """
        Save relevant configuration, authorize at remote verification
        gateway and register there as scheduler.
        :param conf: Dictionary with relevant configuration.
        :param work_dir: Path to the working directory.
        :return:
        """
        self.conf = conf
        self.work_dir = work_dir,
        self.logger = logger


    @abc.abstractmethod
    def register(self, scheduler_type):
        """
        Send unique ID to the Verification Gateway with the other properties to enable receiving tasks.
        :param scheduler_type: Scheduler type.
        """
        return

    @abc.abstractmethod
    def exchange(self, tasks):
        """
        Send to the verification gateway JSON set of solving/solved tasks and get new set back.

        :param tasks: String with JSON task set inside.
        :return: String with JSON task set received from the verification Gateway.
        """
        return tasks

    @abc.abstractmethod
    def pull_task(self, identifier, archive):
        """
        Download verification task data from the verification gateway.
        :param identifier: Verification task identifier.
        :param archive: Path to the zip archive to save.
        """
        return

    @abc.abstractmethod
    def submit_solution(self, identifier, description, archive):
        """
        Send archive and description of an obtained from VerifierCloud solution to the verification gateway.

        :param identifier: Verification task identifier.
        :param description: Path to the JSON file to send.
        :param archive: Path to the zip archive to send.
        """
        return

    @abc.abstractmethod
    def submit_nodes(self, nodes, looping):
        """
        Send string with JSON description of nodes available for verification in VerifierCloud.
        :param nodes: String with JSON nodes description.
        :param looping: Flag that indicates that this request should be attempted until it is successful.
        """
        return

    @abc.abstractmethod
    def submit_tools(self, tools):
        """
        Send string with JSON description of verification tools available for verification in VerifierCloud.
        :param tools: String with JSON verification tools description.
        """
        return

    @abc.abstractmethod
    def stop(self):
        """
        Log out if necessary.
        """
        return


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
