import requests
import time


ERRORS = {
    404: 'Connection refused',
    500: 'Unknown error',
    300: 'Invalid arguments',
    301: 'Timeout',
    302: 'Incorrect status',
    303: 'No access to the verification job',
    304: 'Job with specified identifier was not found',
    305: 'Your session is expired',
    306: 'Account has been disabled',
    307: 'Incorrect username or password'
}


class JobSession(object):

    def __init__(self, username, password, omega='localhost:8998'):
        self.session = None
        self.username = username
        self.password = password
        self.omega_url = 'http://' + omega + '/'
        self.status = True
        self.err_message = ''
        self.err_code = 0
        self.sign_in()

    def sign_in(self):
        if len(self.username) == 0 or len(self.password) == 0:
            return self.__error(300)
        self.session = requests.Session()
        resp = self.session.get(self.omega_url + 'users/signin/')
        if resp.status_code != 200:
            return self.__error()
        if self.session.cookies.get('csrftoken', None):
            url = self.omega_url + 'users/psi_signin/'
            data = {
                'csrfmiddlewaretoken': self.session.cookies['csrftoken'],
                'username': self.username,
                'password': self.password,
            }
            resp = self.session.post(url, data)
            if resp.status_code != 200:
                return self.__error(404)
            if self.session.cookies.get('sessionid', None):
                return
            if resp.json()['error'] > 0:
                return self.__error(resp.json()['error'])
        return self.__error()

    def sign_out(self):
        resp = self.session.get(self.omega_url + 'users/psi_signout/')
        if resp.status_code !=200:
            return self.__error(404)
        if resp.json()['error'] > 0:
            return self.__error(resp.json()['error'])
        self.session = requests.Session()

    def set_status(self, identifier, status):
        url = self.omega_url + 'jobs/setstatus/'
        data = {
            'csrfmiddlewaretoken': self.session.cookies['csrftoken'],
            'status': status,
            'identifier': identifier
        }
        resp = self.session.post(url, data)
        if resp.status_code == 200:
            if resp.json()['error'] > 0:
                return self.__error(resp.json()['error'])
        else:
            return self.__error(404)

    def download_file(self, id, destination, timelimit=60, supported_format=1):
        url = self.omega_url + 'jobs/psi_downloadjob/'
        hash_sum = self.__download_lock(timelimit)
        if hash_sum:
            data = {
                'csrfmiddlewaretoken': self.session.cookies['csrftoken'],
                'hash_sum': hash_sum,
                'identifier': id,
                'supported_format': supported_format
            }
            resp = self.session.post(url, data, stream=True)
            if resp.headers['content-type'] == 'application/x-tar-gz':
                with open(destination, 'wb') as f:
                    for chunk in resp.iter_content(1024):
                        f.write(chunk)
                    f.close()
                    return
            elif resp.headers['content-type'] == 'application/json':
                if resp.json()['error'] > 0:
                    return self.__error(resp.json()['error'])
            return self.__error()

    def __download_lock(self, timelimit):
        url = self.omega_url + 'jobs/downloadlock/'
        for i in range(0, timelimit):
            resp = self.session.get(url)
            if resp.status_code == 200:
                if resp.json()['status'] and len(resp.json()['hash_sum']) > 0:
                    return resp.json()['hash_sum']
            time.sleep(1)
        return self.__error(301)

    def __error(self, code=500):
        self.status = False
        if code not in ERRORS:
            code = 500
        self.err_code = code
        self.err_message = ERRORS[code]
