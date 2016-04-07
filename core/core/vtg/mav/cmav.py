#!/usr/bin/python3

import json
import tarfile
import re
import glob
import shutil
import os
import time

import core.components
import core.session
import core.utils


from core.vtg.mav import MAV


# This class implements Conditional Multi-Aspect Verification in several verification runs.
class CMAV(MAV):

    results = {}
    is_finished = False  # get rid of it.

    def start_mav_cycle(self):
        self.logger.info('Conditional Multi-Aspect Verification in several verification runs')
        iterations = 0
        while True:
            iterations += 1
            self.resources_written = False
            self.create_property_automata()
            self.logger.info('Starting iteration {0}'.format(iterations))
            self.prepare_src_files()
            self.prepare_verification_task_files_archive()
            # Clear output directory since it is the same for all runs.
            if os.path.exists('output'):
                shutil.rmtree('output')
            self.decide_verification_task()

            if self.is_finished:
                break

        self.logger.info('Conditional Multi-Aspect Verification has been completed in {0} iteration(s)'.
                         format(iterations))

    def process_global_error(self, task_error):
        self.logger.warning('Failed to decide verification task: {0}'.format(task_error))
        with open('task error.txt', 'w', encoding='ascii') as fp:
            fp.write(task_error)

        core.utils.report(self.logger,
                          'unknown',
                          {
                              'id': self.id + '/unknown',
                              'parent id': self.id,
                              'problem desc': 'task error.txt',
                              'files': ['task error.txt']
                          },
                          self.mqs['report files'],
                          self.conf['main working directory'])

        self.verification_status = 'unknown'

    def remove_assertion(self, assertion):
        if self.assert_function.__contains__(assertion):
            self.logger.info("Stop checking for assert {0}".format(assertion))
            self.assert_function.__delitem__(assertion)

    def decide_verification_task(self):
        is_finished = True
        results = {}
        self.verification_status = None

        session = core.session.Session(self.logger, self.conf['Klever Bridge'], self.conf['identifier'])
        task_id = session.schedule_task(self.task_desc)

        while True:
            task_status = session.get_task_status(task_id)
            self.logger.info('Status of verification task "{0}" is "{1}"'.format(task_id, task_status))

            if task_status == 'ERROR':
                task_error = session.get_task_error(task_id)
                self.process_global_error(task_error)
                self.is_finished = True
                break

            if task_status == 'FINISHED':
                self.logger.info('Iteration of Multi-Aspect Verification has been successfully completed')

                session.download_decision(task_id)

                with tarfile.open("decision result files.tar.gz") as tar:
                    tar.extractall()

                with open('decision results.json', encoding='ascii') as fp:
                    decision_results = json.load(fp)

                # Parse file with results.
                is_new_verdicts = False
                try:
                    with open(self.path_to_file_with_results, encoding='ascii') as fp:
                        for line in fp:
                            result = re.search(self.verifier_results_regexp, line)
                            if result:
                                bug_kind = result.group(1)
                                verdict = result.group(3).lower()
                                if verdict == 'safe' or verdict == 'unsafe' or verdict == 'unknown':
                                    is_new_verdicts = True
                                results[bug_kind] = verdict
                                self.logger.debug('Assertion "{0}" got verdict "{1}"'.
                                                  format(bug_kind, verdict))
                except FileNotFoundError:
                    with open('cil.i.log', encoding='ascii') as fp:
                        content = fp.readlines()
                    task_error = content
                    self.process_global_error(task_error)
                    self.is_finished = True
                    break

                # No new transitions -> change all checking verdicts to unknown.
                if not is_new_verdicts:
                    self.logger.info('No new verdicts were obtained during this iteration')
                    self.logger.info('Stopping CMAV algorithm')
                    for bug_kind, verdict in results.items():
                        results[bug_kind] = 'unknown'

                # Process all found error traces.
                witness_assert = {}  # Witnss (error trace) <-> assert (bug kind).
                all_found_error_traces = glob.glob(self.path_to_witnesses)
                for error_trace in all_found_error_traces:
                    found_bug_kind = self.get_violated_property(error_trace)
                    witness_assert[error_trace] = found_bug_kind

                for bug_kind, verdict in results.items():
                    decision_results['status'] = verdict
                    if verdict == 'checking':
                        is_finished = False
                    elif verdict == 'unsafe':
                        for error_trace in all_found_error_traces:
                            if witness_assert[error_trace] == bug_kind:
                                self.process_single_verdict(decision_results, suffix=bug_kind,
                                                            specified_witness=error_trace)
                                self.remove_assertion(bug_kind)
                    else:  # Verdicts unknown or safe.
                        self.process_single_verdict(decision_results, suffix=bug_kind)
                        self.remove_assertion(bug_kind)
                self.is_finished = is_finished
                break

            time.sleep(1)
