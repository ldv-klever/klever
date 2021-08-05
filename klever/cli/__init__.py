# Copyright (c) 2021 ISP RAS (http://www.ispras.ru)
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

import json
import logging
import os
import re
# TODO: this is non-standard dependency while it is not required for all users. So, let's create a separate library!
import requests
import zipfile

from klever.cli.utils import get_password


class BridgeError(IOError):
    pass


class UnexpectedStatusCode(IOError):
    pass


class RequestFilesProcessor:
    def __init__(self):
        self._cnt = 0
        self._files_map = {}
        self._files = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for fp in self._files.values():
            fp.close()

    def add_file(self, file_name, file_path):
        file_key = 'file{}'.format(self._cnt)
        self._files_map[file_name] = file_key
        self._files[file_key] = open(file_path, mode='rb', buffering=0)
        self._cnt += 1

    def get_files(self):
        return list(self._files.items())

    def get_map(self):
        return json.dumps(self._files_map)


class Cli:
    def __init__(self, host, username, password):
        self.host = self.__get_host(host)

        if username is None:
            raise ValueError("Username wasn't got")
        self.username = username

        self.password = get_password(password)
        if self.password is None:
            raise ValueError("Password wasn't got")

        self.__signin()

    def __signin(self):
        self.session = requests.Session()
        resp = self.__request('service/get_token/', 'POST', data={
            'username': self.username,
            'password': self.password
        })
        self.session.headers.update({'Authorization': 'Token {}'.format(resp.json()['token'])})

    def __get_host(self, host):
        if not isinstance(host, str) or len(host) == 0:
            raise ValueError('Server host must be set')
        if not host.startswith('http://'):
            host = 'http://' + host
        if host.endswith('/'):
            host = host[:-1]
        return host

    def __request(self, path_url, method='GET', **kwargs):
        url = self.host + '/' + path_url
        resp = self.session.request(method, url, **kwargs)

        if resp.status_code not in (200, 201, 204):
            if resp.headers['content-type'] == 'application/json':
                raise BridgeError('Got error "{0}" when send "{1}" request to "{2}"'
                                  .format(resp.json(), method, url))
            with open('response error.html', 'w', encoding='utf-8') as fp:
                fp.write(resp.text)
            status_code = resp.status_code
            if resp.headers['content-type'] == 'application/json':
                error_str = str(resp.json())
            else:
                error_str = resp.content
            resp.close()
            raise UnexpectedStatusCode('Got unexpected status code "{0}" when send "{1}" request to "{2}": {3}'
                                       .format(status_code, method, url, error_str))
        return resp

    def __download_archive(self, path_url, archive):
        resp = self.__request(path_url, stream=True)

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

    def __parse_replacement(self, replacement):
        if os.path.exists(replacement):
            with open(replacement, mode='r', encoding='utf-8') as fp:
                try:
                    new_files = json.load(fp)
                except Exception as e:
                    logging.exception(e)
                    raise ValueError("Wrong json file with replacement was provided: {}".format(replacement))
        else:
            try:
                new_files = json.loads(replacement)
            except Exception as e:
                logging.exception(e)
                raise ValueError("Wrong json data with replacement was provided: {}".format(replacement))
        if not isinstance(new_files, dict):
            raise ValueError('Json with replacement data should be a dictionary')
        return new_files

    def download_job(self, job_uuid, archive):
        """
        Download job archive.
        :param job_uuid: job identifier
        :param archive: path where to save the archive.
        :return: path where the archive is saved.
        """
        return self.__download_archive('jobs/api/downloadjob/{0}/'.format(job_uuid), archive)

    def upload_job(self, archive):
        """
        Upload job archive.
        :param archive: path to archive
        :return: None
        """
        self.__request(
            'jobs/api/upload_jobs/', 'POST', files=[('file', open(archive, 'rb', buffering=0))], stream=True
        )

    def decision_progress(self, identifier, filename):
        """
        Save decision progress to json file.
        :param identifier: decision identifier (uuid).
        :param filename: path where to save the file.
        :return: None
        """
        resp = self.__request('service/progress/{}/'.format(identifier))
        with open(filename, mode='w', encoding='utf-8') as fp:
            json.dump(resp.json(), fp, ensure_ascii=False, sort_keys=True, indent=4)

    def decision_results(self, identifier, filename):
        """
        Save job decision results to json file.
        :param identifier: decision identifier (uuid).
        :param filename: path where to save the file.
        :return: None
        """
        resp = self.__request('jobs/api/decision-results/{0}/'.format(identifier))
        with open(filename, mode='w', encoding='utf-8') as fp:
            json.dump(resp.json(), fp, ensure_ascii=False, sort_keys=True, indent=4)

    def create_job(self, preset_uuid):
        """
        Create new job on the base of preset files.
        :param preset_uuid: preset job uuid.
        :return: job primary key and identifier
        """
        resp = self.__request('jobs/api/create-default-job/{0}/'.format(preset_uuid), method='POST')
        resp_json = resp.json()
        return resp_json['id'], resp_json['identifier']

    def start_job_decision(self, job_uuid, rundata=None, replacement=None):
        """
        Start job decision.
        :param job_uuid: job identifier.
        :param rundata: path to configuration file, optional (provide None).
        :param replacement: path to json with replacement info or json string with it, optional (provide None).
        :return: decision primary key and identifier
        """
        with RequestFilesProcessor() as rfp:
            request_kwargs = {'method': 'POST'}

            if rundata:
                request_kwargs['stream'] = True
                request_kwargs['files'] = [('file_conf', open(rundata))]

            if replacement:
                new_files = self.__parse_replacement(replacement)
                for f_name, f_path in new_files.items():
                    rfp.add_file(f_name, f_path)
                request_kwargs.setdefault('files', [])
                request_kwargs['files'].extend(rfp.get_files())
                request_kwargs['data'] = {'files': rfp.get_map()}

            resp = self.__request('jobs/api/decide-uuid/{}/'.format(job_uuid), **request_kwargs)

        try:
            resp_json = resp.json()
        except Exception as e:
            logging.exception(
                "Can't parse json response of starting decision request (code {}): {}".format(resp.status_code, e)
            )
            raise BridgeError("Decision wasn't started")
        return resp_json['id'], resp_json['identifier']

    def download_all_marks(self, archive):
        """
        Download all marks.
        :param archive: path to an archive where to save all marks
        :return: path to saved archive.
        """
        return self.__download_archive('marks/api/download-all/', archive)

    def get_updated_preset_mark(self, identifier, report_id):
        url = "marks/api/get-updated-preset/{}/".format(identifier)
        params = {'report': report_id} if report_id else None
        resp = self.__request(url, params=params)
        return resp.json()
