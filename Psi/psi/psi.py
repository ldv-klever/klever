import argparse
import getpass
import json
import os
import resource
import shutil
import subprocess
import timeit
import psi.utils


class Psi:
    default_conf_file = 'psi-conf.json'
    job_format = '1'

    def __init__(self):
        self.conf = None
        self.is_solving_file = None
        self.is_solving_file_fp = None
        self.logger = None

    def __del__(self):
        # Release working directory if it was occupied.
        if self.is_solving_file and self.is_solving_file_fp and not self.is_solving_file_fp.closed:
            os.remove(self.is_solving_file)

    def run(self):
        # Remember approximate time of start.
        start = timeit.default_timer()

        # Get configuration file from command-line options.
        parser = argparse.ArgumentParser(description='Main script of Psi.')
        parser.add_argument('conf file', nargs='?', default=self.default_conf_file,
                            help='configuration file (default: {0})'.format(self.default_conf_file))
        conf_file = vars(parser.parse_args())['conf file']

        # Decode configuration file.
        with open(conf_file) as fp:
            self.conf = json.load(fp)

        # Test whether another Psi occupies the same working directory.
        self.is_solving_file = os.path.join(self.conf['work dir'], 'is solving')
        if os.path.isfile(self.is_solving_file):
            raise FileExistsError('Another Psi occupies working directory "{0}"'.format(self.conf['work dir']))

        # Remove (if exists) and create (if doesn't exist) working directory.
        # Note, that shutil.rmtree() doesn't allow to ignore files as required by specification. So, we have to:
        # - remove the whole working directory (if exists),
        # - create working directory (pass if it is created by another Psi),
        # - test one more time whether another Psi occupies the same working directory,
        # - occupy working directory.
        shutil.rmtree(self.conf['work dir'], True)
        os.makedirs(self.conf['work dir'], exist_ok=True)

        if os.path.isfile(self.is_solving_file):
            raise FileExistsError('Another Psi occupies working directory "{0}"'.format(self.conf['work dir']))

        # Occupy working directory until the end of operation.
        # Yes there may be race condition, but it won't be.
        self.is_solving_file_fp = open(self.is_solving_file, 'w')

        # Remember path to configuration file relative to working directory before changing directory.
        conf_file = os.path.relpath(conf_file, self.conf['work dir'])

        # Move to working directory until the end of operation.
        # We can use path for "is solving" file relative to working directory since exceptions aren't raised when we
        # have relative path but don't change directory yet.
        self.is_solving_file = os.path.relpath(self.is_solving_file, self.conf['work dir'])
        os.chdir(self.conf['work dir'])

        self.logger = psi.utils.get_logger(os.path.basename(__file__), self.conf['logging'])

        # Configuration for Omega.
        omega = {}
        # Configuration for Verification Task Scheduler.
        verification_task_scheduler = {}

        omega['user'] = self.get_user('Omega')
        verification_task_scheduler['user'] = self.get_user('Verification Task Scheduler')

        omega['passwd'] = self.get_passwd('Omega')
        verification_task_scheduler['passwd'] = self.get_passwd('Verification Task Scheduler')

        self.logger.info('Get version')
        # Git repository directory may be located in parent directory of parent directory.
        git_repo_dir = os.path.join(os.path.dirname(__file__), '../../.git')
        if os.path.isdir(git_repo_dir):
            proc = subprocess.Popen(['git', '--git-dir', git_repo_dir, 'describe', '--always', '--abbrev=7', '--dirty'],
                                    stdout=subprocess.PIPE)
            version = proc.stdout.readline().decode('utf-8').rstrip()
            if not version:
                raise ValueError('Could not get Git repository tag')
        else:
            # TODO: get version of installed Psi.
            version = ''
        self.logger.debug('Version is "{0}"'.format(version))

        self.logger.debug('Support jobs of format "{0}"'.format(self.job_format))

        # TODO: create cgroups.

        # TODO: get computer description.
        comp_desc = []

        self.logger.info('Dump start report')
        with open('start report.json', 'w') as fp:
            psi.utils.dump_report(
                {'type': 'start', 'id': 'psi', 'attrs': [{'psi version': version}], 'comp': comp_desc}, fp)
        self.logger.debug('Finish report was dumped to file "{0}"'.format('start report.json'))

        # TODO: get job from Omega.

        # TODO: create parallel process to send requests about successful operation to Omega.

        # TODO: create parallel process (1) to send requests with reports from reports message queue to Omega.

        # TODO: extract job archive to directory "job".

        # TODO: create components configuration file.

        # TODO: get job class.

        # TODO: launch components.

        # TODO: remove cgroups.

        # Note that launching in PyCharm gives its maximum memory size.
        self.logger.info('Count consumed resources')
        utime, stime, maxrss = resource.getrusage(resource.RUSAGE_SELF)[0:3]
        resources = {'wall time': round(100 * (timeit.default_timer() - start)),
                     'CPU time': round(100 * (utime + stime)),
                     'max mem size': 1000 * maxrss}
        self.logger.debug('Consumed resources are:')
        for res in sorted(resources):
            self.logger.debug('    {0} - {1}'.format(res, resources[res]))

        self.logger.info('Dump finish report')
        with open('finish report.json', 'w') as finish_report_fp:
            with open(conf_file) as conf_fp:
                with open('log') as log_fp:
                    psi.utils.dump_report(
                        {'type': 'finish', 'id': 'psi', 'resources': resources, 'desc': conf_fp.read(),
                         'log': log_fp.read()},
                        finish_report_fp)
        self.logger.debug('Finish report was dumped to file "{0}"'.format('finish report.json'))

        # TODO: send request about successful decision of job to Omega.

        # TODO: send terminator to reports message queue

        # TODO: wait for completion of (1)

    def get_passwd(self, name):
        self.logger.info('Get ' + name + ' password')
        passwd = getpass.getpass() if not self.conf[name]['passwd'] else self.conf[name]['passwd']
        return passwd

    def get_user(self, name):
        self.logger.info('Get ' + name + ' user name')
        user = getpass.getuser() if not self.conf[name]['user'] else self.conf[name]['user']
        self.logger.debug(name + ' user name is "{}"'.format(user))
        return user
