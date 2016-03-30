#!/usr/bin/python3

import json
import os
import re
import tarfile
import time

import core.components
import core.session
import core.utils
from core.vtg import common


# This strategy is aimed at merging all bug kinds inside each rule scpecification
# and at checking each rule specification as a separated verification run
# until finding the first bug.
class ABKM(common.CommonStrategy):
    def generate_verification_tasks(self):
        self.logger.info('Generate one verification task by merging all bug kinds')

        self.prepare_common_verification_task_desc()
        self.prepare_bug_kind_functions_file()
        self.prepare_property_file()
        self.prepare_src_files()

        if self.conf['keep intermediate files']:
            self.logger.debug('Create verification task description file "task.json"')
            with open('task.json', 'w', encoding='ascii') as fp:
                json.dump(self.task_desc, fp, sort_keys=True, indent=4)

        self.prepare_verification_task_files_archive()
        self.decide_verification_task()

    main = generate_verification_tasks

    def prepare_bug_kind_functions_file(self):
        self.logger.info('Prepare bug kind functions file "bug kind funcs.c"')

        # Get all bug kinds.
        bug_kinds = []
        for extra_c_file in self.conf['abstract task desc']['extra C files']:
            if 'bug kinds' in extra_c_file:
                bug_kinds.extend(extra_c_file['bug kinds'])

        # Create bug kind function definitions that all call __VERIFIER_error() since this strategy doesn't distinguish
        # different bug kinds.
        with open('bug kind funcs.c', 'w') as fp:
            fp.write('/* http://sv-comp.sosy-lab.org/2015/rules.php */\nvoid __VERIFIER_error(void);\n')
            for bug_kind in bug_kinds:
                fp.write('void ldv_assert_{0}(int expr) {{\n\tif (!expr)\n\t\t__VERIFIER_error();\n}}\n'.format(
                    re.sub(r'\W', '_', bug_kind)))

        # Add bug kind functions file to other abstract verification task files.
        self.conf['abstract task desc']['extra C files'].append(
            {'C file': os.path.relpath('bug kind funcs.c', os.path.realpath(self.conf['source tree root']))})

    def prepare_property_file(self):
        self.logger.info('Prepare verifier property file')

        if 'entry points' in self.conf['abstract task desc']:
            if len(self.conf['abstract task desc']['entry points']) > 1:
                raise NotImplementedError('Several entry points are not supported')

            with open('unreach-call.prp', 'w', encoding='ascii') as fp:
                fp.write('CHECK( init({0}()), LTL(G ! call(__VERIFIER_error())) )'.format(
                    self.conf['abstract task desc']['entry points'][0]))

            self.task_desc['property file'] = 'unreach-call.prp'

            self.logger.debug('Verifier property file was outputted to "unreach-call.prp"')
        else:
            self.logger.warning('Verifier property file was not prepared since entry points were not specified')

    def prepare_verification_task_files_archive(self):
        self.logger.info('Prepare archive with verification task files')

        with tarfile.open('task files.tar.gz', 'w:gz') as tar:
            if os.path.isfile('unreach-call.prp'):
                tar.add('unreach-call.prp')
            for file in self.task_desc['files']:
                tar.add(os.path.join(self.conf['source tree root'], file), os.path.basename(file))
            self.task_desc['files'] = [os.path.basename(file) for file in self.task_desc['files']]

    def decide_verification_task(self):
        self.logger.info('Decide verification task')
        self.verification_status = None

        if not os.path.isfile('unreach-call.prp'):
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

                self.process_single_verdict(decision_results)
                break

            time.sleep(1)
