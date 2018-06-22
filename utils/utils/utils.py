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

import argparse
import getpass
import re
import requests
import sys
import zipfile

PROMPT = 'Password: '


class UnexpectedStatusCode(IOError):
    pass


class BridgeError(IOError):
    pass


def get_password(password):
    if password is not None and len(password) > 0:
        return password
    if sys.stdin.isatty():
        return getpass.getpass(PROMPT)
    else:
        print(PROMPT, end='', flush=True)
        return sys.stdin.readline().rstrip()


def get_args_parser(desc):
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument('--host', required=True, help='Server host')
    parser.add_argument('--username', required=True, help='Your username')
    parser.add_argument('--password', help='Your password')
    return parser


class Session:
    def __init__(self, args):
        self._args = args
        self._host = self.__check_host(args.host)

        if args.username is None:
            raise ValueError("Username wasn't got")
        self._username = args.username

        self._password = get_password(args.password)
        if self._password is None:
            raise ValueError("Password wasn't got")

    def __enter__(self):
        self.session = requests.Session()
        # Get initial value of CSRF token via useless GET request
        self.__request('/users/service_signin/')

        # Sign in
        self.__request('/users/service_signin/', {'username': self._username, 'password': self._password})
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.__request('/users/service_signout/')

    def __check_host(self, host):
        self.__is_not_used()

        if not isinstance(host, str) or len(host) == 0:
            raise ValueError('Server host must be set')
        if not host.startswith('http://'):
            host = 'http://' + host
        if host.endswith('/'):
            host = host[:-1]
        return host

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

    def __get_job_id(self, job):
        if len(job) == 0:
            raise ValueError('The job identifier or its name is not set')
        resp = self.__request('/jobs/get_job_field/', {'job': job, 'field': 'id'})
        return resp.json()['id']

    def download_job(self, job, archive):
        return self.__download_archive('/jobs/ajax/downloadjob/{0}/'.format(self.__get_job_id(job)), None, archive)

    def upload_job(self, parent, archive):
        if len(parent) == 0:
            raise ValueError('The parent identifier or its name is not set')
        resp = self.__request('/jobs/get_job_field/', {'job': parent, 'field': 'identifier'})
        resp = self.__request(
            '/jobs/upload_jobs/{0}/'.format(resp.json()['identifier']), {},
            files=[('file', open(archive, 'rb', buffering=0))], stream=True
        )
        if resp.headers['content-type'] == 'application/json' and 'errors' in resp.json():
            error = resp.json()['errors'][0]
            resp.close()
            raise BridgeError('Got error "{0}" while uploading job'.format(error))

    def upload_reports(self, job, archive):
        self.__request(
            '/jobs/upload_reports/{0}/'.format(self.__get_job_id(job)), {},
            files=[('archive', open(archive, 'rb', buffering=0))], stream=True
        )

    def job_progress(self, job, filename):
        resp = self.__request('/jobs/get_job_progress_json/{0}/'.format(self.__get_job_id(job)))
        with open(filename, mode='w', encoding='utf8') as fp:
            fp.write(resp.json()['data'])

    def decision_results(self, job, filename):
        resp = self.__request('/jobs/decision_results_json/{0}/'.format(self.__get_job_id(job)))
        with open(filename, mode='w', encoding='utf8') as fp:
            fp.write(resp.json()['data'])

    def copy_job(self, job, name=None):
        if isinstance(name, str) and len(name) > 0:
            resp = self.__request('/jobs/save_job_copy/{0}/'.format(self.__get_job_id(job)), {'name': name})
        else:
            resp = self.__request('/jobs/save_job_copy/{0}/'.format(self.__get_job_id(job)), {})
        return resp.json()['identifier']

    def copy_job_version(self, job):
        self.__request('/jobs/copy_job_version/{0}/'.format(self.__get_job_id(job)), {})

    def replace_files(self, job, new_files):
        for f_name in new_files:
            with open(new_files[f_name], mode='rb', buffering=0) as fp:
                self.__request(
                    '/jobs/replace_job_file/{0}/'.format(self.__get_job_id(job)),
                    {'name': f_name}, files=[('file', fp)], stream=True
                )

    def start_job_decision(self, job, data_fp):
        job_id = self.__get_job_id(job)
        if data_fp:
            self.__request('/jobs/run_decision/{0}/'.format(job_id), {'mode': 'data', 'data': data_fp.read()})
        else:
            self.__request('/jobs/run_decision/{0}/'.format(job_id), {'mode': 'fast'})

    def download_all_marks(self, archive):
        return self.__download_archive('/marks/download-all/', None, archive)

    def __is_not_used(self):
        pass
