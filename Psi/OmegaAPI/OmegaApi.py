import requests
import time


class JobSession(object):

    def __init__(self, username, password, omega=None):
        self.session = requests.Session()
        self.username = username
        self.password = password
        if omega:
            self.omega = omega
        else:
            self.omega = 'localhost:8998'
        self.omega = 'http://' + self.omega + '/'
        self.csrf = None
        self.status = True
        self.err_message = ''
        self.__sign_in()

    def __sign_in(self):
        self.session.get(self.omega + 'users/signin/')
        self.csrf = self.session.cookies.get('csrftoken', None)
        if self.csrf:
            login_data = {
                'username': self.username,
                'password': self.password,
                'csrfmiddlewaretoken': self.csrf,
            }
            self.session.post(self.omega + 'users/psi_signin/', login_data)
            if self.session.cookies.get('sessionid', None):
                self.status = True
                return
        self.status = False

    def set_status(self, identifier, status):
        url = self.omega + 'jobs/setstatus/'
        data = {
            'csrfmiddlewaretoken': self.session.cookies['csrftoken'],
            'status': status,
            'identifier': identifier
        }
        self.session.post(url, data)

    def sign_out(self):
        self.session.get(self.omega + 'users/psi_signout/')
        self.session = requests.Session()

    def download_file(self, identifier, destination):
        url = self.omega + 'jobs/psi_downloadjob/'
        hash_sum = self.__download_lock()
        if hash_sum:
            data = {
                'csrfmiddlewaretoken': self.session.cookies['csrftoken'],
                'hash_sum': hash_sum,
                'identifier': identifier
            }
            response = self.session.post(url, data, stream=True)
            if response.headers['content-type'] == 'application/x-tar-gz':
                with open(destination, 'wb') as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
                    f.close()
            elif response.headers['content-type'] == 'application/json':
                self.status = False
                print("ERROR: ", response.json()['status'])

    def __download_lock(self):
        url = self.omega + 'jobs/downloadlock/'
        status = False
        while not status:
            resp = self.session.get(url)
            if resp.status_code == 200:
                if resp.json()['status']:
                    if resp.json()['status']:
                        return resp.json()['hash_sum']
                time.sleep(1)
        return None
