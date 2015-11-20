#!/usr/bin/python3

import psi.components
import psi.utils


class Weaver(psi.components.Component):
    def weave(self):
        self.abstract_task_desc = self.mqs['abstract task description'].get()

        self.func()
        
        self.mqs['abstract task description'].put(self.abstract_task_desc)

    main = weave

    def func(self):
        self.logger.info('')
