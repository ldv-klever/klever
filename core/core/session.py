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

import json
import requests
import time
import zipfile


class UnexpectedStatusCode(IOError):
    pass


class BridgeError(IOError):
    pass


class Session:
    def __init__(self, logger, bridge, job_id):
        logger.info('Create session for user "{0}" at Klever Bridge "{1}"'.format(bridge['user'], bridge['name']))

        self.logger = logger
        self.name = bridge['name']
        self.session = requests.Session()
        self.error = None

        # TODO: try to autentificate like with httplib2.Http().add_credentials().
        # Get initial value of CSRF token via useless GET request.
        self.__request('users/service_signin/')

        # Sign in.
        self.__request('users/service_signin/', {
            'username': bridge['user'],
            'password': bridge['password'],
            'job identifier': job_id
        })
        logger.debug('Session was created')

    def __request(self, path_url, data=None, **kwargs):
        url = 'http://' + self.name + '/' + path_url

        # Presence of data implies POST request.
        method = 'POST' if data else 'GET'

        self.logger.debug('Send "{0}" request to "{1}"'.format(method, url))

        if data:
            data.update({'csrfmiddlewaretoken': self.session.cookies['csrftoken']})

        while True:
            try:
                if data:
                    resp = self.session.post(url, data, **kwargs)
                else:
                    resp = self.session.get(url, **kwargs)

                if resp.status_code != 200:
                    with open('response error.html', 'w', encoding='utf8') as fp:
                        fp.write(resp.text)
                    status_code = resp.status_code
                    resp.close()
                    raise UnexpectedStatusCode(
                        'Got unexpected status code "{0}" when send "{1}" request to "{2}"'.format(status_code,
                                                                                                   method, url))
                if resp.headers['content-type'] == 'application/json' and 'error' in resp.json():
                    self.error = resp.json()['error']
                    resp.close()
                    raise BridgeError(
                        'Got error "{0}" when send "{1}" request to "{2}"'.format(self.error, method, url))

                return resp
            except requests.ConnectionError:
                self.logger.warning('Could not send "{0}" request to "{1}"'.format(method, url))
                time.sleep(1)

    def start_job_decision(self, job, start_report_file):
        with open(start_report_file, encoding='utf8') as fp:
            start_report = fp.read()

        # TODO: report is likely should be compressed.
        self.__download_archive('job', 'jobs/decide_job/',
                                {
                                    'attempt': 0,
                                    'job format': job.FORMAT,
                                    'report': start_report
                                },
                                job.ARCHIVE)

    def schedule_task(self, task_file, archive):
        with open(task_file, 'r', encoding='utf8') as fp:
            data = fp.read()

        resp = self.__upload_archive(
            'service/schedule_task/',
            {'description': data},
            [archive]
        )
        return resp.json()['task id']

    def get_tasks_statuses(self, task_ids):
        resp = self.__request('service/get_tasks_statuses/', {'tasks': json.dumps(task_ids)})
        statuses = resp.json()['tasks statuses']
        return json.loads(statuses)

    def get_task_error(self, task_id):
        resp = self.__request('service/download_solution/', {'task id': task_id})
        return resp.json()['task error']

    def download_decision(self, task_id):
        self.__download_archive('decision', 'service/download_solution/', {'task id': task_id},
                                'decision result files.zip')

    def remove_task(self, task_id):
        self.__request('service/remove_task/', {'task id': task_id})

    def sign_out(self):
        self.logger.info('Finish session')
        self.__request('users/service_signout/')

    def upload_report(self, report_file, archives=None):
        with open(report_file, encoding='utf8') as fp:
            report = fp.read()

        # TODO: report is likely should be compressed.
        self.__upload_archive('reports/upload/', {'report': report}, archives)

    def __download_archive(self, kind, path_url, data, archive):
        while True:
            resp = None
            try:
                resp = self.__request(path_url, data, stream=True)

                self.logger.debug('Write {0} archive to "{1}"'.format(kind, archive))
                with open(archive, 'wb') as fp:
                    for chunk in resp.iter_content(1024):
                        fp.write(chunk)

                if not zipfile.is_zipfile(archive) or zipfile.ZipFile(archive).testzip():
                    self.logger.warning('Could not download ZIP archive')
                else:
                    break
            finally:
                if 'attempt' in data:
                    data['attempt'] += 1

                if resp:
                    resp.close()

    def __upload_archive(self, path_url, data, archives):
        while True:
            resp = None
            try:
                resp = self.__request(path_url, data, files=[('file', open(archive, 'rb', buffering=0))
                                                             for archive in archives], stream=True)
                return resp
            except BridgeError:
                if self.error == 'ZIP error':
                    self.logger.exception('Could not upload ZIP archive')
                    self.error = None
                    time.sleep(1)
                else:
                    raise
            finally:
                if resp:
                    resp.close()
