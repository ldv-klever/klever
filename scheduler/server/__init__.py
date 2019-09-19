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
import re

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

    def get_job_status(self, identifier):
        return self.session.json_exchange("service/job-status/{}/".format(identifier), method='GET').get('status')

    def get_task_status(self, identifier):
        return self.session.json_exchange("service/tasks/{}/?fields=id".format(identifier), method='GET')

    def get_job_tasks(self, identifier):
        ret = self.session.json_exchange("service/tasks/?job={}&fields=status&fields=id".format(identifier),
                                         method='GET')
        return ((item['id'], item['status']) for item in ret)

    def get_all_jobs(self):
        ret = self.session.json_exchange("jobs/api/job-status/", method='GET')
        return ((item['identifier'], item['status']) for item in ret)

    def get_job_progress(self, identifier):
        ret = self.session.json_exchange('service/progress/{}/'.format(identifier), method='GET')
        return ret

    def get_all_tasks(self):
        ret = self.session.json_exchange("service/tasks/?fields=status&fields=id&fields=id", method='GET')
        return ((item['id'], item['status']) for item in ret)

    def cancel_job(self, job_identifier):
        self.session.exchange("service/job-status/{}/".format(job_identifier), method='PATCH', data={"status": "7"})

    def submit_job_status(self, job_identifier, status):
        try:
            self.session.exchange("service/job-status/{}/".format(job_identifier), method='PATCH',
                                  data={"status": status})
        except bridge.BridgeError:
            if self._tolerate_error():
                self.logger.warning('Bridge rejects job {!r} status change to {!r}'.format(job_identifier, status))
                return
            raise

    def submit_job_error(self, job_identifier, error):
        try:
            self.session.exchange("service/job-status/{}/".format(job_identifier), method='PATCH',
                                  data={"status": "4", "error": error})
        except bridge.BridgeError:
            if self._tolerate_error():
                self.logger.warning('Bridge rejects job {!r} status change to FAILED'.format(job_identifier))
                return
            raise

    def submit_task_status(self, task_identifier, status):
        try:
            self.session.exchange("service/tasks/{}/".format(task_identifier), method='PATCH',
                                  data={"status": status})
        except bridge.BridgeError:
            if self._tolerate_error():
                self.logger.warning('Bridge rejects task {!r} status change to {!r}'.format(task_identifier, status))
                return
            raise

    def submit_task_error(self, task_identifier, error):
        try:
            self.session.exchange("service/tasks/{}/".format(task_identifier), method='PATCH',
                                  data={"status": "ERROR", "error": error})
        except bridge.BridgeError:
            if self._tolerate_error():
                self.logger.warning('Bridge rejects task {!r} status change to FAILED'.format(task_identifier))
                return
            raise

    def delete_task(self, task_identifier):
        try:
            self.session.exchange("service/tasks/{}/".format(task_identifier), method='DELETE')
        except bridge.BridgeError:
            if self._tolerate_error():
                self.logger.warning('Bridge rejects task {!r} deletion'.format(task_identifier))
                return
            raise

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
        try:
            return self.session.push_archive("service/solution/",
                                             {
                                                 "task": identifier,
                                                 "description": json.dumps(description, ensure_ascii=False,
                                                                           sort_keys=True, indent=4)
                                             },
                                             archive)
        except bridge.BridgeError:
            if self._tolerate_error():
                self.logger.warning('Bridge rejects task {!r} solution archive'.format(identifier))
                return
            raise

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

    def _tolerate_error(self):
        if isinstance(self.session.error, dict):
            if 'detail' in self.session.error and self.session.error['detail'] == 'Not found.':
                return True
            if 'task' in self.session.error and re.match('Invalid pk', self.session.error['task']):
                return True
        return False
