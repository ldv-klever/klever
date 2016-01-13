import json
import os

import core.components
import core.utils

from core.avtg.emg.interface_specs import CategorySpecification, ModuleSpecification
from core.avtg.emg.event_spec import EventModel
from core.avtg.emg.translator import stub, sequential


class EMG(core.components.Component):

    def generate_environment(self):
        self.logger.info("Start environment model generator {}".format(self.id))
        self.module_interface_spec = None
        self.model = None
        self.interface_spec = None
        self.event_spec = None
        self.translator = None

        # Initialization of EMG
        self.logger.info("============== Initialization stage ==============")

        self.logger.info("Going to extract abstract verification task from queue")
        avt = self.mqs['abstract task description'].get()
        self.logger.info("Abstract verification task {} has been successfully received".format(avt["id"]))

        self.logger.info("Expect directory with specifications provided via configuration property "
                         "'specifications directory'")
        spec_dir = core.utils.find_file_or_dir(self.logger, self.conf["main working directory"],
                                               self.conf["specifications directory"])

        self.logger.info("Determine which configuration files are provided")
        self.__get_specs(self.logger, spec_dir)
        self.logger.info("All configuration files are successfully imported")

        # Import auxilary files for environment model
        self.logger.info("Check whether additional header files are provided to be included in an environment model")
        headers_lines = []
        if "additional headers" in self.conf:
            headers = self.conf["additional headers"]
            if len(headers) > 0:
                for file in headers:
                    self.logger.info("Search for header file {}".format(file))
                    header_file = core.utils.find_file_or_dir(self.logger, self.conf["main working directory"], file)
                    with open(header_file, "r") as fh:
                        headers_lines.extend(fh.readlines())
                    headers_lines.append("\n")
            self.logger.info("{} additional header files are successfully imported for further importing in the model".
                             format(len(headers)))
        else:
            self.logger.info("No additional header files are provided to be added to the an environment model")

        # Import additional aspect files
        self.logger.info("Check whether additional aspect files are provided to be included in an environment model")
        aspect_lines = []
        if "additional aspects" in self.conf:
            aspects = self.conf["additional aspects"]
            if len(aspects) > 0:
                for file in aspects:
                    self.logger.info("Search for aspect {}".format(file))
                    aspect_file = core.utils.find_file_or_dir(self.logger, self.conf["main working directory"], file)
                    with open(aspect_file, "r") as fh:
                        aspect_lines.extend(fh.readlines())
                    aspect_lines.append("\n")
            self.logger.info("{} additional aspect files are successfully imported for further weaving with an "
                             "environment model".format(len(aspects)))
        else:
            self.logger.info("No additional aspect files are provided to be added to the an environment model")

        # Generate module interface specification
        self.logger.info("============== Modules interface categories selection stage ==============")

        # Import interface categories configuration
        self.logger.info("Import content of provided interface categories specification")
        intf_spec = CategorySpecification(self.logger)
        intf_spec.import_specification(self.interface_spec)
        self.logger.info("Interface categories specification has been imported successfully")

        # Import results of source code analysis
        self.logger.info("Import results of source analysis from SA plugin")
        module_spec = ModuleSpecification(self.logger)
        analysis = {}
        if "source analysis" in avt:
            analysis_file = os.path.join(self.conf["main working directory"], avt["source analysis"])
            self.logger.info("Read file with results of source analysis from {}".format(analysis_file))
            with open(analysis_file, "r") as fh:
                analysis = json.loads(fh.read())
        else:
            self.logger.warning("Cannot find any results of source analysis provided from SA plugin")
        module_spec.import_specification(self.module_interface_spec, analysis, intf_spec)
        self.module_interface_spec = module_spec

        new_module_spec_file = "module_specification.json"
        self.logger.info("Save modules interface specification to '{}'".format(new_module_spec_file))
        self.module_interface_spec.save_to_file(new_module_spec_file)

        # Generate module interface specification
        self.logger.info("============== An intermediate model preparation stage ==============")
        # todo: Import existing environment model

        # Import event categories specification
        self.logger.info("Start preparation of an intermediate environment model")
        self.model = EventModel(self.logger, self.module_interface_spec, self.event_spec).model
        self.logger.info("An intermediate environment model has been prepared")

        # todo: Dump an intermediate model to the file

        # Generate module interface specification
        self.logger.info("============== An intermediat model translation stage ==============")

        # Choose translator
        self.logger.info("Choose translator module to translate an intermediate model to C code")
        if "translator" in self.conf:
            translator_name = self.conf["translator"]
        else:
            translator_name = "stub"
            self.logger.info("Try to import translator {}".format(translator_name))
        self.logger.info("Translation module {} has been chosen".format(translator_name))

        # Start translation
        if translator_name == "stub":
            stub.Translator(
                self.logger,
                self.conf,
                avt,
                self.module_interface_spec,
                self.model,
                headers_lines,
                aspect_lines
            )
        elif translator_name == "sequential":
            sequential.Translator(
                self.logger,
                self.conf,
                avt,
                self.module_interface_spec,
                self.model,
                headers_lines,
                aspect_lines
            )
        else:
            raise NotImplementedError("Oops, seems that provided translation module {} has not been implemented yet".
                                      format(translator_name))
        self.logger.info("An environment model has been generated successfully")

        self.logger.info("Add generated environment model to the abstract verification task")
        self.mqs['abstract task description'].put(avt)

        self.logger.info("Environment model generator successfully finished")

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
            FileNotFoundError("Environment model generator expects no less than 2 specifications but found only {}".
                              format(len(files)))

        for file in files:
            logger.info("Import content of specification file {}".format(file))
            with open(file, "r") as fh:
                spec = json.loads(fh.read())

            logger.info("Going to analyze content of specification file {}".format(file))

            if "categories" in spec and "interface implementations" in spec:
                # todo: not supported yet
                logger.info("Specification file {} is treated as module interface specification".format(file))
                self.module_interface_spec = spec
            elif "categories" in spec and "interface implementations" not in spec:
                logger.info("Specification file {} is treated as interface categories specification".format(file))
                self.interface_spec = spec
            elif "environment processes" in spec:
                logger.info("Specification file {} is treated as event categories specification".format(file))
                self.event_spec = spec
            else:
                raise FileNotFoundError("Specification file {} does not match interface categories specification nor it"
                                        " matches event categories specification, please check its content".
                                        format(file))

        if not self.interface_spec:
            raise FileNotFoundError("Environment model generator missed an interface categories specification")
        elif not self.event_spec:
            raise FileNotFoundError("Environment model generator missed an event categories specification")

    main = generate_environment

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
