import json
import os

import core.components
import core.utils

from core.avtg.emg.interfaces import CategorySpecification, ModuleSpecification
from core.avtg.emg.events import EventModel
from core.avtg.emg.translator import stub


class EMG(core.components.Component):
    def generate_environment(self):
        self.logger.info("Start environment model generator instance {}".format(self.id))
        self.module_interface_spec = None
        self.model = None
        self.interface_spec = None
        self.event_spec = None
        self.translator = None

        self.logger.debug("Receive abstract verification task")
        avt = self.mqs['abstract task description'].get()
        self.logger.info("Prepare environment model for an abstract verification task {}".format(avt["id"]))

        spec_dir = core.utils.find_file_or_dir(self.logger, self.conf["main working directory"],
                                               self.conf["specifications directory"])
        self.__get_specs(self.logger, spec_dir)

        # Import interface categories configuration
        intf_spec = CategorySpecification(self.logger)
        intf_spec.import_specification(self.interface_spec)

        # Import results of source code analysis
        module_spec = ModuleSpecification(self.logger)
        analysis = {}
        if "source analysis" in avt:
            analysis_file = os.path.join(self.conf["main working directory"], avt["source analysis"])
            with open(analysis_file, "r") as fh:
                analysis = json.loads(fh.read())
        else:
            self.logger.warning("Results of source analysis are not available for EMG")
        module_spec.import_specification(self.module_interface_spec, intf_spec, analysis)
        self.module_interface_spec = module_spec

        # Import event categories specification
        self.logger.info("Prepare intermediate model")
        # TODO: Import existing environment model
        self.model = EventModel(self.logger, self.module_interface_spec, self.event_spec)

        translator_name = None
        if "translator" in self.conf:
            translator_name = self.conf["translator"]
        else:
            translator_name = "stub"
            self.logger.info("Try to import translator {}".format(translator_name))

        if translator_name == "stub":
            tr = stub.Translator(self.logger, self.conf, avt, self.module_interface_spec, self.model)
        else:
            raise NotImplementedError("Cannot use EMG translator '{}'".format(translator_name))

        self.mqs['abstract task description'].put(avt)

    def __get_specs(self, logger, directory):
        """
        Fins in the given directory two JSON specifications: interface categories specification and event categories
        specifications.
        :param logger: Logger object.
        :param directory: Provided directory with files.
        :return: Dictionaries with interface categories specification and event categories specifications.
        """
        files = [os.path.join(directory, name) for name in os.listdir(directory)]
        if len(files) < 2:
            FileNotFoundError("EMG expects no less than 2 specifications but found {}".format(len(files)))

        for file in files:
            logger.info("Import specification {}".format(file))
            with open(file, "r") as fh:
                spec = json.loads(fh.read())

            logger.info("Going to determine type of the specification {}".format(file))

            if "categories" in spec and "interface implementations" in spec:
                logger.info("File {} is treated as module interface specification".format(file))
                self.module_interface_spec = spec
            elif "categories" in spec and "interface implementations" not in spec:
                logger.info("File {} is treated as interface categories specification".format(file))
                self.interface_spec = spec
            elif "environment processes" in spec:
                logger.info("File {} is treated as event categories specification".format(file))
                self.event_spec = spec
            else:
                raise FileNotFoundError("File {} does not match interface categories specification nor it matches event"
                                        " categories specification, please check its content")

        if not self.interface_spec:
            raise FileNotFoundError("EMG requires interface categories specification but it is missed")
        elif not self.event_spec:
            raise FileNotFoundError("EMG requires event categories specification but it is missed")

    main = generate_environment


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
