#!/usr/bin/python3

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


# Existed strategies for MPV (revision 20543).
# Source: http://www.sosy-lab.org/~dbeyer/spec-decomposition/
# If not specified, can be overwritten with verifier options.
class MPVStrategy(Enum):
    All = [
        {"-setprop": "analysis.mpa.partition.operator=AllThenNoneOperator"}
    ]
    AllThenSep = [
        {"-setprop": "analysis.mpa.partition.operator=AllThenSepOperator"}
    ]
    AllThenSepRefinementTime = [
        {"-setprop": "analysis.mpa.partition.operator=AllThenSepOperator"},
        {"-setprop": "analysis.mpa.budget.limit.avgRefineTime=800ms"}
    ]
    AllThenSepRefinementCount = [
        {"-setprop": "analysis.mpa.partition.operator=AllThenNotExhaustedThenSepOperator"},
        {"-setprop": "analysis.mpa.budget.limit.refinementsTimesMore=2"},
        {"-setprop": "analysis.mpa.budget.limit.numRefinements=10"}
    ]
    AllThenSepExplosion = [
        {"-setprop": "analysis.mpa.partition.operator=AllThenSepOperator"},
        {"-setprop": "analysis.mpa.budget.limit.automataStateExplosionPercent=20"}
    ]
    Relevance = [
        {"-setprop": "analysis.mpa.partition.operator=RelevanceThenIrrelevantThenRelevantOperator"}
    ]
    Sep = [
        {"-setprop": "analysis.mpa.partition.operator=OneForEachOperator"}
    ]


# This class implements Multi-Property Verification (MPV) strategies.
class MPV(CommonStrategy):

    __metaclass__ = ABCMeta

    delta = 200000
    psi = 4/3
    omega = 2/9
    assert_function = {}  # Map of all checked asserts to corresponding 'error' functions.
    # Relevant for revision 20543.
    verifier_results_regexp = r"\Property (.+).spc: (\w+)"
    resources_written = False
    # Assert -> property automata.
    property_automata = {}

    def perform_sanity_checks(self):
        if not self.mpv:
            raise AttributeError("MPV-strategies require property automata")
        if 'unite rule specifications' not in self.conf \
                or not self.conf['unite rule specifications']:
            raise AttributeError("MPV-strategies require united bug types")

    def perform_preprocess_actions(self):
        self.logger.info('Starting Multi-Property Verification')
        self.print_strategy_information()
        self.create_asserts()
        if self.property_automata.__len__() <= 1:
            raise AttributeError("It is strictly forbidden to use MPV for less than 2 asserts")
        self.prepare_common_verification_task_desc()
        self.create_mea()
        self.add_verifier_options()

    def perform_postprocess_actions(self):
        self.print_mea_stats()

    def main_cycle(self):
        self.resources_written = False
        self.create_property_automata()
        self.prepare_src_files()
        self.prepare_verification_task_files_archive()
        self.decide_verification_task()
        self.logger.info('Multi-Property verification has been completed')

    @abstractclassmethod
    def print_strategy_information(self):
        pass

    @abstractclassmethod
    def create_asserts(self):
        pass

    def prepare_verification_task_files_archive(self):
        self.logger.debug('Prepare archive with verification task files')
        with tarfile.open('task files.tar.gz', 'w:gz') as tar:
            for assertion, automaton in self.property_automata.items():
                path_to_file = assertion + '.spc'
                if os.path.isfile(path_to_file):
                    tar.add(path_to_file)
            for file in self.task_desc['files']:
                tar.add(file)
            self.task_desc['files'] = [os.path.basename(file) for file in self.task_desc['files']]

    def create_property_automata(self):
        for assertion, automaton in self.property_automata.items():
            path_to_file = assertion + '.spc'
            shutil.copy(automaton, path_to_file)

    def add_verifier_options(self):
        self.logger.debug('Add common verifier options for MPV')

        # Set time limits for MPV.
        time_limit = self.cpu_time_limit_per_rule_per_module_per_entry_point * self.property_automata.__len__()
        # Soft time limit.
        self.conf['VTG strategy']['verifier']['options'].append({'-setprop': 'limits.time.cpu={0}s'.format(
            round(time_limit / 1000))})
        # Hard time limit.
        self.conf['VTG strategy']['resource limits']['CPU time'] = time_limit + self.delta

        # Add entry point since we do not use property file.
        self.add_option_for_entry_point()

        # Specify all files with property automata.
        for assertion, automaton in self.property_automata.items():
            path_to_file = assertion + '.spc'
            self.conf['VTG strategy']['verifier']['options'].append(
                {'-spec': path_to_file})

        # Option for MEA.
        if self.mea:
            self.conf['VTG strategy']['verifier']['options'].append(
                {'-setprop': 'analysis.stopAfterError=false'})
            self.conf['VTG strategy']['verifier']['options'].append(
                    {'-setprop': 'cpa.automaton.prec.limit.violations=-1'})

        # Specify preset strategy.
        selected_preset = None
        if 'MPV strategy' in self.conf['VTG strategy']['verifier']:
            specified_preset = self.conf['VTG strategy']['verifier']['MPV strategy']
            for preset in MPVStrategy:
                if preset.name == specified_preset:
                    selected_preset = preset
                    break
            if not selected_preset:
                raise AttributeError('Invalid configuration: Specified MPV strategy "{0}" does not supported'.
                                     format(specified_preset))
            else:
                self.logger.info('Using MPV strategy "{0}"'.format(selected_preset.name))
                if selected_preset.name == 'All':
                    selected_preset.value.append({"-setprop": "analysis.mpa.partition.time.cpu={0}s".
                                                 format(round(time_limit / 1000))})
                elif selected_preset.name == 'Relevance':
                    first_step_time_limit = round(self.cpu_time_limit_per_rule_per_module_per_entry_point *
                                                  self.omega / 1000)
                    second_step_time_limit = round(self.cpu_time_limit_per_rule_per_module_per_entry_point *
                                                   self.psi / 1000)
                    third_step_time_limit = round(self.cpu_time_limit_per_rule_per_module_per_entry_point /
                                                  1000)
                    selected_preset.value.append({"-setprop": "analysis.mpa.partition.time.cpu={0}s".
                                                 format(first_step_time_limit)})
                    selected_preset.value.append({"-setprop": "analysis.mpa.time.cpu.relevance.step2={0}s".
                                                 format(second_step_time_limit)})
                    selected_preset.value.append({"-setprop": "analysis.mpa.time.cpu.relevance.step3={0}s".
                                                 format(third_step_time_limit)})
                else:
                    selected_preset.value.append({"-setprop": "analysis.mpa.partition.time.cpu={0}s".format(round(
                        self.cpu_time_limit_per_rule_per_module_per_entry_point / 1000))})
                self.conf['VTG strategy']['verifier']['options'] = \
                    self.conf['VTG strategy']['verifier']['options'].__add__(selected_preset.value)
        else:
            raise AttributeError('No MPV partitioning strategy was specified')

        if {'-setprop': 'cpa.arg.errorPath.exportImmediately=true'} not in \
                self.conf['VTG strategy']['verifier']['options']:
            self.conf['VTG strategy']['verifier']['options'].append(
                {'-setprop': 'cpa.arg.errorPath.exportImmediately=true'})

    def create_verification_report(self, verification_report_id, decision_results, bug_kind=None):
        # TODO: specify the computer where the verifier was invoked (this information should be get from BenchExec or VerifierCloud web client.
        files_to_send = ['benchmark.xml']
        for assertion, automaton in self.property_automata.items():
            path_to_file = assertion + '.spc'
            files_to_send.append(path_to_file)
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
                                  files_to_send + self.task_desc['files']
                                  if self.conf['upload input files of static verifiers']
                                  else []
                              )
                          },
                          self.mqs['report files'],
                          self.conf['main working directory'],
                          bug_kind)
        self.resources_written = True

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

    def get_violated_property(self, file):
        for line in reversed(list(open(file))):
            result = re.search(r"<data key=\"violatedProperty\">(.*).spc</data>", line)
            if result:
                return result.group(1)
        return None

    def decide_verification_task(self):
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
                session.download_decision(task_id)

                with tarfile.open("decision result files.tar.gz") as tar:
                    tar.extractall()

                with open('decision results.json', encoding='ascii') as fp:
                    decision_results = json.load(fp)

                verification_report_id = '{0}/verification'.format(self.id)
                self.create_verification_report(verification_report_id, decision_results)

                # Parse file with statistics.
                results = {}
                is_stats_found = False
                log_file = self.get_verifier_log_file(False)
                with open(log_file, encoding='ascii') as fp:
                    for line in fp:
                        result = re.search(self.verifier_results_regexp, line)
                        if result:
                            assertion = result.group(1)
                            verdict = result.group(2).lower()
                            if verdict == 'false':
                                verdict = 'unsafe'
                            if verdict == 'true':
                                verdict = 'safe'
                            is_stats_found = True
                            results[assertion] = verdict
                            self.logger.debug('Property "{0}" got verdict "{1}"'.
                                              format(assertion, verdict))

                # Process all found error traces.
                witness_assert = {}  # Witnss (error trace) <-> assert (bug kind).
                all_found_error_traces = glob.glob(self.path_to_error_traces)

                if not is_stats_found:
                    if not all_found_error_traces:
                        # Verifier failed before even starting verification.
                        # Create only one Unknown report for strategy.
                        with open(log_file, encoding='ascii') as fp:
                            content = fp.readlines()
                        task_error = content
                        self.process_global_error(''.join(task_error))
                        break
                    else:
                        # Something was wrong during statistic print.
                        for assertion, automaton in self.property_automata.items():
                            results[assertion] = 'unknown'

                for error_trace in all_found_error_traces:
                    violated_property = self.get_violated_property(error_trace)
                    witness_assert[error_trace] = violated_property

                for assertion, verdict in results.items():
                    decision_results['status'] = verdict
                    if verdict == 'unsafe':
                        for error_trace in all_found_error_traces:
                            if witness_assert[error_trace] == assertion:
                                self.process_single_verdict(decision_results, verification_report_id,
                                                            assertion=assertion,
                                                            specified_error_trace=error_trace)
                    else:  # Verdicts unknown or safe.
                        self.process_single_verdict(decision_results, verification_report_id,
                                                    assertion=assertion)

                self.create_verification_finish_report(verification_report_id)
                break
            time.sleep(1)
