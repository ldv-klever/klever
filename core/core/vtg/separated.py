#!/usr/bin/python3

import json
import os
import tarfile
import time
import glob
import re
from abc import abstractclassmethod, ABCMeta

import core.components
import core.session
import core.utils
from core.vtg.common import CommonStrategy


# This class represent sequential VTG strategies.
class SeparatedStrategy(CommonStrategy):

    __metaclass__ = ABCMeta

    automaton_file = None
    resources_written = False

    def perform_sanity_checks(self):
        if 'unite rule specifications' in self.conf and self.conf['unite rule specifications']:
            raise AttributeError("Current VTG strategy does not support united bug types")

    def perform_preprocess_actions(self):
        self.create_mea()
        self.set_verifier_options()
        self.print_strategy_information()

    def perform_postprocess_actions(self):
        self.print_mea_stats()

    @abstractclassmethod
    def main_cycle(self):
        pass

    @abstractclassmethod
    def print_strategy_information(self):
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
                                  (['benchmark.xml'] if os.path.isfile('benchmark.xml') else []) +
                                  [self.automaton_file] + self.task_desc['files']
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
            is_incomplete = True
            log_file = self.get_verifier_log_file()
            with open(log_file) as fp:
                for line in fp:
                    match = re.search(r'Verification result: FALSE', line)
                    if match:
                        is_incomplete = False
            if is_incomplete:
                with open('unsafe-incomplete.txt', 'w', encoding='ascii') as fp:
                    fp.write('Unsafe-incomplete')
                core.utils.report(self.logger,
                                  'unknown',
                                  {
                                      'id': verification_report_id + '/unsafe-incomplete',
                                      'parent id': verification_report_id,
                                      'attrs': [],
                                      'problem desc': 'unsafe-incomplete.txt',
                                      'files': ['unsafe-incomplete.txt']
                                  },
                                  self.mqs['report files'],
                                  self.conf['main working directory'])

    @abstractclassmethod
    def prepare_property_automaton(self, bug_kind=None):
        pass

    def set_specific_options(self, bug_kind=None):
        if self.mpv:
            self.prepare_property_automaton(bug_kind)
        else:
            self.prepare_property_file()

    def prepare_property_file(self):
        self.logger.info('Prepare verifier property file')

        if 'entry points' in self.conf['abstract task desc']:
            if len(self.conf['abstract task desc']['entry points']) > 1:
                raise NotImplementedError('Several entry points are not supported')

            with open('unreach-call.prp', 'w', encoding='ascii') as fp:
                fp.write('CHECK( init({0}()), LTL(G ! call(__VERIFIER_error())) )'.format(
                    self.conf['abstract task desc']['entry points'][0]))

            self.task_desc['property file'] = 'unreach-call.prp'
            self.automaton_file = self.task_desc['property file']

            self.logger.debug('Verifier property file was outputted to "unreach-call.prp"')
        else:
            self.logger.warning('Verifier property file was not prepared since entry points were not specified')

    def set_verifier_options(self):
        if self.mea:
            self.conf['VTG strategy']['verifier']['options'].append(
                {'-setprop': 'analysis.stopAfterError=false'})
            if self.mpv:
                self.conf['VTG strategy']['verifier']['options'].append(
                    {'-setprop': 'cpa.automaton.prec.limit.violations=-1'})
        if self.mpv:
            self.add_option_for_entry_point()
        else:
            # Specify default configuration.
            if not self.verifier_present_configuration:
                self.conf['VTG strategy']['verifier']['options'].append({'-ldv': ''})

        self.set_separated_time_limit()

    def set_separated_time_limit(self):
        # Set time limits for Separated strategy.
        time_limit = self.cpu_time_limit_per_rule_per_module_per_entry_point
        # Soft time limit.
        self.conf['VTG strategy']['verifier']['options'].append({'-setprop': 'limits.time.cpu={0}s'.format(
            round(time_limit / 1000))})
        # Hard time limit.
        self.conf['VTG strategy']['resource limits']['CPU time'] = time_limit

    def prepare_verification_task_files_archive(self):
        self.logger.info('Prepare archive with verification task files')

        with tarfile.open('task files.tar.gz', 'w:gz') as tar:
            if self.automaton_file:
                tar.add(self.automaton_file)
            for file in self.task_desc['files']:
                tar.add(file)
            self.task_desc['files'] = [os.path.basename(file) for file in self.task_desc['files']]

    @abstractclassmethod
    def prepare_bug_kind_functions_file(self, bug_kind=None):
        pass

    def process_sequential_verification_task(self, bug_kind=None):
        self.prepare_common_verification_task_desc()
        if bug_kind:
            self.prepare_bug_kind_functions_file(bug_kind)
        else:
            self.prepare_bug_kind_functions_file()
        self.set_specific_options(bug_kind)
        self.prepare_src_files()

        if self.conf['keep intermediate files']:
            self.logger.debug('Create verification task description file "task.json"')
            with open('task.json', 'w', encoding='ascii') as fp:
                json.dump(self.task_desc, fp, sort_keys=True, indent=4)

        self.prepare_verification_task_files_archive()
        self.decide_verification_task(bug_kind)

    def decide_verification_task(self, bug_kind=None):
        self.logger.info('Decide verification task')
        self.verification_status = None

        if not self.automaton_file:
            self.logger.warning('Verification task will not be decided since verifier property file was not prepared')
            return

        session = core.session.Session(self.logger, self.conf['Klever Bridge'], self.conf['identifier'])
        task_id = session.schedule_task(self.task_desc)

        while True:
            task_status = session.get_task_status(task_id)
            self.logger.info('Status of verification task "{0}" is "{1}"'.format(task_id, task_status))

            if task_status == 'ERROR':
                task_error = session.get_task_error(task_id)

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
                break

            if task_status == 'FINISHED':
                self.logger.info('Verification task was successfully decided')

                session.download_decision(task_id)

                with tarfile.open("decision result files.tar.gz") as tar:
                    tar.extractall()

                with open('decision results.json', encoding='ascii') as fp:
                    decision_results = json.load(fp)

                verification_report_id = '{0}/verification{1}'.format(self.id, bug_kind if bug_kind else '')
                self.create_verification_report(verification_report_id, decision_results, bug_kind)

                if self.mea:
                    all_found_error_traces = glob.glob(self.path_to_error_traces)
                    if all_found_error_traces:
                        decision_results['status'] = 'unsafe'
                    if decision_results['status'] == 'unsafe':
                        for error_trace in all_found_error_traces:
                            self.process_single_verdict(decision_results, verification_report_id,
                                                        assertion=bug_kind,
                                                        specified_error_trace=error_trace)
                    else:
                        self.process_single_verdict(decision_results, verification_report_id,
                                                    assertion=bug_kind)
                else:
                    self.process_single_verdict(decision_results, verification_report_id,
                                                assertion=bug_kind)

                self.create_verification_finish_report(verification_report_id, bug_kind)
                break

            time.sleep(1)
