#!/usr/bin/python3

import json
import os
import tarfile
import re
import glob

import core.components
import core.session
import core.utils
import time

from core.vtg import common


# This group of strategies is meant to check several rule specifications
# (or bug kinds) at once. Several verification runs may be required.
# Several bugs can be reported for each rule specification (or bug kind).
# TODO: Add presets.
class MAV(common.CommonStrategy):

    path_to_file_with_results = 'output/mav_results_file'
    number_of_asserts = 0
    assert_function = {}  # Map of all checked asserts to corresponding 'error' functions.
    path_to_property_automata = 'property_automata.spc'
    error_function_prefix = '__VERIFIER_error_'
    # Relevant for revision 20410.
    verifier_results_regexp = r"\[assert=\[(.+)\], time=(\d+), verdict=(\w+)\]"

    def generate_verification_tasks(self):
        self.logger.info('Starting Multi-Aspect Verification')

        self.create_asserts()

        self.prepare_common_verification_task_desc()
        self.prepare_bug_kind_functions_file()
        self.create_property_automata()
        self.add_verifier_options()
        self.prepare_src_files()

        if self.conf['keep intermediate files']:
            self.logger.debug('Create verification task description file "task.json"')
            with open('task.json', 'w', encoding='ascii') as fp:
                json.dump(self.task_desc, fp, sort_keys=True, indent=4)

        self.prepare_verification_task_files_archive()
        self.start_mav_cycle()

    main = generate_verification_tasks

    def start_mav_cycle(self):
        self.logger.info('Multi-Aspect Verification with a single iteration')
        self.decide_verification_task()
        self.logger.info('Multi-Aspect Verification has been completed')

    def create_verification_report(self, verification_report_id, decision_results, suffix):
        # TODO: specify the computer where the verifier was invoked (this information should be get from BenchExec or VerifierCloud web client.
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
                              'log': 'cil.i.log',
                              'files': ['cil.i.log'] + (
                                  ['benchmark.xml', self.path_to_property_automata] + self.task_desc['files']
                                  if self.conf['upload input files of static verifiers']
                                  else []
                              )
                          },
                          self.mqs['report files'],
                          self.conf['main working directory'],
                          suffix)

    def create_asserts(self):
        # Bug kind is assert.
        bug_kinds = self.get_all_bug_kinds()
        for bug_kind in bug_kinds:
            self.number_of_asserts +=1
            function = "{0}".format(re.sub(r'\W', '_', bug_kind))
            self.assert_function[bug_kind] = function
        self.logger.debug('Multi-Aspect Verification will check "{0}" asserts'.format(self.number_of_asserts))

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

        # Add entry point since we do not use property file.
        if 'entry points' in self.conf['abstract task desc']:
            if len(self.conf['abstract task desc']['entry points']) > 1:
                raise NotImplementedError('Several entry points are not supported')
            self.conf['VTG strategy']['verifier']['options'].append(
                {'-entryfunction': self.conf['abstract task desc']['entry points'][0]})

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
            {'-setprop': 'cpa.arg.errorPath.exportImmediately=true'})
        self.conf['VTG strategy']['verifier']['options'].append(
            {'-setprop': 'analysis.mav.specificationComparator=VIOLATED_PROPERTY'})
        self.conf['VTG strategy']['verifier']['options'].append(
            {'-setprop': 'cpa.arg.errorPath.file='})

        # Option for MEA.
        if 'mea' in self.conf['VTG strategy']['verifier'] and self.conf['VTG strategy']['verifier']['mea']:
            self.activate_mea()
        if self.is_mea_active():
            self.conf['VTG strategy']['verifier']['options'].append(
                {'-setprop': 'analysis.mav.stopAfterError=false'})

        self.add_specific_options()

    def add_specific_options(self):
        None

    def prepare_verification_task_files_archive(self):
        self.logger.debug('Prepare archive with verification task files')

        with tarfile.open('task files.tar.gz', 'w:gz') as tar:
            if os.path.isfile(self.path_to_property_automata):
                tar.add(self.path_to_property_automata)
            for file in self.task_desc['files']:
                tar.add(os.path.join(self.conf['source tree root'], file), os.path.basename(file))
            self.task_desc['files'] = [os.path.basename(file) for file in self.task_desc['files']]

    def prepare_bug_kind_functions_file(self):
        self.logger.debug('Prepare bug kind functions file "bug kind funcs.c"')

        # Create file with all checked asserts.
        with open('bug kind funcs.c', 'w') as fp:
            fp.write('/* This file was generated for Multi-Aspect Verification*/\n')
            for bug_kind, function in self.assert_function.items():
                fp.write('void {0}{1}(void);\n'.format(self.error_function_prefix, function))
                fp.write('void ldv_assert_{0}(int expr) {{\n\tif (!expr)\n\t\t{1}{0}();\n}}\n'.
                    format(function, self.error_function_prefix))

        # Add bug kind functions file to other abstract verification task files.
        self.conf['abstract task desc']['extra C files'].append(
            {'C file': os.path.relpath('bug kind funcs.c', os.path.realpath(self.conf['source tree root']))})

    def get_violated_property(self, file):
        for line in reversed(list(open(file))):
            result = re.search(r"<data key=\"violatedProperty\">(.*)</data>", line)
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
                self.logger.info('Iteration of Multi-Aspect Verification has been successfully completed')

                session.download_decision(task_id)

                with tarfile.open("decision result files.tar.gz") as tar:
                    tar.extractall()

                with open('decision results.json', encoding='ascii') as fp:
                    decision_results = json.load(fp)

                with open(self.path_to_file_with_results, encoding='ascii') as fp:
                    content = fp.readlines()

                witness_assert = {}  # Witnss (error trace) <-> assert (bug kind).
                all_found_error_traces = glob.glob(self.path_to_witnesses)
                for error_trace in all_found_error_traces:
                    found_bug_kind = self.get_violated_property(error_trace)
                    witness_assert[error_trace] = found_bug_kind

                for line in content:
                    result = re.search(self.verifier_results_regexp, line)
                    if result:
                        bug_kind = result.group(1)
                        verdict = result.group(3).lower()
                        self.logger.info('Processing assert "{0}" with verdict "{1}"'.format(bug_kind, verdict))
                        # Ignore verdicts 'checking'.
                        if verdict != 'unsafe' and verdict != 'safe':
                            verdict = 'unknown'
                        decision_results['status'] = verdict
                        if verdict == 'unsafe':
                            for error_trace in all_found_error_traces:
                                if witness_assert[error_trace] == bug_kind:
                                    self.process_single_verdict(decision_results, suffix=bug_kind,
                                                                specified_witness=error_trace)
                        else:
                            self.process_single_verdict(decision_results, suffix=bug_kind)
                break

            time.sleep(1)
