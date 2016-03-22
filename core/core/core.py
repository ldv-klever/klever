import argparse
import copy
import importlib
import json
import multiprocessing
import os
import shutil
import time
import traceback

import core.job
import core.session
import core.utils


def before_launch_all_components(context):
    context.mqs['verification statuses'] = multiprocessing.Queue()


def after_decide_verification_task(context):
    context.mqs['verification statuses'].put(context.verification_status)


def after_generate_all_verification_tasks(context):
    context.logger.info('Terminate verification statuses message queue')
    context.mqs['verification statuses'].put(None)


class Core:
    def __init__(self):
        self._exit_code = 0
        self._start_time = 0
        self._default_conf_file = 'core.json'
        self._conf = {}
        self._is_solving_file = None
        self._is_solving_file_fp = None
        self._logger = None
        self._comp = []
        self._id = '/'
        self._session = None
        self._mqs = {}
        self._uploading_reports_process = None
        self._job_class_components = {
            'Verification of Linux kernel modules': [
                'LKBCE',
                'LKVOG',
                'AVTG',
                'VTG',
            ],
            'Validation on commits in Linux kernel Git repositories': [],
        }
        self._components = []
        self._components_conf = None
        self._callbacks = {}
        self._component_processes = []
        self._data = None

    def main(self):
        try:
            # Use English everywhere below.
            os.environ['LANG'] = 'C'
            os.environ['LC_ALL'] = 'C'
            # Remember approximate time of start to count wall time.
            self._start_time = time.time()
            self._get_conf()
            self._prepare_work_dir()
            self._change_work_dir()
            self._logger = core.utils.get_logger(self.__class__.__name__, self._conf['logging'])
            version = self._get_version()
            job = core.job.Job(self._logger, self._conf['identifier'])
            self._comp = self._get_comp_desc()
            start_report_file = core.utils.report(self._logger,
                                                  'start',
                                                  {
                                                      'id': self._id,
                                                      'attrs': [{'Klever Core version': version}],
                                                      'comp': [
                                                          {attr[attr_shortcut]['name']: attr[attr_shortcut]['value']}
                                                          for attr in self._comp for attr_shortcut in attr
                                                      ]
                                                  })
            self._session = core.session.Session(self._logger, self._conf['Klever Bridge'], job.id)
            self._session.decide_job(job, start_report_file)
            # TODO: create parallel process to send requests about successful operation to Klever Bridge.
            self._mqs['report files'] = multiprocessing.Queue()
            self._uploading_reports_process = multiprocessing.Process(target=self._send_reports)
            self._uploading_reports_process.start()
            job.extract_archive()
            job.get_class()
            self._get_components(job)
            # Do not read anything from job directory untill job class will be examined (it might be unsupported). This
            # differs from specification that doesn't treat unsupported job classes at all.
            with open(core.utils.find_file_or_dir(self._logger, os.path.curdir, 'job.json'), encoding='ascii') as fp:
                job.conf = json.load(fp)
            # TODO: think about implementation in form of classes derived from class Job.
            if job.type == 'Verification of Linux kernel modules':
                self._create_components_conf(job)
                self._callbacks = core.utils.get_component_callbacks(self._logger, [self.__class__] + self._components,
                                                                     self._components_conf)
                core.utils.invoke_callbacks(self._launch_all_components, (self._id,))
                self._wait_for_components()
            elif job.type == 'Validation on commits in Linux kernel Git repositories':
                self._logger.info('Prepare sub-jobs of class "Verification of Linux kernel modules"')
                sub_jobs_common_conf = {}
                if 'Common' in job.conf:
                    sub_jobs_common_conf = job.conf['Common']
                if 'Sub-jobs' in job.conf:
                    for i, sub_job_concrete_conf in enumerate(job.conf['Sub-jobs']):
                        sub_job = core.job.Job(self._logger, i)
                        job.sub_jobs.append(sub_job)
                        sub_job.type = 'Verification of Linux kernel modules'
                        # Sub-job configuration is based on common sub-jobs configuration.
                        sub_job.conf = copy.deepcopy(sub_jobs_common_conf)
                        core.utils.merge_confs(sub_job.conf, sub_job_concrete_conf)
                self._logger.info('Decide prepared sub-jobs')
                # TODO: looks very like the code above.
                # TODO: create artificial log file for Validator.
                with open('__log', 'w', encoding='ascii'):
                    pass
                self._data = []
                for sub_job in job.sub_jobs:
                    commit = sub_job.conf['Linux kernel']['Git repository']['commit']
                    sub_job_id = self._id + str(commit)
                    # TODO: create this auxiliary component reports to allow deciding several sub-jobs. This should be likely done otherwise.
                    core.utils.report(self._logger,
                                      'start',
                                      {
                                          'id': sub_job_id,
                                          'parent id': self._id,
                                          'name': 'Validator',
                                          'attrs': [{'commit': commit}],
                                      },
                                      self._mqs['report files'],
                                      suffix=' validator {0}'.format(commit))
                    try:
                        os.makedirs(commit)
                        with core.utils.Cd(commit):
                            self._get_components(sub_job)
                            self._create_components_conf(sub_job)
                            self._callbacks = core.utils.get_component_callbacks(self._logger,
                                                                                 [self.__class__] + self._components,
                                                                                 self._components_conf)
                            core.utils.invoke_callbacks(self._launch_all_components, (sub_job_id,))
                            self._wait_for_components()
                            # TODO: dirty hack to wait for all reports to be uploaded since they may be accidently removed when local source directories use is allowed and next sub-job is decided.
                            while True:
                                time.sleep(1)
                                # Do not wait if reports uploading failed.
                                if self._uploading_reports_process.exitcode:
                                    break
                                if self._mqs['report files'].empty():
                                    time.sleep(3)
                                    break
                        # Do not proceed to other sub-jobs if reports uploading failed.
                        if self._uploading_reports_process.exitcode:
                            break
                    except Exception:
                        if self._mqs:
                            with open('problem desc.txt', 'w', encoding='ascii') as fp:
                                traceback.print_exc(file=fp)

                            if os.path.isfile('problem desc.txt'):
                                core.utils.report(self._logger,
                                                  'unknown',
                                                  {
                                                      'id': sub_job_id + '/unknown',
                                                      'parent id': sub_job_id,
                                                      'problem desc': 'problem desc.txt',
                                                      'files': ['problem desc.txt']
                                                  },
                                                  self._mqs['report files'],
                                                  suffix=' validator {0}'.format(commit))

                        if self._logger:
                            self._logger.exception('Catch exception')
                        else:
                            traceback.print_exc()

                        self._exit_code = 1

                        break
                    finally:
                        if 'verification statuses' in self._mqs:
                            sub_job.conf['obtained verification statuses'] = []
                            while True:
                                verification_status = self._mqs['verification statuses'].get()

                                if verification_status is None:
                                    self._logger.debug('Verification statuses message queue was terminated')
                                    self._mqs['verification statuses'].close()
                                    del self._mqs['verification statuses']
                                    break

                                sub_job.conf['obtained verification statuses'].append(verification_status)

                            # There is no verification statuses when some (sub)component failed prior to VTG strategy
                            # receives some abstract verification tasks.
                            if not sub_job.conf['obtained verification statuses']:
                                sub_job.conf['obtained verification statuses'].append('unknown')

                            self._data.append([sub_job.conf['Linux kernel']['Git repository']['commit'],
                                               sub_job.conf['ideal verdict']] +
                                              sub_job.conf['obtained verification statuses'] +
                                              [sub_job.conf['comment'] if 'comment' in sub_job.conf else None])

                            self._report_validation_results(commit)

                        core.utils.report(self._logger,
                                          'finish',
                                          {
                                              'id': sub_job_id,
                                              'resources': {'wall time': 0, 'CPU time': 0, 'memory size': 0},
                                              'log': '__log',
                                              'files': ['__log']
                                          },
                                          self._mqs['report files'],
                                          suffix=' validator {0}'.format(commit))

                # All validation results were already reported.
                self._data = []
        except Exception:
            if self._mqs:
                with open('problem desc.txt', 'w', encoding='ascii') as fp:
                    traceback.print_exc(file=fp)

                if os.path.isfile('problem desc.txt'):
                    core.utils.report(self._logger,
                                      'unknown',
                                      {
                                          'id': self._id + '/unknown',
                                          'parent id': self._id,
                                          'problem desc': 'problem desc.txt',
                                          'files': ['problem desc.txt']
                                      },
                                      self._mqs['report files'])

            if self._logger:
                self._logger.exception('Catch exception')
            else:
                traceback.print_exc()

            self._exit_code = 1
        finally:
            try:
                for p in self._component_processes:
                    # Do not terminate components that already exitted.
                    if p.is_alive():
                        p.stop()

                if self._mqs:
                    finish_report = {
                        'id': self._id,
                        'resources': core.utils.count_consumed_resources(
                            self._logger,
                            self._start_time),
                        'log': 'log',
                        'files': ['log']
                    }
                    if self._data:
                        finish_report.update({'data': json.dumps(self._data)})
                    core.utils.report(self._logger,
                                      'finish',
                                      finish_report,
                                      self._mqs['report files'])

                    self._logger.info('Terminate report files message queue')
                    self._mqs['report files'].put(None)

                    self._logger.info('Wait for uploading all reports')
                    self._uploading_reports_process.join()
                    # Do not override exit code of main program with the one of auxiliary process uploading reports.
                    if not self._exit_code:
                        self._exit_code = self._uploading_reports_process.exitcode

                if self._session:
                    self._session.sign_out()
            # At least release working directory if cleaning code above will raise some exception.
            finally:
                if self._is_solving_file_fp and not self._is_solving_file_fp.closed:
                    if self._logger:
                        self._logger.info('Release working directory')
                    os.remove(self._is_solving_file)

                if self._logger:
                    self._logger.info('Exit with code "{0}"'.format(self._exit_code))

                return self._exit_code

    def _get_conf(self):
        # Get configuration file from command-line options. If it is not specified, then use the default one.
        parser = argparse.ArgumentParser(description='Main script of Klever Core.')
        parser.add_argument('conf file', nargs='?', default=self._default_conf_file,
                            help='configuration file (default: {0})'.format(self._default_conf_file))
        conf_file = vars(parser.parse_args())['conf file']

        # Read configuration from file.
        with open(conf_file, encoding='ascii') as fp:
            self._conf = json.load(fp)

    def _prepare_work_dir(self):
        """
        Clean up and create the working directory. Prevent simultaneous usage of the same working directory.
        """
        # This file exists during Klever Core occupies working directory.
        self._is_solving_file = os.path.join(self._conf['working directory'], 'is solving')

        def check_another_instance():
            if not self._conf['ignore another instances'] and os.path.isfile(self._is_solving_file):
                raise FileExistsError('Another instance of Klever Core occupies working directory "{0}"'.format(
                    self._conf['working directory']))

        check_another_instance()

        # Remove (if exists) and create (if doesn't exist) working directory.
        # Note, that shutil.rmtree() doesn't allow to ignore files as required by specification. So, we have to:
        # - remove the whole working directory (if exists),
        # - create working directory (pass if it is created by another Klever Core),
        # - test one more time whether another Klever Core occupies the same working directory,
        # - occupy working directory.
        shutil.rmtree(self._conf['working directory'], True)

        os.makedirs(self._conf['working directory'], exist_ok=True)

        check_another_instance()

        # Occupy working directory until the end of operation.
        # Yes there may be race condition, but it won't be.
        self._is_solving_file_fp = open(self._is_solving_file, 'w', encoding='ascii')

    def _change_work_dir(self):
        # Change working directory forever.
        # We can use path for "is solving" file relative to future working directory since exceptions aren't raised when
        # we have relative path but don't change working directory yet.
        self._is_solving_file = os.path.relpath(self._is_solving_file, self._conf['working directory'])
        os.chdir(self._conf['working directory'])

        self._conf['main working directory'] = os.path.abspath(os.path.curdir)

    def _get_version(self):
        """
        Get version either as a tag in the Git repository of Klever or from the file created when installing Klever.
        """
        # Git repository directory may be located in parent directory of parent directory.
        git_repo_dir = os.path.join(os.path.dirname(__file__), '../../.git')
        if os.path.isdir(git_repo_dir):
            return core.utils.get_entity_val(self._logger, 'version',
                                             'git --git-dir {0} describe --always --abbrev=7 --dirty'.format(
                                                 git_repo_dir))
        else:
            # TODO: get version of installed Klever.
            return ''

    def _get_comp_desc(self):
        self._logger.info('Get computer description')

        return [
            {
                entity_name_cmd[0]: {
                    'name': entity_name_cmd[1] if entity_name_cmd[1] else entity_name_cmd[0],
                    'value': core.utils.get_entity_val(self._logger,
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

    def _send_reports(self):
        try:
            while True:
                # TODO: replace MQ with "reports and report files archives".
                report_and_report_files_archive = self._mqs['report files'].get()

                if report_and_report_files_archive is None:
                    self._logger.debug('Report files message queue was terminated')
                    # Note that this and all other closing of message queues aren't strictly necessary and everything
                    # will work without them as well, but this potentially can save some memory since closing explicitly
                    # notifies that corresponding message queue won't be used any more and its memory could be freed.
                    self._mqs['report files'].close()
                    break

                report_file = report_and_report_files_archive['report file']
                report_files_archive = report_and_report_files_archive.get('report files archive')

                self._logger.debug('Upload report file "{0}"{1}'.format(
                    report_file,
                    ' with report files archive "{0}"'.format(report_files_archive) if report_files_archive else ''))

                self._session.upload_report(report_file, report_files_archive)
        except Exception as e:
            # If we can't send reports to Klever Bridge by some reason we can just silently die.
            self._logger.exception('Catch exception when sending reports to Klever Bridge')
            exit(1)

    def _get_components(self, job):
        self._logger.info('Get components necessary to solve job of class "{0}"'.format(job.type))

        if job.type not in self._job_class_components:
            raise KeyError('Job class "{0}" is not supported'.format(job.type))

        self._components = [getattr(importlib.import_module('.{0}'.format(component.lower()), 'core'), component) for
                            component in self._job_class_components[job.type]]

        self._logger.debug('Components to be launched: "{0}"'.format(
            ', '.join([component.__name__ for component in self._components])))

    def _create_components_conf(self, job):
        """
        Create configuration to be used by all Klever Core components.
        """
        self._logger.info('Create components configuration')

        # Components configuration is based on job configuration.
        self._components_conf = job.conf

        # Convert list of primitive dictionaries to one dictionary to simplify code below.
        comp = {}
        for attr in self._comp:
            comp.update(attr)

        # Add complete Klever Core configuration itself to components configuration since almost all its attributes will
        # be used somewhere in components.
        self._components_conf.update(self._conf)

        self._components_conf.update({'sys': {attr: comp[attr]['value'] for attr in ('CPUs num', 'mem size', 'arch')}})

        if self._conf['keep intermediate files']:
            if os.path.isfile('components conf.json'):
                raise FileExistsError('Components configuration file "components conf.json" already exists')
            self._logger.debug('Create components configuration file "components conf.json"')
            with open('components conf.json', 'w', encoding='ascii') as fp:
                json.dump(self._components_conf, fp, sort_keys=True, indent=4)

    def _launch_all_components(self, parent_id):
        self._logger.info('Launch all components')

        for component in self._components:
            p = component(self._components_conf, self._logger, parent_id, self._callbacks, self._mqs,
                          separate_from_parent=True)
            p.start()
            self._component_processes.append(p)

    def _wait_for_components(self):
        self._logger.info('Wait for components')

        # Every second check whether some component died. Otherwise even if some non-first component will die we
        # will wait for all components that preceed that failed component prior to notice that something went wrong.
        # Treat process that upload reports as component that may fail.
        while True:
            # The number of components that are still operating.
            operating_components_num = 0

            for p in self._component_processes:
                p.join(1.0 / len(self._component_processes))
                operating_components_num += p.is_alive()

            if not operating_components_num or self._uploading_reports_process.exitcode:
                break

        # Clean up this list to properly decide other sub-jobs.
        if not self._uploading_reports_process.exitcode:
            self._component_processes = []

    def _report_validation_results(self, commit):
        self._logger.info('Relate validation results on commits before and after corresponding bug fixes if so')
        validation_results = []
        validation_results_before_bug_fixes = []
        validation_results_after_bug_fixes = []
        for validation_res in self._data:
            # Corresponds to validation result before bug fix.
            if validation_res[1] == 'unsafe':
                validation_results_before_bug_fixes.append(validation_res)
            # Corresponds to validation result after bug fix.
            elif validation_res[1] == 'safe':
                validation_results_after_bug_fixes.append(validation_res)
            else:
                raise ValueError(
                    'Ideal verdict is "{0}" (either "safe" or "unsafe" is expected)'.format(validation_res[1]))
        for commit1, ideal_verdict1, verification_status1, comment1 in validation_results_before_bug_fixes:
            found_validation_res_after_bug_fix = False
            for commit2, ideal_verdict2, verification_status2, comment2 in validation_results_after_bug_fixes:
                # Commit hash before/after corresponding bug fix is considered to be "hash~"/"hash" or v.v.
                if commit1 == commit2 + '~' or commit2 == commit1 + '~':
                    found_validation_res_after_bug_fix = True
                    break
            validation_res_msg = 'Verification status of bug "{0}" before fix is "{1}"{2}'.format(
                commit1, verification_status1, ' ("{0}")'.format(comment1) if comment1 else '')
            # At least save validation result before bug fix.
            if not found_validation_res_after_bug_fix:
                self._logger.warning('Could not find validation result after fix of bug "{0}"'.format(commit1))
                validation_results.append([commit1, verification_status1, comment1, None, None])
            else:
                validation_res_msg += ', after fix is "{0}"{1}'.format(verification_status2,
                                                                       ' ("{0}")'.format(comment2) if comment2 else '')
                validation_results.append([commit1, verification_status1, comment1, verification_status2, comment2])
            self._logger.info(validation_res_msg)

        core.utils.report(self._logger,
                          'data',
                          {
                              'id': self._id,
                              'data': json.dumps(validation_results)
                          },
                          self._mqs['report files'],
                          suffix=' {0}'.format(commit))
