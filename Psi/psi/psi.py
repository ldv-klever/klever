import argparse
import getpass
import json
import os
import resource
import shutil
import subprocess
import tarfile
import timeit
import psi.utils


class Psi:
    default_conf_file = 'psi-conf.json'
    job = {'format': 1}

    def __init__(self):
        self.conf = None
        self.is_solving_file = None
        self.is_solving_file_fp = None
        self.logger = None
        self.session = None

    def __del__(self):
        # Sign out from Omega.
        if self.session:
            self.session.sign_out()

        # Release working directory if it was occupied.
        if self.is_solving_file and self.is_solving_file_fp and not self.is_solving_file_fp.closed:
            os.remove(self.is_solving_file)

    def run(self):
        """
        Main Psi function.
        """
        # Remember approximate time of start to count wall time.
        start_time = timeit.default_timer()

        conf_file = self.get_conf_file()

        # Read configuration from file.
        with open(conf_file) as fp:
            self.conf = json.load(fp)

        self.prepare_work_dir()

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

        self.logger.debug('Support jobs of format "{0}"'.format(self.job['format']))

        # TODO: create cgroups.

        start_report_file = psi.utils.dump_report(self.logger, 'start',
                              {'type': 'start', 'id': 'psi', 'attrs': [{'psi version': self.get_version()}],
                               'comp': psi.utils.get_comp_desc(self.logger)})

        self.job.update({'id': self.conf['job']['id'], 'archive': 'job.tar.gz'})
        self.session = psi.utils.Session(self.logger, omega['user'], omega['passwd'], self.conf['Omega']['name'])
        self.session.decide_job(self.job, start_report_file)

        # TODO: create parallel process to send requests about successful operation to Omega.

        # TODO: create parallel process (1) to send requests with reports from reports message queue to Omega.

        with tarfile.open(self.job['archive']) as TarFile:
            TarFile.extractall('job')

        # TODO: create components configuration file.

        # TODO: get job class.

        # TODO: launch components.

        # TODO: remove cgroups.

        with open(conf_file) as conf_fp:
            with open('log') as log_fp:
                psi.utils.dump_report(self.logger, 'finish',
                                      {'type': 'finish', 'id': 'psi',
                                       'resources': self.count_consumed_resources(start_time), 'desc': conf_fp.read(),
                                       'log': log_fp.read()})

        pass

        # TODO: send request about successful decision of job to Omega.

        # TODO: send terminator to reports message queue

        # TODO: wait for completion of (1)

    def count_consumed_resources(self, start_time):
        """
        Count resources (wall time, CPU time and maximum memory size) consumed by Psi without its childred.
        Note that launching under PyCharm gives its maximum memory size.
        :return: resources.
        """
        self.logger.info('Count consumed resources')
        utime, stime, maxrss = resource.getrusage(resource.RUSAGE_SELF)[0:3]
        resources = {'wall time': round(100 * (timeit.default_timer() - start_time)),
                     'CPU time': round(100 * (utime + stime)),
                     'max mem size': 1000 * maxrss}
        self.logger.debug('Consumed resources are:')
        for res in sorted(resources):
            self.logger.debug('    {0} - {1}'.format(res, resources[res]))
        return resources

    # TODO: may be this function can be reused by other components.
    def get_conf_file(self):
        """
        Try to get configuration file from command-line options. If it is not specified, then use the default one.
        :return: a configuration file.
        """
        parser = argparse.ArgumentParser(description='Main script of Psi.')
        parser.add_argument('conf file', nargs='?', default=self.default_conf_file,
                            help='configuration file (default: {0})'.format(self.default_conf_file))
        return vars(parser.parse_args())['conf file']

    def get_passwd(self, name):
        """
        Get password for the specified name either from configuration or by using password prompt.
        :param name: a name of service for which password is required.
        :return: a password for the specified name.
        """
        self.logger.info('Get ' + name + ' password')
        passwd = getpass.getpass() if not self.conf[name]['passwd'] else self.conf[name]['passwd']
        return passwd

    def get_user(self, name):
        """
        Get user for the specified name either from configuration or by using OS user.
        :param name: a name of service for which user is required.
        :return: a user for the specified name.
        """
        self.logger.info('Get ' + name + ' user name')
        user = getpass.getuser() if not self.conf[name]['user'] else self.conf[name]['user']
        self.logger.debug(name + ' user name is "{}"'.format(user))
        return user

    def get_version(self):
        """
        Get version either as a tag in the Git repository of Psi or from the file created when installing Psi.
        :return: a version.
        """
        # Git repository directory may be located in parent directory of parent directory.
        git_repo_dir = os.path.join(os.path.dirname(__file__), '../../.git')
        if os.path.isdir(git_repo_dir):
            version = psi.utils.get_entity_val(self.logger, 'version',
                                               'git --git-dir {0} describe --always --abbrev=7 --dirty'.format(
                                                   git_repo_dir))
        else:
            # TODO: get version of installed Psi.
            version = ''

        return version

    def prepare_work_dir(self):
        """
        Clean up and create the working directory. Prevent simultaneous usage of the same working directory.
        """
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
        # TODO: uncomment line below after all.
        # self.is_solving_file_fp = open(self.is_solving_file, 'w')
