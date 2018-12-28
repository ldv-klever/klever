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

import requests
import time
import zipfile
import re


class UnexpectedStatusCode(IOError):
    pass


class BridgeError(IOError):
    pass


class Session:

    CANCELLED_STATUS = re.compile('The task \d+ was not found')

    def __init__(self, logger, name, user, password):
        """
        Create http session between scheduler and Klever Bridge server.

        :param name: Server address.
        :param user: User name.
        :param password: Password.
        :return:
        """
        logger.info('Create session for user "{0}" at Klever Bridge "{1}"'.format(user, name))
        self.logger = logger
        self.name = name

        # Sign in.
        self.__signin(user, password)

    def __signin(self, user, password):
        self.session = requests.Session()
        resp = self.__request('service/signin/', 'POST', data={'username': user, 'password': password})
        self.session.headers.update({'Authorization': 'Token {}'.format(resp.json()['token'])})
        self.logger.debug('Session was created')

    def __request(self, path_url, method, looping=True, **kwargs):
        """
        Make request in terms of the active session.

        :param path_url: Address suffix to append.
        :param method: POST or GET.
        :param kwargs: Additional arguments.
        :return:
        """

        kwargs.setdefault('allow_redirects', True)

        while True:
            try:
                url = 'http://' + self.name + '/' + path_url

                self.logger.debug('Send "{0}" request to "{1}"'.format(method, url))
                resp = self.session.request(method, url, **kwargs)

                # 2xx - Success; 1xx(info) and 3xx(redirection) status codes aren't used in Bridge API
                if resp.status_code < 400:
                    return resp

                # 4xx or 5xx status code
                if resp.headers['content-type'] == 'application/json':
                    # TODO: Expected behavior; reps.json() contains an error
                    self.error = resp.text
                    resp.close()
                    raise BridgeError('Got error "{0}" when send "{1}" request to "{2}"'
                                      .format(self.error, method, url))

                with open('response error.html', 'w', encoding='utf8') as fp:
                    fp.write(resp.text)
                status_code = resp.status_code
                resp.close()
                raise UnexpectedStatusCode('Got unexpected status code "{0}" when send "{1}" request to "{2}"'
                                           .format(status_code, method, url))
            except requests.ConnectionError as err:
                self.logger.info('Could not send "{0}" request to "{1}"'.format(method, err.request.url))
                if looping:
                    time.sleep(0.2)
                else:
                    self.logger.warning('Aborting request to Bridge')
                    return None

    def get_archive(self, endpoint, data, archive):
        """
        Download ZIP archive from server.

        :param endpoint: URL endpoint.
        :param data: Data to push in case of POST request.
        :param archive: Path to save the archive.
        :return: True
        """
        ret = True
        while True:
            resp = None
            try:
                resp = self.__request(endpoint, 'POST', data=data, stream=True)

                self.logger.debug('Write archive to {}'.format(archive))
                with open(archive, 'wb') as fp:
                    for chunk in resp.iter_content(1024):
                        fp.write(chunk)

                if not zipfile.is_zipfile(archive) or zipfile.ZipFile(archive).testzip():
                    self.logger.debug('Could not download ZIP archive')
                else:
                    break
            except BridgeError:
                if self.CANCELLED_STATUS.match(self.error):
                    self.logger.warning("Seems that the job was cancelled and we cannot download data to start the task")
                    ret = False
                    break
                else:
                    raise
            finally:
                if resp:
                    resp.close()

        return ret

    def push_archive(self, endpoint, data, archive):
        """
        Apload an arcive to server.

        :param endpoint: URL endpoint.
        :param data: Data to push in case of POST request.
        :param archive: Path to save the archive.
        :return: None.
        """
        ret = True

        while True:
            resp = None
            try:
                resp = self.__request(endpoint, 'POST', data=data, files={'file': open(archive, 'rb', buffering=0)},
                                      stream=True)
                break
            except BridgeError:
                if self.error == 'ZIP error':
                    self.logger.debug('Could not upload ZIP archive')
                    self.error = None
                    time.sleep(0.2)
                elif self.CANCELLED_STATUS.match(self.error):
                    self.logger.warning("Seems that the job was cancelled and we cannot upload results")
                    ret = False
                    break
                else:
                    raise
            finally:
                if resp:
                    resp.close()

        return ret

    def json_exchange(self, endpoint, data, looping=True):
        """
        Exchange with JSON the

        :param endpoint: URL endpoint.
        :param data: Data.
        :param looping: Do the request until it finishes successfully.
        :return: JSON string response from the server.
        """
        response = self.__request(endpoint, 'POST', looping=looping, json=data)

        if response:
            return response.json()
        else:
            return None

    def sign_out(self):
        """
        Stop current session.

        :return: Nothing
        """
        self.logger.info('Finish session at {}'.format(self.name))

