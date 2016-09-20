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


class Session:
    def __init__(self, logger, bridge, job_id):
        logger.info('Create session for user "{0}" at Klever Bridge "{1}"'.format(bridge['user'], bridge['name']))

        self.logger = logger
        self.name = bridge['name']
        self.session = requests.Session()

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
                    raise IOError(
                        'Got unexpected status code "{0}" when send "{1}" request to "{2}"'.format(resp.status_code,
                                                                                                   method, url))
                if resp.headers['content-type'] == 'application/json' and 'error' in resp.json():
                    raise IOError(
                        'Got error "{0}" when send "{1}" request to "{2}"'.format(resp.json()['error'], method, url))

                return resp
            except requests.ConnectionError:
                self.logger.warning('Could not send "{0}" request to "{1}"'.format(method, url))
                time.sleep(1)

    def start_job_decision(self, job, start_report_file):
        # TODO: report is likely should be compressed.
        with open(start_report_file, encoding='utf8') as fp:
            resp = self.__request('jobs/decide_job/', {
                'job format': job.FORMAT,
                'report': fp.read()
            }, stream=True)

        self.logger.debug('Write job archive to "{0}'.format(job.ARCHIVE))
        with open(job.ARCHIVE, 'wb') as fp:
            for chunk in resp.iter_content(1024):
                fp.write(chunk)

    def schedule_task(self, task_desc):
        resp = self.__request('service/schedule_task/',
                              {'description': json.dumps(task_desc, ensure_ascii=False, sort_keys=True, indent=4)},
                              files={'file': open('task files.tar.gz', 'rb')})
        return resp.json()['task id']

    def get_task_status(self, task_id):
        resp = self.__request('service/get_task_status/', {'task id': task_id})
        return resp.json()['task status']

    def get_task_error(self, task_id):
        resp = self.__request('service/download_solution/', {'task id': task_id})
        return resp.json()['task error']

    def download_decision(self, task_id):
        resp = self.__request('service/download_solution/', {'task id': task_id})

        with open('decision result files.tar.gz', 'wb') as fp:
            for chunk in resp.iter_content(1024):
                fp.write(chunk)

    def remove_task(self, task_id):
        self.__request('service/remove_task/', {'task id': task_id})

    def sign_out(self):
        self.logger.info('Finish session')
        self.__request('users/service_signout/')

    def upload_report(self, report, archive=None):
        # TODO: report is likely should be compressed.
        with open(report, encoding='utf8') as fp:
            if archive:
                self.__request('reports/upload/',
                               {'report': fp.read()},
                               files={'file': open(archive, 'rb')})
            else:
                self.__request('reports/upload/', {'report': fp.read()})
