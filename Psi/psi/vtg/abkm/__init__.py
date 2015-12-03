#!/usr/bin/python3

import psi.components
import psi.utils


class ABKM(psi.components.Component):
    def generate_verification_tasks(self):
        pass

    main = generate_verification_tasks
