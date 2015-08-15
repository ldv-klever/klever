# TODO: try to use standard library instead since we don't need something very special.
import requests
import time


class Session:
    def __init__(self, logger, user, passwd, name):
        # Check arguments passed.
        if not isinstance(user, str):
            raise ValueError('User name should be a string')
        if len(user) == 0:
            raise ValueError('User name should not be empty')
        if not isinstance(passwd, str):
            raise ValueError('Password should be a string')
        if len(passwd) == 0:
            raise ValueError('Password should not be empty')
        if not isinstance(name, str):
            raise ValueError('Server name should be a string')
        if len(name) == 0:
            raise ValueError('Server name should not be empty')

        logger.info('Create session for user "{0}" on server "{1}"'.format(user, name))

        self.logger = logger
        self.user = user
        self.name = name
        self.session = requests.Session()

        # Get CSRF token via GET request.
        self.__request('users/psi_signin/')

        # Sign in.
        self.__request('users/psi_signin/', 'POST', {
            'username': user,
            'password': passwd,
        })
        logger.debug('Session was created')

    def __request(self, path_url, method='GET', data=None, **kwargs):
        while True:
            try:
                url = 'http://' + self.name + '/' + path_url

                self.logger.debug('Send "{0}" request to "{1}"'.format(method, url))

                if data:
                    data.update({'csrfmiddlewaretoken': self.session.cookies['csrftoken']})

                resp = self.session.get(url, **kwargs) if method == 'GET' else self.session.post(url, data, **kwargs)

                if resp.status_code != 200:
                    with open('response error.html', 'w') as fp:
                        fp.write(resp.text)
                    raise IOError(
                        'Got unexpected status code "{0}" when send "{1}" request to "{2}"'.format(resp.status_code,
                                                                                                   method, url))
                if resp.headers['content-type'] == 'application/json' and 'error' in resp.json():
                    raise IOError(
                        'Got error "{0}" when send "{1}" request to "{2}"'.format(resp.json()['error'], method, url))

                return resp
            except requests.ConnectionError as err:
                self.logger.warning('Could not send "{0}" request to "{1}"'.format(method, err.request.url))
                time.sleep(1)

    def decide_job(self, job, start_report_file):
        # Acquire download lock.
        resp = self.__request('jobs/downloadlock/')
        if 'status' not in resp.json() or 'hash_sum' not in resp.json():
            raise IOError('Could not get download lock at "{0}"'.format(resp.request.url))

        # TODO: report is likely should be compressed.
        with open(start_report_file) as fp:
            resp = self.__request('jobs/decide_job/', 'POST', {
                'job id': job.id,
                'job format': job.format,
                'report': fp.read(),
                'hash sum': resp.json()['hash_sum']
            }, stream=True)

        self.logger.debug('Write job archive to "{0}'.format(job.archive))
        with open(job.archive, 'wb') as fp:
            for chunk in resp.iter_content(1024):
                fp.write(chunk)

    def sign_out(self):
        self.logger.info('Finish session for user "{0}" on server "{1}"'.format(self.user, self.name))
        self.__request('users/psi_signout/')

    def upload_report(self, report_file):
        # TODO: report is likely should be compressed.
        with open(report_file) as fp:
            self.__request('reports/upload/', 'POST', {'report': fp.read()})
