#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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

import argparse
import hashlib
import json
import multiprocessing
import os
import queue
import shutil
import time
import traceback

import pkg_resources

import klever.core.components
import klever.core.job
import klever.core.session
import klever.core.utils
from klever.core.session import BridgeError


class Core:
    DEFAULT_CONF_FILE = 'core.json'
    ID = '/'

    def __init__(self):
        self.exit_code = 0
        self.start_time = 0
        self.conf = {}
        self.logger = None
        self.comp = []
        self.session = None
        self.mqs = {}
        self.report_id = multiprocessing.Value('i', 1)
        self.uploading_reports_process = None
        self.uploading_reports_process_exitcode = multiprocessing.Value('i', 0)
        self.is_start_report_uploaded = False

    def main(self):
        try:
            # Remember approximate time of start to count wall time.
            self.start_time = time.time()

            self.get_conf()

            self.prepare_work_dir()
            self.change_work_dir()

            self.logger = klever.core.utils.get_logger(type(self).__name__, self.conf['logging'])
            self.logger.info('Solve job "%s"', self.conf['identifier'])

            self.session = klever.core.session.Session(self.logger, self.conf['Klever Bridge'], self.conf['identifier'])
            self.session.start_job_decision(klever.core.job.JOB_FORMAT, klever.core.job.JOB_ARCHIVE)

            self.mqs['report files'] = multiprocessing.Manager().Queue()

            os.makedirs('child resources'.encode('utf-8'))

            self.uploading_reports_process = Reporter(self.conf, self.logger, self.ID, self.mqs,
                                                      {'report id': self.report_id})
            self.uploading_reports_process.start()

            self.get_comp_desc()
            klever.core.utils.report(
                self.logger,
                'start',
                {
                    'identifier': self.ID,
                    'parent': None,
                    'component': type(self).__name__,
                    'attrs': [{
                        'name': 'Klever version',
                        'value': pkg_resources.get_distribution('klever').version
                    }],
                    'computer': self.comp
                },
                self.mqs['report files'],
                self.report_id,
                self.conf['main working directory']
            )
            self.is_start_report_uploaded = True

            klever.core.job.start_jobs(self, {
                'report id': self.report_id,
                'coverage_finished': multiprocessing.Manager().dict()
            })
        except Exception:  # pylint: disable=broad-exception-caught
            self.process_exception()

            if self.mqs:
                try:
                    with open('problem desc.txt', 'a', encoding='utf-8') as fp:
                        if fp.tell():
                            fp.write('\n')
                        traceback.print_exc(file=fp)

                    if self.is_start_report_uploaded:
                        klever.core.utils.report(
                            self.logger,
                            'unknown',
                            {
                                'identifier': self.ID + '/',
                                'parent': self.ID,
                                'problem_description': klever.core.utils.ArchiveFiles(['problem desc.txt'])
                            },
                            self.mqs['report files'],
                            self.report_id,
                            self.conf['main working directory']
                        )
                except Exception:  # pylint: disable=broad-exception-caught
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
                    child_resources = klever.core.components.all_child_resources()
                    report = {'identifier': self.ID}
                    report.update(klever.core.components.count_consumed_resources(
                        self.logger, self.start_time, child_resources=child_resources))

                    if os.path.isfile('log.txt') and self.conf['weight'] == "0":
                        report['log'] = klever.core.utils.ArchiveFiles(['log.txt'])

                    klever.core.utils.report(self.logger, 'finish', report, self.mqs['report files'], self.report_id,
                                             self.conf['main working directory'])

                    self.logger.info('Terminate report files message queue')
                    self.mqs['report files'].put(None)

                    # Do not try to upload Core finish report if uploading of other reports already failed.
                    if not self.uploading_reports_process.exitcode:
                        self.uploading_reports_process = Reporter(self.conf, self.logger, self.ID,
                                                                  self.mqs, {'report id': self.report_id})
                        self.uploading_reports_process.start()
                        self.logger.info('Wait for uploading Core finish report')
                        self.uploading_reports_process.join()

                    # Do not override exit code of main program with the one of auxiliary process uploading reports.
                    if not self.exit_code:
                        self.exit_code = self.uploading_reports_process.exitcode
            except Exception:  # pylint: disable=broad-exception-caught
                self.process_exception()

                # Do not upload reports and wait for corresponding process any more if something else went wrong above.
                if self.uploading_reports_process.is_alive():
                    self.uploading_reports_process.terminate()
            finally:
                # Remove the whole working directory after all if needed.
                if self.conf and not self.conf['keep intermediate files']:
                    shutil.rmtree(os.path.abspath('.'))

                if self.logger:
                    self.logger.info('Exit with code "%s"', self.exit_code)

        return self.exit_code

    def get_conf(self):
        # Get configuration file from command-line options. If it is not specified, then use the default one.
        parser = argparse.ArgumentParser(description='Main script of Klever Core.')
        parser.add_argument('conf file', nargs='?', default=self.DEFAULT_CONF_FILE,
                            help='configuration file (default: {0})'.format(self.DEFAULT_CONF_FILE))
        conf_file = vars(parser.parse_args())['conf file']

        # Read configuration from file.
        with open(conf_file, encoding='utf-8') as fp:
            self.conf = json.load(fp)

    def prepare_work_dir(self):
        # Create working directory.
        os.makedirs(self.conf['working directory'])

        # Create directory where all reports and report files archives will be actually written to.
        os.mkdir(os.path.join(self.conf['working directory'], 'reports'))

    def change_work_dir(self):
        # Change working directory forever.
        os.chdir(self.conf['working directory'])
        self.conf['main working directory'] = os.path.abspath(os.path.curdir)

    def get_comp_desc(self):
        self.logger.info('Get computer description')

        entities = tuple(
            {entity_name_cmd[0]: klever.core.utils.get_entity_val(self.logger, entity_name_cmd[0], entity_name_cmd[1])}
            for entity_name_cmd in (
                ('node name', 'uname -n'),
                ('CPU model', 'cat /proc/cpuinfo | grep -m1 "model name" | sed -r "s/^.*: //"'),
                ('number of CPU cores', 'cat /proc/cpuinfo | grep processor | wc -l'),
                ('memory size', 'cat /proc/meminfo | grep "MemTotal" | sed -r "s/^.*: *([0-9]+).*/1024 * \\1/" | bc'),
                ('Linux kernel version', 'uname -r'),
                ('host architecture', 'uname -m'),
            ))

        # Add computer description to configuration since it can be used by (sub)components.
        for entity in entities:
            self.conf.update(entity)

        # Represent memory size for users more pretty.
        entities[3]['memory size'] = '{0} GB'.format(int(entities[3]['memory size'] / 10 ** 9))

        self.comp = {
            'identifier': hashlib.sha224(json.dumps(entities).encode('utf-8')).hexdigest(),
            'display': entities[0]['node name'],
            'data': entities[1:]
        }

    def process_exception(self):
        self.exit_code = 1

        if self.logger:
            self.logger.exception('Catch exception')
        else:
            traceback.print_exc()


class Reporter(klever.core.components.Component):

    def send_reports(self):
        session = klever.core.session.Session(self.logger, self.conf['Klever Bridge'], self.conf['identifier'])
        issleep = True
        while True:
            # Report batches of reports each 3 seconds. This reduces the number of requests quite considerably.
            if issleep:
                time.sleep(3)
            else:
                issleep = True

            reports_and_report_file_archives = []
            is_finish = False
            while True:
                try:
                    # TODO: replace MQ with "reports and report file archives".
                    report_and_report_file_archives = self.mqs['report files'].get_nowait()

                    if report_and_report_file_archives is None:
                        self.logger.debug('Report files message queue was terminated')
                        is_finish = True
                        break

                    reports_and_report_file_archives.append(report_and_report_file_archives)

                    # We may fail if we try to upload too big report.
                    # In such a case we switch to upload reports separately.
                    if len(reports_and_report_file_archives) == 10:
                        # Do not sleep since there may be pending reports already.
                        issleep = False
                        break
                except queue.Empty:
                    break

            def upload_data(reports: list) -> str:
                # pylint: disable=broad-exception-caught
                error_msg = ""
                try:
                    session.upload_reports_and_report_file_archives(reports, self.conf['keep intermediate files'])
                except BridgeError as exc:
                    error_msg = 'Cannot upload reports due to too big archive (%s)', exc
                except Exception as exc:
                    error_msg = 'Cannot upload report due to unknown reason (%s)', exc
                return error_msg

            if reports_and_report_file_archives:
                for report_and_report_file_archives in reports_and_report_file_archives:
                    report_file_archives = report_and_report_file_archives.get('report file archives')
                    self.logger.debug('Upload report file "%s" with report file archives:\n%s',
                        report_and_report_file_archives['report file'],
                        '\n'.join(['  {0}'.format(archive) for archive in report_file_archives])
                        if report_file_archives else '')

                if upload_data(reports_and_report_file_archives):
                    # Failed to upload all reports - try to upload each of them separately.
                    for report in reports_and_report_file_archives:
                        err_msg = upload_data([report])
                        if err_msg:
                            self.logger.error(err_msg)
                            raise BridgeError(err_msg)
                            # TODO: we still may fail here in case of big report.
            if is_finish:
                break

    main = send_reports
