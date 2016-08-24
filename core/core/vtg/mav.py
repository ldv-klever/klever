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

import json
import os
import tarfile
import time
import glob
import re
import shutil
from enum import Enum
from abc import abstractclassmethod, ABCMeta

import core.components
import core.session
import core.utils
from core.vtg.common import CommonStrategy


# Existed presets for MAV, which are specify the level of accuracy:
# more higher level will provide more accurate results,
# but also will require more resources.
# Can be overwritten with verifier options.
class MAVPreset(Enum):
    L1 = {'ATL': 900, 'IITL': 20, 'BITL': 100, 'FITL': 100}
    L2 = {'ATL': 900, 'IITL': 20, 'BITL': 100, 'FITL': 1200}
    L3 = {'ATL': 900, 'IITL': 20, 'BITL': 200, 'FITL': 1200}
    L4 = {'ATL': 900, 'IITL': 20, 'BITL': 900, 'FITL': 1200}
    L5 = {'ATL': 1200, 'IITL': 50, 'BITL': 900, 'FITL': 1200}


# This class represent Multi-Aspect Verification (MAV) strategies.
class MAV(CommonStrategy):

    __metaclass__ = ABCMeta

    path_to_file_with_results = 'output/mav_results_file'
    number_of_asserts = 0
    assert_function = {}  # Map of all checked asserts to corresponding 'error' functions.
    path_to_property_automata = 'property_automata.spc'
    error_function_prefix = '__VERIFIER_error_'
    # Relevant for revision 20410.
    verifier_results_regexp = r"\[assert=\[(.+)\], time=(\d+), verdict=(\w+)\]"
    resources_written = False
    resources_written_unsafe = False
    # Possible values: internal, external, no.
    relaunch = "internal"
    is_finished = False  # TODO: work-around.

    def perform_sanity_checks(self):
        if self.mpv:
            # MPV strategies should be used for property automata.
            raise AttributeError("MAV-strategies do not support property automata")
        if 'unite rule specifications' not in self.conf \
            or not self.conf['unite rule specifications']:
            raise AttributeError("Current VTG strategy supports only united bug types")

    def perform_preprocess_actions(self):
        self.logger.info('Starting Multi-Aspect Verification')
        self.print_strategy_information()
        self.create_asserts()
        self.prepare_common_verification_task_desc()
        self.prepare_bug_kind_functions_file()
        self.create_mea()
        self.add_verifier_options()

    def perform_postprocess_actions(self):
        self.print_mea_stats()

    def main_cycle(self):
        iterations = 0
        while True:
            iterations += 1
            self.resources_written_unsafe = False
            self.resources_written = False
            self.create_property_automata()
            self.logger.info('Starting iteration {0}'.format(iterations))
            self.prepare_src_files()
            self.prepare_verification_task_files_archive()
            # Clear output directory since it is the same for all runs.
            if os.path.exists('output'):
                shutil.rmtree('output')
            self.decide_verification_task(iterations)
            if self.is_finished:
                break
        self.logger.info('Conditional Multi-Aspect Verification has been completed in {0} iteration(s)'.
                         format(iterations))

        core.utils.report(self.logger,
                          'data',
                          {
                              'id': self.id,
                              'data': json.dumps({
                                  'the number of verification tasks prepared for abstract verification task': iterations
                              }, ensure_ascii=False, sort_keys=True, indent=4)
                          },
                          self.mqs['report files'],
                          self.conf['main working directory'])

    @abstractclassmethod
    def print_strategy_information(self):
        pass

    @abstractclassmethod
    def create_asserts(self):
        pass

    def prepare_verification_task_files_archive(self):
        self.logger.debug('Prepare archive with verification task files')

        with tarfile.open('task files.tar.gz', 'w:gz', encoding='utf8') as tar:
            if os.path.isfile(self.path_to_property_automata):
                tar.add(self.path_to_property_automata)
            for file in self.task_desc['files']:
                tar.add(file)
            self.task_desc['files'] = [os.path.basename(file) for file in self.task_desc['files']]

    def create_property_automata(self):
        self.task_desc['specification file'] = self.path_to_property_automata
        with open(self.path_to_property_automata, 'w', encoding='utf8') as fp:
            fp.write('//This file with property automaton was generated for Multi-Aspect Verification.\n')
            fp.write('CONTROL AUTOMATON MAV_ERROR_FUNCTIONS\n')
            fp.write('INITIAL STATE Init;\n')
            fp.write('STATE USEFIRST Init:\n')
            for bug_kind, function in self.assert_function.items():
                fp.write('  MATCH {{{0}{1}()}} -> ERROR("{2}");\n'.format(self.error_function_prefix,
                                                                      function, bug_kind))
            fp.write('END AUTOMATON\n')

    def add_verifier_options(self):
        self.logger.debug('Add common verifier options for MAV')

        # Specify default configuration.
        self.conf['VTG strategy']['verifier']['options'].append({'-ldv': ''})

        # Add entry point since we do not use property file.
        self.add_option_for_entry_point()

        # Specify path for file with results.
        self.conf['VTG strategy']['verifier']['options'].append(
            {'-setprop': "analysis.mav.resultsFile={0}".format(self.path_to_file_with_results)})

        # Specify specification file.
        self.conf['VTG strategy']['verifier']['options'].append(
            {'-spec': self.path_to_property_automata})

        # Multi-Aspect Verification specific options.
        self.conf['VTG strategy']['verifier']['options'].append(
            {'-setprop': 'analysis.stopAfterError=false'})
        self.conf['VTG strategy']['verifier']['options'].append(
            {'-setprop': 'analysis.multiAspectVerification=true'})
        self.conf['VTG strategy']['verifier']['options'].append(
            {'-setprop': 'analysis.mav.precisionCleanStrategy=BY_SPECIFICATION'})
        self.conf['VTG strategy']['verifier']['options'].append(
            {'-setprop': 'analysis.mav.precisionCleanSet=WAITLIST'})
        self.conf['VTG strategy']['verifier']['options'].append(
            {'-setprop': 'analysis.mav.specificationComparator=VIOLATED_PROPERTY'})
        self.conf['VTG strategy']['verifier']['options'].append(
            {'-setprop': 'cpa.arg.errorPath.file='})
        self.conf['VTG strategy']['verifier']['options'].append(
            {'-setprop': 'counterexample.export.filters=NullCounterexampleFilter'})
        self.conf['VTG strategy']['verifier']['options'].append(
            {'-setprop': 'counterexample.export.exportImmediately=true'})

        # Option for MEA.
        if self.mea:
            self.conf['VTG strategy']['verifier']['options'].append(
                {'-setprop': 'analysis.mav.stopAfterError=false'})

        # Option for Conditional Multi-Aspect Verification (CMAV).
        if 'relaunch' in self.conf['VTG strategy']['verifier']:
            self.relaunch = self.conf['VTG strategy']['verifier']['relaunch']
        if self.relaunch == 'internal':
            self.logger.info('Launching Conditional Multi-Aspect Verification in one verification run')
            self.conf['VTG strategy']['verifier']['options'].append(
                {'-setprop': 'analysis.mav.relaunchInOneRun=true'})
        elif self.relaunch == 'external':
            self.logger.info('Launching Conditional Multi-Aspect Verification in several verification run')
        else:
            self.logger.info('Launching single iteration of Multi-Aspect Verification')

        self.parse_preset()

    def parse_preset(self):
        # By default no preset is specified. In this case it is expected, that the user
        # will specify required limitation with verifier options.
        selected_preset = None
        if 'mav_preset' in self.conf['VTG strategy']['verifier']:
            specified_preset = self.conf['VTG strategy']['verifier']['mav_preset']
            for preset in MAVPreset:
                if preset.name == specified_preset:
                    selected_preset = preset
            if not selected_preset:
                self.logger.warning('Specified MAV preset "{0}" is not supported, no limitations will be used'.
                                    format(specified_preset))
            else:
                # Existed preset was specified.
                self.logger.info('Using MAV preset "{0}" for limitations'.format(selected_preset.name))
                self.conf['VTG strategy']['verifier']['options'].append(
                    {'-setprop': 'analysis.mav.assertTimeLimit={0}'.
                        format(selected_preset.value['ATL'])})
                self.conf['VTG strategy']['verifier']['options'].append(
                    {'-setprop': 'analysis.mav.idleIntervalTimeLimit={0}'.
                        format(selected_preset.value['IITL'])})
                self.conf['VTG strategy']['verifier']['options'].append(
                    {'-setprop': 'analysis.mav.basicIntervalTimeLimit={0}'.
                        format(selected_preset.value['BITL'])})
                self.conf['VTG strategy']['verifier']['options'].append(
                    {'-setprop': 'analysis.mav.firstIntervalTimeLimit={0}'.
                        format(selected_preset.value['FITL'])})
        else:
            self.logger.debug('No MAV preset was specified, no limitations will be used')

    @abstractclassmethod
    def prepare_bug_kind_functions_file(self):
        pass

    def create_verification_report(self, verification_report_id, decision_results, bug_kind=None):
        # TODO: specify the computer where the verifier was invoked (this information should be get from BenchExec or VerifierCloud web client.
        log_file = self.get_verifier_log_file()
        core.utils.report(self.logger,
                          'verification',
                          {
                              # TODO: replace with something meaningful, e.g. tool name + tool version + tool configuration.
                              'id': verification_report_id,
                              'parent id': self.id,
                              # TODO: replace with something meaningful, e.g. tool name + tool version + tool configuration.
                              'attrs': [],
                              'name': self.conf['VTG strategy']['verifier']['name'],
                              'resources': decision_results['resources'],
                              'log': log_file,
                              'files': ([log_file] if log_file else []) + (
                                  ['benchmark.xml', self.path_to_property_automata] + self.task_desc['files']
                                  if self.conf['upload input files of static verifiers']
                                  else []
                              )
                          },
                          self.mqs['report files'],
                          self.conf['main working directory'],
                          bug_kind)
        if decision_results['status'] == 'unsafe' and self.mea:
            # Unsafe-incomplete.
            # TODO: fix this.
            is_incomplete = False
            log_file = self.get_verifier_log_file()
            with open(log_file, encoding='utf8') as fp:
                for line in fp:
                    match = re.search(r'Assert \[(.+)\] has exhausted its', line)
                    if match:
                        exhausted_assert = match.group(1)
                        if exhausted_assert in bug_kind:
                            is_incomplete = True
                    match = re.search(r'Shutdown requested', line)
                    if match:
                        is_incomplete = True
            if is_incomplete:
                name = 'unsafe-incomplete{0}.txt'.format(bug_kind)
                with open(name, 'w', encoding='utf8') as fp:
                    fp.write('Unsafe-incomplete')
                core.utils.report(self.logger,
                                  'unknown',
                                  {
                                      'id': verification_report_id + '/unsafe-incomplete',
                                      'parent id': verification_report_id,
                                      'attrs': [],
                                      'problem desc': name,
                                      'files': [name]
                                  },
                                  self.mqs['report files'],
                                  self.conf['main working directory'],
                                  bug_kind)
            self.resources_written_unsafe = True
        self.resources_written = True

    def process_global_error(self, task_error):
        self.logger.warning('Failed to decide verification task: {0}'.format(task_error))
        with open('task error.txt', 'w', encoding='utf8') as fp:
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

    def get_violated_property(self, file):
        for line in reversed(list(open(file, encoding='utf8'))):
            result = re.search(r"<data key=\"violatedProperty\">(.*)</data>", line)
            if result:
                return result.group(1)
        return None

    # TODO: Why it can not return anything?
    def decide_verification_task(self, iteration):
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
                break

            if task_status == 'FINISHED':
                self.logger.info('Iteration of Multi-Aspect Verification has been successfully completed')

                session.download_decision(task_id)

                with tarfile.open("decision result files.tar.gz", encoding='utf8') as tar:
                    tar.extractall()

                with open('decision results.json', encoding='utf8') as fp:
                    decision_results = json.load(fp)

                verification_report_id = '{0}/verification{1}'.format(self.id, iteration)
                self.create_verification_report(verification_report_id, decision_results, iteration)

                # Parse file with results.
                is_new_verdicts = False
                try:
                    with open(self.path_to_file_with_results, encoding='utf8') as fp:
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
                            else:
                                result = re.search(r'\[(.+)\]', line)
                                if result:
                                    # LCA here.
                                    LCA = result.group(1)
                                    self.logger.info('LCA is "{0}"'.format(LCA))
                                    if not is_new_verdicts:
                                        is_new_verdicts = True
                                        results[LCA] = 'unknown'

                except FileNotFoundError:
                    log_file = self.get_verifier_log_file()
                    with open(log_file, encoding='utf8') as fp:
                        content = fp.readlines()
                    task_error = content
                    self.process_global_error(task_error)
                    break

                # No new transitions -> change all checking verdicts to unknown.
                if not is_new_verdicts:
                    self.logger.info('No new verdicts were obtained during this iteration')
                    self.logger.info('Stopping algorithm')
                    for bug_kind, verdict in results.items():
                        results[bug_kind] = 'unknown'

                # Process all found error traces.
                witness_assert = {}  # Witnss (error trace) <-> assert (bug kind).
                all_found_error_traces = glob.glob(self.path_to_error_traces)
                for error_trace in all_found_error_traces:
                    found_bug_kind = self.get_violated_property(error_trace)
                    witness_assert[error_trace] = found_bug_kind

                for bug_kind, verdict in results.items():
                    if verdict == 'checking':
                        if self.relaunch == 'external':
                            is_finished = False
                        else:
                            verdict = 'unknown'
                    decision_results['status'] = verdict
                    if verdict == 'unsafe':
                        for error_trace in all_found_error_traces:
                            if witness_assert[error_trace] == bug_kind:
                                self.process_single_verdict(decision_results, verification_report_id,
                                                            assertion=bug_kind,
                                                            specified_error_trace=error_trace)
                                self.remove_assertion(bug_kind)
                    else:  # Verdicts unknown or safe.
                        self.process_single_verdict(decision_results, verification_report_id,
                                                    assertion=bug_kind)
                        if verdict != 'checking':
                            self.remove_assertion(bug_kind)

                self.create_verification_finish_report(verification_report_id, iteration)
                break
            time.sleep(1)
        self.is_finished = is_finished


