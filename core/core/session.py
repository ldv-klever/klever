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
        self.job_id = job_id

        self.error = None

        self.__parameters = {
            'username': bridge['user'],
            'password': bridge['password']
        }

        # Sign in.
        self.__signin()

    def __signin(self):
        self.session = requests.Session()
        resp = self.__request('service/get_token/', 'POST', data=self.__parameters)
        self.session.headers.update({'Authorization': 'Token {}'.format(resp.json()['token'])})
        self.logger.debug('Session was created')

    def __request(self, path_url, method, **kwargs):
        url = 'http://' + self.name + '/' + path_url

        kwargs.setdefault('allow_redirects', True)

        self.logger.debug('Send "{0}" request to "{1}"'.format(method, url))

        while True:
            try:
                resp = self.session.request(method, url, **kwargs)

                if resp.status_code != 200:
                    if resp.headers['content-type'] == 'application/json':
                        # TODO: analize resp.json()
                        self.error = resp.json()
                        raise BridgeError(
                            'Got error "{0}" when send "{1}" request to "{2}"'.format(self.error, method, url)
                        )
                    with open('response error.html', 'w', encoding='utf8') as fp:
                        fp.write(resp.text)
                    status_code = resp.status_code
                    resp.close()
                    raise UnexpectedStatusCode(
                        'Got unexpected status code "{0}" when send "{1}" request to "{2}"'.format(status_code,
                                                                                                   method, url))
                return resp
            except requests.ConnectionError:
                self.logger.warning('Could not send "{0}" request to "{1}"'.format(method, url))
                time.sleep(0.2)

    def start_job_decision(self, job_format, archive):
        self.__download_archive('job', 'jobs/api/download-files/' + self.job_id,
                                {'job format': job_format},
                                archive)

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
        resp = self.__request('service/get_tasks_statuses/', data={'tasks': json.dumps(task_ids)})
        statuses = resp.json()['tasks statuses']
        return json.loads(statuses)

    def get_task_error(self, task_id):
        resp = self.__request('service/download_solution/', data={'task id': task_id})
        return resp.json()['task error']

    def download_decision(self, task_id):
        self.__download_archive('decision', 'service/download_solution/', {'task id': task_id},
                                'decision result files.zip')

    def remove_task(self, task_id):
        self.__request('service/remove_task/', data={'task id': task_id})

    def sign_out(self):
        self.logger.info('Finish session')

    def upload_reports_and_report_file_archives(self, reports_and_report_file_archives):
        batch_reports = []
        batch_report_file_archives = []
        for report_and_report_file_archives in reports_and_report_file_archives:
            with open(report_and_report_file_archives['report file'], encoding='utf8') as fp:
                batch_reports.append(json.load(fp))

            report_file_archives = report_and_report_file_archives.get('report file archives')
            if report_file_archives:
                batch_report_file_archives.extend(report_file_archives)

        # TODO: report is likely should be compressed.
        self.__upload_archive('reports/api/upload/{0}/'.format(self.job_id),
                              {'reports': json.dumps(batch_reports)},
                              batch_report_file_archives)

        # We can safely remove task and its files after uploading report referencing task files.
        for report in batch_reports:
            if 'task identifier' in report:
                self.remove_task(report['task identifier'])

    def submit_progress(self, progress):
        self.logger.info('Submit solution progress')
        self.__request('service/progress/{0}/'.format(self.job_id), 'PATCH', data=progress)

    def __download_archive(self, kind, path_url, data, archive):
        while True:
            resp = None
            try:
                resp = self.__request(path_url, 'GET', data=data, stream=True)

                self.logger.debug('Write {0} archive to "{1}"'.format(kind, archive))
                with open(archive, 'wb') as fp:
                    for chunk in resp.iter_content(1024):
                        fp.write(chunk)

                if not zipfile.is_zipfile(archive) or zipfile.ZipFile(archive).testzip():
                    self.logger.warning('Could not download ZIP archive')
                else:
                    break
            finally:
                if resp:
                    resp.close()

    def __upload_archive(self, path_url, data, archives):
        while True:
            resp = None
            try:
                resp = self.__request(path_url, 'POST', data=data, files=[('file', open(archive, 'rb', buffering=0))
                                                                          for archive in archives], stream=True)
                return resp
            except BridgeError:
                if self.error == 'ZIP error':
                    self.logger.exception('Could not upload ZIP archive')
                    self.error = None
                    time.sleep(0.2)
                else:
                    raise
            finally:
                if resp:
                    resp.close()
