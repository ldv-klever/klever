#!/usr/bin/python3

import psi.components
import psi.utils


class RI(psi.components.Component):
    def do_something_useful(self):
        abstract_task_desc = self.mqs['abstract task description'].get()
        self.mqs['abstract task description'].put(abstract_task_desc)

    main = do_something_useful
