#!/usr/bin/python3

import json
import os
import tarfile
import time
import glob
import re
import shutil
from enum import Enum
from math import sqrt

import core.components
import core.session
import core.utils
from core.vtg.common import CommonStrategy


# Existed presets for MAV, which are specify the level of accuracy:
# more higher level will provide more accurate results,
# but also will require more resources.
# Can be overwritten with verifier options.
# The following notion will be used:
# TL = cpu_time_limit_per_rule_per_module_per_entry_point
# ATL = alpha*TL (Assert Time Limit - limit per one rule/assert)
# IITL = betta*TL (for conditional MAV)
# BITL = gamma*TL (heuristic time limit)
# FITL = epsilon*TL (heuristic time limit)
# L5 is considered only for experiments (it is not MAV).
# L5 is supported only be internal launch of CMAV.
# The default preset is L1.
class MAVPreset(Enum):
    L1 = {'alpha': 1.0, 'betta': 1/45, 'gamma': 1/9, 'epsilon': 1/9}
    L2 = {'alpha': 1.0, 'betta': 1/45, 'gamma': 1/9, 'epsilon': 4/3}
    L3 = {'alpha': 1.0, 'betta': 1/45, 'gamma': 1/4, 'epsilon': 4/3}
    L4 = {'alpha': 1.0, 'betta': 1/45, 'gamma': 1.0, 'epsilon': 4/3}
    L5 = {'alpha': 0.0, 'betta': 0.0,  'gamma': 0.0, 'epsilon': 0.0}


# Different strategies for cleaning precision in CMAV.
# NONE - do not clear precision,
# WL - clear precision in waitlist,
# ARG - clear precision in ARG,
# SUB - clear precision only for current checked rule,
# ALL - clear precision for all rules.
# For relatively low number of checked rules (~15) it is recommended to use strategy 'WL_SUB',
# for larger number of checked rules it is recommended to use strategy 'ALL'.
class MAVPrecisionCleaningStrategy(Enum):
    NONE = {
        'analysis.mav.precisionCleanStrategy': 'NONE',
        'analysis.mav.precisionCleanSet': 'NONE'
    }
    WL_SUB = {
        'analysis.mav.precisionCleanStrategy': 'BY_SPECIFICATION',
        'analysis.mav.precisionCleanSet': 'WAITLIST'
    }
    WL_CLEAR = {
        'analysis.mav.precisionCleanStrategy': 'FULL',
        'analysis.mav.precisionCleanSet': 'WAITLIST'
    }
    ARG_SUB = {
        'analysis.mav.precisionCleanStrategy': 'BY_SPECIFICATION',
        'analysis.mav.precisionCleanSet': 'ALL'
    }
    ALL = {
        'analysis.mav.precisionCleanStrategy': 'FULL',
        'analysis.mav.precisionCleanSet': 'ALL'
    }


# This class represent Multi-Aspect Verification (MAV) strategies.
# More information about MAV can be found:
# http://link.springer.com/chapter/10.1007/978-3-319-41579-6_17 and
# http://link.springer.com/article/10.1134/S0361768816040058.
# This strategy requires CPAchecker verifier, branch cmav, revision >= 20410.
class MAV(CommonStrategy):

    # Private strategy variables.
    path_to_file_with_results = ''
    number_of_asserts = 0
    assert_function = {}  # Map of all checked asserts to corresponding 'error' functions.
    path_to_property_automata = 'property_automata.spc'
    error_function_prefix = '__VERIFIER_error_'
    verifier_results_regexp = r"\[assert=\[(.+)\], time=(\d+), verdict=(\w+)\]"
    assert_to_bug_kinds = {}  # Map of all asserts to considered bug kinds.
    prec_value = "value.precision"
    prec_predicate = "predicate.precision"

    # Public strategy parameters.
    # Option ['VTG strategy']['verifier']['relaunch'] - determines relaunches of conditional MAV.
    # Possible values: internal (inside one verifier run), external (several verifier runs),
    # no (only for Sequential Combination).
    relaunch = "internal"
    # Option ['VTG strategy']['verifier']['MAV cleaning strategy'] - determines cleaning strategy.
    # Option ['VTG strategy']['verifier']['MAV preset'] - determines internal limitations.

    def perform_sanity_checks(self):
        if self.mpv:
            # MPV strategies should be used for property automata.
            raise AttributeError("MAV-strategies do not support property automata")
        if 'unite rule specifications' not in self.conf \
            or not self.conf['unite rule specifications']:
            raise AttributeError("Current VTG strategy supports only united rules")

    def perform_preprocess_actions(self):
        self.print_strategy_information()
        self.create_asserts()
        #if self.number_of_asserts <= 1:
        #    raise AttributeError("It is strictly forbidden to use MAV for less than 2 asserts")
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
            self.create_property_automata()
            self.logger.info('Start iteration {0}'.format(iterations))
            self.prepare_src_files()
            self.prepare_verification_task_files_archive()
            # Clear output directory since it is the same for all runs.
            if os.path.exists('output'):
                shutil.rmtree('output')
            if self.decide_verification_task(iterations):
                break
        self.logger.info('Conditional Multi-Aspect Verification has been completed in {0} iteration(s)'.
                         format(iterations))

    def print_strategy_information(self):
        self.logger.info('Launch Multi-Aspect Verification')
        self.logger.info('Generate one verification task and check all asserts at once')

    def get_all_bug_kinds(self):
        bug_kinds = []
        for extra_c_file in self.conf['abstract task desc']['extra C files']:
            if 'bug kinds' in extra_c_file:
                bug_kinds_for_rule_specification = extra_c_file['bug kinds']
                common_bug_kind = bug_kinds_for_rule_specification[0]
                rule = self.parse_bug_kind(common_bug_kind)
                if rule:
                    common_bug_kind = rule
                self.assert_to_bug_kinds[common_bug_kind] = bug_kinds_for_rule_specification
                bug_kinds.append(common_bug_kind)
        return bug_kinds

    def create_asserts(self):
        self.logger.info('Merge all asserts for each rule specification')
        # Bug kind is rule specification.
        bug_kinds = self.get_all_bug_kinds()
        for bug_kind in bug_kinds:
            self.number_of_asserts += 1
            function = "{0}".format(re.sub(r'\W', '_', bug_kind))
            self.assert_function[bug_kind] = function
        self.logger.debug('Multi-Aspect Verification will check "{0}" asserts'.format(self.number_of_asserts))

    def prepare_verification_task_files_archive(self):
        self.logger.debug('Prepare archive with verification task files')

        with tarfile.open('task files.tar.gz', 'w:gz') as tar:
            if os.path.isfile(self.path_to_property_automata):
                tar.add(self.path_to_property_automata)
            for file in self.task_desc['files']:
                tar.add(file)
            self.task_desc['files'] = [os.path.basename(file) for file in self.task_desc['files']]

    def create_property_automata(self):
        with open(self.path_to_property_automata, 'w') as fp:
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
        if not self.verifier_present_configuration:
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
            {'-setprop': 'analysis.mav.specificationComparator=VIOLATED_PROPERTY'})
        self.conf['VTG strategy']['verifier']['options'].append(
            {'-setprop': 'cpa.arg.errorPath.file='})
        if {'-setprop': 'cpa.arg.errorPath.exportImmediately=true'} not in \
                self.conf['VTG strategy']['verifier']['options']:
            self.conf['VTG strategy']['verifier']['options'].append(
                {'-setprop': 'cpa.arg.errorPath.exportImmediately=true'})

        # Option for MEA.
        if self.mea:
            self.conf['VTG strategy']['verifier']['options'].append(
                {'-setprop': 'analysis.mav.stopAfterError=false'})

        # Option for Conditional Multi-Aspect Verification (CMAV).
        if 'relaunch' in self.conf['VTG strategy']['verifier']:
            self.relaunch = self.conf['VTG strategy']['verifier']['relaunch']
        if self.relaunch == 'internal':
            self.logger.info('Launch Conditional Multi-Aspect Verification in one verifier run')
            self.conf['VTG strategy']['verifier']['options'].append(
                {'-setprop': 'analysis.mav.relaunchInOneRun=true'})
            # Set time limits for internal MAV.
            time_limit = self.cpu_time_limit_per_rule_per_module_per_entry_point * self.number_of_asserts
        elif self.relaunch == 'external':
            self.logger.info('Launch Conditional Multi-Aspect Verification in several verifier run')
            # Set time limits for external MAV.
            time_limit = round(self.cpu_time_limit_per_rule_per_module_per_entry_point * sqrt(self.number_of_asserts))
        else:
            self.logger.info('Launch only the first iteration of Multi-Aspect Verification')
            # This is not full MAV and only can be used as a part of Sequential Combination.
            self.relaunch = 'no'
            time_limit = self.cpu_time_limit_per_rule_per_module_per_entry_point

        # Soft time limit.
        self.conf['VTG strategy']['verifier']['options'].append({'-setprop': 'limits.time.cpu={0}s'.format(
            round(time_limit / 1000))})
        # Hard time limit.
        self.conf['VTG strategy']['resource limits']['CPU time'] = time_limit

        self.parse_preset()
        self.parse_cleaning_strategy()

        # Three modes for precision reuse are supported:
        # - save: write current precision to the files;
        # - load: read initial precision from the files;
        # - update: read initial precision, then write new precision.
        if 'precision reuse' in self.conf['VTG strategy']['verifier']:
            mode = self.conf['VTG strategy']['verifier']['precision reuse']['mode']
            if 'precision directory' in self.conf['VTG strategy']['verifier']['precision reuse']:
                # Load precision from corresponding files.
                # 2 precision types are supported: value and predicate.
                # TODO: make more general implementation.
                precision_directory = self.conf['VTG strategy']['verifier']['precision reuse']['precision directory']
                module = re.sub('/', '-', self.verification_object)
                path_val = precision_directory + "/" + module + "." + self.prec_value
                path_pred = precision_directory + "/" + module + "." + self.prec_predicate
                # If precision file does not exist (e.g., Unknown verdict), ignore it.
                if not os.path.isfile(path_val):
                    path_val = None
                if not os.path.isfile(path_pred):
                    path_pred = None
            else:
                path_val = None
                path_pred = None
            if mode == "save" or mode == "update":
                if not path_val:
                    path_val = self.prec_value
                if not path_pred:
                    path_pred = self.prec_predicate
                self.conf['VTG strategy']['verifier']['options'].append(
                    {'-setprop': 'cpa.value.precisionFile={0}'.format(path_val)})
                self.conf['VTG strategy']['verifier']['options'].append(
                    {'-setprop': 'cpa.predicate.predmap.file={0}'.format(path_pred)})
            if mode == "load" or mode == "update":
                if path_val:
                    self.conf['VTG strategy']['verifier']['options'].append(
                        {'-setprop': 'cpa.value.initialPrecisionFile={0}'.format(path_val)})
                if path_pred:
                    self.conf['VTG strategy']['verifier']['options'].append(
                        {'-setprop': 'cpa.predicate.abstraction.initialPredicates={0}'.format(path_pred)})

    def parse_cleaning_strategy(self):
        # By default no cleaning strategy is specified. In this case it is expected, that the user
        # will specify required parameters with verifier options.
        selected_strategy = None
        if 'MAV cleaning strategy' in self.conf['VTG strategy']['verifier']:
            specified_strategy = self.conf['VTG strategy']['verifier']['MAV cleaning strategy']
            for strategy in MAVPrecisionCleaningStrategy:
                if strategy.name == specified_strategy:
                    selected_strategy = strategy
            if not selected_strategy:
                self.logger.warning('Precision will not be cleaned, since cleaning strategy "{0}" is not supported'.
                                    format(selected_strategy))
            else:
                self.logger.info('Use precision cleaning strategy "{0}"'.format(selected_strategy.name))
                for key, value in selected_strategy.value.items():
                    self.conf['VTG strategy']['verifier']['options'].append(
                        {'-setprop': '{0}={1}'.format(key, value)})
        else:
            self.logger.warning('Precision will not be cleaned')

    def parse_preset(self):
        # By default no preset is specified. In this case it is expected, that the user
        # will specify required limitation with verifier options.
        selected_preset = None
        if 'MAV preset' in self.conf['VTG strategy']['verifier']:
            specified_preset = self.conf['VTG strategy']['verifier']['MAV preset']
            for preset in MAVPreset:
                if preset.name == specified_preset:
                    selected_preset = preset
            if not selected_preset:
                # TODO: This option is considered only for debug mode and should not get in production!
                # Otherwise the user can easily break MAV with just one parameter.
                self.logger.warning('Specified MAV preset "{0}" is not supported, no limitations will be used'.
                                    format(specified_preset))
            else:
                # Existed preset was specified.
                if self.relaunch == 'external' and selected_preset.name == 'L5':
                    raise AttributeError(
                        "Preset L5 can be used only with internal relaunch of CMAV")
                TL = self.cpu_time_limit_per_rule_per_module_per_entry_point / 1000
                ATL = round(selected_preset.value['alpha'] * TL)
                IITL = round(selected_preset.value['betta'] * TL)
                BITL = round(selected_preset.value['gamma'] * TL)
                FITL = round(selected_preset.value['epsilon'] * TL)
                self.logger.info('Use MAV preset "{0}" for limitations'.format(selected_preset.name))
                self.conf['VTG strategy']['verifier']['options'].append(
                    {'-setprop': 'analysis.mav.assertTimeLimit={0}'.format(ATL)})
                self.conf['VTG strategy']['verifier']['options'].append(
                    {'-setprop': 'analysis.mav.idleIntervalTimeLimit={0}'.format(IITL)})
                self.conf['VTG strategy']['verifier']['options'].append(
                    {'-setprop': 'analysis.mav.basicIntervalTimeLimit={0}'.format(BITL)})
                self.conf['VTG strategy']['verifier']['options'].append(
                    {'-setprop': 'analysis.mav.firstIntervalTimeLimit={0}'.format(FITL)})
        else:
            # TODO: This option is considered only for debug mode and should not get in production!
            # Otherwise the user can easily break MAV with just one parameter.
            self.logger.debug('No MAV preset was specified, no limitations will be used')

    def prepare_bug_kind_functions_file(self):
        self.logger.debug('Prepare bug kind functions file "bug kind funcs.c"')

        # Create file with all checked asserts.
        with open('bug kind funcs.c', 'w') as fp:
            fp.write('/* This file was generated for Multi-Aspect Verification*/\n')
            for rule_specification, bug_kinds in self.assert_to_bug_kinds.items():
                error_function_for_rule_specification = "{0}".format(re.sub(r'\W', '_', rule_specification))
                fp.write('void {0}{1}(void);\n'.format(self.error_function_prefix,
                                                       error_function_for_rule_specification))
                for bug_kind in bug_kinds:
                    error_function_for_bug_kind = "{0}".format(re.sub(r'\W', '_', bug_kind))
                    fp.write('void ldv_assert_{0}(int expr) {{\n\tif (!expr)\n\t\t{1}{2}();\n}}\n'.
                        format(error_function_for_bug_kind, self.error_function_prefix,
                               error_function_for_rule_specification))

        # Add bug kind functions file to other abstract verification task files.
        self.conf['abstract task desc']['extra C files'].append(
            {'C file': os.path.abspath('bug kind funcs.c')})

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
            self.logger.debug("Stop checking for assert {0}".format(assertion))
            self.assert_function.__delitem__(assertion)

    def get_violated_property(self, file):
        for line in reversed(list(open(file))):
            result = re.search(r"<data key=\"violatedProperty\">(.*)</data>", line)
            if result:
                return result.group(1)
        return None

    def decide_verification_task(self, iteration):
        is_finished = True
        results = {}
        self.verification_status = None

        session = core.session.Session(self.logger, self.conf['Klever Bridge'], self.conf['identifier'])
        task_id = session.schedule_task(self.task_desc)

        while True:
            task_status = session.get_task_status(task_id)
            self.logger.debug('Status of verification task "{0}" is "{1}"'.format(task_id, task_status))

            if task_status == 'ERROR':
                task_error = session.get_task_error(task_id)
                self.process_global_error(task_error)
                break

            if task_status == 'FINISHED':
                self.logger.info('Iteration of Multi-Aspect Verification has been successfully completed')

                session.download_decision(task_id)

                with tarfile.open("decision result files.tar.gz") as tar:
                    tar.extractall()

                with open('decision results.json', encoding='ascii') as fp:
                    decision_results = json.load(fp)

                verification_report_id = '{0}/verification{1}'.format(self.id, iteration)
                self.create_verification_report(verification_report_id, decision_results, iteration)

                is_global_error = True
                log_file = self.get_verifier_log_file(False)
                if os.path.isfile(self.path_to_file_with_results):
                    # Specific result file (for backward compatibility).
                    with open(self.path_to_file_with_results, encoding='ascii') as fp:
                        for line in fp:
                            result = re.search(self.verifier_results_regexp, line)
                            if result:
                                bug_kind = result.group(1)
                                verdict = result.group(3).lower()
                                if verdict == 'safe' or verdict == 'unsafe' or verdict == 'unknown':
                                    is_global_error = False
                                results[bug_kind] = verdict
                                self.logger.debug('Assertion "{0}" got verdict "{1}"'.
                                                  format(bug_kind, verdict))
                            else:
                                result = re.search(r'\[(.+)\]', line)
                                if result and self.relaunch == 'external':
                                    # LCA here.
                                    LCA = result.group(1)
                                    self.logger.debug('LCA is "{0}"'.format(LCA))
                                    if is_global_error:
                                        is_global_error = False
                                        results[LCA] = 'unknown'
                else:
                    # Take all information from log.
                    with open(log_file, encoding='ascii') as fp:
                        for line in fp:
                            result = re.search(r"Property (.+): (\w+)$", line)
                            if result:
                                is_global_error = False
                                assertion = result.group(1)
                                verdict = result.group(2).lower()
                                if verdict == 'false':
                                    verdict = 'unsafe'
                                if verdict == 'true':
                                    verdict = 'safe'
                                results[assertion] = verdict

                if self.relaunch == 'no':
                    is_global_error = False
                    with open(log_file) as f_res:
                        for line in f_res:
                            result = re.search(r'Assert \[(\S+)\] has exhausted its Assert Time Limit', line)
                            if result:
                                rule = result.group(1)
                                results[rule] = 'unknown-complete'

                # Process all found error traces.
                witness_assert = {}  # Witnss (error trace) <-> assert (bug kind).
                all_found_error_traces = glob.glob(self.path_to_error_traces)
                for error_trace in all_found_error_traces:
                    found_bug_kind = self.get_violated_property(error_trace)
                    witness_assert[error_trace] = found_bug_kind
                    results[found_bug_kind] = 'unsafe'  # just in case
                    is_global_error = False

                if is_global_error:
                    # Verifier failed before even starting verification.
                    # Create only one Unknown report for strategy.
                    with open(log_file, encoding='ascii') as fp:
                        content = fp.readlines()
                    task_error = content
                    self.process_global_error(''.join(task_error))
                    break

                for bug_kind, verdict in results.items():
                    if verdict == 'checking':
                        if self.relaunch == 'external':
                            is_finished = False
                        else:
                            verdict = 'unknown'
                    decision_results['status'] = verdict
                    if verdict == 'unsafe':
                        # Process unsafe-incomplete.
                        if self.mea:
                            is_incomplete = False
                            is_stopped = False
                            with open(log_file) as fp:
                                for line in fp:
                                    match = re.search(r'Assert \[(.+)\] has exhausted its', line)
                                    if match:
                                        exhausted_assert = match.group(1)
                                        if exhausted_assert in bug_kind:
                                            is_incomplete = True
                                    match = re.search(r'Shutdown requested', line)
                                    if match:
                                        is_incomplete = True
                                    match = re.search(r'Stopping analysis \.\.\.', line)
                                    if match:
                                        is_stopped = True
                            if not is_stopped:
                                is_incomplete = True
                            if is_incomplete:
                                self.process_unsafe_incomplete(verification_report_id, bug_kind)
                        for error_trace in all_found_error_traces:
                            if witness_assert[error_trace] == bug_kind:
                                self.process_single_verdict(decision_results, verification_report_id,
                                                            assertion=bug_kind,
                                                            specified_error_trace=error_trace)
                                self.remove_assertion(bug_kind)

                    else:  # Verdicts unknown or safe.
                        if self.relaunch == 'no':
                            if verdict == 'unknown-complete' or verdict == 'safe':
                                self.process_single_verdict(decision_results, verification_report_id,
                                                            assertion=bug_kind)
                            else:
                                # Do not create reports for 'incomplete' Unknown.
                                pass
                        else:
                            self.process_single_verdict(decision_results, verification_report_id,
                                                        assertion=bug_kind)
                        if verdict != 'checking':
                            self.remove_assertion(bug_kind)

                self.create_verification_finish_report(verification_report_id, iteration)
                break
            time.sleep(self.poll_interval)
        return is_finished
