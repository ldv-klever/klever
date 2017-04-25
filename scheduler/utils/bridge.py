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

import logging
import requests
import time


class Session:
    def __init__(self, name, user, password, parameters=dict()):
        """
        Create http session between scheduler and Klever Bridge server.

        :param name: Server address.
        :param user: User name.
        :param password: Password.
        :param parameters: Dictionary with parameters to add alongside with user name and password..
        :return:
        """
        logging.info('Create session for user "{0}" at Klever Bridge "{1}"'.format(user, name))

        self.name = name
        self.session = requests.Session()

        # Get CSRF token via GET request.
        self.__request('users/service_signin/')

        # Prepare data
        parameters["username"] = user
        parameters["password"] = password

        # Sign in.
        # TODO: Replace with proper signin
        self.__request('users/service_signin/', 'POST', parameters)
        logging.debug('Session was created')

    def __request(self, path_url, method='GET', data=None, **kwargs):
        """
        Make request in terms of the active session.

        :param path_url: Address suffix to append.
        :param method: POST or GET.
        :param data: Data to push in case of POST request.
        :param kwargs: Additional arguments.
        :return:
        """
        if data:
            data.update({'csrfmiddlewaretoken': self.session.cookies['csrftoken']})

        while True:
            try:
                url = 'http://' + self.name + '/' + path_url

                logging.debug('Send "{0}" request to "{1}"'.format(method, url))

                if method == 'GET':
                    resp = self.session.get(url, **kwargs)
                else:
                    resp = self.session.post(url, data, **kwargs)

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
            except requests.ConnectionError as err:
                logging.warning('Could not send "{0}" request to "{1}"'.format(method, err.request.url))
                time.sleep(1)

    def get_archive(self, endpoint, data, archive):
        resp = self.__request(endpoint, 'POST', data, stream=True)

        logging.debug('Write an archive to {}'.format(archive))
        with open(archive, 'wb') as fp:
            for chunk in resp.iter_content(1024):
                fp.write(chunk)

    def push_archive(self, endpoint, data, archive):
        self.__request(endpoint, 'POST', data, files={'file': open(archive, 'rb')})

    def json_exchange(self, endpoint, json_data):
        response = self.__request(endpoint, 'POST', json_data)

        return response.json()

    def sign_out(self):
        """
        Sign out and stop current session.

        :return: Nothing
        """
        logging.info('Finish session at {}'.format(self.name))
        self.__request('users/service_signout/')

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
