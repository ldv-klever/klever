import json
import os

import psi.components
import psi.utils


class EMG(psi.components.Component):
    def generate_environment(self):
        self.logger.info("Start environment model generator instance {}".format(self.id))

        spec_dir = psi.utils.find_file_or_dir(self.logger, self.conf["root id"], self.conf["specifications directory"])

        # TODO: Import interface categories configuration

        # TODO: Generate aspect files

        # TODO: Start CIF for each C file with generated aspect and read outut

        # TODO: Can we do it in parallel

        # TODO: Read output and parse CIF out

        # TODO: Generate module interface specification

        return

    main = generate_environment
