#!/usr/bin/python3

import psi.components
import psi.utils


class RSG(psi.components.Component):
    def generate_rule_specification(self):
        abstract_task_desc = self.mqs['abstract task description'].get()
        self.mqs['abstract task description'].put(abstract_task_desc)

    main = generate_rule_specification
