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

import glob
import json
import multiprocessing
import os
import re
import sys
import time
import traceback
import zipfile
from xml.etree import ElementTree

from clade import Clade

import klever.core.components
import klever.core.session
import klever.core.utils
from klever.core.coverage import LCOV
from klever.core.vrp.et import import_error_trace, ErrorTraceParser

MEA_LIB = os.path.join("MEA", "cv")


class VRP(klever.core.components.Component):

    def __init__(self, conf, logger, parent_id, mqs, vals, cur_id=None, work_dir=None, attrs=None,
                 separate_from_parent=False, include_child_resources=False):
        self.__workers = None
        # Common initialization
        super().__init__(conf, logger, parent_id, mqs, vals, cur_id, work_dir, attrs,
                         separate_from_parent, include_child_resources)

        self.source_paths = None
        self.processing_tasks = multiprocessing.Queue()

    def process_results(self):
        self.__workers = klever.core.utils.get_parallel_threads_num(self.logger, self.conf, 'Results processing')
        self.logger.info("Going to start %s workers to process results", self.__workers)

        self.source_paths = self.conf['working source trees']
        self.logger.info('Source paths to be trimmed file names: %s', self.source_paths)

        # Do result processing
        self._report('patch',
                     {
                         'identifier': self.id,
                         'attrs': self.__get_common_attrs()
                     })

        subcomponents = [('RPL', self.__result_processing)]
        for _ in range(self.__workers):
            subcomponents.append(('RPWL', self.__loop_worker))
        self.launch_subcomponents(*subcomponents)

        self.clean_dir = True
        self.logger.info('Task results processing has finished')

    main = process_results

    def __result_processing(self):
        self.logger.info('Start waiting messages from VTG to track their statuses')
        pending = {}
        # todo: implement them in GUI
        solution_timeout = 1

        receiving = True
        session = klever.core.session.Session(self.logger, self.conf['Klever Bridge'], self.conf['identifier'])
        while True:
            # Get new tasks
            if receiving:
                # Functions below close the queue!
                data = []
                res = klever.core.utils.drain_queue(data, self.mqs['pending tasks'])
                if not res:
                    receiving = False
                    self.logger.info("Expect no tasks to be generated")

                if data:
                    self.logger.info('Received %s items', len(data))
                for item in data:
                    assert item
                    pending[item[0]] = item

            # Plan for processing new tasks
            if pending:
                tasks_statuses = session.get_tasks_statuses()
                for item in tasks_statuses:
                    task = str(item['id'])
                    if task in pending:
                        if item['status'] in ('FINISHED', 'ERROR'):
                            task_data = pending[task]
                            self.logger.info('Track processing task %s', str(task_data[1]))
                            self.processing_tasks.put([item['status'].lower(), task_data])
                            del pending[task]
                        elif item['status'] in ('PENDING', 'PROCESSING'):
                            pass
                        else:
                            raise NotImplementedError('Unknown task status {!r}'.format(item['status']))

            if not receiving and not pending:
                for _ in range(self.__workers):
                    self.processing_tasks.put(None)
                self.processing_tasks.close()
                break

            time.sleep(solution_timeout)

        self.logger.debug("Shutting down result processing gracefully")

    def __loop_worker(self):
        self.logger.info("VRP fetcher is ready to work")

        while True:
            element = self.processing_tasks.get()
            if element is None:
                break

            status, data = element
            pf, _, envmodel, requirement, _, _ = data[1]
            result_key = f'{pf}:{envmodel}:{requirement}'
            self.logger.info('Receive solution %s', result_key)
            new_id = "RP/{}/{}/{}".format(pf, envmodel, requirement)
            workdir = os.path.join(pf, envmodel, requirement)
            try:
                if not os.path.isdir(workdir):
                    os.makedirs(workdir.encode('utf-8'))
                rp = RP(self.conf, self.logger, self.id, self.mqs, self.vals, new_id,
                        workdir, self.source_paths, [status, data])
                rp.run()
                self.logger.info('Successfully processed %s', result_key)
            except klever.core.components.ComponentError:
                self.logger.debug("RP that processed %r, %r failed", pf, requirement)
            self.logger.debug('Continue fetching items after processing %s', result_key)

        self.logger.info("VRP fetcher finishes its work")

    def __get_common_attrs(self):
        self.logger.info('Get common attributes')

        common_attrs = self.mqs['VRP common attrs'].get()

        self.mqs['VRP common attrs'].close()

        return common_attrs


class RP(klever.core.components.Component):

    def __init__(self, conf, logger, parent_id, mqs, vals, cur_id, work_dir, source_paths, element):
        # Read this in a callback
        self.element = element
        self.verdict = None
        self.req_spec_id = None
        self.program_fragment_id = None
        self.envmodel = None
        self.report_attrs = None
        self.files_list_file = 'files list.txt'
        self.task_error = None
        self.source_paths = source_paths
        self.additional_srcs = None
        self.verification_task_files = None
        self.processed_data = [None, None, None]
        # Common initialization
        super().__init__(conf, logger, parent_id, mqs, vals, cur_id, work_dir, separate_from_parent=True)

        self.clean_dir = True
        self.session = klever.core.session.Session(self.logger, self.conf['Klever Bridge'], self.conf['identifier'])

        # Obtain file prefixes that can be removed from file paths.
        clade_conf = {"log_level": "ERROR"}
        self.clade = Clade(self.conf['build base'], conf=clade_conf)
        if not self.clade.work_dir_ok():
            raise RuntimeError('Build base is not OK')

        self.search_dirs = klever.core.utils.get_search_dirs(self.conf['main working directory'], abs_paths=True)
        self.verification_report_id = None
        # Reset global maps
        ErrorTraceParser.reset()

    def fetcher(self):
        self.logger.info("VRP instance is ready to work")
        status, data = self.element
        task_id, task_desc, opts, program_fragment_desc, verifier, self.additional_srcs, verification_task_files = data
        self.program_fragment_id, _, self.envmodel, self.req_spec_id, _, envattrs = task_desc
        self.verification_task_files = verification_task_files
        self.logger.debug("Process results of task %s", task_id)

        klever.core.utils.save_program_fragment_description(program_fragment_desc, self.files_list_file)

        # These attributes should not have "associate": True. Otherwise, new unknown marks for RP will be associated by
        # them automatically.
        self.report_attrs = [
            {
                "name": "Program fragment",
                "value": self.program_fragment_id,
                "data": self.files_list_file,
                "compare": True
            },
            {
                "name": "Requirements specification",
                "value": self.req_spec_id,
                "compare": True
            }
        ]
        if envattrs:
            for attr, value in envattrs:
                if value:
                    self.report_attrs.append({
                        "name": f"Environment model '{attr}'",
                        "value": value,
                        "compare": True
                    })

        self._report('patch',
                     {
                         'identifier': self.id,
                         'attrs': self.report_attrs
                     },
                     data_files=[self.files_list_file])

        # In contrast when these attributes will be reported for Safes and Unsafes, new marks should be associated by
        # them automatically.
        for attr in self.report_attrs:
            attr["associate"] = True

        # Update solution status
        self.processed_data[0] = status

        try:
            if status == 'finished':
                self.process_finished_task(task_id, opts, verifier)
            elif status == 'error':
                self.process_failed_task(task_id)
                # Raise exception just here since the method above has callbacks.
                raise RuntimeError(self.task_error)
            else:
                raise ValueError("Unknown task {!r} status {!r}".format(task_id, status))
        finally:
            results_key = f'{self.program_fragment_id}:{self.envmodel}:{self.req_spec_id}'
            self.logger.info('Submit solution for %s', results_key)
            self.mqs['processed'].put(('Task', tuple(data[1]), self.processed_data))

    main = fetcher

    def process_witness(self, witness):
        error_trace, attrs = import_error_trace(self.logger, witness, self.verification_task_files)
        error_trace['files'] = self.__trim_file_names(error_trace['files'])

        # Distinguish multiple witnesses and error traces by using artificial unique identifiers encoded within witness
        # file names.
        match = re.search(r'witness\.(.+)\.graphml', witness)
        if match:
            error_trace_file = 'error trace {0}.json'.format(match.group(1))
        else:
            error_trace_file = 'error trace.json'

        self.logger.info('Write processed witness to "%s"', error_trace_file)
        with open(error_trace_file, 'w', encoding='utf-8') as fp:
            klever.core.utils.json_dump(error_trace, fp, self.conf['keep intermediate files'])

        return error_trace_file, attrs

    def report_unsafe(self, error_trace_file, attrs, identifier=''):
        attrs.extend(self.report_attrs)
        self._report('unsafe',
                     {
                         # To distinguish several Unsafes specific identifiers should be used.
                         'identifier': self.verification_report_id + '/' + identifier,
                         'parent': self.verification_report_id,
                         'attrs': attrs,
                         'error_trace': klever.core.utils.ArchiveFiles(
                             [error_trace_file],
                             arcnames={error_trace_file: 'error trace.json'}
                         )
                     },
                     data_files=[self.files_list_file])

    def __filter_witnesses(self, witnesses: list) -> list:
        # Export MEA lib
        for env_path in os.environ['PATH'].split(':'):
            if MEA_LIB in env_path:
                sys.path.append(env_path)
                from filter import execute_filtering  # pylint: disable=import-outside-toplevel
                return execute_filtering(witnesses)
        # Sanity check - if MEA was not installed, then ignore filtering
        # TODO: check for MEA on top level
        raise RuntimeError("Failed to export MEA lib")

    def process_single_verdict(self, decision_results, log_file):
        """The function has a callback that collects verdicts to compare them with the ideal ones."""
        # Parse reports and determine status
        benchexec_reports = glob.glob(os.path.join('output', '*.results.xml'))
        if len(benchexec_reports) != 1:
            raise FileNotFoundError('Expect strictly single BenchExec XML report file, but found {}'.
                                    format(len(benchexec_reports)))

        # Expect single report file
        with open(benchexec_reports[0], encoding="utf-8") as fp:
            result = ElementTree.parse(fp).getroot()

            run = result.findall("run")[0]
            for column in run.iter("column"):
                name, value = [column.attrib.get(name) for name in ("title", "value")]
                if name == "status":
                    decision_results["status"] = value

        # Check that we have set status
        if "status" not in decision_results:
            raise KeyError("There is no solution status in BenchExec XML report")

        self.logger.info('Verification task decision status is "%s"', decision_results['status'])

        # Do not fail immediately in case of witness processing failures that often take place. Otherwise we will
        # not upload all witnesses that can be properly processed as well as information on all such failures.
        # Necessary verification finish report also won't be uploaded causing Bridge to corrupt the whole job.
        if re.search('true', decision_results['status']):
            self._report('safe',
                         {
                             # There may be the only Safe, so, "/" uniquely distinguishes it.
                             'identifier': self.verification_report_id + '/',
                             'parent': self.verification_report_id,
                             'attrs': self.report_attrs
                             # TODO: add a correctness witness here if it was found.
                             # 'proof': None
                         },
                         data_files=[self.files_list_file])
            self.verdict = 'safe'
        else:
            witnesses = sorted(glob.glob(os.path.join('output', 'witness.*.graphml')))
            error_msg = ""
            self.logger.info("Found %s witnesses", len(witnesses))
            if len(witnesses) > 1:
                witnesses = self.__filter_witnesses(witnesses)

            # Create unsafe reports independently on status. Later we will create unknown report in addition if status
            # is not "unsafe".
            self.verdict = 'unsafe'

            if not witnesses and re.search('false', decision_results['status']):
                self.logger.warning('No witnesses found with Unsafe verdict')
                self.verdict = 'non-verifier unknown'

            identifier = 1
            for witness in witnesses:
                try:
                    error_trace_file, attrs = self.process_witness(witness)
                    self.report_unsafe(error_trace_file, attrs, str(identifier))
                except Exception as err:  # pylint: disable=broad-except
                    self.logger.warning('Failed to process a witness: %s\n%s', err, traceback.format_exc().rstrip())
                    self.verdict = 'non-verifier unknown'
                    error_msg = f"{error_msg}Failed to process a witness due to:\n" \
                                f"{str(traceback.format_exc().rstrip())}\n"
                finally:
                    identifier += 1

            if not re.search('false', decision_results['status']) or error_msg:
                self.verdict = 'unknown'

                # Prepare file to send it with unknown report.
                os.mkdir('verification')
                verification_problem_desc = os.path.join('verification', 'problem desc.txt')

                # Check resource limitations
                if decision_results['status'] in ('OUT OF MEMORY', 'TIMEOUT') or error_msg:
                    if decision_results['status'] == 'OUT OF MEMORY':
                        msg = "memory exhausted"
                    elif decision_results['status'] == 'TIMEOUT':
                        msg = "CPU time exhausted"
                    else:
                        msg = ""
                    if error_msg:
                        msg = f"{error_msg}{msg}"
                    with open(verification_problem_desc, 'w', encoding='utf-8') as fp:
                        fp.write(msg)

                    if decision_results['status'] in ('OUT OF MEMORY', 'TIMEOUT'):
                        self.processed_data[2] = decision_results['status']
                else:
                    os.symlink(os.path.relpath(log_file, 'verification'), verification_problem_desc)

                klever.core.utils.report(
                    self.logger,
                    'unknown',
                    {
                        # There may be the only Unknown, so, "/" uniquely distinguishes it.
                        'identifier': self.verification_report_id + '/',
                        'parent': self.verification_report_id,
                        'attrs': [],
                        'problem_description': klever.core.utils.ArchiveFiles(
                            [verification_problem_desc],
                            {verification_problem_desc: 'problem desc.txt'}
                        )
                    },
                    self.mqs['report files'],
                    self.vals['report id'],
                    self.conf['main working directory'],
                    'verification'
                )

    def process_failed_task(self, task_id):
        if 'verification statuses' in self.mqs:
            self.mqs['verification statuses'].put({
                'program fragment id': self.program_fragment_id,
                'environment model': self.envmodel,
                'req spec id': self.req_spec_id,
                'verdict': 'non-verifier unknown',
                'sub-job identifier': self.conf['sub-job identifier'],
                'ideal verdicts': self.conf['ideal verdicts'],
                'data': self.conf.get('data')
            })
        self.task_error = self.session.get_task_error(task_id)
        # We do not need task and its files anymore.
        self.session.remove_task(task_id)

    def process_finished_task(self, task_id, opts, verifier):
        self.session.download_decision(task_id)

        with zipfile.ZipFile('decision result files.zip') as zfp:
            zfp.extractall()

        with open('decision results.json', encoding='utf-8') as fp:
            decision_results = json.load(fp)

        if "output dir" in decision_results:
            # Local run, the data is on the file system
            if not os.path.exists('output'):
                os.symlink(decision_results["output dir"], os.path.join(os.getcwd(), "output"))
            else:
                # strange, but use downloaded data
                pass

        # TODO: specify the computer where the verifier was invoked (this information should be get from
        # BenchExec or VerifierCloud web client.
        log_files_dir = glob.glob(os.path.join('output', 'benchmark*logfiles'))[0]
        log_files = os.listdir(log_files_dir)

        if len(log_files) != 1:
            raise NotImplementedError('Exactly one log file should be outputted (but "{0}" are given)'
                                      .format(len(log_files)))

        log_file = os.path.join(log_files_dir, log_files[0])

        self.verification_report_id = "{}/{}".format(self.id, verifier)
        # Send an initial report
        report = {
            'identifier': self.verification_report_id,
            'parent': self.id,
            # TODO: replace with something meaningful, e.g. tool name + tool version + tool configuration.
            'attrs': [],
            'component': verifier,
            'wall_time': decision_results['resources']['wall time'],
            'cpu_time': decision_results['resources']['CPU time'],
            'memory': decision_results['resources']['memory size'],
            'original_sources':
                self.clade.get_uuid() +
                '-' +
                klever.core.utils.get_file_name_checksum(json.dumps(self.clade.get_meta()))[:12]
        }

        if self.additional_srcs:
            report['additional_sources'] = klever.core.utils.ArchiveFiles(
                [os.path.join(self.conf['main working directory'], self.additional_srcs)])

        # Update solution progress. It is necessary to update the whole list to sync changes
        self.processed_data[1] = decision_results['resources']

        if not self.logger.disabled and log_file and self.conf['weight'] == "0":
            report['log'] = klever.core.utils.ArchiveFiles([log_file], {log_file: 'log.txt'})

        if self.conf['upload verifier input files']:
            report['task'] = task_id

        # Remember exception and raise it if verdict is not unknown
        exception = False
        if 'req spec ids and coverage info' in self.mqs:
            # At the moment Klever supports just one code coverage report per a verification task. So, we can use
            # code coverage reports corresponding to violation witnesses just in case when there is the only
            # violation witness. Otherwise, use a common code coverage report.
            if len(glob.glob(os.path.join('output', 'witness.*.graphml'))) == 1:
                coverage_files = glob.glob(os.path.join('output', 'Counterexample.*.additionalCoverage.info'))

                if coverage_files:
                    coverage_file = coverage_files[0]
                # TODO: CPALockator does not output enhanced code coverage reports at the moment.
                else:
                    coverage_file = os.path.join('output', 'coverage.info')
            else:
                coverage_file = os.path.join('output', 'additionalCoverage.info')

                # TODO: CPALockator does not output enhanced code coverage reports at the moment.
                if not os.path.exists(coverage_file):
                    coverage_file = os.path.join('output', 'coverage.info')

            if os.path.isfile(coverage_file):
                # Get coverage
                coverage_info_dir = os.path.join('total coverages',
                                                 self.conf['sub-job identifier'],
                                                 self.req_spec_id.replace('/', '-'))
                coverage_info_dir = os.path.join(self.conf['main working directory'], coverage_info_dir)
                os.makedirs(coverage_info_dir, exist_ok=True)
                coverage_info_file = os.path.join(coverage_info_dir,
                                                  "{0}_coverage_info.json".format(task_id.replace('/', '-')))

                lcov = LCOV(self.logger, coverage_file,
                            self.clade.storage_dir, self.source_paths,
                            self.search_dirs,
                            opts['code coverage details'],
                            self.conf['keep intermediate files'],
                            coverage_info_file,
                            self.verification_task_files)

                coverage_info = lcov.import_coverage()
                if coverage_info:
                    # even for empty coverage
                    self.mqs['req spec ids and coverage info'].put({
                        'sub-job identifier': self.conf['sub-job identifier'],
                        'req spec id': self.req_spec_id,
                        'coverage info': coverage_info
                    })
                    report['coverage'] = klever.core.utils.ArchiveFiles(['coverage'])
                    self.vals['coverage_finished'][self.conf['sub-job identifier']] = False
            else:
                exception = True

        # todo: This should be checked to guarantee that we can reschedule tasks
        self._report('verification', report)

        try:
            # Submit a verdict
            self.process_single_verdict(decision_results, log_file)
        finally:
            if 'verification statuses' in self.mqs:
                self.mqs['verification statuses'].put({
                    'program fragment id': self.program_fragment_id,
                    'environment model': self.envmodel,
                    'req spec id': self.req_spec_id,
                    'verdict': self.verdict,
                    'sub-job identifier': self.conf['sub-job identifier'],
                    'ideal verdicts': self.conf['ideal verdicts'],
                    'data': self.conf.get('data')
                })
            # Submit a closing report
            self._report('verification finish',
                         {'identifier': self.verification_report_id})

        # Check verdict
        if exception and self.verdict != 'unknown':
            raise klever.core.components.ComponentError(
                'No coverage data for task {}'.format(task_id))
        if exception:
            self.logger.exception('No coverage data for task %s', task_id)

    def __trim_file_names(self, file_names):
        trimmed_file_names = []

        for file_name in file_names:
            # Remove storage from file names if files were put there.
            storage_file = klever.core.utils.make_relative_path([self.clade.storage_dir], file_name)
            # Try to make paths relative to source paths or standard search directories.
            tmp = klever.core.utils.make_relative_path(self.source_paths, storage_file, absolutize=True)

            # Append special directory name "source files" when cutting off source file names.
            if tmp != os.path.join(os.path.sep, storage_file):
                trimmed_file_names.append(os.path.join('source files', tmp))
            else:
                # Like in klever.core.vtg.weaver.Weaver#weave.
                tmp = klever.core.utils.make_relative_path(self.search_dirs, storage_file, absolutize=True)
                if tmp != os.path.join(os.path.sep, storage_file):
                    if tmp.startswith('specifications'):
                        trimmed_file_names.append(tmp)
                    else:
                        trimmed_file_names.append(os.path.join('generated models', tmp))
                else:
                    # Caller expects a returned dictionary maps each file name, so, let's fill it anyway.
                    trimmed_file_names.append(storage_file)

        return trimmed_file_names
