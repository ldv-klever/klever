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

import re
import requests
import zipfile


class UnexpectedStatusCode(IOError):
    pass


class BridgeError(IOError):
    pass


class Session:
    def __init__(self, host, username, password):
        self._host = self.__check_host(host)

        if username is None:
            raise ValueError("Username wasn't got")

        if password is None:
            raise ValueError("Password wasn't got")

        self._parameters = {'username': username, 'password': password}
        self.__signin()

    def __check_host(self, host):
        self.__is_not_used()

        if not isinstance(host, str) or len(host) == 0:
            raise ValueError('Server host must be set')
        if not host.startswith('http://'):
            host = 'http://' + host
        if host.endswith('/'):
            host = host[:-1]
        return host

    def __signin(self):
        self.session = requests.Session()
        # Get initial value of CSRF token via useless GET request
        self.__request('/users/service_signin/')

        # Sign in
        self.__request('/users/service_signin/', self._parameters)

    def __request(self, path_url, data=None, **kwargs):
        url = self._host + path_url
        method = 'POST' if data else 'GET'

        if data is None:
            resp = self.session.get(url, **kwargs)
        else:
            data.update({'csrfmiddlewaretoken': self.session.cookies['csrftoken']})
            resp = self.session.post(url, data, **kwargs)

        if resp.status_code != 200:
            # with open('response error.html', 'w', encoding='utf8') as fp:
            #     fp.write(resp.text)
            status_code = resp.status_code
            resp.close()
            raise UnexpectedStatusCode(
                'Got unexpected status code "{0}" when send "{1}" request to "{2}"'.format(status_code, method, url)
            )
        if resp.headers['content-type'] == 'application/json' and 'error' in resp.json():
            error = resp.json()['error']
            resp.close()
            raise BridgeError('Got error "{0}" when send "{1}" request to "{2}"'.format(error, method, url))
        else:
            return resp

    def __download_archive(self, path_url, data, archive):
        resp = self.__request(path_url, data, stream=True)

        if archive is None:
            # Get filename from content disposition
            fname = re.findall('filename=(.+)', resp.headers.get('content-disposition'))
            if len(fname) == 0:
                archive = 'archive.zip'
            else:
                archive = fname[0]
                if archive.startswith('"') or archive.startswith("'"):
                    archive = archive[1:-1]

        with open(archive, 'wb') as fp:
            for chunk in resp.iter_content(1024):
                fp.write(chunk)

        if not zipfile.is_zipfile(archive) or zipfile.ZipFile(archive).testzip():
            raise BridgeError('Could not download ZIP archive to {0}'.format(archive))

        resp.close()
        return archive

    def download_job(self, identifier, archive):
        if len(identifier) == 0:
            raise ValueError('The job identifier is not set')
        resp = self.__request('/jobs/ajax/get_job_id/', {'identifier': identifier})
        return self.__download_archive('/jobs/ajax/downloadjob/{0}/'.format(resp.json()['id']), None, archive)

    def upload_job(self, parent_id, archive):
        if len(parent_id) == 0:
            raise ValueError('The parent identifier is not set')
        self.__request(
            '/jobs/ajax/upload_job/{0}/'.format(parent_id), {},
            files=[('file', open(archive, 'rb', buffering=0))], stream=True
        )

    def job_progress(self, identifier, filename):
        resp = self.__request('/jobs/ajax/get_job_progress_json/', {'identifier': identifier})
        with open(filename, mode='w', encoding='utf8') as fp:
            fp.write(resp.json()['data'])

    def decision_results(self, identifier, filename):
        resp = self.__request('/jobs/ajax/get_job_decision_results/', {'identifier': identifier})
        with open(filename, mode='w', encoding='utf8') as fp:
            fp.write(resp.json()['data'])

    def copy_job(self, identifier):
        resp = self.__request('/jobs/ajax/save_job_copy/', {'identifier': identifier})
        return resp.json()['identifier']

    def copy_job_version(self, identifier):
        self.__request('/jobs/ajax/copy_job_version/', {'identifier': identifier})

    def replace_files(self, identifier, new_files):
        for f_name in new_files:
            with open(new_files[f_name], mode='rb', buffering=0) as fp:
                self.__request(
                    '/jobs/ajax/replace_job_file/', {'identifier': identifier, 'name': f_name},
                    files=[('file', fp)], stream=True
                )

    def start_job_decision(self, identifier, data_fp):
        resp = self.__request('/jobs/ajax/get_job_id/', {'identifier': identifier})
        if data_fp:
            self.__request('/jobs/ajax/run_decision/', {'job_id': resp.json()['id'], 'data': data_fp.read()})
        else:
            self.__request('/jobs/ajax/fast_run_decision/', {'job_id': resp.json()['id']})

    def sign_out(self):
        self.__request('/users/service_signout/')

    def __is_not_used(self):
        pass
