#!/usr/bin/python3

import psi.components
import psi.utils


class ASG(psi.components.Component):
    def generate_argument_signatures(self):
        self.abstract_task_desc = self.mqs['abstract task description'].get()
        self.mqs['abstract task description'].put(self.abstract_task_desc)

    main = generate_argument_signatures
