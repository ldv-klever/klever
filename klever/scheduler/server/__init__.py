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

from klever.scheduler.utils import bridge


def _robust_request(req):
    """
    This decorator processes some error that can happen at requesting Bridge. If an error occurred the decorated
    function will return None. This function should be used for decorating all requests that can fail but does not
    influence the whole scheduler but particular jobs or tasks.
    """

    def tolerant_method(self, *args, **kwargs):
        try:
            return req(self, *args, **kwargs)
        except bridge.BridgeError:
            if self._tolerate_error(): # pylint: disable=protected-access
                self.logger.debug('Ignore error from failed request {!r}: {!r}'.
                                  format(req.__name__, str(self.session.error)))
                return None
            raise

    return tolerant_method

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
        self.work_dir = work_dir
        self.logger = logger

    @_robust_request
    def pull_job_conf(self, job_identifier):
        self.logger.debug(f'Pull the configuration of job {job_identifier}')
        return self.session.json_exchange("service/configuration/{}".format(job_identifier), method='GET')

    @_robust_request
    def pull_task_conf(self, task_identifier):
        self.logger.debug(f'Pull the task configuration of task {task_identifier}')
        return self.session.json_exchange("service/tasks/{}/?fields=description".format(task_identifier), method='GET')

    @_robust_request
    def get_job_status(self, identifier):
        ret = self.session.json_exchange("service/decision-status/{}/".format(identifier), method='GET').get('status')
        self.logger.debug(f'Requested the status of job {identifier} and got {ret}')
        return ret

    @_robust_request
    def get_job_progress(self, identifier):
        ret = self.session.json_exchange('service/progress/{}/'.format(identifier), method='GET')
        return ret

    @_robust_request
    def cancel_job(self, job_identifier):
        self.logger.debug(f'Request cancelling of the job {job_identifier}')
        self.session.exchange("service/decision-status/{}/".format(job_identifier), method='PATCH',
                              data={"status": "7"})

    @_robust_request
    def submit_job_status(self, job_identifier, status):
        self.logger.debug(f'Submit a new job {job_identifier} status: {status}')
        self.session.exchange("service/decision-status/{}/".format(job_identifier), method='PATCH',
                              data={"status": status})

    @_robust_request
    def submit_job_error(self, job_identifier, error):
        self.logger.debug(f'Submit job {job_identifier} error: {error}')
        self.session.exchange("service/decision-status/{}/".format(job_identifier), method='PATCH',
                              data={"status": "4", "error": error})

    @_robust_request
    def submit_task_status(self, task_identifier, status):
        self.logger.debug(f'Submit status {status} for task {task_identifier}')
        self.session.exchange("service/tasks/{}/".format(task_identifier), method='PATCH', data={"status": status})

    @_robust_request
    def submit_task_error(self, task_identifier, error):
        self.logger.debug(f'Submit an error for task {task_identifier}: {error}')
        self.session.exchange("service/tasks/{}/".format(task_identifier), method='PATCH',
                              data={"status": "ERROR", "error": error})

    @_robust_request
    def delete_task(self, task_identifier):
        self.logger.debug(f'Submit deletion of task {task_identifier}')
        self.session.exchange("service/tasks/{}/".format(task_identifier), method='DELETE')

    @_robust_request
    def pull_task(self, identifier, archive):
        """
        Download verification task data from the verification gateway.

        :param identifier: Verification task identifier.
        :param archive: Path to the zip archive to save.
        """
        self.logger.debug(f'Pull task {identifier} data')
        return self.session.get_archive("service/tasks/{}/download/".format(identifier), archive=archive)

    @_robust_request
    def submit_solution(self, identifier, description, archive):
        """
        Send archive and description of an obtained from VerifierCloud solution to the verification gateway.

        :param identifier: Verification task identifier.
        :param description: Path to the JSON file to send.
        :param archive: Path to the zip archive to send.
        """
        self.logger.debug(f'Submit the solution of task {identifier}')
        self.session.push_archive("service/solution/",
                                  {
                                      "task": identifier,
                                      "description": json.dumps(description, ensure_ascii=False,
                                                                sort_keys=True, indent=4)
                                  },
                                  archive)

    def get_user_credentials(self, identifier):
        """
        Get VerifierCloud user credentials from the server by the given job identifier.

        :param identifier: job identifier.
        """
        self.logger.debug(f'Request user credentials {identifier}')
        return self.session.json_exchange('service/scheduler-user/{}/'.format(identifier), method='GET')

    def register(self, scheduler_type=None):
        """
        Send unique ID to the Verification Gateway with the other properties to enable receiving tasks.
        :param scheduler_type: Scheduler scheduler_type.
        """
        # Create session
        self.scheduler_type = scheduler_type
        self.session = bridge.Session(self.logger, self.conf["name"], self.conf["user"], self.conf["password"])

    def get_job_tasks(self, identifier):
        """
        Get all tasks related to a particular job from Bridge.

        :param identifier: Job identifier
        :return: ((id, status), ...)
        """
        self.logger.debug(f'Request tasks for job {identifier}')
        ret = self.session.json_exchange("service/tasks/?job={}&fields=status&fields=id".format(identifier),
                                         method='GET')
        return ((item['id'], item['status']) for item in ret)

    def get_all_jobs(self):
        """
        Get all jobs from Bridge and their statuses.

        :return: ((id, status))
        """
        self.logger.debug('Request a list of all running jobs')
        ret = self.session.json_exchange("jobs/api/decision-status/", method='GET')
        if ret:
            return ((item['identifier'], item['status']) for item in ret)

        return ret

    def get_all_tasks(self):
        """
        Get all tasks from Bridge and their statuses.

        :return: ((id, status))
        """
        self.logger.debug('Request a list of all running tasks')
        ret = self.session.json_exchange("service/tasks/?fields=status&fields=id&fields=id", method='GET')
        return ((item['id'], item['status']) for item in ret)

    def submit_nodes(self, nodes, looping=True):
        """
        Send string with JSON description of nodes available for verification in VerifierCloud.

        :param nodes: List of node descriptions.
        :param looping: Flag that indicates that this request should be attempted until it is successful.
        """
        self.session.json_exchange("service/update-nodes/", nodes, looping=looping)

    def submit_tools(self, tools, looping=True):
        """
        Send string with JSON description of verification tools available for verification in VerifierCloud.

        :param tools: Dictionary from scheduler configuration {'tool': {'version': path}}.
        :param looping: Do not wait for a Bridge successful answer.
        """
        tools_list = []
        for tool in tools.keys():
            for version in tools[tool]:
                tools_list.append({'name': tool, 'version': version})

        data = {'scheduler': self.scheduler_type, 'tools': tools_list}
        self.session.json_exchange("service/update-tools/", data, looping=looping)

    def _tolerate_error(self):
        if isinstance(self.session.error, dict) and \
            (('detail' in self.session.error and self.session.error['detail'] == 'Not found.') or
             ('task' in self.session.error and re.match('Invalid pk', self.session.error['task'][-1])) or
             ('status' in self.session.error and re.match('Status change from', self.session.error['status'][-1]))):
            self.logger.debug("Ignore an error from Bridge: {!r}".format(str(self.session.error)))
            return True
        return False
