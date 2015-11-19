#!/usr/bin/python3

import psi.components
import psi.utils


class EMG(psi.components.Component):
    def generate_environment(self):
        self.logger.info("Prepare environment model for an abstract verification task {}".format(self.id))
        abstract_task_desc = self.mqs['abstract task description'].get()
        self.mqs['abstract task description'].put(abstract_task_desc)

    main = generate_environment
