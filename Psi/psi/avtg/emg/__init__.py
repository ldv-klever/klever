import json
import os

import psi.components
import psi.utils

from psi.avtg.emg.interfaces import CategorySpecification, Analysis


class EMG(psi.components.Component):
    def generate_environment(self):
        self.logger.info("Start environment model generator instance {}".format(self.id))

        self.logger.debug("Receive abstract verification task")
        avt = self.mqs['abstract task description'].get()
        self.logger.info("Prepare environment model for an abstract verification task {}".format(avt["id"]))

        spec_dir = psi.utils.find_file_or_dir(self.logger, self.conf["main working directory"],
                                              self.conf["specifications directory"])
        intf_spec_dict, event_spec_dict = self.__get_specs(self.logger, spec_dir)

        # Import interface categories configuration
        intf_spec = CategorySpecification(self.logger)
        intf_spec.import_specification(intf_spec_dict)

        # TODO: Generate aspect files
        sa = Analysis(self.logger, self.conf, self.work_dir, avt, intf_spec)

        # TODO: Start CIF for each C file with generated aspect and read outut

        # TODO: Can we do it in parallel

        # TODO: Read output and parse CIF out

        # TODO: Generate module interface specification
        self.mqs['abstract task description'].put(avt)

        return

    @staticmethod
    def __get_specs(logger, directory):
        """
        Fins in the given directory two JSON specifications: interface categories specification and event categories
        specifications.
        :param logger: Logger object.
        :param directory: Provided directory with files.
        :return: Dictionaries with interface categories specification and event categories specifications.
        """
        files = [os.path.join(directory, name) for name in os.listdir(directory)]
        if len(files) != 2:
            FileNotFoundError("EMG expects exactly 2 specifications but found {}".format(len(files)))

        intf_spec = None,
        event_spec = None
        for file in files:
            logger.info("Import specification {}".format(file))
            with open(file, "r") as fh:
                spec = json.loads(fh.read())

            logger.info("Going to determine type of the specification {}".format(file))

            if "categories" in spec:
                logger.info("File {} is treated as interface categories specification".format(file))
                intf_spec = spec
            elif "environment processes" in spec:
                logger.info("File {} is treated as event categories specification".format(file))
                event_spec = spec
            else:
                raise FileNotFoundError("File {} does not match interface categories specification nor it matches event"
                                        " categories specification, please check its content")

        if not intf_spec:
            raise FileNotFoundError("EMG requires interface categories specification but it is missed")
        elif not event_spec:
            raise FileNotFoundError("EMG requires event categories specification but it is missed")
        else:
            return intf_spec, event_spec

    main = generate_environment


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
