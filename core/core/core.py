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

import argparse
import json
import multiprocessing
import os
import setuptools_scm
import setuptools_scm.hacks
import shutil
import time
import traceback

import core.job
import core.session
import core.utils


class Core(core.utils.CallbacksCaller):
    DEFAULT_CONF_FILE = 'core.json'
    ID = '/'

    def __init__(self):
        self.exit_code = 0
        self.start_time = 0
        self.conf = {}
        self.is_solving_file = None
        self.is_solving_file_fp = None
        self.logger = None
        self.comp = []
        self.session = None
        self.mqs = {}
        self.report_id = multiprocessing.Value('i', 1)
        self.uploading_reports_process = None
        self.uploading_reports_process_exitcode = multiprocessing.Value('i', 0)
        self.callbacks = {}

    def main(self):
        try:
            # Remember approximate time of start to count wall time.
            self.start_time = time.time()
            self.get_conf()
            self.prepare_work_dir()
            self.change_work_dir()
            self.logger = core.utils.get_logger(type(self).__name__, self.conf['logging'])
            version = self.get_version()
            job = core.job.Job(self.logger, self.ID)
            self.logger.info('Support jobs of format "{0}"'.format(job.FORMAT))
            self.get_comp_desc()
            start_report_file = core.utils.report(self.logger,
                                                  'start',
                                                  {
                                                      'id': self.ID,
                                                      'attrs': [{'Klever Core version': version}],
                                                      'comp': self.comp
                                                  },
                                                  None,
                                                  self.report_id,
                                                  self.conf['main working directory'])
            self.session = core.session.Session(self.logger, self.conf['Klever Bridge'], self.conf['identifier'])
            self.session.start_job_decision(job, start_report_file)
            self.mqs['report files'] = multiprocessing.Manager().Queue()
            self.uploading_reports_process = multiprocessing.Process(target=self.send_reports)
            self.uploading_reports_process.start()
            job.decide(self.conf, self.mqs, {'build': multiprocessing.Manager().Lock()},
                       {'report id': self.report_id},
                       self.uploading_reports_process_exitcode)
        except Exception:
            self.process_exception()

            if self.mqs:
                try:
                    with open('problem desc.txt', 'w', encoding='utf8') as fp:
                        traceback.print_exc(file=fp)

                    core.utils.report(self.logger,
                                      'unknown',
                                      {
                                          'id': self.ID + '/unknown',
                                          'parent id': self.ID,
                                          'problem desc': 'problem desc.txt',
                                          'files': ['problem desc.txt']
                                      },
                                      self.mqs['report files'],
                                      self.report_id,
                                      self.conf['main working directory'])
                except Exception:
                    self.process_exception()
        finally:
            try:
                if self.mqs:
                    self.logger.info('Terminate report files message queue')
                    self.mqs['report files'].put(None)

                    if self.uploading_reports_process.is_alive():
                        self.logger.info('Wait for uploading all reports except Core finish report')
                        self.uploading_reports_process.join()

                    # Create Core finish report just after other reports are uploaded. Otherwise time between creating
                    # Core finish report and finishing uploading all reports won't be included into wall time of Core.
                    core.utils.report(self.logger,
                                      'finish',
                                      {
                                          'id': self.ID,
                                          'resources': core.utils.count_consumed_resources(
                                              self.logger,
                                              self.start_time),
                                          'log': 'log.txt' if os.path.isfile('log.txt') else None,
                                          'files': ['log.txt'] if os.path.isfile('log.txt') else []
                                      },
                                      self.mqs['report files'],
                                      self.report_id,
                                      self.conf['main working directory'])
                    self.logger.info('Terminate report files message queue')
                    self.mqs['report files'].put(None)

                    # Do not try to upload Core finish report if uploading of other reports already failed.
                    if not self.uploading_reports_process.exitcode:
                        self.uploading_reports_process = multiprocessing.Process(target=self.send_reports)
                        self.uploading_reports_process.start()
                        self.logger.info('Wait for uploading Core finish report')
                        self.uploading_reports_process.join()

                    # Do not override exit code of main program with the one of auxiliary process uploading reports.
                    if not self.exit_code:
                        self.exit_code = self.uploading_reports_process.exitcode

                if self.session:
                    self.session.sign_out()
            except Exception:
                self.process_exception()

                # Do not upload reports and wait for corresponding process any more if something else went wrong above.
                if self.uploading_reports_process.is_alive():
                    self.uploading_reports_process.terminate()
            # At least release working directory even if cleaning code above raised some exceptions.
            finally:
                if self.is_solving_file_fp and not self.is_solving_file_fp.closed:
                    if self.logger:
                        self.logger.info('Release working directory')
                    os.remove(self.is_solving_file)

                if self.logger:
                    self.logger.info('Exit with code "{0}"'.format(self.exit_code))

                return self.exit_code

    def get_conf(self):
        # Get configuration file from command-line options. If it is not specified, then use the default one.
        parser = argparse.ArgumentParser(description='Main script of Klever Core.')
        parser.add_argument('conf file', nargs='?', default=self.DEFAULT_CONF_FILE,
                            help='configuration file (default: {0})'.format(self.DEFAULT_CONF_FILE))
        conf_file = vars(parser.parse_args())['conf file']

        # Read configuration from file.
        with open(conf_file, encoding='utf8') as fp:
            self.conf = json.load(fp)

    def prepare_work_dir(self):
        """
        Clean up and create the working directory. Prevent simultaneous usage of the same working directory.
        """
        # This file exists during Klever Core occupies working directory.
        self.is_solving_file = os.path.join(self.conf['working directory'], 'is solving')

        def check_another_instance():
            if not self.conf['ignore other instances'] and os.path.isfile(self.is_solving_file):
                raise FileExistsError('Another instance of Klever Core occupies working directory "{0}"'.format(
                    self.conf['working directory']))

        check_another_instance()

        # Remove (if exists) and create (if doesn't exist) working directory.
        # Note, that shutil.rmtree() doesn't allow to ignore files as required by specification. So, we have to:
        # - remove the whole working directory (if exists),
        # - create working directory (pass if it is created by another Klever Core),
        # - test one more time whether another Klever Core occupies the same working directory,
        # - occupy working directory.
        shutil.rmtree(self.conf['working directory'], True)

        os.makedirs(self.conf['working directory'].encode('utf8'), exist_ok=True)

        check_another_instance()

        # Occupy working directory until the end of operation.
        # Yes there may be race condition, but it won't be.
        self.is_solving_file_fp = open(self.is_solving_file, 'w', encoding='utf8')

        # Create directory where all reports and report files archives will be actually written to.
        os.mkdir(os.path.join(self.conf['working directory'], 'reports'))

    def change_work_dir(self):
        # Change working directory forever.
        # We can use path for "is solving" file relative to future working directory since exceptions aren't raised when
        # we have relative path but don't change working directory yet.
        self.is_solving_file = os.path.relpath(self.is_solving_file, self.conf['working directory'])
        os.chdir(self.conf['working directory'])

        self.conf['main working directory'] = os.path.abspath(os.path.curdir)

    def get_version(self):
        """
        Get version either as a tag in the Git repository of Klever or from the file created when installing Klever.
        """
        # Git repository directory may be located in parent directory of parent directory.
        git_repo_dir = os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir)
        if os.path.isdir(os.path.join(git_repo_dir, '.git')):
            self.logger.info('Get version on the basis of the Git repository')
            version = setuptools_scm.get_version(root=git_repo_dir)
        else:
            self.logger.info('Get version on the basis of package information')
            version = setuptools_scm.get_version(os.path.join(os.path.dirname(__file__), os.path.pardir, 'EGG-INFO'),
                                                 parse=setuptools_scm.hacks.parse_pkginfo)
        self.logger.debug('Klever Core version is "{0}"'.format(version))
        return version

    def get_comp_desc(self):
        self.logger.info('Get computer description')

        self.comp = tuple([
            {entity_name_cmd[0]: core.utils.get_entity_val(self.logger, entity_name_cmd[0], entity_name_cmd[1])}
            for entity_name_cmd in (
                ('node name', 'uname -n'),
                ('CPU model', 'cat /proc/cpuinfo | grep -m1 "model name" | sed -r "s/^.*: //"'),
                ('number of CPU cores', 'cat /proc/cpuinfo | grep processor | wc -l'),
                ('memory size', 'cat /proc/meminfo | grep "MemTotal" | sed -r "s/^.*: *([0-9]+).*/1024 * \\1/" | bc'),
                ('Linux kernel version', 'uname -r'),
                ('architecture', 'uname -m'),
            )
            ])

        # Add computer description to configuration since it can be used by (sub)components.
        for entity in self.comp:
            self.conf.update(entity)

    def send_reports(self):
        try:
            while True:
                # TODO: replace MQ with "reports and report file archives".
                report_and_report_file_archives = self.mqs['report files'].get()

                if report_and_report_file_archives is None:
                    self.logger.debug('Report files message queue was terminated')
                    break

                report_file = report_and_report_file_archives['report file']
                report_file_archives = report_and_report_file_archives.get('report file archives')

                self.logger.debug('Upload report file "{0}"{1}'.format(
                    report_file,
                    ' with report file archives:\n{0}'.format(
                        '\n'.join(['  {0} - {1}'.format(archive_name, archive)
                                   for archive_name, archive in report_file_archives.items()]))
                    if report_file_archives else ''))

                self.session.upload_report(report_file, report_file_archives)
        except Exception as e:
            # If we can't send reports to Klever Bridge by some reason we can just silently die.
            self.logger.exception('Catch exception when sending reports to Klever Bridge')
            self.uploading_reports_process_exitcode.value = 1
            os._exit(1)

    def process_exception(self):
        self.exit_code = 1

        if self.logger:
            self.logger.exception('Catch exception')
        else:
            traceback.print_exc()
