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
import zipfile

import core.utils
import core.components
import core.progress
import core.vrp.coverage_parser


JOB_FORMAT = 1
JOB_ARCHIVE = 'job.zip'


def start_jobs(core_obj, locks, vals):
    core_obj.logger.info('Check how many jobs we need to start and setup them')

    core_obj.logger.info('Extract job archive "{0}" to directory "{1}"'.format(JOB_ARCHIVE, 'job'))
    with zipfile.ZipFile(JOB_ARCHIVE) as ZipFile:
        ZipFile.extractall('job')

    core_obj.logger.info('Get job class')
    with open(os.path.join('job', 'class'), encoding='utf8') as fp:
        job_type = fp.read()
    core_obj.logger.debug('Job class is "{0}"'.format(job_type))

    common_components_conf = __get_common_components_conf(core_obj.logger, core_obj.conf)
    core_obj.logger.info("Start results arranging and reporting subcomponent")

    if 'Common' in common_components_conf and 'Sub-jobs' not in common_components_conf:
        raise KeyError('You can not specify common sub-jobs configuration without sub-jobs themselves')

    if 'Common' in common_components_conf:
        common_components_conf.update(common_components_conf['Common'])
        del (common_components_conf['Common'])

    subcomponents = []
    try:
        queues_to_terminate = []

        pc = core.progress.PW(core_obj.conf, core_obj.logger, core_obj.ID, core_obj.callbacks,
                              core_obj.mqs, locks, vals, separate_from_parent=False,
                              include_child_resources=True, session=core_obj.session,
                              total_subjobs=(len(common_components_conf['Sub-jobs'])
                                              if 'Sub-jobs' in common_components_conf else 0))
        pc.start()
        subcomponents.append(pc)

        if 'collect total code coverage' in common_components_conf and \
                common_components_conf['collect total code coverage']:
            cr = JCR(core_obj.conf, core_obj.logger, core_obj.ID, core_obj.callbacks, core_obj.mqs,
                     locks, vals, separate_from_parent=False, include_child_resources=True,
                     queues_to_terminate=queues_to_terminate)
            cr.start()
            subcomponents.append(cr)

        if 'Sub-jobs' in common_components_conf:
            if __check_ideal_verdicts(common_components_conf):
                ra = RA(core_obj.conf, core_obj.logger, core_obj.ID, core_obj.callbacks, core_obj.mqs,
                        locks, vals, separate_from_parent=False, include_child_resources=True,
                        job_type=job_type, queues_to_terminate=queues_to_terminate)
                ra.start()
                subcomponents.append(ra)

            core_obj.logger.info('Decide sub-jobs')
            sub_job_solvers_num = core.utils.get_parallel_threads_num(core_obj.logger, common_components_conf,
                                                                      'Sub-jobs processing')
            core_obj.logger.debug('Sub-jobs will be decided in parallel by "{0}" solvers'.format(sub_job_solvers_num))
            __solve_sub_jobs(core_obj, locks, vals, common_components_conf, job_type,
                             subcomponents + [core_obj.uploading_reports_process])
        else:
            # Klever Core working directory is used for the only sub-job that is job itcore.
            job = Job(
                core_obj.conf, core_obj.logger, core_obj.ID, core_obj.callbacks, core_obj.mqs,
                locks, vals,
                id=core_obj.ID,
                work_dir=os.path.join(os.path.curdir, 'job'),
                separate_from_parent=True,
                include_child_resources=False,
                job_type=job_type,
                components_common_conf=common_components_conf)
            core.components.launch_workers(core_obj.logger, [job], subcomponents + [core_obj.uploading_reports_process])
            core_obj.logger.info("Finished main job")
    except Exception:
        for p in subcomponents:
            if p.is_alive():
                p.terminate()
        raise

    # Stop queues
    for queue in queues_to_terminate:
        core_obj.logger.info('Terminate queue {!r}'.format(queue))
        core_obj.mqs[queue].put(None)
    # Stop subcomponents
    core_obj.logger.info('Jobs are solved, waiting for subcomponents')
    for subcomponent in subcomponents:
        subcomponent.join()
    core_obj.logger.info('Jobs and arranging results reporter finished')


def __check_ideal_verdicts(conf):
    # Check that configuration has ideal verdicts sets for at least one sub-job
    if 'ideal verdicts' in conf:
        return True
    if 'Sub-jobs' in conf:
        for sj in conf['Sub-jobs']:
            if 'ideal verdicts' in sj:
                return True
    return False


def __get_common_components_conf(logger, conf):
    logger.info('Get components common configuration')

    with open(core.utils.find_file_or_dir(logger, os.path.curdir, 'job.json'), encoding='utf8') as fp:
        components_common_conf = json.load(fp)

    # Add complete Klever Core configuration itself to components configuration since almost all its attributes will
    # be used somewhere in components.
    components_common_conf.update(conf)

    if components_common_conf['keep intermediate files']:
        if os.path.isfile('components common conf.json'):
            raise FileExistsError(
                'Components common configuration file "components common conf.json" already exists')
        logger.debug('Create components common configuration file "components common conf.json"')
        with open('components common conf.json', 'w', encoding='utf8') as fp:
            json.dump(components_common_conf, fp, ensure_ascii=False, sort_keys=True, indent=4)

    return components_common_conf


def __solve_sub_jobs(core_obj, locks, vals, components_common_conf, job_type, subcomponents):
    sub_jobs = []

    def constructor(number):
        # Sub-job configuration is based on common sub-jobs configuration.
        sub_job_components_common_conf = copy.deepcopy(components_common_conf)
        del (sub_job_components_common_conf['Sub-jobs'])
        sub_job_concrete_conf = core.utils.merge_confs(sub_job_components_common_conf,
                                                       components_common_conf['Sub-jobs'][number])

        core_obj.logger.info('Get sub-job name and type')
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

        if job_type == 'Validation on commits in Linux kernel Git repositories':
            commit = sub_job_concrete_conf['Linux kernel']['Git repository']['commit']
            if len(commit) != 12 and (len(commit) != 13 or commit[12] != '~'):
                raise ValueError(
                    'Commit hashes should have 12 symbols and optional "~" at the end ("{0}" is given)'
                    .format(commit))

            sub_job_id_prefix = os.path.join(commit, external_modules)
        elif job_type == 'Verification of Linux kernel modules':
            sub_job_id_prefix = os.path.join(str(number), external_modules)
        else:
            raise NotImplementedError('Job class "{0}" is not supported'.format(job_type))

        sub_job_id = os.path.join(sub_job_id_prefix, modules_hash, rule_specs_hash)
        sub_job_work_dir = os.path.join(sub_job_id_prefix, modules_hash, re.sub(r'\W', '-', rule_specs_hash))
        core_obj.logger.debug('Sub-job identifier and type are "{0}" and "{1}"'.format(sub_job_id, job_type))

        for sub_job in sub_jobs:
            if sub_job.id == sub_job_id:
                raise ValueError('Several sub-jobs have the same identifier "{0}"'.format(sub_job_id))

        job = Subjob(
            core_obj.conf, core_obj.logger, core_obj.ID, core_obj.callbacks, core_obj.mqs,
            locks, vals,
            id=sub_job_id,
            work_dir=sub_job_work_dir,
            attrs=[{'name': sub_job_id}],
            separate_from_parent=True,
            include_child_resources=False,
            job_type=job_type,
            components_common_conf=sub_job_concrete_conf,
            id_prefix=sub_job_id_prefix)

        sub_jobs.append(job)

        return job

    core_obj.logger.info('Start job sub-jobs')
    sub_job_solvers_num = core.utils.get_parallel_threads_num(core_obj.logger, components_common_conf,
                                                              'Sub-jobs processing')
    core_obj.logger.debug('Sub-jobs will be decided in parallel by "{0}" solvers'.format(sub_job_solvers_num))

    subjob_queue = multiprocessing.Queue()
    # Initialize queue first
    core_obj.logger.debug('Initialize workqueue with sub-job identifiers')
    for num in range(len(components_common_conf['Sub-jobs'])):
        subjob_queue.put(num)
    subjob_queue.put(None)

    # Then run jobs
    core_obj.logger.debug('Start sub-jobs pull of workers')
    core.components.launch_queue_workers(core_obj.logger, subjob_queue, constructor, sub_job_solvers_num,
                                         components_common_conf['ignore failed sub-jobs'], subcomponents)


class RA(core.components.Component):

    def __init__(self, conf, logger, parent_id, callbacks, mqs, locks, vals, id=None, work_dir=None, attrs=None,
                 separate_from_parent=True, include_child_resources=False, job_type=None, queues_to_terminate=None):
        super(RA, self).__init__(conf, logger, parent_id, callbacks, mqs, locks, vals, id, work_dir, attrs,
                                 separate_from_parent, include_child_resources)
        self.job_type = job_type
        self.data = dict()

        # Initialize callbacks
        self.mqs['verification statuses'] = multiprocessing.Queue()
        queues_to_terminate.append('verification statuses')
        self.__set_callbacks()

    def report_results(self):
        # Process exceptions like for uploading reports.
        os.mkdir('results')

        while True:
            verification_status = self.mqs['verification statuses'].get()

            if verification_status is None:
                self.logger.debug('Verification statuses message queue was terminated')
                self.mqs['verification statuses'].close()
                break

            # Block several sub-jobs from each other to reliably produce outcome.
            id_prefix, id_suffix, verification_result = self.__match_ideal_verdict(verification_status)

            task_id = os.path.join(id_prefix, id_suffix)

            if self.job_type == 'Verification of Linux kernel modules':
                self.logger.info('Ideal/obtained verdict for test "{0}" is "{1}"/"{2}"{3}'.format(
                    id, verification_result['ideal verdict'], verification_result['verdict'],
                    ' ("{0}")'.format(verification_result['comment'])
                    if verification_result['comment'] else ''))
            elif self.job_type == 'Validation on commits in Linux kernel Git repositories':
                task_id, verification_result = self.__process_validation_results(task_id, verification_result)
            else:
                raise NotImplementedError('Job class {!r} is not supported'.format(self.job_type))

            results_dir = os.path.join('results', re.sub(r'/', '-', task_id))
            os.makedirs(results_dir)

            core.utils.report(self.logger,
                              'data',
                              {
                                  'id': self.parent_id,
                                  'data': {task_id: verification_result}
                              },
                              self.mqs['report files'],
                              self.vals['report id'],
                              self.conf['main working directory'],
                              results_dir)

    main = report_results

    def __set_callbacks(self):

        def after_plugin_fail_processing(context):
            context.mqs['verification statuses'].put({
                'verification object': context.verification_object,
                'rule specification': context.rule_specification,
                'verdict': 'non-verifier unknown',
                'id prefix': context.conf['job identifier prefix'],
                'ideal verdicts': context.conf['ideal verdicts']
            })

        def after_process_failed_task(context):
            context.mqs['verification statuses'].put({
                'verification object': context.verification_object,
                'rule specification': context.rule_specification,
                'verdict': context.verdict,
                'id prefix': context.conf['job identifier prefix'],
                'ideal verdicts': context.conf['ideal verdicts']
            })

        def after_process_single_verdict(context):
            context.mqs['verification statuses'].put({
                'verification object': context.verification_object,
                'rule specification': context.rule_specification,
                'verdict': context.verdict,
                'id prefix': context.conf['job identifier prefix'],
                'ideal verdicts': context.conf['ideal verdicts']
            })

        core.components.set_component_callbacks(self.logger, type(self),
                                                (
                                                    after_plugin_fail_processing,
                                                    after_process_single_verdict,
                                                    after_process_failed_task
                                                ))

    @staticmethod
    def __match_ideal_verdict(verification_status):
        verification_object = verification_status['verification object']
        rule_specification = verification_status['rule specification']
        id_prefix = verification_status['id prefix']
        ideal_verdicts = verification_status['ideal verdicts']

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
                        and ideal_verdict['verification object'] == verification_object:
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
        id_suffix = os.path.join(verification_object, rule_specification)\
            if verification_object and rule_specification else ''

        return id_prefix, id_suffix, {
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


class JCR(core.components.Component):

    def __init__(self, conf, logger, parent_id, callbacks, mqs, locks, vals, id=None, work_dir=None, attrs=None,
                 separate_from_parent=True, include_child_resources=False, queues_to_terminate=None):
        super(JCR, self).__init__(conf, logger, parent_id, callbacks, mqs, locks, vals, id, work_dir,
                                  attrs, separate_from_parent, include_child_resources)

        # This function adds callbacks and it should work until we call it in the new process
        self.mqs['rule specifications and coverage info files'] = multiprocessing.Queue()
        queues_to_terminate.append('rule specifications and coverage info files')
        self.__set_callbacks()
        self.coverage = dict()

    def collect_total_coverage(self):
        total_coverage_infos = dict()
        os.mkdir('total coverages')
        self.logger.debug("Begin collecting coverage")
        while True:
            coverage_info = self.mqs['rule specifications and coverage info files'].get()

            if coverage_info is None:
                self.logger.debug('Rule specification coverage info files message queue was terminated')
                self.mqs['rule specifications and coverage info files'].close()
                break

            if 'coverage info file' in coverage_info:
                if coverage_info['job id'] not in total_coverage_infos:
                    total_coverage_infos[coverage_info['job id']] = dict()
                rule_spec = coverage_info['rule specification']
                total_coverage_infos[coverage_info['job id']].setdefault(rule_spec, {})

                with open(os.path.join(self.conf['main working directory'],
                                       coverage_info['coverage info file']), encoding='utf8') as fp:
                    loaded_coverage_info = json.load(fp)

                for file_name, coverage_info_element in loaded_coverage_info.items():
                    total_coverage_infos[coverage_info['job id']][rule_spec].setdefault(file_name, [])
                    total_coverage_infos[coverage_info['job id']][rule_spec][file_name] += coverage_info_element
            else:
                job_id = coverage_info['job id']
                self.logger.debug("Coverage of the job {!r}".format(job_id))

                total_coverages = dict()
                for rule_spec, coverage_info in total_coverage_infos[job_id].items():
                    total_coverage_dir = os.path.join('total coverages', re.sub(r'/', '-', job_id),
                                                      re.sub(r'/', '-', rule_spec))
                    os.makedirs(total_coverage_dir)

                    total_coverage_file = os.path.join(total_coverage_dir, 'coverage.json')
                    if os.path.isfile(total_coverage_file):
                        raise FileExistsError('Total coverage file "{0}" already exists'.format(total_coverage_file))
                    arcnames = {total_coverage_file: 'coverage.json'}

                    coverage = core.vrp.coverage_parser.LCOV.get_coverage(coverage_info)

                    with open(total_coverage_file, 'w', encoding='utf8') as fp:
                        json.dump(coverage, fp, ensure_ascii=True, sort_keys=True, indent=4)

                    arcnames.update({info[0]['file name']: info[0]['arcname'] for info in coverage_info.values()})

                    total_coverages[rule_spec] = core.utils.ReportFiles([total_coverage_file] +
                                                                        list(arcnames.keys()), arcnames)

                if len(total_coverages.keys()) > 0:
                    core.utils.report(self.logger,
                                      'job coverage',
                                      {
                                          'id': job_id,
                                          'coverage': total_coverages
                                      },
                                      self.mqs['report files'],
                                      self.vals['report id'],
                                      self.conf['main working directory'],
                                      os.path.join('total coverages', re.sub(r'/', '-', job_id)))
                    del total_coverage_infos[job_id]
                else:
                    self.logger.warning('There is no coverage to send for Job {!r}'.format(job_id))
        self.logger.info("Finish coverage reporting")

    main = collect_total_coverage

    def __set_callbacks(self):

        def after_process_finished_task(context):
            if os.path.isfile('coverage info.json'):
                context.mqs['rule specifications and coverage info files'].put({
                    'job id': context.conf['job identifier'],
                    'rule specification': context.rule_specification,
                    'coverage info file': os.path.relpath('coverage info.json',
                                                          context.conf['main working directory'])
                })

        def after_launch_sub_job_components(context):
            context.mqs['rule specifications and coverage info files'].put({
                'job id': context.id
            })

        core.components.set_component_callbacks(self.logger, type(self),
                                                (
                                                    after_process_finished_task,
                                                    after_launch_sub_job_components
                                                ))


class Job(core.components.Component):
    SUPPORTED_JOB_TYPES = [
        'Verification of Linux kernel modules',
        'Validation on commits in Linux kernel Git repositories'
    ]
    JOB_CLASS_COMPONENTS = [
        'LKBCE',
        'LKVOG',
        'VTG',
        'VRP'
    ]

    def __init__(self, conf, logger, parent_id, callbacks, mqs, locks, vals, id=None, work_dir=None, attrs=None,
                 separate_from_parent=True, include_child_resources=False, job_type=None, components_common_conf=None,
                 id_prefix=None):
        super(Job, self).__init__(conf, logger, parent_id, callbacks, mqs, locks, vals, id, work_dir, attrs,
                                  separate_from_parent, include_child_resources)
        self.id_prefix = id_prefix
        self.job_type = job_type
        self.common_components_conf = components_common_conf

        self.components = []
        self.component_processes = []

    def decide_job(self):
        self.logger.info('Decide sub-job of type "{0}" with identifier "{1}"'.format(self.job_type, self.id))

        # All sub-job names should be unique, so there shouldn't be any problem to create directories with these names
        # to be used as working directories for corresponding sub-jobs. Jobs without sub-jobs don't have names.
        if self.id_prefix:
            self.common_components_conf['job identifier prefix'] = self.id_prefix
        self.common_components_conf['job identifier'] = self.id

        if self.id_prefix:
            if self.common_components_conf['keep intermediate files']:
                if os.path.isfile('conf.json'):
                    raise FileExistsError(
                        'Components configuration file "conf.json" already exists')
                self.logger.debug('Create components configuration file "conf.json"')
                with open('conf.json', 'w', encoding='utf8') as fp:
                    json.dump(self.common_components_conf, fp, ensure_ascii=False, sort_keys=True, indent=4)

        self.__get_sub_job_components()
        self.callbacks = core.components.get_component_callbacks(self.logger, [type(self)] + self.components,
                                                                 self.common_components_conf)
        self.launch_sub_job_components()
        self.logger.info("All components finished")

    main = decide_job

    def __get_sub_job_components(self):
        self.logger.info('Get components for sub-job of type "{0}" with identifier "{1}"'.
                         format(self.job_type, self.id))

        if self.job_type not in self.SUPPORTED_JOB_TYPES:
            raise NotImplementedError('Job class "{0}" is not supported'.format(self.job_type))

        self.components = [getattr(importlib.import_module('.{0}'.format(component.lower()), 'core'), component) for
                           component in self.JOB_CLASS_COMPONENTS]

        self.logger.debug('Components to be launched: "{0}"'.format(
            ', '.join([component.__name__ for component in self.components])))

    def launch_sub_job_components(self):
        """Has callbacks"""
        self.logger.info('Launch components for sub-job of type "{0}" with identifier "{1}"'.
                         format(self.job_type, self.id))
        for component in self.components:
            p = component(self.common_components_conf, self.logger, self.id, self.callbacks, self.mqs,
                          self.locks, self.vals, separate_from_parent=True)
            self.component_processes.append(p)

        core.components.launch_workers(self.logger, self.component_processes)


class Subjob(Job):

    def decide_subjob(self):
        try:
            self.decide_job()
            self.vals['subjobs progress'][self.id] = 'finished'
        except Exception:
            self.vals['subjobs progress'][self.id] = 'failed'
            raise

    main = decide_subjob
