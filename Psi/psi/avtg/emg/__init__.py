#!/usr/bin/python3

import psi.components
import psi.utils


class EMG(psi.components.Component):
    def generate_environment(self):
        self.logger.info("Prepare environment model for an abstract verification task {}".format(self.id))
        self.__check_specifications()



    main = generate_environment
