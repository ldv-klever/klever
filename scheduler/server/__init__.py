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

import utils.bridge as bridge


class Server:
    """Exchange with gateway via net."""

    session = None
    scheduler_type = None

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

    def register(self, scheduler_type=None):
        """
        Send unique ID to the Verification Gateway with the other properties to enable receiving tasks.
        :param scheduler_type: Scheduler scheduler_type.
        :param require_login: Flag indicating whether or not user should authorize to send tasks.
        """
        # Create session
        self.scheduler_type = scheduler_type
        self.session = bridge.Session(self.logger, self.conf["name"], self.conf["user"], self.conf["password"])

    def pull_job_conf(self, job_identifier):
        ret = self.session.json_exchange("service/configuration/{}".format(job_identifier), method='GET')
        return ret

    def pull_task_conf(self, task_identifier):
        ret = self.session.json_exchange("service/tasks/{}/?fields=description".format(task_identifier), method='GET')
        return ret

    def cancel_job(self, job_identifier):
        self.session.json_exchange("service/job-status/{}/".format(job_identifier), method='PATCH',
                                   data={"status": "7"})

    def submit_job_error(self, job_identifier, error):
        try:
            self.session.json_exchange("service/job-status/{}/".format(job_identifier), method='PATCH',
                                       data={"status": "4", "error": error})
        except Exception as err:
            self.logger.warning("")

    def submit_job_finished(self, job_identifier):
        self.session.json_exchange("service/job-status/{}/".format(job_identifier), method='PATCH',
                                   data={"status": "3"})

    def submit_processing_task(self, task_identifier):
        self.session.json_exchange("service/tasks/{}/".format(task_identifier), method='PATCH',
                                   data={"status": "PROCESSING"})

    def submit_finished_task(self, task_identifier):
        self.session.json_exchange("service/tasks/{}/".format(task_identifier), method='PATCH',
                                   data={"status": "FINISHED"})

    def delete_task(self, task_identifier):
        self.session.json_exchange("service/tasks/{}/".format(task_identifier), method='DELETE')

    def submit_task_error(self, task_identifier, error):
        try:
            self.session.json_exchange("service/tasks/{}/".format(task_identifier), method='PATCH',
                                       data={"status": "ERROR", "error": error})
        except bridge.UnexpectedStatusCode:
            self.logger.warning("Unexpected status code of task {!r}".format(task_identifier))

    def pull_task(self, identifier, archive):
        """
        Download verification task data from the verification gateway.

        :param identifier: Verification task identifier.
        :param archive: Path to the zip archive to save.
        """
        return self.session.get_archive("service/tasks/{}/download/".format(identifier), archive=archive)

    def submit_solution(self, identifier, description, archive):
        """
        Send archive and description of an obtained from VerifierCloud solution to the verification gateway.

        :param identifier: Verification task identifier.
        :param description: Path to the JSON file to send.
        :param archive: Path to the zip archive to send.
        """
        return self.session.push_archive("service/solution/",
                                         {
                                             "task": identifier,
                                             "description": json.dumps(description, ensure_ascii=False, sort_keys=True,
                                                                       indent=4)
                                         },
                                         archive)

    def submit_nodes(self, nodes, looping=True):
        """
        Send string with JSON description of nodes available for verification in VerifierCloud.

        :param nodes: List of node descriptions.
        :param looping: Flag that indicates that this request should be attempted until it is successful.
        """
        self.session.json_exchange("service/update-nodes/", nodes, looping=looping)

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
        self.session.json_exchange("service/update-tools/", data)

    def stop(self):
        """
        Log out if necessary.
        """
        self.session.sign_out()
