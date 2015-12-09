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

        session = psi.session.Session(self.logger, self.conf['Omega'], self.conf['identifier'])
        task_id = session.schedule_task(self.task_desc)

        while True:
            task_status = session.get_task_status(task_id)
            if task_status == 'FINISHED':
                break
            time.sleep(1)

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

        if self.conf['debug']:
            self.logger.debug('Create verification task description file "task.json"')
            with open('task.json', 'w') as fp:
                json.dump(self.task_desc, fp, sort_keys=True, indent=4)
    def prepare_property_file(self):
        self.logger.info('Prepare verifier property file')
        with open('unreach-call.prp', 'w') as fp:
            # TODO: replace usb_serial_bus_register() with entry point name.
            fp.write('CHECK( init(usb_serial_bus_register()), LTL(G ! call(__VERIFIER_error())) )')
        self.task_desc['property file'] = 'unreach-call.prp'
        self.logger.debug('Verifier property file was outputted to "unreach-call.prp"')

    def prepare_verification_task_files_archive(self):
        self.logger.info('Prepare archive with verification task files')

        with tarfile.open('task files.tar.gz', 'w:gz') as tar:
            for extra_c_file in self.conf['abstract task desc']['extra C files']:
                tar.add(os.path.join(self.conf['source tree root'], extra_c_file['C file']),
                        os.path.basename(extra_c_file['C file']))
