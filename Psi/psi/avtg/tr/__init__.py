#!/usr/bin/python3

import psi.components
import psi.utils


class TR(psi.components.Component):
    def render_templates(self):
        self.abstract_task_desc = self.mqs['abstract task description'].get()
        self.mqs['abstract task description'].put(self.abstract_task_desc)

    main = render_templates
