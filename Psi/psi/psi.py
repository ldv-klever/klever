import argparse
import getpass
import io
import json
import multiprocessing
import os
import re
import shutil
import time
import traceback

import psi.job
import psi.session
import psi.utils

# Psi components.
import psi.lkbce.lkbce
import psi.lkvog.lkvog
import psi.avtg.avtg
import psi.vtg.vtg
import psi.vtsc.vtsc


class Psi:
    def __init__(self):
        self.exit_code = 0
        self.start_time = 0
        self.default_conf_file = 'psi-conf.json'
        self.conf_file = None
        self.conf = {}
        self.is_solving_file = None
        self.is_solving_file_fp = None
        self.logger = None
        self.omega = {}
        self.version = None
        self.job = None
        self.comp = []
        self.id = '/'
        self.session = None
        self.mqs = {}
        self.uploading_reports_process = None
        self.job_class_components = {
            'Verification of Linux kernel modules': [psi.lkbce.lkbce.LKBCE, psi.lkvog.lkvog.LKVOG],
            # These components are likely appropriate for all job classes.
            'Common': [psi.avtg.avtg.AVTG, psi.vtg.vtg.VTG, psi.vtsc.vtsc.VTSC]}
        self.components = []
        self.components_conf = None
        self.callbacks = {}
        self.component_processes = []

    def main(self):
        """
        Main Psi function.
        """
        try:
            # Remember approximate time of start to count wall time.
            self.start_time = time.time()
            self.get_conf()
            self.prepare_work_dir()
            self.change_work_dir()
            self.logger = psi.utils.get_logger(self.__class__.__name__, self.conf['logging'])
            # Configuration for Omega.
            self.omega = {'name': self.conf['Omega']['name'], 'user': self.get_user('Omega'),
                          'passwd': self.get_passwd('Omega')}
            self.get_version()
            self.job = psi.job.Job(self.logger, self.conf['identifier'])
            self.get_comp_desc()
            start_report_file = psi.utils.report(self.logger,
                                                 'start',
                                                 {'id': self.id,
                                                  'attrs': [{'PSI version': self.version}],
                                                  'comp': [{attr[attr_shortcut]['name']: attr[attr_shortcut]['value']}
                                                           for attr in self.comp for attr_shortcut in attr]})
            self.session = psi.session.Session(self.logger, self.omega, self.job.id)
            self.session.decide_job(self.job, start_report_file)
            # TODO: create parallel process to send requests about successful operation to Omega.
            self.mqs['report files'] = multiprocessing.Queue()
            self.uploading_reports_process = multiprocessing.Process(target=self.send_reports)
            self.uploading_reports_process.start()
            self.job.extract_archive()
            self.job.get_class()
            self.get_components()
            # Do not read anything from job directory untill job class will be examined (it might be unsupported). This
            # differs from specification that doesn't treat unsupported job classes at all.
            self.create_components_conf()
            self.callbacks = psi.utils.get_component_callbacks(self.logger, self.components, self.components_conf)
            psi.utils.invoke_callbacks(self.launch_all_components)
            self.wait_for_components()
        except Exception:
            if self.mqs:
                with open('problem desc', 'w') as fp:
                    traceback.print_exc(file=fp)

                if os.path.isfile('problem desc'):
                    psi.utils.report(self.logger,
                                     'unknown',
                                     {'id': 'unknown',
                                      'parent id': self.id,
                                      'problem desc': '__file:problem desc'},
                                     self.mqs['report files'])

            if self.logger:
                self.logger.exception('Catch exception')
            else:
                traceback.print_exc()

            self.exit_code = 1
        finally:
            try:
                for p in self.component_processes:
                    # Do not terminate components that already exitted.
                    if p.is_alive():
                        p.stop()

                if self.mqs:
                    psi.utils.report(self.logger,
                                     'finish',
                                     {'id': self.id,
                                      'resources': psi.utils.count_consumed_resources(
                                          self.logger,
                                          self.start_time),
                                      'desc': '__file:{0}'.format(self.conf_file),
                                      'log': '__file:log',
                                      'data': ''},
                                     self.mqs['report files'])

                    self.logger.info('Terminate report files message queue')
                    self.mqs['report files'].put(None)

                    self.logger.info('Wait for uploading all reports')
                    self.uploading_reports_process.join()
                    # Do not override exit code of main program with the one of auxiliary process uploading reports.
                    if not self.exit_code:
                        self.exit_code = self.uploading_reports_process.exitcode

                if self.session:
                    self.session.sign_out()
            # At least release working directory if cleaning code above will raise some exception.
            finally:
                if self.is_solving_file_fp and not self.is_solving_file_fp.closed:
                    if self.logger:
                        self.logger.info('Release working directory')
                    os.remove(self.is_solving_file)

                if self.logger:
                    self.logger.info('Exit with code "{0}"'.format(self.exit_code))

                exit(self.exit_code)

    def get_conf(self):
        # Get configuration file from command-line options. If it is not specified, then use the default one.
        parser = argparse.ArgumentParser(description='Main script of Psi.')
        parser.add_argument('conf file', nargs='?', default=self.default_conf_file,
                            help='configuration file (default: {0})'.format(self.default_conf_file))
        self.conf_file = vars(parser.parse_args())['conf file']

        # Read configuration from file.
        with open(self.conf_file) as fp:
            self.conf = json.load(fp)

    def prepare_work_dir(self):
        """
        Clean up and create the working directory. Prevent simultaneous usage of the same working directory.
        """
        # This file exists during Psi occupies working directory.
        self.is_solving_file = os.path.join(self.conf['working directory'], 'is solving')

        def check_another_instance():
            if os.path.isfile(self.is_solving_file):
                raise FileExistsError(
                    'Another instance occupies working directory "{0}"'.format(self.conf['working directory']))

        check_another_instance()

        # Remove (if exists) and create (if doesn't exist) working directory.
        # Note, that shutil.rmtree() doesn't allow to ignore files as required by specification. So, we have to:
        # - remove the whole working directory (if exists),
        # - create working directory (pass if it is created by another Psi),
        # - test one more time whether another Psi occupies the same working directory,
        # - occupy working directory.
        shutil.rmtree(self.conf['working directory'], True)

        os.makedirs(self.conf['working directory'], exist_ok=True)

        check_another_instance()

        # Occupy working directory until the end of operation.
        # Yes there may be race condition, but it won't be.
        self.is_solving_file_fp = open(self.is_solving_file, 'w')

    def change_work_dir(self):
        # Remember path to configuration file relative to future working directory before changing to it.
        self.conf_file = os.path.relpath(self.conf_file, self.conf['working directory'])

        # Change working directory forever.
        # We can use path for "is solving" file relative to future working directory since exceptions aren't raised when
        # we have relative path but don't change working directory yet.
        self.is_solving_file = os.path.relpath(self.is_solving_file, self.conf['working directory'])
        os.chdir(self.conf['working directory'])

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

    def get_passwd(self, name):
        """
        Get password for the specified name either from configuration or by using password prompt.
        :param name: a name of service for which password is required.
        :return: a password for the specified name.
        """
        self.logger.info('Get ' + name + ' password')
        passwd = getpass.getpass() if not self.conf[name]['password'] else self.conf[name]['password']
        return passwd

    def get_version(self):
        """
        Get version either as a tag in the Git repository of Psi or from the file created when installing Psi.
        """
        # Git repository directory may be located in parent directory of parent directory.
        git_repo_dir = os.path.join(os.path.dirname(__file__), '../../.git')
        if os.path.isdir(git_repo_dir):
            self.version = psi.utils.get_entity_val(self.logger, 'version',
                                                    'git --git-dir {0} describe --always --abbrev=7 --dirty'.format(
                                                        git_repo_dir))
        else:
            # TODO: get version of installed Psi.
            self.version = ''

    def get_comp_desc(self):
        self.logger.info('Get computer description')

        self.comp = [
            {
                entity_name_cmd[0]: {
                    'name': entity_name_cmd[1] if entity_name_cmd[1] else entity_name_cmd[0],
                    'value': psi.utils.get_entity_val(self.logger,
                                                      entity_name_cmd[1]
                                                      if entity_name_cmd[1]
                                                      else entity_name_cmd[0],
                                                      entity_name_cmd[2])
                }
            }
            for entity_name_cmd in [
                ['node name', '', 'uname -n'],
                ['CPU model', '', 'cat /proc/cpuinfo | grep -m1 "model name" | sed -r "s/^.*: //"'],
                ['CPUs num', 'number of CPU cores', 'cat /proc/cpuinfo | grep processor | wc -l'],
                ['mem size', 'memory size',
                 'cat /proc/meminfo | grep "MemTotal" | sed -r "s/^.*: *([0-9]+).*/1024 * \\1/" | bc'],
                ['Linux kernel version', '', 'uname -r'],
                ['arch', 'architecture', 'uname -m']

            ]
            ]

    def send_reports(self):
        try:
            while True:
                report_file = self.mqs['report files'].get()

                if report_file is None:
                    self.logger.debug('Report files message queue was terminated')
                    # Note that this and all other closing of message queues aren't strictly necessary and everything
                    # will work without them as well, but this potentially can save some memory since closing explicitly
                    # notifies that corresponding message queue won't be used any more and its memory could be freed.
                    self.mqs['report files'].close()
                    break

                self.logger.debug('Upload report file "{0}"'.format(report_file))
                with open(report_file) as fp:
                    report = json.load(fp)
                # Read content of files specified via "__file:".
                for key in report:
                    if isinstance(report[key], str):
                        match = re.search(r'^__file:(.+)$', report[key])
                        if match:
                            # All these files should be placed in the same directory as uploaded report file.
                            file = os.path.join(os.path.dirname(report_file), match.groups()[0])
                            # As well these files may not exist.
                            with open(file) if os.path.isfile(file) else io.StringIO('') as fp:
                                report[key] = fp.read()
                self.session.upload_report(json.dumps(report))
        except Exception as e:
            # If we can't send reports to Omega by some reason we can just silently die.
            self.logger.exception('Catch exception when sending reports to Omega')
            exit(1)

    def get_components(self):
        self.logger.info('Get components necessary to solve job of class "{0}"'.format(self.job.type))

        if self.job.type not in self.job_class_components:
            raise KeyError('Job class "{0}" is not supported'.format(self.job.type))

        self.components = self.job_class_components[self.job.type]

        # Get modules of common components.
        if 'Common' in self.job_class_components:
            self.components.extend(self.job_class_components['Common'])

        self.logger.debug(
            'Components to be launched: "{0}"'.format(', '.join([component.__name__ for component in self.components])))

    def create_components_conf(self):
        """
        Create configuration to be used by all Psi components.
        """
        self.logger.info('Create components configuration')

        # Read job configuration from file.
        with open('job/root/conf.json') as fp:
            self.components_conf = json.load(fp)

        # Convert list of primitive dictionaries to one dictionary to simplify code below.
        comp = {}
        for attr in self.comp:
            comp.update(attr)

        self.components_conf.update(
            {'root id': os.path.abspath(os.path.curdir),
             'sys': {attr: comp[attr]['value'] for attr in ('CPUs num', 'mem size', 'arch')},
             'priority': self.conf['priority'],
             'abstract tasks generation priority': self.conf['abstract tasks generation priority'],
             'debug': self.conf['debug'],
             'allow local source directories use': self.conf['allow local source directories use'],
             'parallelism': self.conf['parallelism'],
             'logging': self.conf['logging']})

        if self.conf['debug']:
            self.logger.debug('Create components configuration file "components conf.json"')
            with open('components conf.json', 'w') as fp:
                json.dump(self.components_conf, fp, sort_keys=True, indent=4)

    def launch_all_components(self):
        self.logger.info('Launch all components')

        for component in self.components:
            p = component(self.components_conf, self.logger, self.id, self.callbacks, self.mqs,
                          separate_from_parent=True)
            p.start()
            self.component_processes.append(p)

    def wait_for_components(self):
        self.logger.info('Wait for components')

        # Every second check whether some component died. Otherwise even if some non-first component will die we
        # will wait for all components that preceed that failed component prior to notice that something went wrong.
        # Treat process that upload reports as component that may fail.
        while True:
            # The number of components that are still operating.
            operating_components_num = 0

            for p in self.component_processes:
                p.join(1.0 / len(self.component_processes))
                operating_components_num += p.is_alive()

            if not operating_components_num or self.uploading_reports_process.exitcode:
                break
