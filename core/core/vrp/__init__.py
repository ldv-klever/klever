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

import glob
import json
import os
import queue
import re
import time
import traceback
import xml.etree.ElementTree as ElementTree
import zipfile
import multiprocessing

from core.vrp.et import import_error_trace

import core.components
import core.session
import core.utils
from core.vrp.coverage_parser import LCOV


@core.components.before_callback
def __launch_sub_job_components(context):
    context.mqs['VRP common prj attrs'] = multiprocessing.Queue()
    context.mqs['processing tasks'] = multiprocessing.Queue()


@core.components.after_callback
def __set_common_prj_attrs(context):
    context.mqs['VRP common prj attrs'].put(context.common_prj_attrs)


class VRP(core.components.Component):

    def __init__(self, conf, logger, parent_id, callbacks, mqs, locks, vals, id=None, work_dir=None, attrs=None,
                 separate_from_parent=False, include_child_resources=False):
        # Rule specification descriptions were already extracted when getting VTG callbacks.
        self.__downloaded = dict()
        self.__workers = None

        # Read this in a callback
        self.verdict = None
        self.rule_specification = None
        self.verification_object = None

        # Common initialization
        super(VRP, self).__init__(conf, logger, parent_id, callbacks, mqs, locks, vals, id, work_dir, attrs,
                                  separate_from_parent, include_child_resources)

    def process_results(self):
        self.__workers = core.utils.get_parallel_threads_num(self.logger, self.conf, 'Results processing')
        self.logger.info("Going to start {} workers to process results".format(self.__workers))

        # Do result processing
        core.utils.report(self.logger,
                          'attrs',
                          {
                              'id': self.id,
                              'attrs': self.__get_common_prj_attrs()
                          },
                          self.mqs['report files'],
                          self.vals['report id'],
                          self.conf['main working directory'])

        subcomponents = [('RPL', self.__result_processing)]
        for i in range(self.__workers):
            subcomponents.append(('RPWL', self.__loop_worker))
        self.launch_subcomponents(False, *subcomponents)

        self.clean_dir = True
        # Finalize
        self.finish_task_results_processing()

    def finish_task_results_processing(self):
        """Function has a callback at Job.py."""
        self.logger.info('Task results processing has finished')

    main = process_results

    def __result_processing(self):
        pending = dict()
        # todo: implement them in GUI
        solution_timeout = 10
        generation_timeout = 5

        def submit_processing_task(status, t):
            self.mqs['processing tasks'].put([status, pending[t]])

        receiving = True
        session = core.session.Session(self.logger, self.conf['Klever Bridge'], self.conf['identifier'])
        try:
            while True:
                # Get new tasks
                if receiving:
                    if len(pending) > 0:
                        number = 0
                        try:
                            while True:
                                data = self.mqs['pending tasks'].get_nowait()
                                if not data:
                                    receiving = False
                                    self.logger.info("Expect no tasks to be generated")
                                else:
                                    pending[data[0]] = data
                                number += 1
                        except queue.Empty:
                            self.logger.debug("Fetched {} tasks".format(number))
                    else:
                        try:
                            data = self.mqs['pending tasks'].get(block=True, timeout=generation_timeout)
                            if not data:
                                receiving = False
                                self.logger.info("Expect no tasks to be generated")
                            else:
                                pending[data[0]] = data
                        except queue.Empty:
                            self.logger.debug("No tasks has come for last 30 seconds")

                # Plan for processing new tasks
                if len(pending) > 0:
                    tasks_statuses = session.get_tasks_statuses(list(pending.keys()))
                    for task in list(pending.keys()):
                        if task in tasks_statuses['finished']:
                            submit_processing_task('finished', task)
                            del pending[task]
                        elif task in tasks_statuses['error']:
                            submit_processing_task('error', task)
                            del pending[task]
                        elif task not in tasks_statuses['processing'] and task not in tasks_statuses['pending']:
                            raise KeyError("Cannot find task {!r} in either finished, processing, pending or erroneus "
                                           "tasks".format(task))

                if not receiving and len(pending) == 0:
                    # Wait for all rest tasks, no tasks can come currently
                    self.mqs['pending tasks'].close()
                    for _ in range(self.__workers):
                        self.mqs['processing tasks'].put(None)
                    self.mqs['processing tasks'].close()
                    break

                time.sleep(solution_timeout)
        finally:
            session.sign_out()
        self.logger.debug("Shutting down result processing gracefully")

    def __loop_worker(self):
        self.logger.info("VRP fetcher is ready to work")
        while True:
            element = self.mqs['processing tasks'].get()
            if element is None:
                break

            status, data = element
            vo = data[2]
            rule = data[3]
            new_id = "{}/{}/RP".format(vo, rule)
            workdir = os.path.join(vo, rule)
            try:
                rp = RP(self.conf, self.logger, self.id, self.callbacks, self.mqs, self.locks, self.vals, new_id,
                        workdir, [
                            {
                                "name": "Rule specification",
                                "value": rule,
                                "compare": True,
                                "associate": True
                            },
                            {
                                "name": "Verification object",
                                "value": vo,
                                "compare": True,
                                "associate": True
                            }
                        ], separate_from_parent=True,
                        element=element)
                rp.start()
                rp.join()
            except core.components.ComponentError:
                self.logger.debug("RP that processed {!r}, {!r} failed".format(vo, rule))
            finally:
                self.mqs['processed tasks'].put((vo, rule))
                self.mqs['finished and failed tasks'].put([self.conf['job identifier'], 'finished'])

        self.logger.info("VRP fetcher finishes its work")

    def __get_common_prj_attrs(self):
        self.logger.info('Get common project atributes')

        common_prj_attrs = self.mqs['VRP common prj attrs'].get()

        self.mqs['VRP common prj attrs'].close()

        return common_prj_attrs


class RP(core.components.Component):

    def __init__(self, conf, logger, parent_id, callbacks, mqs, locks, vals, id=None, work_dir=None, attrs=None,
                 separate_from_parent=False, include_child_resources=False, element=None):
        # Read this in a callback
        self.element = element
        self.verdict = None
        self.rule_specification = None
        self.verification_object = None
        self.task_error = None
        self.verification_coverage = None
        self.__exception = None

        # Common initialization
        super(RP, self).__init__(conf, logger, parent_id, callbacks, mqs, locks, vals, id, work_dir, attrs,
                                 separate_from_parent, include_child_resources)

        self.clean_dir = True
        self.session = core.session.Session(self.logger, self.conf['Klever Bridge'], self.conf['identifier'])

    def fetcher(self):
        self.logger.info("VRP instance is ready to work")
        element = self.element
        status, data = element
        task_id, opts, verification_object, rule_specification, verifier, shadow_src_dir = data
        self.verification_object = verification_object
        self.rule_specification = rule_specification

        self.logger.debug("Prcess results of task {}".format(task_id))

        try:
            if status == 'finished':
                self.process_finished_task(task_id, opts, verifier, shadow_src_dir)
                # Raise exception just here sinse the method above has callbacks.
                if self.__exception:
                    self.logger.warning("Raising the saved exception")
                    raise self.__exception
            elif status == 'error':
                self.process_failed_task(task_id)
                # Raise exception just here sinse the method above has callbacks.
                raise RuntimeError('Failed to decide verification task: {0}'.format(self.task_error))
            else:
                raise ValueError("Unknown task {!r} status {!r}".format(task_id, status))
        finally:
            self.session.sign_out()

    main = fetcher

    def process_witness(self, witness, shadow_src_dir, get_error_trace_id=False):
        error_trace = import_error_trace(self.logger, witness)
        sources = self.__trim_file_names(error_trace['files'], shadow_src_dir)
        error_trace['files'] = [sources[file] for file in error_trace['files']]

        if get_error_trace_id:
            match = re.search(r'witness\.(.+)\.graphml', witness)
            if not match:
                raise ValueError('Witness "{0}" does not encode error trace identifier'.format(witness))
            error_trace_id = match.group(1)

            error_trace['attrs'] = [{
                'name': 'Error trace identifier',
                'value': error_trace_id,
                'compare': True,
                'associate': True
            }]

            error_trace_file = 'error trace {0}.json'.format(error_trace_id)
        else:
            error_trace_file = 'error trace.json'

        self.logger.info('Write processed witness to "{0}"'.format(error_trace_file))
        with open(error_trace_file, 'w', encoding='utf8') as fp:
            json.dump(error_trace, fp, ensure_ascii=False, sort_keys=True, indent=4)

        return sources, error_trace_file

    def report_unsafe(self, sources, error_trace_files):
        core.utils.report(self.logger,
                          'unsafe',
                          {
                              'id': "{}/verification/unsafe".format(self.id),
                              'parent id': "{}/verification".format(self.id),
                              'attrs': [],
                              'sources': core.utils.ReportFiles(list(sources.keys()), arcnames=sources),
                              'error traces': [core.utils.ReportFiles([error_trace_file],
                                                                      arcnames={error_trace_file: 'error trace.json'})
                                               for error_trace_file in error_trace_files]
                          },
                          self.mqs['report files'],
                          self.vals['report id'],
                          self.conf['main working directory'])

    def process_single_verdict(self, decision_results, opts, shadow_src_dir, log_file):
        """The function has a callback that collects verdicts to compare them with the ideal ones."""
        # Parse reports and determine status
        benchexec_reports = glob.glob(os.path.join('output', '*.results.xml'))
        if len(benchexec_reports) != 1:
            raise FileNotFoundError('Expect strictly single BenchExec XML report file, but found {}'.
                                    format(len(benchexec_reports)))

        # Expect single report file
        with open(benchexec_reports[0], encoding="utf8") as fp:
            result = ElementTree.parse(fp).getroot()

            run = result.findall("run")[0]
            for column in run.iter("column"):
                name, value = [column.attrib.get(name) for name in ("title", "value")]
                if name == "status":
                    decision_results["status"] = value

        # Check that we have set status
        if "status" not in decision_results:
            raise KeyError("There is no solution status in BenchExec XML report")

        self.logger.info('Verification task decision status is "{0}"'.format(decision_results['status']))

        # Do not fail immediately in case of witness processing failures that often take place. Otherwise we will
        # not upload all witnesses that can be properly processed as well as information on all such failures.
        # Necessary verificaiton finish report also won't be uploaded causing Bridge to corrupt the whole job.
        if re.match('true', decision_results['status']):
            core.utils.report(self.logger,
                              'safe',
                              {
                                  'id': "{}/verification/safe".format(self.id),
                                  'parent id': "{}/verification".format(self.id),
                                  'attrs': []
                                  # TODO: at the moment it is unclear what are verifier proofs.
                                  # 'proof': None
                              },
                              self.mqs['report files'],
                              self.vals['report id'],
                              self.conf['main working directory'])
            self.verdict = 'safe'
        else:
            witnesses = glob.glob(os.path.join('output', 'witness.*.graphml'))
            self.logger.info("Found {} witnesses".format(len(witnesses)))

            # Create unsafe reports independently on status. Later we will create unknown report in addition if status
            # is not "unsafe".
            if "expect several witnesses" in opts and opts["expect several witnesses"] and len(witnesses) != 0:
                self.verdict = 'unsafe'
                # Collect all sources referred by all error traces. Different error traces can refer almost the same
                # sources, so reporting them separately is redundant.
                sources = {}
                error_trace_files = []
                for witness in witnesses:
                    try:
                        error_trace_sources, error_trace_file = self.process_witness(witness, shadow_src_dir,
                                                                                     get_error_trace_id=True)
                        sources.update(error_trace_sources)
                        error_trace_files.append(error_trace_file)
                    except Exception as e:
                        self.logger.warning('Failed to process a witness:\n{}'.format(traceback.format_exc().rstrip()))
                        self.verdict = 'non-verifier unknown'

                        if self.__exception:
                            try:
                                raise e from self.__exception
                            except Exception as e:
                                self.__exception = e
                        else:
                            self.__exception = e

                # Do not report unsafe if processing of all witnesses failed.
                if error_trace_files:
                    self.report_unsafe(sources, error_trace_files)
            if re.match('false', decision_results['status']) and \
                    ("expect several witnesses" not in opts or not opts["expect several witnesses"]):
                self.verdict = 'unsafe'
                try:
                    if len(witnesses) != 1:
                        NotImplementedError('Just one witness is supported (but "{0}" are given)'.
                                            format(len(witnesses)))

                    sources, error_trace_file = self.process_witness(witnesses[0], shadow_src_dir)
                    self.report_unsafe(sources, [error_trace_file])
                except Exception as e:
                    self.logger.warning('Failed to process a witness:\n{}'.format(traceback.format_exc().rstrip()))
                    self.verdict = 'non-verifier unknown'
                    self.__exception = e
            elif not re.match('false', decision_results['status']):
                self.verdict = 'unknown'

                # Prepare file to send it with unknown report.
                os.mkdir('verification')
                verification_problem_desc = os.path.join('verification', 'problem desc.txt')

                # Check resource limitiations
                if decision_results['status'] in ('OUT OF MEMORY', 'TIMEOUT'):
                    if decision_results['status'] == 'OUT OF MEMORY':
                        msg = "memory exhausted"
                    else:
                        msg = "CPU time exhausted"

                    with open(verification_problem_desc, 'w', encoding='utf8') as fp:
                        fp.write(msg)
                else:
                    os.symlink(os.path.relpath(log_file, 'verification'), verification_problem_desc)

                if decision_results['status'] in ('CPU time exhausted', 'memory exhausted'):
                    log_file = 'problem desc.txt'
                    with open(log_file, 'w', encoding='utf8') as fp:
                        fp.write(decision_results['status'])

                core.utils.report(self.logger,
                                  'unknown',
                                  {
                                      'id': "{}/verification/unknown".format(self.id),
                                      'parent id': "{}/verification".format(self.id),
                                      'attrs': [],
                                      'problem desc': core.utils.ReportFiles(
                                          [verification_problem_desc], {verification_problem_desc: 'problem desc.txt'})
                                  },
                                  self.mqs['report files'],
                                  self.vals['report id'],
                                  self.conf['main working directory'],
                                  'verification')

    def process_failed_task(self, task_id):
        """The function has a callback at Job module."""
        self.task_error = self.session.get_task_error(task_id)
        # We do not need task and its files anymore.
        self.session.remove_task(task_id)

        self.verdict = 'non-verifier unknown'

    def process_finished_task(self, task_id, opts, verifier, shadow_src_dir):
        """Function has a callback at Job.py."""
        self.session.download_decision(task_id)

        with zipfile.ZipFile('decision result files.zip') as zfp:
            zfp.extractall()

        with open('decision results.json', encoding='utf8') as fp:
            decision_results = json.load(fp)

        # TODO: specify the computer where the verifier was invoked (this information should be get from BenchExec or VerifierCloud web client.
        log_files_dir = glob.glob(os.path.join('output', 'benchmark*logfiles'))[0]
        log_files = os.listdir(log_files_dir)

        if len(log_files) != 1:
            raise NotImplementedError('Exactly one log file should be outputted (but "{0}" are given)'
                                      .format(len(log_files)))

        log_file = os.path.join(log_files_dir, log_files[0])

        # Send an initial report
        report = {
            'id': "{}/verification".format(self.id),
            'parent id': self.id,
            # TODO: replace with something meaningful, e.g. tool name + tool version + tool configuration.
            'attrs': [],
            'name': verifier,
            'resources': decision_results['resources'],
        }

        if not self.logger.disabled and log_file:
            report['log'] = core.utils.ReportFiles([log_file], {log_file: 'log.txt'})

        if self.conf['upload input files of static verifiers']:
            report['task identifier'] = task_id

        # Save coverage in 'total coverages' dir
        coverage_info_dir = os.path.join('total coverages',
                                         self.conf['job identifier'].replace('/', '-'),
                                         self.rule_specification.replace('/', '-'))
        os.makedirs(os.path.join(self.conf['main working directory'], coverage_info_dir), exist_ok=True)

        self.coverage_info_file = os.path.join(coverage_info_dir,
                                                "{0}_coverage_info.json".format(task_id.replace('/', '-')))

        self.verification_coverage = LCOV(self.logger, os.path.join('output', 'coverage.info'), shadow_src_dir,
                                          self.conf['main working directory'], opts.get('coverage', None),
                                          os.path.join(self.conf['main working directory'], self.coverage_info_file),
                                          os.path.join(self.conf['main working directory'], coverage_info_dir))

        if os.path.isfile('coverage.json'):
            report['coverage'] = core.utils.ReportFiles(['coverage.json'] +
                                                        list(self.verification_coverage.arcnames.keys()),
                                                        arcnames=self.verification_coverage.arcnames)
            self.vals['coverage_finished'][self.conf['job identifier']] = False

        core.utils.report(self.logger,
                          'verification',
                          report,
                          self.mqs['report files'],
                          self.vals['report id'],
                          self.conf['main working directory'])

        try:
            # Submit a verdict
            self.process_single_verdict(decision_results, opts, shadow_src_dir, log_file)
        finally:
            # Submit a closing report
            core.utils.report(self.logger,
                              'verification finish',
                              {'id': report['id']},
                              self.mqs['report files'],
                              self.vals['report id'],
                              self.conf['main working directory'])

    def __trim_file_names(self, file_names, shadow_src_dir):
        arcnames = {}
        for file_name in file_names:
            if file_name.startswith(shadow_src_dir):
                new_file_name = os.path.relpath(file_name, shadow_src_dir)
            else:
                new_file_name = core.utils.make_relative_path(self.logger, self.conf['main working directory'],
                                                              file_name)
            arcnames[file_name] = new_file_name
        return arcnames
