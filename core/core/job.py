#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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

import copy
import importlib
import json
import multiprocessing
import os
import tarfile
import time
import zipfile

import core.utils
import core.components
from core.progress import PW
from core.coverage import JCR


JOB_FORMAT = 1
JOB_ARCHIVE = 'job.zip'
NECESSARY_FILES = [
    'job.json',
    'tasks.json',
    'program fragmentation.json',
    'verifier profiles.json',
    'specifications/base.json'
]


def start_jobs(core_obj, vals):
    core_obj.logger.info('Check how many jobs we need to start and setup them')

    core_obj.logger.info('Extract job archive "{0}" to directory "{1}"'.format(JOB_ARCHIVE, 'job'))
    with zipfile.ZipFile(JOB_ARCHIVE) as ZipFile:
        ZipFile.extractall('job')

    for configuration_file in NECESSARY_FILES:
        path = core.utils.find_file_or_dir(core_obj.logger, os.path.curdir, configuration_file)
        with open(path, 'r', encoding='utf8') as fp:
            try:
                json.load(fp)
            except json.decoder.JSONDecodeError as err:
                raise ValueError("Cannot parse JSON configuration file {!r}: {}".format(configuration_file, err)) \
                    from None

    common_components_conf = __get_common_components_conf(core_obj.logger, core_obj.conf)
    core_obj.logger.info("Start results arranging and reporting subcomponent")

    core_obj.logger.info('Get job class')
    if 'Class' in common_components_conf:
        job_type = common_components_conf['Class']
    else:
        raise KeyError('Specify job class within job.json')
    core_obj.logger.debug('Job class is "{0}"'.format(job_type))

    if 'Common' in common_components_conf and 'Sub-jobs' not in common_components_conf:
        raise KeyError('You can not specify common sub-jobs configuration without sub-jobs themselves')

    if 'Common' in common_components_conf:
        common_components_conf.update(common_components_conf['Common'])
        del (common_components_conf['Common'])

    # Save for next components specifications desc and verifiers profiles
    common_components_conf['requirements DB'] = os.path.abspath(
        core.utils.find_file_or_dir(core_obj.logger, os.path.curdir, 'specifications/base.json'))
    common_components_conf['verifier profiles DB'] = os.path.abspath(
        core.utils.find_file_or_dir(core_obj.logger, os.path.curdir, 'verifier profiles.json'))
    common_components_conf['program fragmentation DB'] = os.path.abspath(
        core.utils.find_file_or_dir(core_obj.logger, os.path.curdir, 'program fragmentation.json'))

    subcomponents = []
    try:
        queues_to_terminate = []

        pc = PW(core_obj.conf, core_obj.logger, core_obj.ID, core_obj.callbacks, core_obj.mqs, vals,
                separate_from_parent=False, include_child_resources=True, session=core_obj.session,
                total_subjobs=(len(common_components_conf['Sub-jobs']) if 'Sub-jobs' in common_components_conf else 0))
        pc.start()
        subcomponents.append(pc)

        if 'collect total code coverage' in common_components_conf and \
                common_components_conf['collect total code coverage']:
            def after_process_finished_task(context):
                coverage_info_file = os.path.join(context.conf['main working directory'], context.coverage_info_file)
                if os.path.isfile(coverage_info_file):
                    context.mqs['requirements and coverage info files'].put({
                        'sub-job identifier': context.conf['sub-job identifier'],
                        'requirement': context.requirement,
                        'coverage info file': coverage_info_file
                    })

            def after_launch_sub_job_components(context):
                context.logger.debug('Put "{0}" sub-job identifier for finish coverage'.format(context.id))
                context.mqs['requirements and coverage info files'].put({
                    'sub-job identifier': context.common_components_conf['sub-job identifier']
                })

            cr = JCR(core_obj.conf, core_obj.logger, core_obj.ID, core_obj.callbacks, core_obj.mqs, vals,
                     separate_from_parent=False, include_child_resources=True, queues_to_terminate=queues_to_terminate)
            # This can be done only in this module otherwise callbacks will be missed
            core.components.set_component_callbacks(core_obj.logger, Job,
                                                    [after_launch_sub_job_components, after_process_finished_task])
            cr.start()
            subcomponents.append(cr)

        if 'Sub-jobs' in common_components_conf:
            if __check_ideal_verdicts(common_components_conf):
                ra = RA(core_obj.conf, core_obj.logger, core_obj.ID, core_obj.callbacks, core_obj.mqs,
                        vals, separate_from_parent=False, include_child_resources=True,
                        job_type=job_type, queues_to_terminate=queues_to_terminate)
                ra.start()
                subcomponents.append(ra)

            core_obj.logger.info('Decide sub-jobs')
            sub_job_solvers_num = core.utils.get_parallel_threads_num(core_obj.logger, common_components_conf,
                                                                      'Sub-jobs processing')
            core_obj.logger.debug('Sub-jobs will be decided in parallel by "{0}" solvers'.format(sub_job_solvers_num))
            __solve_sub_jobs(core_obj, vals, common_components_conf, job_type,
                             subcomponents + [core_obj.uploading_reports_process])
        else:
            job = Job(
                core_obj.conf, core_obj.logger, core_obj.ID, core_obj.callbacks, core_obj.mqs,
                vals,
                id='-',
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
        logger.debug('Create components common configuration file "components common conf.json"')
        with open('components common conf.json', 'w', encoding='utf8') as fp:
            json.dump(components_common_conf, fp, ensure_ascii=False, sort_keys=True, indent=4)

    return components_common_conf


def __solve_sub_jobs(core_obj, vals, components_common_conf, job_type, subcomponents):
    def constructor(number):
        # Sub-job configuration is based on common sub-jobs configuration.
        sub_job_components_common_conf = copy.deepcopy(components_common_conf)
        del (sub_job_components_common_conf['Sub-jobs'])
        sub_job_concrete_conf = core.utils.merge_confs(sub_job_components_common_conf,
                                                       components_common_conf['Sub-jobs'][number])

        job = SubJob(
            core_obj.conf, core_obj.logger, core_obj.ID, core_obj.callbacks, core_obj.mqs,
            vals,
            id=str(number),
            work_dir=str(number),
            attrs=[{
                'name': 'Sub-job identifier',
                'value': str(number),
                # Sub-jobs are intended for combining several relatively small jobs together into one large job. For
                # instance, this abstraction is useful for testing and validation. But most likely most of users do not
                # need even to know about them.
                # From ancient time we tried to assign nice names to sub-jobs to distinguish them, in particular to be
                # able to compare corresponding verification results. These names were based on sub-job configurations,
                # e.g. they included commit hashes, requirement identifiers, module names, etc. Such the approach
                # turned out to be inadequate since we had to add more and more information to sub-job names that
                # involves source code changes and results in large working directories that look like these names.
                # After all we decided to use sub-job ordinal numbers to distinguish them uniqly (during a some time
                # old style names were used in addition to these ordinal numbers). The only bad news is that in case of
                # any changes in a global arrangment of sub-jobs, such as a new sub-job is added somewhere in the middle
                # or an old sub-job is removed, one is not able to compare verification results as it was with pretty
                # names since correspondence of ordinal numbers breaks.
                'compare': True,
            }],
            separate_from_parent=True,
            include_child_resources=False,
            job_type=job_type,
            components_common_conf=sub_job_concrete_conf
        )

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

    def __init__(self, conf, logger, parent_id, callbacks, mqs, vals, id=None, work_dir=None, attrs=None,
                 separate_from_parent=True, include_child_resources=False, job_type=None, queues_to_terminate=None):
        super(RA, self).__init__(conf, logger, parent_id, callbacks, mqs, vals, id, work_dir, attrs,
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

            id_suffix, verification_result = self.__match_ideal_verdict(verification_status)
            sub_job_id = verification_status['sub-job identifier']

            if self.job_type == 'Verification of Linux kernel modules':
                # For testing jobs there can be several verification tasks for each sub-job, so for uniqueness of
                # tasks and directories add identifier suffix in addtition.
                task_id = os.path.join(sub_job_id, id_suffix)
                self.logger.info('Ideal/obtained verdict for test "{0}" is "{1}"/"{2}"{3}'.format(
                    task_id, verification_result['ideal verdict'], verification_result['verdict'],
                    ' ("{0}")'.format(verification_result['comment'])
                    if verification_result['comment'] else ''))
                results_dir = os.path.join('results', task_id)
            elif self.job_type == 'Validation on commits in Linux kernel Git repositories':
                # For validation jobs we can't refer to sub-job identifier for additional identification of verification
                # results because of most likely we will consider pairs of sub-jobs before and after corresponding bug
                # fixes.
                task_id, verification_result = self.__process_validation_results(verification_result,
                                                                                 verification_status['data'], id_suffix)
                # For validation jobs sub-job identifiers guarantee uniqueness for naming directories since there is
                # the only verification task for each sub-job.
                results_dir = os.path.join('results', sub_job_id)
            else:
                raise NotImplementedError('Job class {!r} is not supported'.format(self.job_type))

            os.makedirs(results_dir)

            core.utils.report(self.logger,
                              'patch',
                              {
                                  'identifier': self.parent_id,
                                  'data': {task_id: verification_result}
                              },
                              self.mqs['report files'],
                              self.vals['report id'],
                              self.conf['main working directory'],
                              results_dir)

    main = report_results

    def __set_callbacks(self):

        # TODO: these 3 functions are very similar, so, they should be merged.
        def after_plugin_fail_processing(context):
            context.mqs['verification statuses'].put({
                'program fragment': context.program_fragment['id'],
                'requirement': context.requirement,
                'verdict': 'non-verifier unknown',
                'sub-job identifier': context.conf['sub-job identifier'],
                'ideal verdicts': context.conf['ideal verdicts'],
                'data': context.conf.get('data')
            })

        def after_process_failed_task(context):
            context.mqs['verification statuses'].put({
                'program fragment': context.program_fragment,
                'requirement': context.requirement,
                'verdict': context.verdict,
                'sub-job identifier': context.conf['sub-job identifier'],
                'ideal verdicts': context.conf['ideal verdicts'],
                'data': context.conf.get('data')
            })

        def after_process_single_verdict(context):
            context.mqs['verification statuses'].put({
                'program fragment': context.program_fragment,
                'requirement': context.requirement,
                'verdict': context.verdict,
                'sub-job identifier': context.conf['sub-job identifier'],
                'ideal verdicts': context.conf['ideal verdicts'],
                'data': context.conf.get('data')
            })

        core.components.set_component_callbacks(self.logger, type(self),
                                                (
                                                    after_plugin_fail_processing,
                                                    after_process_single_verdict,
                                                    after_process_failed_task
                                                ))

    @staticmethod
    def __match_ideal_verdict(verification_status):
        def match_attr(attr, ideal_attr):
            if ideal_attr and ((isinstance(ideal_attr, str) and attr == ideal_attr) or
                               (isinstance(ideal_attr, list) and attr in ideal_attr)):
                return True

            return False

        program_fragment = verification_status['program fragment']
        requirement = verification_status['requirement']
        ideal_verdicts = verification_status['ideal verdicts']

        matched_ideal_verdict = None

        # Try to match exactly by both program fragment and requirement.
        for ideal_verdict in ideal_verdicts:
            if match_attr(program_fragment, ideal_verdict.get('program fragment')) \
                    and match_attr(requirement, ideal_verdict.get('requirement')):
                matched_ideal_verdict = ideal_verdict
                break

        # Try to match just by program fragment.
        if not matched_ideal_verdict:
            for ideal_verdict in ideal_verdicts:
                if 'requirement' not in ideal_verdict \
                        and match_attr(program_fragment, ideal_verdict.get('program fragment')):
                    matched_ideal_verdict = ideal_verdict
                    break

        # Try to match just by requirement specification.
        if not matched_ideal_verdict:
            for ideal_verdict in ideal_verdicts:
                if 'program fragment' not in ideal_verdict \
                        and match_attr(requirement, ideal_verdict.get('requirement')):
                    matched_ideal_verdict = ideal_verdict
                    break

        # If nothing of above matched.
        if not matched_ideal_verdict:
            for ideal_verdict in ideal_verdicts:
                if 'program fragment' not in ideal_verdict and 'requirement' not in ideal_verdict:
                    matched_ideal_verdict = ideal_verdict
                    break

        if not matched_ideal_verdict:
            raise ValueError(
                'Could not match ideal verdict for program fragment "{0}" and requirement "{1}"'
                .format(program_fragment, requirement))

        # This suffix will help to distinguish sub-jobs easier.
        id_suffix = os.path.join(program_fragment, requirement)\
            if program_fragment and requirement else ''

        return id_suffix, {
            'verdict': verification_status['verdict'],
            'ideal verdict': matched_ideal_verdict['ideal verdict'],
            'comment': matched_ideal_verdict.get('comment')
        }

    def __process_validation_results(self, verification_result, data, id_suffix):
        # Relate verification results on commits before and after corresponding bug fixes if so.
        # Data (variable "self.data") is intended to keep verification results that weren't bound still. For such the
        # results we will need to update corresponding data sent before.

        # Verification results can be bound on the basis of data (parameter "data").
        if not data or 'bug identifier' not in data:
            raise KeyError('Bug identifier is not specified for some sub-job of validation job')

        # Identifier suffix clarifies bug nature without preventing relation of verification results, so, just add it
        # to bug identifier. Sometimes just this concatenation actually serves as unique identifier, e.g. when a bug
        # identifier is just a commit hash, while an identifier suffix contains a program fragment and a requirement
        # specification.
        bug_id = os.path.join(data['bug identifier'], id_suffix)

        bug_verification_result = None
        bug_fix_verification_result = None
        if verification_result['ideal verdict'] == 'unsafe':
            bug_verification_result = verification_result

            if bug_id in self.data:
                bug_fix_verification_result = self.data[bug_id]
        elif verification_result['ideal verdict'] == 'safe':
            bug_fix_verification_result = verification_result

            if bug_id in self.data:
                bug_verification_result = self.data[bug_id]
        else:
            raise ValueError('Ideal verdict is "{0}" (either "safe" or "unsafe" is expected)'
                             .format(verification_result['ideal verdict']))

        validation_status_msg = 'Verdict for bug "{0}"'.format(bug_id)

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

        if bug_id in self.data:
            # We don't need to keep previously obtained verification results since we found both
            # verification results before and after bug fix.
            del self.data[bug_id]
        else:
            # Keep obtained verification results to relate them later.
            self.data.update({bug_id: verification_result})

        return bug_id, new_verification_result


class Job(core.components.Component):
    SUPPORTED_JOB_TYPES = [
        'Verification of userspace programs',
        'Verification of Linux kernel modules',
        'Validation on commits in Linux kernel Git repositories'
    ]
    JOB_CLASS_COMPONENTS = [
        'PFG',
        'VTG',
        'VRP'
    ]

    def __init__(self, conf, logger, parent_id, callbacks, mqs, vals, id=None, work_dir=None, attrs=None,
                 separate_from_parent=True, include_child_resources=False, job_type=None, components_common_conf=None):
        super(Job, self).__init__(conf, logger, parent_id, callbacks, mqs, vals, id, work_dir, attrs,
                                  separate_from_parent, include_child_resources)
        self.job_type = job_type
        self.common_components_conf = components_common_conf

        self.components = []
        self.component_processes = []

    def decide_job_or_sub_job(self):
        self.logger.info('Decide job/sub-job of type "{0}" with identifier "{1}"'.format(self.job_type, self.id))

        # This is required to associate verification results with particular sub-jobs.
        # Skip leading "/" since this identifier is used in os.path.join() that returns absolute path otherwise.
        self.common_components_conf['sub-job identifier'] = self.id[1:]

        # Check and set build base here since many Core components need it.
        self.__set_build_base()

        if self.common_components_conf['keep intermediate files']:
            self.logger.debug('Create components configuration file "conf.json"')
            with open('conf.json', 'w', encoding='utf8') as fp:
                json.dump(self.common_components_conf, fp, ensure_ascii=False, sort_keys=True, indent=4)

        self.__get_job_or_sub_job_components()
        self.callbacks = core.components.get_component_callbacks(self.logger, [type(self)] + self.components,
                                                                 self.common_components_conf)
        self.launch_sub_job_components()

        self.clean_dir = True
        self.logger.info("All components finished")
        if self.conf.get('collect total code coverage', None):
            self.logger.debug('Waiting for a collecting coverage')
            while not self.vals['coverage_finished'].get(self.common_components_conf['sub-job identifier'], True):
                time.sleep(1)
            self.logger.debug("Coverage collected")

    main = decide_job_or_sub_job

    def __set_build_base(self):
        if 'build base' not in self.common_components_conf:
            raise KeyError("Provide 'build base' configuration option to start verification")

        common_advice = 'please, fix "job.json" (attribute "build base")'
        common_advice += ' or/and deployment configuration file (attribute "Klever Build Bases")'

        # Try to find specified build base either in normal way or additionally in directory "build bases" that is
        # convenient to use when working with many build bases.
        try:
            build_base = core.utils.find_file_or_dir(self.logger, os.path.curdir,
                                                     self.common_components_conf['build base'])
        except FileNotFoundError:
            try:
                build_base = core.utils.find_file_or_dir(self.logger, os.path.curdir,
                                                         os.path.join('build bases',
                                                                      self.common_components_conf['build base']))
            except FileNotFoundError:
                raise FileNotFoundError(
                    'Specified build base "{0}" does not exist, {1}'.format(self.common_components_conf['build base'],
                                                                            common_advice)) from None

        # Extract build base from archive. There should not be any intermediate directories in archives.
        if os.path.isfile(build_base) and (tarfile.is_tarfile(build_base) or zipfile.is_zipfile(build_base)):
            if tarfile.is_tarfile(build_base):
                self.logger.debug('Build base "{0}" is provided in form of TAR archive'.format(build_base))
                with tarfile.open(build_base) as TarFile:
                    TarFile.extractall('build base')
            else:
                self.logger.debug('Build base "{0}" is provided in form of ZIP archive'.format(build_base))
                with zipfile.ZipFile(build_base) as zfp:
                    zfp.extractall('build base')

            # Directory contains extracted build base.
            extracted_from = ' extracted from "{0}"'.format(os.path.realpath(build_base))
            build_base = 'build base'
        else:
            extracted_from = ''

        # We need to specify absolute path to build base since it will be used in different Klever components. Besides,
        # this simplifies troubleshooting.
        build_base = os.path.realpath(build_base)

        if not os.path.isdir(build_base):
            raise FileExistsError('Build base "{0}" is not a directory, {1}'
                                  .format(build_base, extracted_from, common_advice))

        if not os.path.isfile(os.path.join(build_base, 'meta.json')):
            raise FileExistsError(
                'Directory "{0}"{1} is not a build base since it does not contain file "meta.json", {2}'
                .format(build_base, extracted_from, common_advice))

        self.common_components_conf['build base'] = build_base

        self.logger.debug('Klever components will use build base "{0}"'
                          .format(self.common_components_conf['build base']))

    def __get_job_or_sub_job_components(self):
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
                          self.vals, separate_from_parent=True)
            self.component_processes.append(p)

        core.components.launch_workers(self.logger, self.component_processes)


class SubJob(Job):

    def decide_sub_job(self):
        try:
            self.decide_job_or_sub_job()
            self.vals['subjobs progress'][self.id] = 'finished'
        except Exception:
            self.vals['subjobs progress'][self.id] = 'failed'
            raise

    main = decide_sub_job
