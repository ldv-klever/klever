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

import json

import server as server
import utils.bridge as bridge


class Server(server.AbstractServer):
    """Exchange with gateway via net."""

    session = None
    scheduler_type = None

    def register(self, scheduler_type=None):
        """
        Send unique ID to the Verification Gateway with the other properties to enable receiving tasks.
        :param scheduler_type: Scheduler scheduler_type.
        :param require_login: Flag indicating whether or not user should authorize to send tasks.
        """
        # Create session
        self.scheduler_type = scheduler_type
        self.session = bridge.Session(self.logger, self.conf["name"], self.conf["user"], self.conf["password"])

    def exchange(self, tasks):
        """
        Send to the verification gateway JSON set of solving/solved tasks and get new set back.

        :param tasks: String with JSON task set inside.
        :return: String with JSON task set received from the verification Gateway.
        """
        data = {"jobs and tasks status": json.dumps(tasks, ensure_ascii=False, sort_keys=True, indent=4)}
        ret = self.session.json_exchange("service/get_jobs_and_tasks/", data)
        return json.loads(ret["jobs and tasks status"])

    def pull_task(self, identifier, archive):
        """
        Download verification task data from the verification gateway.

        :param identifier: Verification task identifier.
        :param archive: Path to the zip archive to save.
        """
        return self.session.get_archive("service/download_task/", {"task id": identifier}, archive)

    def submit_solution(self, identifier, description, archive):
        """
        Send archive and description of an obtained from VerifierCloud solution to the verification gateway.

        :param identifier: Verification task identifier.
        :param description: Path to the JSON file to send.
        :param archive: Path to the zip archive to send.
        """
        return self.session.push_archive("service/upload_solution/",
                                         {
                                             "task id": identifier,
                                             "description": json.dumps(description, ensure_ascii=False, sort_keys=True,
                                                                       indent=4)
                                         },
                                         archive)

    def submit_nodes(self, nodes, looping=True):
        """
        Send string with JSON description of nodes available for verification in VerifierCloud.

        :param nodes: String with JSON nodes description.
        :param looping: Flag that indicates that this request should be attempted until it is successful.
        """
        data = {"nodes data": json.dumps(nodes, ensure_ascii=False, sort_keys=True, indent=4)}
        self.session.json_exchange("service/update_nodes/", data, looping=looping)

    def submit_tools(self, tools):
        """
        Send string with JSON description of verification tools available for verification in VerifierCloud.

        :param tools: Dictionary from scheduler configuration {'tool': {'version': path}}.
        """
        tools_list = list()
        for tool in tools.keys():
            for version in tools[tool]:
                tools_list.append({'name': tool, 'version': version})

        data = {'scheduler': self.scheduler_type, 'tools': tools_list}
        self.session.json_exchange("service/update_tools/", data)

    def stop(self):
        """
        Log out if necessary.
        """
        self.session.sign_out()

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
