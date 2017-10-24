#
# Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
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

import copy
import hashlib
import importlib
import json
import multiprocessing
import os
import re
import sys
import zipfile
import traceback

import core.utils
import core.vrp.coverage_parser


class Job(core.utils.CallbacksCaller):
    FORMAT = 1
    ARCHIVE = 'job.zip'
    DIR = 'job'
    CLASS_FILE = os.path.join(DIR, 'class')
    DEFAULT_CONF_FILE = 'core.json'
    JOB_CLASS_COMPONENTS = {
        'Verification of Linux kernel modules': [
            'LKBCE',
            'LKVOG',
            'VTG',
            'VRP'
        ],
    }

    def __init__(self, logger, id, type=None):
        self.logger = logger
        self.id = id
        self.logger.debug('Job identifier is "{0}"'.format(id))
        self.parent = {}
        self.name_prefix = None
        self.name = None
        self.work_dir = None
        self.mqs = {}
        self.locks = {}
        self.vals = {}
        self.uploading_reports_process_exitcode = None
        self.data = None
        self.data_lock = None
        # This attribute will be used if there are not sub-jobs.
        self.total_coverages = multiprocessing.Manager().dict()
        self.type = type
        self.components_common_conf = None
        self.sub_jobs = []
        self.components = []
        self.callbacks = {}
        self.component_processes = []
        self.reporting_results_process = None
        self.collecting_total_coverages_process = None

    def decide(self, conf, mqs, locks, vals, uploading_reports_process_exitcode):
        self.logger.info('Decide job')

        self.mqs = mqs
        self.locks = locks
        self.vals = vals
        self.uploading_reports_process_exitcode = uploading_reports_process_exitcode
        self.data = multiprocessing.Manager().dict()
        self.data_lock = multiprocessing.Lock()
        self.extract_archive()
        self.get_class()
        self.get_common_components_conf(conf)
        self.get_sub_jobs()

        if self.sub_jobs:
            self.logger.info('Decide sub-jobs')

            sub_job_solvers_num = core.utils.get_parallel_threads_num(self.logger, self.components_common_conf,
                                                                      'Sub-jobs processing')
            self.logger.debug('Sub-jobs will be decided in parallel by "{0}" solvers'.format(sub_job_solvers_num))

            self.mqs['sub-job indexes'] = multiprocessing.Queue()
            for i in range(len(self.sub_jobs)):
                self.mqs['sub-job indexes'].put(i)
            for i in range(sub_job_solvers_num):
                self.mqs['sub-job indexes'].put(None)

            sub_job_solver_processes = []
            try:
                for i in range(sub_job_solvers_num):
                    p = multiprocessing.Process(target=self.decide_sub_job, name='Worker ' + str(i))
                    p.start()
                    sub_job_solver_processes.append(p)

                self.logger.info('Wait for sub-jobs')
                while True:
                    operating_sub_job_solvers_num = 0

                    for p in sub_job_solver_processes:
                        p.join(1.0 / len(sub_job_solver_processes))
                        if p.exitcode:
                            self.logger.warning('Sub-job worker exitted with "{0}"'.format(p.exitcode))
                            raise ChildProcessError('Decision of sub-job failed')
                        operating_sub_job_solvers_num += p.is_alive()

                    if not operating_sub_job_solvers_num:
                        break
            finally:
                for p in sub_job_solver_processes:
                    if p.is_alive():
                        p.terminate()
        else:
            # Klever Core working directory is used for the only sub-job that is job itself.
            self.__decide_sub_job()

    def decide_sub_job(self):
        while True:
            sub_job_index = self.mqs['sub-job indexes'].get()

            if sub_job_index is None:
                self.logger.debug('Sub-job indexes message queue was terminated')
                break

            try:
                self.sub_jobs[sub_job_index].__decide_sub_job()
            except SystemExit:
                self.logger.error('Decision of sub-job of type "{0}" with identifier "{1}" failed'.
                                  format(self.type, self.sub_jobs[sub_job_index].id))
                if not self.components_common_conf['ignore failed sub-jobs']:
                    sys.exit(1)

    def __decide_sub_job(self):
        if self.name:
            self.logger.info('Decide sub-job of type "{0}" with identifier "{1}"'.format(self.type, self.id))

        # All sub-job names should be unique, so there shouldn't be any problem to create directories with these names
        # to be used as working directories for corresponding sub-jobs. Jobs without sub-jobs don't have names.
        if self.name:
            os.makedirs(self.work_dir.encode('utf8'))

        # Do not produce any reports until changing directory. Otherwise there can be races between various sub-jobs.
        with core.utils.Cd(self.work_dir if self.name else os.path.curdir):
            try:
                if self.name:
                    if self.components_common_conf['keep intermediate files']:
                        if os.path.isfile('conf.json'):
                            raise FileExistsError(
                                'Components configuration file "conf.json" already exists')
                        self.logger.debug('Create components configuration file "conf.json"')
                        with open('conf.json', 'w', encoding='utf8') as fp:
                            json.dump(self.components_common_conf, fp, ensure_ascii=False, sort_keys=True, indent=4)

                    core.utils.report(self.logger,
                                      'start',
                                      {
                                          'id': self.id,
                                          'parent id': self.parent['id'],
                                          'name': 'Sub-job',
                                          'attrs': [{'name': self.name}],
                                      },
                                      self.mqs['report files'],
                                      self.vals['report id'],
                                      self.components_common_conf['main working directory'])

                if 'ideal verdicts' in self.components_common_conf:
                    # Create queue and specify callbacks to collect verification statuses from VTG. They will be used to
                    # calculate validation and testing results.
                    self.mqs['verification statuses'] = multiprocessing.Queue()

                    def after_plugin_fail_processing(context):
                        context.mqs['verification statuses'].put({
                            'verification object': context.verification_object,
                            'rule specification': context.rule_specification,
                            'verdict': 'non-verifier unknown'
                        })

                    def after_process_failed_task(context):
                        context.mqs['verification statuses'].put({
                            'verification object': context.verification_object,
                            'rule specification': context.rule_specification,
                            'verdict': context.verdict
                        })

                    def after_process_single_verdict(context):
                        context.mqs['verification statuses'].put({
                            'verification object': context.verification_object,
                            'rule specification': context.rule_specification,
                            'verdict': context.verdict
                        })

                    core.utils.set_component_callbacks(self.logger, type(self),
                                                       (
                                                           after_plugin_fail_processing,
                                                           after_process_single_verdict,
                                                           after_process_failed_task
                                                       ))

                    # Start up parallel process for reporting results. Without this there can be deadlocks since queue
                    # created and filled above can be overfilled that results in VTG processes will not terminate.
                    self.reporting_results_process = multiprocessing.Process(target=self.report_results)
                    self.reporting_results_process.start()

                def after_finish_task_results_processing(context):
                    if 'ideal verdicts' in self.components_common_conf:
                        context.logger.info('Terminate verification statuses message queue')
                        context.mqs['verification statuses'].put(None)

                    if self.components_common_conf['collect total code coverage']:
                        context.logger.info('Terminate rule specifications and coverage infos message queue')
                        context.mqs['rule specifications and coverage info files'].put(None)

                core.utils.set_component_callbacks(self.logger, type(self), (after_finish_task_results_processing,))

                if self.components_common_conf['collect total code coverage']:
                    self.mqs['rule specifications and coverage info files'] = multiprocessing.Queue()

                    def after_process_finished_task(context):
                        if os.path.isfile('coverage info.json'):
                            context.mqs['rule specifications and coverage info files'].put({
                                'rule specification': context.rule_specification,
                                'coverage info file': os.path.relpath('coverage info.json',
                                                                      context.conf['main working directory'])
                            })

                    core.utils.set_component_callbacks(self.logger, type(self), (after_process_finished_task,))

                    self.collecting_total_coverages_process = \
                        multiprocessing.Process(target=self.collect_total_coverage)
                    self.collecting_total_coverages_process.start()

                self.get_sub_job_components()

                self.callbacks = core.utils.get_component_callbacks(self.logger, [type(self)] + self.components,
                                                                    self.components_common_conf)

                self.launch_sub_job_components()
            except Exception:
                if self.name:
                    self.logger.exception('Catch exception')

                    try:
                        with open('problem desc.txt', 'w', encoding='utf8') as fp:
                            traceback.print_exc(file=fp)

                        core.utils.report(self.logger,
                                          'unknown',
                                          {
                                              'id': self.id + '/unknown',
                                              'parent id': self.id,
                                              'problem desc': core.utils.ReportFiles(['problem desc.txt'])
                                          },
                                          self.mqs['report files'],
                                          self.vals['report id'],
                                          self.components_common_conf['main working directory'])
                    except Exception:
                        self.logger.exception('Catch exception')
                    finally:
                        sys.exit(1)
                else:
                    raise
            finally:
                try:
                    core.utils.remove_component_callbacks(self.logger, type(self))

                    if self.name:
                        report = {
                            'id': self.id,
                            'resources': {'wall time': 0, 'CPU time': 0, 'memory size': 0},
                        }

                        if len(self.total_coverages):
                            report['coverage'] = self.total_coverages.copy()

                        core.utils.report(self.logger, 'finish', report, self.mqs['report files'],
                                          self.vals['report id'], self.components_common_conf['main working directory'])
                except Exception:
                    self.logger.exception('Catch exception')

    def get_class(self):
        self.logger.info('Get job class')
        with open(self.CLASS_FILE, encoding='utf8') as fp:
            self.type = fp.read()
        self.logger.debug('Job class is "{0}"'.format(self.type))

    def get_common_components_conf(self, core_conf):
        self.logger.info('Get components common configuration')

        with open(core.utils.find_file_or_dir(self.logger, os.path.curdir, 'job.json'), encoding='utf8') as fp:
            self.components_common_conf = json.load(fp)

        # Add complete Klever Core configuration itself to components configuration since almost all its attributes will
        # be used somewhere in components.
        self.components_common_conf.update(core_conf)

        if self.components_common_conf['keep intermediate files']:
            if os.path.isfile('components common conf.json'):
                raise FileExistsError(
                    'Components common configuration file "components common conf.json" already exists')
            self.logger.debug('Create components common configuration file "components common conf.json"')
            with open('components common conf.json', 'w', encoding='utf8') as fp:
                json.dump(self.components_common_conf, fp, ensure_ascii=False, sort_keys=True, indent=4)

    def get_sub_jobs(self):
        self.logger.info('Get job sub-jobs')

        if 'Common' in self.components_common_conf and 'Sub-jobs' not in self.components_common_conf:
            raise KeyError('You can not specify common sub-jobs configuration without sub-jobs themselves')

        if 'Common' in self.components_common_conf:
            self.components_common_conf.update(self.components_common_conf['Common'])
            del (self.components_common_conf['Common'])

        if 'Sub-jobs' in self.components_common_conf:
            for number, sub_job_concrete_conf in enumerate(self.components_common_conf['Sub-jobs']):
                # Sub-job configuration is based on common sub-jobs configuration.
                sub_job_components_common_conf = copy.deepcopy(self.components_common_conf)
                del (sub_job_components_common_conf['Sub-jobs'])
                sub_job_concrete_conf = core.utils.merge_confs(sub_job_components_common_conf, sub_job_concrete_conf)

                self.logger.info('Get sub-job name and type')
                external_modules = sub_job_concrete_conf['Linux kernel'].get('external modules', '')

                modules = sub_job_concrete_conf['Linux kernel']['modules']
                if len(modules) == 1:
                    modules_hash = modules[0]
                else:
                    modules_hash = hashlib.sha1(''.join(modules).encode('utf8')).hexdigest()[:7]

                rule_specs = sub_job_concrete_conf['rule specifications']
                if len(rule_specs) == 1:
                    rule_specs_hash = rule_specs[0]
                else:
                    rule_specs_hash = hashlib.sha1(''.join(rule_specs).encode('utf8')).hexdigest()[:7]

                if self.type == 'Validation on commits in Linux kernel Git repositories':
                    commit = sub_job_concrete_conf['Linux kernel']['Git repository']['commit']
                    if len(commit) != 12 and (len(commit) != 13 or commit[12] != '~'):
                        raise ValueError(
                            'Commit hashes should have 12 symbols and optional "~" at the end ("{0}" is given)'.format(
                                commit))
                    sub_job_name_prefix = os.path.join(commit, external_modules)
                    sub_job_name = os.path.join(commit, external_modules, modules_hash, rule_specs_hash)
                    sub_job_work_dir = os.path.join(commit, external_modules, modules_hash,
                                                    re.sub(r'\W', '-', rule_specs_hash))
                    sub_job_type = 'Verification of Linux kernel modules'
                elif self.type == 'Verification of Linux kernel modules':
                    external_modules = os.path.join(str(number), external_modules)
                    sub_job_name_prefix = os.path.join(external_modules)
                    sub_job_name = os.path.join(external_modules, modules_hash, rule_specs_hash)
                    sub_job_work_dir = os.path.join(external_modules, modules_hash, re.sub(r'\W', '-', rule_specs_hash))
                    sub_job_type = 'Verification of Linux kernel modules'
                else:
                    raise NotImplementedError('Job class "{0}" is not supported'.format(self.type))
                self.logger.debug('Sub-job name and type are "{0}" and "{1}"'.format(sub_job_name, sub_job_type))

                sub_job_id = self.id + sub_job_name

                for sub_job in self.sub_jobs:
                    if sub_job.id == sub_job_id:
                        raise ValueError('Several sub-jobs have the same identifier "{0}"'.format(sub_job_id))

                sub_job = Job(self.logger, sub_job_id, sub_job_type)
                self.sub_jobs.append(sub_job)
                sub_job.parent = {'id': self.id, 'type': self.type}
                sub_job.name_prefix = sub_job_name_prefix
                sub_job.name = sub_job_name
                sub_job.work_dir = sub_job_work_dir
                sub_job.mqs = self.mqs
                sub_job.locks = self.locks
                sub_job.vals = self.vals
                sub_job.uploading_reports_process_exitcode = self.uploading_reports_process_exitcode
                sub_job.data = self.data
                sub_job.data_lock = self.data_lock
                # Each particular sub-job has its own total coverages.
                sub_job.total_coverages = multiprocessing.Manager().dict()
                sub_job.components_common_conf = sub_job_concrete_conf

    def get_sub_job_components(self):
        self.logger.info('Get components for sub-job of type "{0}" with identifier "{1}"'.format(self.type, self.id))

        if self.type not in self.JOB_CLASS_COMPONENTS:
            raise NotImplementedError('Job class "{0}" is not supported'.format(self.type))

        self.components = [getattr(importlib.import_module('.{0}'.format(component.lower()), 'core'), component) for
                           component in self.JOB_CLASS_COMPONENTS[self.type]]

        self.logger.debug('Components to be launched: "{0}"'.format(
            ', '.join([component.__name__ for component in self.components])))

    def extract_archive(self):
        self.logger.info('Extract job archive "{0}" to directory "{1}"'.format(self.ARCHIVE, self.DIR))
        with zipfile.ZipFile(self.ARCHIVE) as ZipFile:
            ZipFile.extractall(self.DIR)

    def launch_sub_job_components(self):
        self.logger.info('Launch components for sub-job of type "{0}" with identifier "{1}"'.format(self.type, self.id))

        try:
            for component in self.components:
                p = component(self.components_common_conf, self.logger, self.id, self.callbacks, self.mqs,
                              self.locks, self.vals, separate_from_parent=True)
                p.start()
                self.component_processes.append(p)

            # Every second check whether some component died. Otherwise even if some non-first component will die we
            # will wait for all components that preceed that failed component prior to notice that something went
            # wrong. Treat process that upload reports as component that may fail.
            while True:
                # The number of components that are still operating.
                operating_components_num = 0

                for p in self.component_processes:
                    p.join(1.0 / len(self.component_processes))
                    operating_components_num += p.is_alive()

                if not operating_components_num:
                    break

                if self.uploading_reports_process_exitcode.value:
                    raise RuntimeError('Uploading reports failed')

                if self.reporting_results_process and self.reporting_results_process.exitcode:
                    raise RuntimeError('Reporting results failed')

                if self.collecting_total_coverages_process and \
                        self.collecting_total_coverages_process.exitcode:
                    raise RuntimeError('Collecting total coverages failed')
        except Exception:
            for p in self.component_processes:
                # Do not terminate components that already exitted.
                if p.is_alive():
                    p.stop()

            if 'verification statuses' in self.mqs:
                self.logger.info('Forcibly terminate verification statuses message queue')
                self.mqs['verification statuses'].put(None)

            if 'rule specifications and coverage info files' in self.mqs:
                self.logger.info('Forcibly terminate rule specification and coverage info files message queue')
                self.mqs['rule specifications and coverage info files'].put(None)

            raise
        finally:
            if self.reporting_results_process:
                self.logger.info('Wait for reporting all results')
                self.reporting_results_process.join()
                if self.reporting_results_process.exitcode:
                    raise RuntimeError('Reporting results failed')

            if self.collecting_total_coverages_process:
                self.logger.info('Wait for collecting all total coverages')
                self.collecting_total_coverages_process.join()
                if self.collecting_total_coverages_process.exitcode:
                    raise RuntimeError('Collecting total coverages failed')

    def collect_total_coverage(self):
        # Process exceptions like for uploading reports.
        try:
            total_coverage_infos = {}

            while True:
                rule_spec_and_coverage_info_files = self.mqs['rule specifications and coverage info files'].get()

                if rule_spec_and_coverage_info_files is None:
                    self.logger.debug('Rule specification coverage info files message queue was terminated')
                    self.mqs['rule specifications and coverage info files'].close()
                    break

                rule_spec = rule_spec_and_coverage_info_files['rule specification']
                total_coverage_infos.setdefault(rule_spec, {})

                with open(os.path.join(self.components_common_conf['main working directory'],
                                       rule_spec_and_coverage_info_files['coverage info file']), encoding='utf8') as fp:
                    coverage_info = json.load(fp)

                for file_name, coverage_info in coverage_info.items():
                    total_coverage_infos[rule_spec].setdefault(file_name, [])
                    total_coverage_infos[rule_spec][file_name] += coverage_info

            os.mkdir('total coverages')

            total_coverages = {}

            for rule_spec, coverage_info in total_coverage_infos.items():
                total_coverage_dir = os.path.join('total coverages', re.sub(r'/', '-', rule_spec))
                os.mkdir(total_coverage_dir)

                total_coverage_file = os.path.join(total_coverage_dir, 'coverage.json')
                if os.path.isfile(total_coverage_file):
                    raise FileExistsError('Total coverage file "{0}" already exists'.format(total_coverage_file))
                arcnames = {total_coverage_file: 'coverage.json'}

                coverage = core.vrp.coverage_parser.LCOV.get_coverage(coverage_info)

                with open(total_coverage_file, 'w', encoding='utf8') as fp:
                    json.dump(coverage, fp, ensure_ascii=True, sort_keys=True, indent=4)

                arcnames.update({info[0]['file name']: info[0]['arcname'] for info in coverage_info.values()})

                total_coverages[rule_spec] = core.utils.ReportFiles([total_coverage_file] + list(arcnames.keys()),
                                                                    arcnames)

            # Share collected total coverages and arcnames to report them within Sub-job/Core finish report.
            self.total_coverages.update(total_coverages)
        except Exception:
            self.logger.exception('Catch exception when collecting total coverages')
            os._exit(1)

    def report_results(self):
        # Process exceptions like for uploading reports.
        try:
            os.mkdir('results')

            while True:
                verification_status = self.mqs['verification statuses'].get()

                if verification_status is None:
                    self.logger.debug('Verification statuses message queue was terminated')
                    self.mqs['verification statuses'].close()
                    del self.mqs['verification statuses']
                    break

                # Block several sub-jobs from each other to reliably produce outcome.
                with self.data_lock:
                    name_suffix, verification_result = self.__match_ideal_verdict(verification_status)

                    name = os.path.join(self.name_prefix, name_suffix)

                    if self.parent['type'] == 'Verification of Linux kernel modules':
                        self.logger.info('Ideal/obtained verdict for test "{0}" is "{1}"/"{2}"{3}'.format(
                            name, verification_result['ideal verdict'], verification_result['verdict'],
                            ' ("{0}")'.format(verification_result['comment'])
                            if verification_result['comment'] else ''))
                    elif self.parent['type'] == 'Validation on commits in Linux kernel Git repositories':
                        name, verification_result = self.__process_validation_results(name, verification_result)
                    else:
                        raise NotImplementedError('Job class "{0}" is not supported'.format(self.parent['type']))

                    results_dir = os.path.join('results', re.sub(r'/', '-', name_suffix))
                    os.mkdir(results_dir)

                    core.utils.report(self.logger,
                                      'data',
                                      {
                                          'id': self.parent['id'],
                                          'data': {name: verification_result}
                                      },
                                      self.mqs['report files'],
                                      self.vals['report id'],
                                      self.components_common_conf['main working directory'],
                                      results_dir)
        except Exception:
            self.logger.exception('Catch exception when reporting results')
            os._exit(1)

    def __match_ideal_verdict(self, verification_status):
        def match_verification_object(vo, iv):
            if (isinstance(iv['verification object'], str) and iv['verification object'] == vo) or \
               (isinstance(iv['verification object'], list) and vo in iv['verification object']):
                return True
            else:
                return False

        verification_object = verification_status['verification object']
        rule_specification = verification_status['rule specification']
        ideal_verdicts = self.components_common_conf['ideal verdicts']

        is_matched = False

        # Try to match exactly by both verification object and rule specification.
        for ideal_verdict in ideal_verdicts:
            if 'verification object' in ideal_verdict and 'rule specification' in ideal_verdict \
                    and ideal_verdict['verification object'] == verification_object \
                    and ideal_verdict['rule specification'] == rule_specification:
                is_matched = True
                break

        # Try to match just by verification object.
        if not is_matched:
            for ideal_verdict in ideal_verdicts:
                if 'verification object' in ideal_verdict and 'rule specification' not in ideal_verdict \
                        and match_verification_object(verification_object, ideal_verdict):
                    is_matched = True
                    break

        # Try to match just by rule specification.
        if not is_matched:
            for ideal_verdict in ideal_verdicts:
                if 'verification object' not in ideal_verdict and 'rule specification' in ideal_verdict \
                        and ideal_verdict['rule specification'] == rule_specification:
                    is_matched = True
                    break

        # If nothing of above matched.
        if not is_matched:
            for ideal_verdict in ideal_verdicts:
                if 'verification object' not in ideal_verdict and 'rule specification' not in ideal_verdict:
                    is_matched = True
                    break

        if not is_matched:
            raise ValueError(
                'Could not match ideal verdict for verification object "{0}" and rule specification "{1}"'
                .format(verification_object, rule_specification))

        # Refine name (it can contain hashes if several modules or/and rule specifications are checked within one
        # sub-job).
        name_suffix = os.path.join(verification_object, rule_specification)\
            if verification_object and rule_specification else ''

        return name_suffix, {
            'verdict': verification_status['verdict'],
            'ideal verdict': ideal_verdict['ideal verdict'],
            'comment': ideal_verdict.get('comment')
        }

    def __process_validation_results(self, name, verification_result):
        # Relate verificaiton results on commits before and after corresponding bug fixes if so.
        # Without this we won't be able to reliably iterate over data since it is multiprocessing.Manager().dict().
        # Data is intended to keep verification results that weren't bound still. For such the results
        # we will need to update corresponding data sent before.
        data = self.data.copy()

        # Try to find out previous verification result. Commit hash before/after corresponding bug fix
        # is considered to be "hash~"/"hash" or v.v. Also it is taken into account that all commit
        # hashes have exactly 12 symbols.
        is_prev_found = False
        for prev_name, prev_verification_result in data.items():
            if name[:12] == prev_name[:12] and (name[13:] == prev_name[12:]
                                                if len(name) > 12 and name[12] == '~'
                                                else name[12:] == prev_name[13:]):
                is_prev_found = True
                break

        bug_verification_result = None
        bug_fix_verification_result = None
        if verification_result['ideal verdict'] == 'unsafe':
            bug_name = name
            bug_verification_result = verification_result

            if is_prev_found:
                if prev_verification_result['ideal verdict'] != 'safe':
                    raise ValueError(
                        'Ideal verdict for bug "{0}" after fix is "{1}" ("safe" is expected)'
                        .format(bug_name, prev_verification_result['ideal verdict']))

                bug_fix_verification_result = prev_verification_result
        elif verification_result['ideal verdict'] == 'safe':
            bug_fix_verification_result = verification_result

            if is_prev_found:
                bug_name = prev_name

                if prev_verification_result['ideal verdict'] != 'unsafe':
                    raise ValueError(
                        'Ideal verdict for bug "{0}" before fix is "{1}" ("unsafe" is expected)'
                        .format(bug_name, prev_verification_result['ideal verdict']))

                bug_verification_result = prev_verification_result
            else:
                # Verification result after bug fix was found while verification result before bug fix
                # wasn't found yet. So construct bug name on the basis of bug fix name. To do that
                # either remove or add "~" after commit hash.
                if name[12] == '~':
                    bug_name = name[:12] + name[13:]
                else:
                    bug_name = name[:12] + '~' + name[12:]
        else:
            raise ValueError('Ideal verdict is "{0}" (either "safe" or "unsafe" is expected)'
                             .format(verification_result['ideal verdict']))

        validation_status_msg = 'Verdict for bug "{0}"'.format(bug_name)

        new_verification_result = {}

        if bug_verification_result:
            new_verification_result.update({'before fix': bug_verification_result})
            validation_status_msg += ' before fix is "{0}"{1}'.format(
                bug_verification_result['verdict'],
                ' ("{0}")'.format(bug_verification_result['comment'])
                if bug_verification_result['comment']
                else '')

        if bug_fix_verification_result:
            new_verification_result.update({'after fix': bug_fix_verification_result})
            if bug_verification_result:
                validation_status_msg += ','
            validation_status_msg += ' after fix is "{0}"{1}'.format(
                bug_fix_verification_result['verdict'],
                ' ("{0}")'.format(
                    bug_fix_verification_result['comment'])
                if bug_fix_verification_result['comment'] else '')

        self.logger.info(validation_status_msg)

        if is_prev_found:
            # We don't need to keep previously obtained verification results since we found both
            # verification results before and after bug fix.
            del self.data[prev_name]
        else:
            # Keep obtained verification results to relate them later.
            self.data.update({name: verification_result})

        return bug_name, new_verification_result
