#!/usr/bin/python3

import time

import psi.components
import psi.session
import psi.utils


class ABKM(psi.components.Component):
    def generate_verification_tasks(self):
        task_desc = {
            # Safely use id of corresponding abstract verification task since all bug kinds will be merged and each
            # abstract verification task will correspond to exactly one verificatoin task.
            'id': self.conf['abstract task desc']['id'],
            'format': 1,
            # Simply use priority of parent job.
            'priority': self.conf['priority'],
        }
        # Use resource limits and verifier specified in job configuration.
        task_desc.update({name: self.conf['VTG strategy'][name] for name in ('resource limits', 'verifier')})

        session = psi.session.Session(self.logger, self.conf['Omega'], self.conf['identifier'])
        task_id = session.schedule_task(task_desc)
        while True:
            task_status = session.get_task_status(task_id)
            if task_status == 'FINISHED':
                break
            time.sleep(1)


    main = generate_verification_tasks
