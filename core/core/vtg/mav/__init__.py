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
# TODO: add sanity checks (CPAchecker version, specific options, ...).
class MAV(common.CommonStrategy):

    path_to_file_with_results = 'output/mav_results_file'
    number_of_iterations = 0
    number_of_asserts = 0
    assert_function = {}  # Map of all checked asserts to corresponding 'error' functions.
    path_to_property_automata = 'property_automata.spc'
    error_function_prefix = '__VERIFIER_error_'

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
        self.decide_verification_task()

    main = generate_verification_tasks

    def create_asserts(self):
        # Bug kind is assert.
        bug_kinds = self.get_all_bug_kinds()
        for bug_kind in bug_kinds:
            self.number_of_asserts +=1
            function = "{0}".format(re.sub(r'\W', '_', bug_kind))
            self.assert_function[bug_kind] = function
        self.logger.info('MAV will check {0} asserts'.format(self.number_of_asserts))

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
        #TODO: dispose of this
        self.task_desc['property file'] = 'None'

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
        # TODO: sanity checks, more options, new version.

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

    def decide_verification_task(self):
        self.logger.info('Decide verification task')
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
                self.logger.info('Verification task was successfully decided')

                session.download_decision(task_id)

                with tarfile.open("decision result files.tar.gz") as tar:
                    tar.extractall()

                with open('decision results.json', encoding='ascii') as fp:
                    decision_results = json.load(fp)

                # TODO: new CPAchecker version
                with open(self.path_to_file_with_results, encoding='ascii') as fp:
                    content = fp.readlines()
                unsafe_trace = {}
                for line in content:
                    result = re.search(r"\[specification=\[(.+)\], time=(\d+), status=(\w+)\]", line)
                    if result:
                        bug_kind = result.group(1)
                        verdict = result.group(3).lower()
                        self.logger.info('Processing bug kind "{0}" with verdict "{1}"'.format(bug_kind, verdict))
                        if verdict != 'unsafe' and verdict != 'safe':
                            verdict = 'unknown'
                        decision_results['status'] = verdict
                        if verdict == 'unsafe':
                            unsafes = []
                            # TODO: this.
                            error_traces = glob.glob('output/ErrorPath.*.txt')
                            for error_trace in error_traces:
                                with open(error_trace) as fh:
                                    for line in fh:
                                        pass
                                    last = line
                                    error_function = self.assert_function[bug_kind]
                                    result = re.search(error_function, last)
                                    if result:
                                        result = re.search(r"ErrorPath\.(\d+)\.txt", error_trace)
                                        if result:
                                            key = result.group(1)
                                            unsafes.append(key)
                            unsafe_trace[bug_kind] = unsafes
                            for key in unsafe_trace[bug_kind]:
                                # TODO: place name outside
                                error_trace = "output/witness.{0}.graphml".format(key)
                                self.process_single_verdict(decision_results, suffix=bug_kind,
                                                            specified_witness=error_trace)
                        else:
                            self.process_single_verdict(decision_results, suffix=bug_kind)
                break

            time.sleep(1)
