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


class UnexpectedStatusCode(IOError):
    pass


class BridgeError(IOError):
    pass


class Session:

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
        resp = self.__request('service/get_token/', 'POST', data={'username': user, 'password': password})
        self.session.headers.update({
            'Authorization': 'Token {}'.format(resp.json()['token']),
            'Accept-Language': 'en'
        })
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
        if looping:
            attempts = 20
        else:
            attempts = 3

        while attempts:
            attempts -= 1
            try:
                url = 'http://' + self.name + '/' + path_url

                self.logger.debug('Send "{0}" request to "{1}"'.format(method, url))
                resp = self.session.request(method, url, **kwargs)

                # 2xx - Success; 1xx(info) and 3xx(redirection) status codes aren't used in Bridge API
                if resp.status_code < 400:
                    return resp

                # 4xx or 5xx status code
                if resp.headers['content-type'] == 'application/json':
                    self.error = resp.json()
                    resp.close()
                    raise BridgeError('Got error {!r} when send {!r} request to {!r}'.
                                      format(str(self.error), method, url))

                with open('response error.html', 'w', encoding='utf-8') as fp:
                    fp.write(resp.text)
                status_code = resp.status_code
                resp.close()
                raise UnexpectedStatusCode('Got unexpected status code "{0}" when send "{1}" request to "{2}"'
                                           .format(status_code, method, url))
            except requests.ConnectionError as err:
                self.logger.info('Could not send "{0}" request to "{1}"'.format(method, err.request.url))
                if attempts:
                    time.sleep(0.2)
                else:
                    self.logger.warning('Aborting request to Bridge')
                    return None

    def get_archive(self, endpoint, archive=None):
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
                resp = self.__request(endpoint, 'GET', stream=True)

                self.logger.debug('Write archive to {}'.format(archive))
                with open(archive, 'wb') as fp:
                    for chunk in resp.iter_content(1024):
                        fp.write(chunk)

                if not zipfile.is_zipfile(archive) or zipfile.ZipFile(archive).testzip():
                    self.logger.debug('Could not download ZIP archive')
                else:
                    break
            except BridgeError:
                raise
            finally:
                if resp:
                    resp.close()

        return ret

    def push_archive(self, endpoint, data, archive):
        """
        Upload an archive to server.

        :param endpoint: URL endpoint.
        :param data: Data to push in case of POST request.
        :param archive: Path to save the archive.
        :return: None.
        """
        self.__request(endpoint, 'POST', data=data, files={'archive': open(archive, 'rb')}, stream=True)

    def exchange(self, endpoint, data=None, method='POST', looping=True):
        """
        Exchange with JSON the

        :param endpoint: URL endpoint.
        :param data: Data.
        :param method: HTTP method.
        :param looping: Do the request until it finishes successfully.
        :return: JSON string response from the server.
        """
        self.__request(endpoint, method, looping=looping, json=data)

    def json_exchange(self, endpoint, data=None, method='POST', looping=True):
        """
        Exchange with JSON the

        :param endpoint: URL endpoint.
        :param data: Data.
        :param method: HTTP method.
        :param looping: Do the request until it finishes successfully.
        :return: JSON string response from the server.
        """
        response = self.__request(endpoint, method, looping=looping, json=data)

        if response:
            return response.json()
        else:
            return None
