import json
import requests
import time


class Session:
    def __init__(self, logger, omega, job_id):
        logger.info('Create session for user "{0}" at Omega "{1}"'.format(omega['user'], omega['name']))

        self.logger = logger
        self.name = omega['name']
        self.session = requests.Session()

        # TODO: try to autentificate like with httplib2.Http().add_credentials().
        # Get initial value of CSRF token via useless GET request.
        self.__request('users/service_signin/')

        # Sign in.
        self.__request('users/service_signin/', {
            'username': omega['user'],
            'password': omega['password'],
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
                    with open('response error.html', 'w') as fp:
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

    def decide_job(self, job, start_report_file):
        # TODO: report is likely should be compressed.
        with open(start_report_file) as fp:
            resp = self.__request('jobs/decide_job/', {
                'job format': job.format,
                'report': fp.read()
            }, stream=True)

        self.logger.debug('Write job archive to "{0}'.format(job.archive))
        with open(job.archive, 'wb') as fp:
            for chunk in resp.iter_content(1024):
                fp.write(chunk)

    def schedule_task(self, task_desc):
        resp = self.__request('service/schedule_task/',
                              {'description': json.dumps(task_desc)},
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

    def sign_out(self):
        self.logger.info('Finish session')
        self.__request('users/service_signout/')

    def upload_report(self, report):
        # TODO: report is likely should be compressed.
        self.__request('reports/upload/', {'report': report})
