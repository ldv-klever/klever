#!/usr/bin/python3

import psi.components
import psi.utils


class EMG(psi.components.Component):
    def generate_environment(self):
        self.logger.info("Start environment model generator instance {}".format(self.id))
        # TODO: Check existanc of all necessary configuration files

        # TODO: Import interface categories configuration

        # TODO: Generate aspect files

        # TODO: Start CIF for each C file with generated aspect and read outut

        # TODO: Can we do it in parallel

        # TODO: Read output and parse CIF out

        # TODO: Generate module interface specification

        self.__check_specifications()



    main = generate_environment
