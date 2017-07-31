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
import multiprocessing
import os
import traceback
import zipfile
import json
import xml.etree.ElementTree as ElementTree
import glob
import re

import core.components
import core.utils
import core.session
#import core.vtgvrp.vrp.et as et


class VRP(core.components.Component):

    def __init__(self, conf, logger, parent_id, callbacks, mqs, locks, id=None, work_dir=None, attrs=None,
                 unknown_attrs=None, separate_from_parent=False, include_child_resources=False):
        # Rule specification descriptions were already extracted when getting VTG callbacks.
        self.__pending = dict()
        self.__downloaded = dict()
        self.mqs['VRP result processing'] = multiprocessing.Queue
        self.__workers = core.utils.get_parallel_threads_num(logger, conf, 'todo')

        super(VRP, self).__init__(conf, logger, parent_id, callbacks, mqs, locks, id, work_dir, attrs,
                                  unknown_attrs, separate_from_parent, include_child_resources)

    def process_results(self):
        self.launch_subcomponents(
            [('RP', self.__process_results) for _ in range(self.__workers)]
        )

        pending = {}
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
                        data = self.mqs['VTGVRP pending tasks'].get(block=True, timout=30)
                        if not data:
                            receiving = False
                            self.logger.info("Expect no tasks to be generated")
                        else:
                            pending[data[0]] = data
                    except queue.Empty:
                        self.logger.debug("No tasks has come for last 30 seconds")

            if len(pending) > 0:
                tasks_statuses = session.get_tasks_statuses(list(pending.keys()))
                for task in pending:
                    if task in tasks_statuses['finished']:
                        self.mqs['VRP result processing'].put(pending[task])
                        del pending[task]
                    elif task in tasks_statuses['error']:
                        task_error = session.get_task_error(task)

                        self.logger.warning('Failed to decide verification task: {0}'.format(task_error))

                        with open('task error.txt', 'w', encoding='utf8') as fp:
                            fp.write(task_error)

                        core.utils.report(self.logger,
                                          'unknown',
                                          {
                                              # todo: What should I submit there?
                                              'id': 'id?' + '/unknown',
                                              'parent id': 'id?',
                                              'problem desc': 'task error.txt',
                                              'files': ['task error.txt']
                                          },
                                          self.mqs['report files'],
                                          self.conf['main working directory'])
                        del pending[task]
                    elif task not in tasks_statuses['processing'] and task not in tasks_statuses['pending']:
                        raise KeyError("Cannot find task {!r} in either finished, processing, pending or erroneus "
                                       "tasks".format(task))
            elif not receiving:
                for i in range(self.__workers):
                    self.mqs['VRP result processing'].put(None)
                break

        # todo: Clean work dirs
        self.logger.debug("Shutting down result processing gracefully")

    main = process_results

    def __process_results(self):
        self.logger.debug("A worker starts its watch")
        session = core.session.Session(self.logger, self.conf['Klever Bridge'], self.conf['identifier'])

        while True:
            data = self.mqs['VTGVRP pending tasks'].get()
            if not data:
                break

            task_id, opts, rule_specification, files, shadow_src_dir, work_dir = data
            mydir = os.curdir
            os.chdir(work_dir)
            try:
                self.logger.info('Verification task {} was successfully decided'.format(task_id))
                session.download_decision(task_id)

                with zipfile.ZipFile('decision result files.zip') as zfp:
                    zfp.extractall()

                with open('decision results.json', encoding='utf8') as fp:
                    decision_results = json.load(fp)

                verification_report_id = '{0}/verification'.format(self.id)
                log_file = self.__create_verification_report(verification_report_id, decision_results, files)

                witness_processing_exception = self.__process_single_verdict(
                    decision_results, verification_report_id, opts, rule_specification, shadow_src_dir, log_file)

                self.__create_verification_finish_report(verification_report_id)

                if witness_processing_exception:
                    raise witness_processing_exception
            except Exception:
                self.logger.warning("Cannot process results of the verification task {}:\n {}".
                                    format(task_id, traceback.format_exc().rstrip()))
            # Return back anyway
            os.chdir(mydir)

        self.logger.debug("A worker has finished its watch")

    def __create_verification_report(self, verification_report_id, decision_results, files):
        # TODO: specify the computer where the verifier was invoked (this information should be get from BenchExec or VerifierCloud web client.
        log_files = glob.glob(os.path.join('output', 'benchmark*logfiles/*'))

        if len(log_files) != 1:
            RuntimeError(
                'Exactly one log file should be outputted when source files are merged (but "{0}" are given)'.format(
                    log_files))

        log_file = log_files[0]

        core.utils.report(self.logger,
                          'verification',
                          {
                              # TODO: replace with something meaningful, e.g. tool name + tool version + tool configuration.
                              'id': verification_report_id,
                              'parent id': self.id,
                              # TODO: replace with something meaningful, e.g. tool name + tool version + tool configuration.
                              'attrs': [],
                              'name': self.conf['VTG']['verifier']['name'],
                              'resources': decision_results['resources'],
                              'log': None if self.logger.disabled else log_file,
                              'files': ([] if self.logger.disabled else [log_file]) + (
                                  files if self.conf['upload input files of static verifiers'] else []
                              )
                          },
                          self.mqs['report files'],
                          self.conf['main working directory'])
        return log_file

    def __process_single_verdict(self, decision_results, verification_report_id, opts, rule_specification,
                                 shadow_src_dir, log_file):
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
        witness_processing_exception = None

        if re.match('true', decision_results['status']):
            core.utils.report(self.logger,
                              'safe',
                              {
                                  'id': verification_report_id + '/safe',
                                  'parent id': verification_report_id,
                                  'attrs': [{"Rule specification": rule_specification}],
                                  # TODO: at the moment it is unclear what are verifier proofs.
                                  'proof': None
                              },
                              self.mqs['report files'],
                              self.conf['main working directory'])
        else:
            witnesses = glob.glob(os.path.join('output', 'witness.*.graphml'))

            # Create unsafe reports independently on status. Later we will create unknown report in addition if status
            # is not "unsafe".
            if "expect several files" in opts and opts["expect several files"] and len(witnesses) != 0:
                for witness in witnesses:
                    try:
                        etrace = et.import_error_trace(self.logger, witness,
                                                       opts["namespace"] if "namespace" in opts else None)

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
                                              'id': verification_report_id + '/unsafe' + '_' + trace_id,
                                              'parent id': verification_report_id,
                                              'attrs': [
                                                  {"Rule specification": rule_specification},
                                                  {"Error trace identifier": trace_id}],
                                              'error trace': error_trace_name,
                                              'files': [error_trace_name] + list(arcnames.keys()),
                                              'arcname': arcnames
                                          },
                                          self.mqs['report files'],
                                          self.conf['main working directory'],
                                          trace_id)
                    except Exception as e:
                        if witness_processing_exception:
                            try:
                                raise e from witness_processing_exception
                            except Exception as e:
                                witness_processing_exception = e
                        else:
                            witness_processing_exception = e

            if re.match('false', decision_results['status']) and \
                    ("expect several files" not in opts or not opts["expect several files"]):
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
                                          'id': verification_report_id + '/unsafe',
                                          'parent id': verification_report_id,
                                          'attrs': [{"Rule specification": rule_specification}],
                                          'error trace': 'error trace.json',
                                          'files': ['error trace.json'] + list(arcnames.keys()),
                                          'arcname': arcnames
                                      },
                                      self.mqs['report files'],
                                      self.conf['main working directory'])
                except Exception as e:
                    witness_processing_exception = e

            elif not re.match('false', decision_results['status']):
                # Prepare file to send it with unknown report.
                # TODO: otherwise just the same file as parent log is reported, looks strange.
                if decision_results['status'] in ('CPU time exhausted', 'memory exhausted'):
                    log_file = 'error.txt'
                    with open(log_file, 'w', encoding='utf8') as fp:
                        fp.write(decision_results['status'])

                core.utils.report(self.logger,
                                  'unknown',
                                  {
                                      'id': verification_report_id + '/unknown',
                                      'parent id': verification_report_id,
                                      'attrs': [{"Rule specification": rule_specification}],
                                      'problem desc': log_file,
                                      'files': [log_file]
                                  },
                                  self.mqs['report files'],
                                  self.conf['main working directory'])

        return witness_processing_exception

    def __create_verification_finish_report(self, verification_report_id):
        core.utils.report(self.logger,
                          'verification finish',
                          {'id': verification_report_id},
                          self.mqs['report files'],
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
