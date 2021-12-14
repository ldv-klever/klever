#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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
import os
import requests
import time
import zipfile


class UnexpectedStatusCode(IOError):
    pass


class BridgeError(IOError):
    pass


# TODO: it would be better to name it BridgeRequests. This is the case for Scheduler and CLI.
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

    # TODO: It is not signing in anymore. It is getting token. This is the case for Scheduler and CLI.
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

                if resp.status_code not in (200, 201, 204):
                    if resp.headers['content-type'] == 'application/json':
                        self.error = resp.json()
                        raise BridgeError(
                            'Got error "{0}" when send "{1}" request to "{2}"'.format(self.error, method, url)
                        )
                    with open('response error.html', 'w', encoding='utf-8') as fp:
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
        with open(task_file, 'r', encoding='utf-8') as fp:
            data = fp.read()

        resp = self.__upload_archives('service/tasks/',
                                      {
                                          'job': str(self.job_id),
                                          'description': data
                                      },
                                      {'archive': archive})

        return resp['id']

    def check_original_sources(self, src_id):
        resp = self.__request('reports/api/has-sources/?identifier={0}'.format(src_id), method='GET')
        return resp.json()['exists']

    def get_tasks_statuses(self):
        resp = self.__request('service/tasks/?job={}&fields=status&fields=id'.format(self.job_id), method='GET')
        return resp.json()

    def get_task_error(self, task_id):
        resp = self.__request('service/tasks/{}/?fields=error'.format(task_id), method='GET')
        return resp.json()['error']

    def download_decision(self, task_id):
        self.__download_archive('decision', 'service/solution/{}/download/'.format(task_id),
                                archive='decision result files.zip')

    def remove_task(self, task_id):
        self.__request('service/tasks/{}/'.format(task_id), method='DELETE')

    def upload_original_sources(self, src_id, src_archive):
        self.__upload_archives('reports/api/upload-sources/',
                               {'identifier': src_id},
                               {'archive': src_archive})

    def upload_reports_and_report_file_archives(self, reports_and_report_file_archives):
        batch_reports = []
        batch_report_file_archives = []
        for report_and_report_file_archives in reports_and_report_file_archives:
            with open(report_and_report_file_archives['report file'], encoding='utf-8') as fp:
                batch_reports.append(json.load(fp))

            report_file_archives = report_and_report_file_archives.get('report file archives')
            if report_file_archives:
                batch_report_file_archives.extend(report_file_archives)

        # TODO: report is likely should be compressed.
        self.__upload_archives('reports/api/upload/{0}/'.format(self.job_id),
                               {
                                   'reports': json.dumps(batch_reports),
                                   'archives': json.dumps([os.path.basename(archive)
                                                           for archive in batch_report_file_archives])
                               },
                               {os.path.basename(archive): archive for archive in batch_report_file_archives})

        # We can safely remove task and its files after uploading report referencing task files.
        for report in batch_reports:
            if 'task identifier' in report:
                self.remove_task(report['task identifier'])

    def submit_progress(self, progress):
        self.logger.info('Submit solution progress')
        self.__request('service/progress/{0}/'.format(self.job_id), 'PATCH', data=progress)

    def __download_archive(self, kind, path_url, data=None, archive=None):
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

    def __upload_archives(self, path_url, data, archives):
        resp = self.__request(path_url, 'POST', data=data,
                              files={archive_name: open(archive_path, 'rb')
                                     for archive_name, archive_path in archives.items()},
                              stream=True)
        return resp.json()

    def create_image(self, component_id, title, dot_file, image_file):
        self.logger.info('Upload image "{0}"'.format(title))
        data = {
            'decision': self.job_id,
            'report': component_id,
            'title': title
        }
        self.logger.info('Upload image "{0}"'.format(data))
        with open(image_file, mode='rb') as image_fp:
            with open(dot_file, mode='rb') as dot_fp:
                self.__request('reports/api/component/images-create/'.format(), 'POST', data=data,
                               files=[('image', image_fp), ('data', dot_fp)])
