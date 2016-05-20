import json
import os

import core.components
import core.utils

from core.avtg.emg.interface_categories import CategoriesSpecification
from core.avtg.emg.module_categories import ModuleCategoriesSpecification
from core.avtg.emg.process_parser import parse_event_specification
from core.avtg.emg.intermediate_model import ProcessModel


class EMG(core.components.Component):
    """
    EMG plugin for environment model generation.
    """

    ####################################################################################################################
    # PUBLIC METHODS
    ####################################################################################################################

    def generate_environment(self):
        """
        Main function of EMG plugin.

        Plugin generates an environment model for a module (modules) in abstract verification task. The model is
        represented in as a set of aspect files which will be included after generation to an abstract verification
        task.

        :return: None
        """
        self.logger.info("Start environment model generator {}".format(self.id))

        # Initialization of EMG
        self.logger.info("============== Initialization stage ==============")

        self.logger.info("Going to extract abstract verification task from queue")
        avt = self.mqs['abstract task description'].get()
        self.logger.info("Abstract verification task {} has been successfully received".format(avt["id"]))

        self.logger.info("Expect directory with specifications provided via configuration property "
                         "'specifications directory'")
        spec_dir = core.utils.find_file_or_dir(self.logger, self.conf["main working directory"],
                                               self.conf["specifications directory"])

        self.logger.info("Import results of source analysis from SA plugin")
        analysis = self.__get_analysis(avt)

        # Choose translator
        tr = self.__get_translator(avt)

        # Find specifications
        self.logger.info("Determine which specifications are provided")
        interface_spec, module_interface_spec, event_categories_spec = self.__get_specs(self.logger, spec_dir)
        self.logger.info("All necessary data has been successfully found")

        # Generate module interface specification
        self.logger.info("============== Modules interface categories selection stage ==============")
        mcs = ModuleCategoriesSpecification(self.logger, self.conf)
        mcs.import_specification(avt, interface_spec, module_interface_spec, analysis)
        # todo: export specification (issue 6561)
        #mcs.save_to_file("module_specification.json")

        # Generate module interface specification
        self.logger.info("============== An intermediate model preparation stage ==============")
        model_processes, env_processes = parse_event_specification(self.logger, event_categories_spec)

        if 'intermediate model options' not in self.conf:
            self.conf['intermediate model options'] = {}
        model = ProcessModel(self.logger, self.conf['intermediate model options'], model_processes, env_processes)
        model.generate_event_model(mcs)
        self.logger.info("An intermediate environment model has been prepared")

        # Generate module interface specification
        self.logger.info("============== An intermediat model translation stage ==============")
        tr.translate(mcs, model)
        self.logger.info("An environment model has been generated successfully")

        self.logger.info("Add generated environment model to the abstract verification task")
        self.mqs['abstract task description'].put(avt)

        self.logger.info("Environment model generator successfully finished")

    main = generate_environment

    ####################################################################################################################
    # PRIVATE METHODS
    ####################################################################################################################

    def __read_additional_content(self, file_type):
        lines = []
        if "additional {}".format(file_type) in self.conf:
            files = sorted(self.conf["additional {}".format(file_type)])
            if len(files) > 0:
                for file in files:
                    self.logger.info("Search for {} file {}".format(file, file_type))
                    path = core.utils.find_file_or_dir(self.logger, self.conf["main working directory"], file)
                    with open(path, encoding="ascii") as fh:
                        lines.extend(fh.readlines())
                    lines.append("\n")
            self.logger.info("{} additional {} files are successfully imported for further importing in the model".
                             format(len(files), file_type))
        else:
            self.logger.info("No additional {} files are provided to be added to the an environment model".
                             format(file_type))
        return lines

    def __get_analysis(self, avt):
        analysis = {}
        if "source analysis" in avt:
            analysis_file = os.path.join(self.conf["main working directory"], avt["source analysis"])
            self.logger.info("Read file with results of source analysis from {}".format(analysis_file))

            with open(analysis_file, encoding="ascii") as fh:
                analysis = json.loads(fh.read())
        else:
            self.logger.warning("Cannot find any results of source analysis provided from SA plugin")

        return analysis

    def __get_translator(self, avt):
        self.logger.info("Choose translator module to translate an intermediate model to C code")
        if "translator" in self.conf:
            translator_name = self.conf["translator"]
        else:
            translator_name = "default"
        self.logger.info("Translation module {} has been chosen".format(translator_name))

        translator = getattr(__import__("core.avtg.emg.translator.{}".format(translator_name),
                                        fromlist=['Translator']),
                             'Translator')

        # Import additional aspect files
        self.logger.info("Check whether additional aspect files are provided to be included in an environment model")
        aspect_lines = self.__read_additional_content("aspects")

        return translator(self.logger, self.conf, avt, aspect_lines)

    def __get_specs(self, logger, directory):
        """
        Fins in the given directory two JSON specifications: interface categories specification and event categories
        specifications.
        :param logger: Logger object.
        :param directory: Provided directory with files.
        :return: Dictionaries with interface categories specification and event categories specifications.
        """
        interface_spec = None
        module_interface_spec = None
        event_categories_spec = None

        files = [os.path.join(directory, name) for name in sorted(os.listdir(directory))]
        if len(files) < 2:
            FileNotFoundError("Environment model generator expects no less than 2 specifications but found only {}".
                              format(len(files)))

        for file in files:
            if '.json' in file:
                logger.info("Import content of specification file {}".format(file))
                with open(file, encoding="ascii") as fh:
                    spec = json.loads(fh.read())

                logger.info("Going to analyze content of specification file {}".format(file))

                if "categories" in spec and "interface implementations" in spec:
                    # todo: not supported yet
                    logger.info("Specification file {} is treated as module interface specification".format(file))
                    module_interface_spec = spec
                elif "categories" in spec and "interface implementations" not in spec:
                    logger.info("Specification file {} is treated as interface categories specification".format(file))
                    interface_spec = spec
                elif "environment processes" in spec:
                    logger.info("Specification file {} is treated as event categories specification".format(file))
                    event_categories_spec = spec

        if not interface_spec:
            raise FileNotFoundError("Environment model generator missed an interface categories specification")
        elif not event_categories_spec:
            raise FileNotFoundError("Environment model generator missed an event categories specification")

        return interface_spec, module_interface_spec, event_categories_spec

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
