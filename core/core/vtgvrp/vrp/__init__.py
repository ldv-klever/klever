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

import queue
import os
import zipfile
import json
import xml.etree.ElementTree as ElementTree
import glob
import re
import time
import traceback

import core.components
import core.utils
import core.session
from core.vtgvrp.vrp.et import import_error_trace
from core.vtgvrp.vrp.coverage_parser import LCOV


class VRP(core.components.Component):

    def __init__(self, conf, logger, parent_id, callbacks, mqs, locks, id=None, work_dir=None, attrs=None,
                 separate_from_parent=False, include_child_resources=False):
        # Rule specification descriptions were already extracted when getting VTG callbacks.
        self.__downloaded = dict()
        self.__workers = None

        # Read this in a callback
        self.verdict = None
        self.rule_specification = None
        self.verification_object = None

        # Common initialization
        super(VRP, self).__init__(conf, logger, parent_id, callbacks, mqs, locks, id, work_dir, attrs,
                                  separate_from_parent, include_child_resources)

    def process_results(self):
        self.__workers = core.utils.get_parallel_threads_num(self.logger, self.conf, 'Tasks generation')
        self.logger.info("Going to start {} workers to process results".format(self.__workers))

        # Do result processing
        # Start plugins
        subcomponents = [('RPL', self.result_processing)]
        for i in range(self.__workers):
            subcomponents.append(('RPWL', self.__loop_worker))
        self.launch_subcomponents(*subcomponents)

        # Finalize
        self.finish_tasks_results_processing()

    def finish_tasks_results_processing(self):
        """Function has a callback at Job.py."""
        self.logger.info('Task results processing has finished')

    main = process_results

    def result_processing(self):
        pending = dict()
        # todo: implement them in GUI
        #if 'task solutions pending period' in self.conf['VTGVRP']['VRP']:
        #    solution_timeout = int(self.conf['VTGVRP']['VRP']['task solutions pending period'])
        #else:
        solution_timeout = 30
        #if 'task generation pending period' in self.conf['VTGVRP']['VRP']:
        #    generation_timeout = int(self.conf['VTGVRP']['VRP']['task generation pending period'])
        #else:
        generation_timeout = 30

        def submit_processing_task(status, t):
            self.mqs['VRP processing tasks'].put([status, pending[t]])

        receiving = True
        session = core.session.Session(self.logger, self.conf['Klever Bridge'], self.conf['identifier'])
        while True:
            # Get new tasks
            if receiving:
                if len(pending) > 0:
                    number = 0
                    try:
                        while True:
                            data = self.mqs['VTGVRP pending tasks'].get_nowait()
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
                        data = self.mqs['VTGVRP pending tasks'].get(block=True, timeout=generation_timeout)
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
                self.mqs['VTGVRP pending tasks'].close()
                for _ in range(self.__workers):
                    self.mqs['VRP processing tasks'].put(None)
                self.mqs['VRP processing tasks'].close()
                break

            time.sleep(solution_timeout)

        self.logger.debug("Shutting down result processing gracefully")

    def __loop_worker(self):
        self.logger.info("VRP fetcher is ready to work")
        while True:
            element = self.mqs['VRP processing tasks'].get()
            if element is None:
                break

            status, data = element
            vo = data[2]
            rule = data[3]
            new_id = "{}/{}/RP".format(vo, rule)
            workdir = os.path.join(vo, rule)
            try:
                rp = RP(self.conf, self.logger, self.id, self.callbacks, self.mqs, self.locks, new_id, workdir,
                        [{"Rule specification": rule}, {"Verification object": vo}], separate_from_parent=True,
                        element=element)
                rp.start()
                rp.join()
            except core.components.ComponentError:
                self.logger.debug("RP that processed {!r}, {!r} failed".format(vo, rule))
            self.mqs['VTGVRP processed tasks'].put((vo, rule))

        self.logger.info("VRP fetcher finishes its work")


class RP(core.components.Component):

    def __init__(self, conf, logger, parent_id, callbacks, mqs, locks, id=None, work_dir=None, attrs=None,
                 separate_from_parent=False, include_child_resources=False, element=None):
        # Read this in a callback
        self.element = element
        self.verdict = None
        self.rule_specification = None
        self.verification_object = None
        self.__exception = None

        # Common initialization
        super(RP, self).__init__(conf, logger, parent_id, callbacks, mqs, locks, id, work_dir, attrs,
                                 separate_from_parent, include_child_resources)
        self.session = core.session.Session(self.logger, self.conf['Klever Bridge'], self.conf['identifier'])

    def fetcher(self):
        self.logger.info("VRP instance is ready to work")
        element = self.element
        status, data = element
        task_id, opts, verification_object, rule_specification, verifier, shadow_src_dir, work_dir = data
        self.verification_object = verification_object
        self.rule_specification = rule_specification

        if len(verifier) > 20:
            self.logger.warning("Verifier name {!r} is longer than 20 symbols, shrinking it")
            verifier = verifier[0:20]

        try:
            if status == 'finished':
                self.__process_finished_task(task_id, opts, verifier, shadow_src_dir, work_dir)
            elif status == 'error':
                self.__process_failed_task(task_id)
            else:
                raise ValueError("Unknown task {!r} status {!r}".format(task_id, status))
        finally:
            self.session.remove_task(task_id)

    main = fetcher

    def send_unknown_report(self, report_id, parent_id, problem):
        """The function has a callback at Job module."""
        self.__send_unknown_report(report_id, parent_id, problem)

    def __send_unknown_report(self, report_id, parent_id, problem):
        self.verdict = 'unknown'

        core.utils.report(self.logger,
                          'unknown',
                          {
                              'id': "{}/unknown".format(report_id),
                              'parent id': parent_id,
                              'attrs': [],
                              'problem desc': problem,
                              'files': [problem]
                          },
                          self.mqs['report files'],
                          self.conf['main working directory'])

    def process_single_verdict(self, task_id, decision_results, opts, shadow_src_dir, log_file):
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
                                  'id': "{}/{}/verification/safe".format(self.id, task_id),
                                  'parent id': "{}/{}/verification".format(self.id, task_id),
                                  'attrs': [],
                                  # TODO: at the moment it is unclear what are verifier proofs.
                                  'proof': None
                              },
                              self.mqs['report files'],
                              self.conf['main working directory'])
            self.verdict = 'safe'
        else:
            witnesses = glob.glob(os.path.join('output', 'witness.*.graphml'))
            self.logger.info("Found {} witnesses".format(len(witnesses)))

            # Create unsafe reports independently on status. Later we will create unknown report in addition if status
            # is not "unsafe".
            if "expect several witnesses" in opts and opts["expect several witnesses"] and len(witnesses) != 0:
                for witness in witnesses:
                    self.verdict = 'unsafe'
                    try:
                        etrace = import_error_trace(self.logger, witness)

                        result = re.search(r'witness\.(.*)\.graphml', witness)
                        trace_id = result.groups()[0]
                        error_trace_name = 'error trace_' + trace_id + '.json'

                        self.logger.info('Write processed witness to "' + error_trace_name + '"')
                        arcnames = self.__trim_file_names(etrace['files'], shadow_src_dir)
                        etrace['files'] = [arcnames[file] for file in etrace['files']]
                        with open(error_trace_name, 'w', encoding='utf8') as fp:
                            json.dump(etrace, fp, ensure_ascii=False, sort_keys=True, indent=4)

                        core.utils.report(self.logger,
                                          'unsafe',
                                          {
                                              'id': "{}/{}/verification/unsafe_{}".format(self.id, task_id, trace_id),
                                              'parent id': "{}/{}/verification".format(self.id, task_id),
                                              'attrs': [{"Error trace identifier": trace_id}],
                                              'error trace': error_trace_name,
                                              'files': [error_trace_name] + list(arcnames.keys()),
                                              'arcname': arcnames
                                          },
                                          self.mqs['report files'],
                                          self.conf['main working directory'])
                    except Exception as e:
                        self.logger.warning('Failed to process a witness:\n{}'.format(traceback.format_exc().rstrip()))
                        if self.__exception:
                            try:
                                raise e from self.__exception
                            except Exception as e:
                                self.__exception = e
                        else:
                            self.__exception = e

            if re.match('false', decision_results['status']) and \
                    ("expect several witnesses" not in opts or not opts["expect several witnesses"]):
                self.verdict = 'unsafe'
                try:
                    if len(witnesses) != 1:
                        NotImplementedError('Just one witness is supported (but "{0}" are given)'.
                                            format(len(witnesses)))

                    etrace = et.import_error_trace(self.logger, witnesses[0])
                    self.logger.info('Write processed witness to "error trace.json"')

                    arcnames = self.__trim_file_names(etrace['files'], shadow_src_dir)
                    etrace['files'] = [arcnames[file] for file in etrace['files']]
                    with open('error trace.json', 'w', encoding='utf8') as fp:
                        json.dump(etrace, fp, ensure_ascii=False, sort_keys=True, indent=4)

                    core.utils.report(self.logger,
                                      'unsafe',
                                      {
                                          'id': "{}/{}/verification/unsafe".format(self.id, task_id),
                                          'parent id': "{}/{}/verification".format(self.id, task_id),
                                          'attrs': [],
                                          'error trace': 'error trace.json',
                                          'files': ['error trace.json'] + list(arcnames.keys()),
                                          'arcname': arcnames
                                      },
                                      self.mqs['report files'],
                                      self.conf['main working directory'])
                except Exception as e:
                    self.logger.warning('Failed to process a witness:\n{}'.format(traceback.format_exc().rstrip()))
                    self.__exception = e

            elif not re.match('false', decision_results['status']):
                # Prepare file to send it with unknown report.
                # Check resource limitiations
                if decision_results['status'] in ('OUT OF MEMORY', 'TIMEOUT'):
                    if decision_results['status'] == 'OUT OF MEMORY':
                        msg = "memory exhausted"
                    else:
                        msg = "CPU time exhausted"
                    log_file = 'error.txt'
                    with open(log_file, 'w', encoding='utf8') as fp:
                        fp.write(msg)

                if decision_results['status'] in ('CPU time exhausted', 'memory exhausted'):
                    log_file = 'error.txt'
                    with open(log_file, 'w', encoding='utf8') as fp:
                        fp.write(decision_results['status'])

                self.__send_unknown_report("{}/{}/verification".format(self.id, task_id),
                                           "{}/{}/verification".format(self.id, task_id), log_file)

    def __process_failed_task(self, task_id):
        task_error = self.session.get_task_error(task_id)
        self.logger.warning('Failed to decide verification task: {0}'.format(task_error))

        task_err_file = 'task error.txt'
        with open(task_err_file, 'w', encoding='utf8') as fp:
            fp.write(task_error)

        self.send_unknown_report("{}/{}".format(self.id, task_id), self.id, task_err_file)

    def __process_finished_task(self, task_id, opts, verifier, shadow_src_dir, work_dir):
        self.logger.debug("Prcess results of the task {}".format(task_id))
        vtgvrp_path, vrp_dir = os.path.abspath(os.path.curdir).split('/vrp/', 1)
        work_dir = os.path.join(vtgvrp_path, 'vtg', work_dir)
        mydir = os.path.abspath(os.curdir)
        os.chdir(work_dir)

        try:
            self.session.download_decision(task_id)

            with zipfile.ZipFile('decision result files.zip') as zfp:
                zfp.extractall()

            with open('decision results.json', encoding='utf8') as fp:
                decision_results = json.load(fp)

            # TODO: specify the computer where the verifier was invoked (this information should be get from BenchExec or VerifierCloud web client.
            log_files = glob.glob(os.path.join('output', 'benchmark*logfiles/*'))

            if len(log_files) != 1:
                raise RuntimeError(
                    'Exactly one log file should be outputted when source files are merged (but "{0}" are given)'.format(
                        log_files))

            log_file = log_files[0]

            # Send an initial report
            report = {
                'id': "{}/{}/verification".format(self.id, task_id),
                'parent id': self.id,
                # TODO: replace with something meaningful, e.g. tool name + tool version + tool configuration.
                'attrs': [],
                'name': verifier,
                'resources': decision_results['resources'],
                'log': None if self.logger.disabled or not log_file else log_file,
                'coverage':
                    'coverage.json' if 'coverage' in opts and opts['coverage'] else None,
                'files': {
                    'report': [] if self.logger.disabled or not log_file else [log_file]
                }
            }
            if self.conf['upload input files of static verifiers']:
                report['task identifier'] = task_id
            if 'coverage' in opts and opts['coverage'] and\
                    os.path.isfile(os.path.join('output', 'coverage.info')):
                cov = LCOV(self.logger, os.path.join('output', 'coverage.info'),
                           shadow_src_dir, self.conf['main working directory'],
                           opts['coverage'])
                with open('coverage.json', 'w', encoding='utf-8') as fp:
                    json.dump(cov.coverage, fp, ensure_ascii=True, sort_keys=True, indent=4)

                arcnames = cov.arcnames
                report['files']['coverage'] = ['coverage.json'] + list(arcnames.keys())
                report['arcname'] = arcnames
            core.utils.report(self.logger,
                              'verification',
                              report,
                              self.mqs['report files'],
                              self.conf['main working directory'])

            # Submit a verdict
            self.process_single_verdict(task_id, decision_results, opts, shadow_src_dir, log_file)
            # Submit a closing report
            core.utils.report(self.logger,
                              'verification finish',
                              {'id': "{}/{}/verification".format(self.id, task_id)},
                              self.mqs['report files'],
                              self.conf['main working directory'])
            if self.__exception:
                self.logger.warning("Raising the saved exception")
                raise self.__exception
        finally:
            # Return back anyway
            os.chdir(mydir)

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
