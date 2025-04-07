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

import copy
import importlib
import json
import multiprocessing
import os
import shutil
import tarfile
import time
import traceback
import zipfile

import yaml
from clade import Clade

import klever.core.utils
import klever.core.session
import klever.core.components
from klever.core.cross_refs import CrossRefs
from klever.core.progress import PW
from klever.core.coverage import JCR

JOB_FORMAT = 1
JOB_ARCHIVE = 'job.zip'
NECESSARY_FILES = [
    'job.json',
    'tasks.json',
    'verifier profiles.yml'
]
DEFAULT_ARCH = 'x86-64'
DEFAULT_ARCH_OPTS = {
    'ARM': {
        'CIF': {
            'cross compile prefix': 'arm-unknown-eabi-'
        },
        'CIL': {
            'machine': 'gcc_arm_32'
        },
        'Clade': {
            'preset': 'klever_linux_kernel_arm'
        }
    },
    'ARM64': {
        'CIF': {
            'cross compile prefix': 'aarch64_be-unknown-linux-gnu-'
        },
        # As above.
        'CIL': {
            'machine': 'gcc_arm_64'
        },
        'Clade': {
            'preset': 'klever_linux_kernel_arm'
        }
    },
    'x86-64': {
        'CIF': {
            'cross compile prefix': ''
        },
        'CIL': {
            'machine': 'gcc_x86_64'
        },
        # Hey! Everybody will use Linux kernel specific preset for Clade. Let's hope that it does not matter since at the
        # moment this is used just for getting cross references.
        'Clade': {
            'preset': 'klever_linux_kernel'
        }
    }
}
CODE_COVERAGE_DETAILS_MAP = {
    '0': 'Original C source files',
    '1': 'C source files including models',
    '2': 'All source files'
}


def start_jobs(core_obj, vals):
    core_obj.logger.info('Check how many jobs we need to start and setup them')

    core_obj.logger.info('Extract job archive "{0}" to directory "{1}"'.format(JOB_ARCHIVE, 'job'))
    with zipfile.ZipFile(JOB_ARCHIVE) as ZipFile:
        ZipFile.extractall('job')

    for configuration_file in NECESSARY_FILES:
        path = klever.core.utils.find_file_or_dir(core_obj.logger, os.path.curdir, configuration_file)
        with open(path, 'r', encoding='utf-8') as fp:
            if path.endswith('json'):
                try:
                    json.load(fp)
                except json.decoder.JSONDecodeError as err:
                    raise ValueError("Cannot parse JSON configuration file {!r}: {}".format(configuration_file, err)) \
                        from None
            elif path.endswith('yml') or path.endswith('yaml'):
                try:
                    yaml.safe_load(fp)
                except yaml.YAMLError as err:
                    raise ValueError("Cannot parse YAML configuration file {!r}: {}".format(configuration_file, err)) \
                        from None

    common_components_conf = __get_common_components_conf(core_obj.logger, core_obj.conf)
    core_obj.logger.info("Start results arranging and reporting subcomponent")

    core_obj.logger.info('Get project')
    if 'project' in common_components_conf:
        project = common_components_conf['project']
    else:
        raise KeyError('Specify attribute "project" within job.json')
    core_obj.logger.debug('Project is "{0}"'.format(project))

    # Save bases for components.
    common_components_conf['specifications dir'] = os.path.abspath(
        klever.core.utils.find_file_or_dir(core_obj.logger, os.path.curdir, 'specifications'))
    common_components_conf['specifications base'] = os.path.abspath(
        klever.core.utils.find_file_or_dir(core_obj.logger, os.path.curdir,
                                           os.path.join('specifications',
                                                        '{0}.yml'.format(common_components_conf['project']))))
    common_components_conf['verifier profiles base'] = os.path.abspath(
        klever.core.utils.find_file_or_dir(core_obj.logger, os.path.curdir, 'verifier profiles.yml'))
    common_components_conf['program fragments base'] = os.path.abspath(
        klever.core.utils.find_file_or_dir(core_obj.logger, os.path.curdir, 'fragmentation sets'))

    common_components_conf['code coverage details'] = CODE_COVERAGE_DETAILS_MAP[
        common_components_conf['code coverage details']]

    subcomponents = []
    try:
        queues_to_terminate = []

        pc = PW(core_obj.conf, core_obj.logger, core_obj.ID, core_obj.mqs, vals,
                len(common_components_conf['sub-jobs']) if 'sub-jobs' in common_components_conf else -1)
        pc.start()
        subcomponents.append(pc)

        # TODO: split collecting total code coverage for sub-jobs. Otherwise there is too much redundant data.
        if 'collect total code coverage' in common_components_conf and \
                common_components_conf['collect total code coverage']:

            vals['coverage src info'] = multiprocessing.Manager().dict()
            cr = JCR(common_components_conf, core_obj.logger, core_obj.ID, core_obj.mqs, vals,
                     queues_to_terminate)
            cr.start()
            subcomponents.append(cr)

        if 'extra results processing' in common_components_conf and common_components_conf['weight'] == '0':
            # data reports from REP are ignored in lightweight mode
            ra = REP(common_components_conf, core_obj.logger, core_obj.ID, core_obj.mqs, vals, queues_to_terminate)
            ra.start()
            subcomponents.append(ra)

        if 'sub-jobs' in common_components_conf:
            core_obj.logger.info('Decide sub-jobs')
            sub_job_solvers_num = klever.core.utils.get_parallel_threads_num(core_obj.logger, common_components_conf,
                                                                             'Sub-jobs processing')
            core_obj.logger.debug('Sub-jobs will be decided in parallel by "{0}" solvers'.format(sub_job_solvers_num))
            __solve_sub_jobs(core_obj, vals, common_components_conf,
                             subcomponents + [core_obj.uploading_reports_process])
        else:
            job = Job(
                core_obj.conf, core_obj.logger, core_obj.ID, core_obj.mqs,
                vals,
                'Job',
                os.path.join(os.path.curdir, 'job'),
                components_common_conf=common_components_conf)
            klever.core.components.launch_workers(core_obj.logger, [job], subcomponents +
                                                  [core_obj.uploading_reports_process])
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


def __get_common_components_conf(logger, conf):
    logger.info('Get components common configuration')

    with open(klever.core.utils.find_file_or_dir(logger, os.path.curdir, 'job.json'), encoding='utf-8') as fp:
        components_common_conf = json.load(fp)

    # Add architecture specific options. At the moment there are only default options but one may add dedicated
    # configuration files to jobs.
    if 'architecture' not in components_common_conf:
        components_common_conf['architecture'] = DEFAULT_ARCH
    if components_common_conf['architecture'] not in DEFAULT_ARCH_OPTS:
        raise ValueError("Klever does not support architecture {!r} yet, available options are: {}"
                         .format(components_common_conf['architecture'], ', '.join(DEFAULT_ARCH_OPTS.keys())))
    components_common_conf.update(DEFAULT_ARCH_OPTS[components_common_conf['architecture']])
    if 'cross compile prefix' in components_common_conf:
        components_common_conf['CIF']['cross compile prefix'] = components_common_conf['cross compile prefix']

    # Add complete Klever Core configuration itself to components configuration since almost all its attributes will
    # be used somewhere in components.
    components_common_conf.update(conf)

    if components_common_conf['keep intermediate files']:
        logger.debug('Create components common configuration file "components common conf.json"')
        with open('components common conf.json', 'w', encoding='utf-8') as fp:
            json.dump(components_common_conf, fp, ensure_ascii=False, sort_keys=True, indent=4)

    return components_common_conf


def __solve_sub_jobs(core_obj, vals, components_common_conf, subcomponents):
    def constructor(number):
        # Sub-job configuration is based on common sub-jobs configuration.
        sub_job_components_common_conf = copy.deepcopy(components_common_conf)
        del sub_job_components_common_conf['sub-jobs']
        sub_job_concrete_conf = klever.core.utils.merge_confs(sub_job_components_common_conf,
                                                              components_common_conf['sub-jobs'][number])

        job = SubJob(
            core_obj.conf, core_obj.logger, core_obj.ID, core_obj.mqs,
            vals,
            'Sub-job-{0}'.format(number),
            'sub-job-{0}'.format(number),
            attrs=[{
                'name': 'Sub-job identifier',
                'value': str(number),
                # Sub-jobs are intended for combining several relatively small jobs together into one large job. For
                # instance, this abstraction is useful for testing and validation. But most likely most of users do not
                # need even to know about them.
                # From ancient time we tried to assign nice names to sub-jobs to distinguish them, in particular to be
                # able to compare corresponding verification results. These names were based on sub-job configurations,
                # e.g. they included commit hashes, requirement specification identifiers, module names, etc. Such the
                # approach turned out to be inadequate since we had to add more and more information to sub-job names
                # that involves source code changes and results in large working directories that look like these names.
                # After all we decided to use sub-job ordinal numbers to distinguish them uniquely (during a some time
                # old style names were used in addition to these ordinal numbers). The only bad news is that in case of
                # any changes in a global arrangement of sub-jobs, such as a new sub-job is added somewhere in the
                # middle or an old sub-job is removed, one is not able to compare verification results as it was with
                # pretty names since correspondence of ordinal numbers breaks.
                'compare': True,
            }],
            components_common_conf=sub_job_concrete_conf
        )

        return job

    core_obj.logger.info('Start job sub-jobs')
    sub_job_solvers_num = klever.core.utils.get_parallel_threads_num(core_obj.logger, components_common_conf,
                                                                     'Sub-jobs processing')
    core_obj.logger.debug('Sub-jobs will be decided in parallel by "{0}" solvers'.format(sub_job_solvers_num))

    subjob_queue = multiprocessing.Queue()
    # Initialize queue first
    core_obj.logger.debug('Initialize workqueue with sub-job identifiers')
    for num in range(len(components_common_conf['sub-jobs'])):
        subjob_queue.put(num)
    subjob_queue.put(None)

    # Then run jobs
    core_obj.logger.debug('Start sub-jobs pull of workers')
    klever.core.components.launch_queue_workers(core_obj.logger, subjob_queue, constructor, sub_job_solvers_num,
                                                components_common_conf['ignore failed sub-jobs'], subcomponents)


class REP(klever.core.components.Component):

    def __init__(self, conf, logger, parent_id, mqs, vals, queues_to_terminate):
        super().__init__(conf, logger, parent_id, mqs, vals, separate_from_parent=False, include_child_resources=True)
        self.data = {}

        self.mqs['verification statuses'] = multiprocessing.Queue()
        queues_to_terminate.append('verification statuses')

    def process_results_extra(self):
        os.mkdir('results')

        while True:
            verification_status = self.mqs['verification statuses'].get()

            if verification_status is None:
                self.logger.debug('Verification statuses message queue was terminated')
                self.mqs['verification statuses'].close()
                break

            id_suffix, verification_result = self.__match_ideal_verdict(verification_status)
            sub_job_id = verification_status['sub-job identifier']

            if self.conf['extra results processing'] == 'testing':
                # For testing jobs there can be several verification tasks for each sub-job, so for uniqueness of
                # tasks and directories add identifier suffix in addition.
                test_id = os.path.join(sub_job_id, id_suffix)
                self.logger.info('Ideal/obtained verdict for test "%s" is "%s"/"%s"%s',
                                 test_id, verification_result['ideal verdict'], verification_result['verdict'],
                                 ' ("{0}")'.format(verification_result['comment'])
                                 if verification_result['comment'] else '')
                results_dir = os.path.join('results', test_id)
                data = {
                    'type': 'testing',
                    'test': test_id
                }
                data.update(verification_result)
            elif self.conf['extra results processing'] == 'validation':
                # For validation jobs we can't refer to sub-job identifier for additional identification of verification
                # results because of most likely we will consider pairs of sub-jobs before and after corresponding bug
                # fixes.
                bug_id, verification_result = self.__process_validation_results(verification_result,
                                                                                verification_status['data'], id_suffix)
                # For validation jobs sub-job identifiers guarantee uniqueness for naming directories since there is
                # the only verification task for each sub-job.
                results_dir = os.path.join('results', sub_job_id)
                data = {
                    'type': 'validation',
                    'bug': bug_id
                }
                data.update(verification_result)
            else:
                raise NotImplementedError('Extra results processing {!r} is not supported'
                                          .format(self.conf['extra results processing']))

            os.makedirs(results_dir)

            self._report('patch',
                         {
                             'identifier': self.parent_id,
                             'data': data
                         },
                         report_dir=results_dir)

    main = process_results_extra

    def __match_ideal_verdict(self, verification_status):
        def match_attr(attr, ideal_attr):
            if ideal_attr and ((isinstance(ideal_attr, str) and attr == ideal_attr) or
                               (isinstance(ideal_attr, list) and attr in ideal_attr)):
                return True

            return False

        program_fragment_id = verification_status['program fragment id']
        req_spec_id = verification_status['req spec id']
        envmodel_id = verification_status.get('environment model')
        ideal_verdicts = verification_status['ideal verdicts']
        comparison_list = [(program_fragment_id, 'program fragments'),
                           (req_spec_id, 'requirements specification'),
                           (envmodel_id, 'environment model')]

        matched_ideal_verdict = None
        ideal_verdicts = sorted(ideal_verdicts, key=lambda x: len(x.keys()), reverse=True)
        for verdicts in ideal_verdicts:
            matched = True
            for value, attribute in comparison_list:
                if attribute in verdicts:
                    matched = match_attr(value, verdicts[attribute])
                    if not matched:
                        break

            if matched:
                matched_ideal_verdict = verdicts
                break

        if not matched_ideal_verdict:
            raise ValueError(
                'Could not match ideal verdict for program fragment "{0}", environment model {1} and requirements '
                'specification "{2}"'.format(program_fragment_id, envmodel_id, req_spec_id))

        # This suffix will help to distinguish sub-jobs easier.
        if envmodel_id == 'base':
            id_suffix = os.path.join(program_fragment_id, req_spec_id) \
                if program_fragment_id and req_spec_id else ''
        else:
            id_suffix = os.path.join(program_fragment_id, req_spec_id, envmodel_id) \
                if program_fragment_id and req_spec_id and envmodel_id else ''

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
        # identifier is just a commit hash, while an identifier suffix contains a program fragment and a requirements
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


class Job(klever.core.components.Component):
    CORE_COMPONENTS = [
        'PFG',
        'VTG',
        'VRP'
    ]

    def __init__(self, conf, logger, parent_id, mqs, vals, cur_id=None, work_dir=None, attrs=None,
                 separate_from_parent=True, components_common_conf=None):
        super().__init__(conf, logger, parent_id, mqs, vals, cur_id, work_dir, attrs,
                         separate_from_parent=separate_from_parent)
        self.common_components_conf = components_common_conf

        if work_dir:
            self.common_components_conf['additional sources directory'] = os.path.join(os.path.realpath(work_dir),
                                                                                       'additional sources')

        self.clade = None
        self.logger.info('Get components for sub-job "%s"', self.id)

        self.components = [getattr(importlib.import_module('.{0}'.format(component.lower()), 'klever.core'), component)
                           for component in self.CORE_COMPONENTS]

        self.logger.debug('Components to be launched: "%s"',
                          ', '.join([component.__name__ for component in self.components]))

    def decide_job_or_sub_job(self):
        self.logger.info('Decide job/sub-job "%s"', self.id)

        # This is required to associate verification results with particular sub-jobs.
        # Skip leading "/" since this identifier is used in os.path.join() that returns absolute path otherwise.
        self.common_components_conf['sub-job identifier'] = self.id[1:]

        self.logger.info('Get specifications set')
        if 'specifications set' in self.common_components_conf:
            spec_set = self.common_components_conf['specifications set']
        else:
            raise KeyError('Specify attribute "specifications set" within job.json')
        self.logger.debug('Specifications set is "%s"', spec_set)

        # Check that specifications set is supported.
        with open(self.common_components_conf['specifications base'], encoding='utf-8') as fp:
            req_spec_base = yaml.safe_load(fp)
        spec_set = self.common_components_conf['specifications set']
        if spec_set not in req_spec_base['specification sets']:
            raise ValueError("Klever does not support specifications set {!r} yet, available options are: {}"
                             .format(spec_set, ', '.join(req_spec_base['specification sets'])))

        # Check and set build base here since many Core components need it.
        self.__set_build_base()
        clade_conf = {"log_level": "ERROR"}
        self.clade = Clade(self.common_components_conf['build base'], conf=clade_conf)
        if not self.clade.work_dir_ok():
            raise RuntimeError(f'Build base "{self.common_components_conf["build base"]}" is not OK')

        self.__retrieve_working_src_trees()
        self.__get_original_sources_basic_info()
        self.__upload_original_sources()

        # Create directory where files will be cached and remember absolute path to it for components.
        os.mkdir('cache')
        self.common_components_conf['cache directory'] = os.path.realpath('cache')

        if self.common_components_conf['keep intermediate files']:
            self.logger.debug('Create components configuration file "conf.json"')
            with open('conf.json', 'w', encoding='utf-8') as fp:
                json.dump(self.common_components_conf, fp, ensure_ascii=False, sort_keys=True, indent=4)

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
            build_base = klever.core.utils.find_file_or_dir(self.logger,
                                                            self.common_components_conf['main working directory'],
                                                            self.common_components_conf['build base'])
        except FileNotFoundError:
            self.logger.warning('Failed to find build base:\n%s', traceback.format_exc().rstrip())
            try:
                build_base = klever.core.utils.find_file_or_dir(
                    self.logger, self.common_components_conf['main working directory'],
                    os.path.join('build bases', self.common_components_conf['build base']))
            except FileNotFoundError:
                self.logger.warning('Failed to find build base:\n%s', traceback.format_exc().rstrip())
                raise FileNotFoundError(
                    'Specified build base "{0}" does not exist, {1}'.format(self.common_components_conf['build base'],
                                                                            common_advice)) from None

        # Extract build base from archive. There should not be any intermediate directories in archives.
        if os.path.isfile(build_base) and (tarfile.is_tarfile(build_base) or zipfile.is_zipfile(build_base)):
            if tarfile.is_tarfile(build_base):
                self.logger.debug('Build base "%s" is provided in form of TAR archive', build_base)
                with tarfile.open(build_base) as TarFile:
                    TarFile.extractall('build base')
            else:
                self.logger.debug('Build base "%s" is provided in form of ZIP archive', build_base)
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

        # TODO: fix after https://github.com/17451k/clade/issues/108.
        if not os.path.isdir(build_base):
            raise FileExistsError('Build base "{0}" {1} is not a directory, {2}'
                                  .format(build_base, extracted_from, common_advice))

        if not os.path.isfile(os.path.join(build_base, 'meta.json')):
            raise FileExistsError(
                'Directory "{0}"{1} is not a build base since it does not contain file "meta.json", {2}'
                .format(build_base, extracted_from, common_advice))

        self.common_components_conf['build base'] = build_base

        self.logger.debug('Klever components will use build base "%s"'
                          , self.common_components_conf['build base'])

    # Klever will try to cut off either working source trees (if specified) or maximum common paths of CC/CL input files
    # and LD/Link output files (otherwise) from referred file names. Sometimes this is rather optional like for source
    # files referred by error traces, but, say, for program fragment identifiers this is strictly necessary, e.g.
    # because of otherwise expert assessment will not work as expected.
    def __retrieve_working_src_trees(self):
        clade_meta = self.clade.get_meta()

        # Best of all if users specify working source trees in build bases manually themselves. It is a most accurate
        # approach.
        if 'working source trees' in clade_meta:
            work_src_trees = clade_meta['working source trees']
        # Otherwise try to find out them automatically as described above.
        else:
            in_files = []
            for cmd in self.clade.get_all_cmds_by_type("CC") + self.clade.get_all_cmds_by_type("CL"):
                if cmd['in']:
                    for in_file in cmd['in']:
                        # Sometimes some auxiliary stuff is built in addition to normal C source files that are most
                        # likely located in a place we would like to get.
                        if not in_file.startswith('/tmp') and in_file != '/dev/null':
                            in_files.append(os.path.join(cmd['cwd'], in_file))
            in_files_prefix = os.path.dirname(os.path.commonprefix(in_files))
            self.logger.info('Common prefix of CC/CL input files is "%s"', in_files_prefix)

            out_files = []
            for cmd in self.clade.get_all_cmds_by_type("LD") + self.clade.get_all_cmds_by_type("Link"):
                if cmd['out']:
                    for out_file in cmd['out']:
                        # Like above.
                        if not out_file.startswith('/tmp') and out_file != '/dev/null':
                            out_files.append(os.path.join(cmd['cwd'], out_file))
            out_files_prefix = os.path.dirname(os.path.commonprefix(out_files))
            self.logger.info('Common prefix of LD/Link output files is "%s"', out_files_prefix)

            # Meaningful paths look like "/dir...".
            meaningful_paths = []
            for path in (in_files_prefix, out_files_prefix):
                if path and path != os.path.sep and path not in meaningful_paths:
                    meaningful_paths.append(path)

            if meaningful_paths:
                work_src_trees = meaningful_paths
            # At least consider build directory as working source tree if the automatic procedure fails.
            else:
                self.logger.warning(
                    'Consider build directory "%s" as working source tree.'
                    'This may be dangerous and we recommend to specify appropriate working source trees manually!'
                    , clade_meta['build_dir'])
                work_src_trees = [clade_meta['build_dir']]

        # Consider minimal path if it is common prefix for other ones. For instance, if we have "/dir1/dir2" and "/dir1"
        # then "/dir1" will become the only working source tree.
        if len(work_src_trees) > 1:
            min_work_src_tree = min(work_src_trees)
            if os.path.commonprefix(work_src_trees) == min_work_src_tree:
                work_src_trees = [min_work_src_tree]

        self.logger.info(
            'Working source trees to be used are as follows:\n%s'
            , '\n'.join(['  {0}'.format(t) for t in work_src_trees]))
        self.common_components_conf['working source trees'] = work_src_trees

    def __refer_original_sources(self, src_id):
        self._report('patch',
                     {
                         'identifier': self.id,
                         'original_sources': src_id
                     })

    def __process_source_file(self):
        while True:
            file_name = self.mqs['file names'].get()

            if not file_name:
                return

            src_file_name = klever.core.utils.make_relative_path(self.common_components_conf['working source trees'],
                                                                 file_name)

            if src_file_name != file_name:
                src_file_name = os.path.join('source files', src_file_name)

            new_file_name = os.path.join('original sources', src_file_name.lstrip(os.path.sep))
            os.makedirs(os.path.dirname(new_file_name), exist_ok=True)
            shutil.copy(self.clade.get_storage_path(file_name), new_file_name)

            if self.common_components_conf.get("collect cross-references", False):
                cross_refs = CrossRefs(self.common_components_conf, self.logger, self.clade,
                                       file_name, new_file_name,
                                       self.common_components_conf['working source trees'], 'source files')
                cross_refs.get_cross_refs()

    def __get_original_sources_basic_info(self):
        self.logger.info('Get information on original sources for following visualization of uncovered source files')

        if 'coverage src info' not in self.vals:
            # No JCR, no need the information
            return
        # For each source file we need to know the total number of lines and places where functions are defined.
        src_files_info = {}
        for file_name, file_size in self.clade.src_info.items():
            src_file_name = klever.core.utils.make_relative_path(self.common_components_conf['working source trees'],
                                                                 file_name)

            # Skip non-source files.
            if src_file_name == file_name:
                continue

            src_file_name = os.path.join('source files', src_file_name)

            # Store source file size.
            src_files_info[src_file_name] = [file_size['loc']]

            # Store source file function definition lines.
            func_def_lines = []
            funcs = self.clade.get_functions_by_file([file_name], False)

            if funcs:
                for _, func_info in list(funcs.values())[0].items():
                    func_def_lines.append(int(func_info['line']))

            src_files_info[src_file_name].append(sorted(func_def_lines))

        self.vals['coverage src info'][self.common_components_conf['sub-job identifier']] = src_files_info

        # Dump obtain information (huge data!)
        self.dump_if_necessary('original sources basic information.json', src_files_info,
                               "original sources basic information")

    def __upload_original_sources(self):
        # Use Clade UUID to distinguish various original sources. It is pretty well since this UUID is uuid.uuid4().
        src_id = self.clade.get_uuid()
        # In addition, take into account a meta content as we like to change it manually often. In this case it may be
        # necessary to re-index the build base. It is not clear if this is the case actually, so, do this in case of
        # any changes in meta.
        src_id += '-' + klever.core.utils.get_file_name_checksum(json.dumps(self.clade.get_meta()))[:12]

        session = klever.core.session.Session(self.logger, self.conf['Klever Bridge'], self.conf['identifier'])

        if session.check_original_sources(src_id):
            self.logger.info('Original sources were uploaded already')
            self.__refer_original_sources(src_id)
            return

        self.logger.info(
            'Cut off working source trees or build directory from original source file names and convert index data')
        os.makedirs('original sources')
        self.mqs['file names'] = multiprocessing.Queue()
        for file_name in self.clade.src_info:
            self.mqs['file names'].put(file_name)

        subcomponents = []
        workers_num = klever.core.utils.get_parallel_threads_num(self.logger, self.conf)
        for _ in range(workers_num):
            subcomponents.append(('PSF', self.__process_source_file))
            self.mqs['file names'].put(None)
        self.launch_subcomponents(*subcomponents)
        self.mqs['file names'].close()

        self.logger.info('Compress original sources')
        klever.core.utils.ArchiveFiles(['original sources']).make_archive('original sources.zip')

        self.logger.info('Upload original sources')
        try:
            session.upload_original_sources(src_id, 'original sources.zip')
        # Do not fail if there are already original sources. There may be complex data races because of checking and
        # uploading original sources archive are not atomic.
        except klever.core.session.BridgeError:
            if "original sources with this identifier already exists." not in list(session.error.values())[0]:
                raise

        self.__refer_original_sources(src_id)

        if not self.conf['keep intermediate files']:
            shutil.rmtree('original sources')
            os.remove('original sources.zip')

    def launch_sub_job_components(self):
        self.logger.info('Launch components for sub-job "%s"', self.id)
        self.mqs['VRP common attrs'] = multiprocessing.Queue()

        # Queues used exclusively in VTG
        self.mqs['program fragment desc'] = multiprocessing.Queue()

        # Queues shared by VRP
        self.mqs['pending tasks'] = multiprocessing.Queue()
        self.mqs['processed'] = multiprocessing.Queue()

        component_processes = []
        for component in self.components:
            p = component(self.common_components_conf, self.logger, self.id, self.mqs,
                          self.vals, separate_from_parent=True)
            component_processes.append(p)

        klever.core.components.launch_workers(self.logger, component_processes)

        self.logger.debug('Put "%s" sub-job identifier for finish coverage', self.id)
        if 'req spec ids and coverage info' in self.mqs:
            self.mqs['req spec ids and coverage info'].put({
                'sub-job identifier': self.common_components_conf['sub-job identifier']
            })


class SubJob(Job):

    def decide_sub_job(self):
        try:
            self.decide_job_or_sub_job()
            self.vals['subjobs progress'][self.id] = 'finished'
        except Exception:
            self.vals['subjobs progress'][self.id] = 'failed'
            raise

    main = decide_sub_job
