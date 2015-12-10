#!/usr/bin/python3

import json
import os
import tarfile
import time

import psi.components
import psi.session
import psi.utils


class ABKM(psi.components.Component):
    def generate_verification_tasks(self):
        self.logger.info('Generate one verification task by merging all bug kinds')

        self.prepare_common_verification_task_desc()
        self.prepare_property_file()
        self.prepare_source_files()

        if self.conf['debug']:
            self.logger.debug('Create verification task description file "task.json"')
            with open('task.json', 'w') as fp:
                json.dump(self.task_desc, fp, sort_keys=True, indent=4)

        self.prepare_verification_task_files_archive()

        self.decide_verification_task()

    main = generate_verification_tasks

    def prepare_common_verification_task_desc(self):
        self.logger.info('Prepare common verification task description')

        self.task_desc = {
            # Safely use id of corresponding abstract verification task since all bug kinds will be merged and each
            # abstract verification task will correspond to exactly one verificatoin task.
            'id': self.conf['abstract task desc']['id'],
            'format': 1,
            # Simply use priority of parent job.
            'priority': self.conf['priority'],
        }

        # Use resource limits and verifier specified in job configuration.
        self.task_desc.update({name: self.conf['VTG strategy'][name] for name in ('resource limits', 'verifier')})

    def prepare_property_file(self):
        self.logger.info('Prepare verifier property file')
        with open('unreach-call.prp', 'w') as fp:
            # TODO: replace usb_serial_bus_register() with entry point name.
            fp.write('CHECK( init(usb_serial_bus_register()), LTL(G ! call(__VERIFIER_error())) )')
        self.task_desc['property file'] = 'unreach-call.prp'
        self.logger.debug('Verifier property file was outputted to "unreach-call.prp"')

    def prepare_source_files(self):
        self.task_desc['files'] = []

        if self.conf['VTG strategy']['merge source files']:
            self.logger.info('Merge source files by means of CIL')

            with open('cil input files.txt', 'w') as fp:
                for extra_c_file in self.conf['abstract task desc']['extra C files']:
                    fp.write('{0}\n'.format(extra_c_file['C file']))

            cil_out_file = os.path.relpath('cil.i', os.path.realpath(self.conf['source tree root']))

            psi.utils.execute(self.logger,
                              (
                                  'cilly.asm.exe',
                                  '--extrafiles', os.path.relpath('cil input files.txt',
                                                                  os.path.realpath(self.conf['source tree root'])),
                                  '--out', cil_out_file,
                                  '--printCilAsIs',
                                  '--domakeCFG',
                                  '--decil',
                                  '--noInsertImplicitCasts',
                                  # Now supported by CPAchecker frontend.
                                  '--useLogicalOperators',
                                  '--ignore-merge-conflicts',
                                  # Don't transform simple function calls to calls-by-pointers.
                                  '--no-convert-direct-calls',
                                  # Don't transform s->f to pointer arithmetic.
                                  '--no-convert-field-offsets',
                                  # Don't transform structure fields into variables or arrays.
                                  '--no-split-structs',
                                  '--rmUnusedInlines'
                              ),
                              cwd=self.conf['source tree root'])

            self.task_desc['files'].append(cil_out_file)

            self.logger.debug('Merged source files was outputted to "cil.i"')
        else:
            for extra_c_file in self.conf['abstract task desc']['extra C files']:
                self.task_desc['files'].append(extra_c_file['C file'])

    def prepare_verification_task_files_archive(self):
        self.logger.info('Prepare archive with verification task files')

        with tarfile.open('task files.tar.gz', 'w:gz') as tar:
            tar.add('unreach-call.prp')
            for file in self.task_desc['files']:
                tar.add(os.path.join(self.conf['source tree root'], file), os.path.basename(file))
            self.task_desc['files'] = [os.path.basename(file) for file in self.task_desc['files']]

    def decide_verification_task(self):
        self.logger.info('Decide verification task')

        session = psi.session.Session(self.logger, self.conf['Omega'], self.conf['identifier'])
        task_id = session.schedule_task(self.task_desc)

        while True:
            task_status = session.get_task_status(task_id)

            if task_status == 'ERROR':
                task_error = session.get_task_error(task_id)
                self.logger.warning('Failed to decide verification task: {0}'.format(task_error))
                psi.utils.report(self.logger,
                                 'unknown',
                                 {
                                     'id': 'unknown',
                                     'parent id': self.id,
                                     'problem desc': task_error
                                 },
                                 self.mqs['report files'],
                                 self.conf['main working directory'])
                break

            if task_status == 'FINISHED':
                self.logger.info('Verification task was successfully decided')

                session.download_decision(task_id)

                tar = tarfile.open("decision result files.tar.gz")
                tar.extractall()
                tar.close()

                with open('decision results.json') as fp:
                    decision_results = json.load(fp)

                # TODO: specify the computer where the verifier was invoked (this information should be get from BenchExec.
                psi.utils.report(self.logger,
                                 'verification',
                                 {
                                     # TODO: replace with something meaningful, e.g. tool name + tool version + tool configuration.
                                     'id': '1',
                                     'parent id': self.id,
                                     # TODO: replace with something meaningful, e.g. tool name + tool version + tool configuration.
                                     'attrs': [],
                                     'name': self.conf['VTG strategy']['verifier']['name'],
                                     'resources': decision_results['resources'],
                                     'desc': decision_results['desc'],
                                     'log': '__file:cil.i.log',
                                     'data': ''
                                 },
                                 self.mqs['report files'],
                                 self.conf['main working directory'])

                self.logger.info('Verification task decision status is "{0}"'.format(decision_results['status']))

                if decision_results['status'] == 'safe':
                    psi.utils.report(self.logger,
                                     'safe',
                                     {
                                         'id': 'safe',
                                         'parent id': '1',
                                         'attrs': [],
                                         # TODO: just the same file as parent log, looks strange.
                                         'proof': '__file:cil.i.log'
                                     },
                                     self.mqs['report files'],
                                     self.conf['main working directory'])
                elif decision_results['status'] == 'unsafe':
                    psi.utils.report(self.logger,
                                     'unsafe',
                                     {
                                         'id': 'unsafe',
                                         'parent id': '1',
                                         'attrs': [],
                                         'error trace': 'witness.graphml',
                                         'files': ['witness.graphml']
                                     },
                                     self.mqs['report files'],
                                     self.conf['main working directory'])
                elif decision_results['status'] in ('error', 'CPU time exhausted', 'memory exhausted'):
                    psi.utils.report(self.logger,
                                     'unknown',
                                     {
                                         'id': 'unknown',
                                         'parent id': '1',
                                         # TODO: just the same file as parent log, looks strange.
                                         'problem desc':
                                             '__file:cil.i.log' if decision_results['status'] == 'error'
                                             else decision_results['status']
                                     },
                                     self.mqs['report files'],
                                     self.conf['main working directory'])
                else:
                    raise NotImplementedError(
                        'Status "{0}" of verification task decision results is not supported'.format(
                            decision_results['status']))

                break

            time.sleep(1)
