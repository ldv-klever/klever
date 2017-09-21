#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import glob
import json
import os
import re

import core.vtg.plugins

import core.utils
from core.vtg.emg.common import check_or_set_conf_property, get_necessary_conf_property, get_conf_property
from core.vtg.emg.interfacespec import InterfaceCategoriesSpecification
from core.vtg.emg.processmodel import ProcessModel
from core.vtg.emg.processmodel.process_parser import parse_event_specification
from core.vtg.emg.translator import translate_intermediate_model


class EMG(core.vtg.plugins.Plugin):
    """
    EMG plugin for environment model generation.
    """

    specification_extension_re = re.compile('.json$')
    depend_on_rule = False

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

        self.logger.info("Expect directory with specifications provided via configuration property "
                         "'specifications directory'")
        spec_dir = self.__get_path(self.conf, "specifications directory")

        self.logger.info("Import results of source analysis from SA plugin")
        analysis = self.__get_analysis(self.abstract_task_desc)

        # Find specifications
        self.logger.info("Determine which specifications are provided")
        interface_spec, event_categories_spec = self.__get_specs(self.logger, spec_dir)
        self.logger.info("All necessary data has been successfully found")

        # Generate module interface specification
        self.logger.info("============== Modules interface categories selection stage ==============")
        check_or_set_conf_property(self.conf, 'interface categories options', default_value=dict(), expected_type=dict)
        ics = InterfaceCategoriesSpecification(self.logger, self.conf['interface categories options'],
                                               self.abstract_task_desc, interface_spec, analysis)
        # todo: export specification (issue 6561)
        #mcs.save_to_file("module_specification.json")

        # Generate module interface specification
        self.logger.info("============== An intermediate model preparation stage ==============")
        check_or_set_conf_property(self.conf, 'intermediate model options', default_value=dict(), expected_type=dict)
        model_processes, env_processes = \
            parse_event_specification(self.logger, get_necessary_conf_property(self.conf, 'intermediate model options'),
                                      event_categories_spec)

        model = ProcessModel(self.logger, get_necessary_conf_property(self.conf, 'intermediate model options'),
                             model_processes, env_processes,
                             self.__get_json_content(get_necessary_conf_property(self.conf,
                                                                                 'intermediate model options'),
                                                     "roles map file"))
        model.generate_event_model(ics)
        self.logger.info("An intermediate environment model has been prepared")

        # Generate module interface specification
        self.logger.info("============== An intermediat model translation stage ==============")
        check_or_set_conf_property(self.conf, 'translation options', default_value=dict(), expected_type=dict)

        # Get instance maps if possible
        instance_maps = dict()
        if get_conf_property(self.conf, "EMG instances"):
            self.logger.info('Looking for a file with an instance map {!r}'.
                             format(get_necessary_conf_property(self.conf, "EMG instances")))
            with open(core.utils.find_file_or_dir(self.logger,
                                                  get_necessary_conf_property(self.conf, "main working directory"),
                                                  get_necessary_conf_property(self.conf, "EMG instances")),
                      encoding='utf8') as fp:
                instance_maps = json.load(fp)

        # Import additional aspect files
        instance_maps = translate_intermediate_model(self.logger, self.conf, self.abstract_task_desc, ics, model,
                                                     instance_maps, self.__read_additional_content("aspects"))
        self.logger.info("An environment model has been generated successfully")

        # Dump to disk instance map
        instance_map_file = 'instance map.json'
        self.logger.info("Dump information on chosen instances to file '{}'".format(instance_map_file))
        with open(instance_map_file, "w", encoding="utf8") as fh:
            fh.writelines(json.dumps(instance_maps, ensure_ascii=False, sort_keys=True, indent=4))

        # Send data to the server
        self.logger.info("Send data on generated instances to server")
        core.utils.report(self.logger,
                          'data',
                          {
                              'id': self.id,
                              'data': instance_maps
                          },
                          self.mqs['report files'],
                          get_necessary_conf_property(self.conf, "main working directory"),
                          'emg data report')

    main = generate_environment

    ####################################################################################################################
    # PRIVATE METHODS
    ####################################################################################################################

    def __read_additional_content(self, file_type):
        lines = []
        if get_conf_property(self.conf, "additional {}".format(file_type)):
            files = sorted(get_necessary_conf_property(self.conf, "additional {}".format(file_type)))
            if len(files) > 0:
                for file in files:
                    self.logger.info("Search for {} file {}".format(file, file_type))
                    path = core.utils.find_file_or_dir(self.logger,
                                                       get_necessary_conf_property(self.conf, "main working directory"),
                                                       file)
                    with open(path, encoding="utf8") as fh:
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
            analysis_file = os.path.join(get_necessary_conf_property(self.conf, "main working directory"),
                                         avt["source analysis"])
            self.logger.info("Read file with results of source analysis from {}".format(analysis_file))

            with open(analysis_file, encoding="utf8") as fh:
                analysis = json.loads(fh.read())
        else:
            self.logger.warning("Cannot find any results of source analysis provided from SA plugin")

        return analysis

    def __get_specs(self, logger, directory):
        """
        todo: Update.
        :param logger: Logger object.
        :param directory: Provided directory with files.
        :return: Dictionaries with interface categories specification and event categories specifications.
        """
        logger.info('Search for event and interface categories specifications in {}'.format(directory))
        interface_specifications = list()
        event_specifications = list()

        # Find all json files
        file_candidates = set()
        for root, dirs, files in os.walk(directory):
            # Check only full pathes to files
            json_files = glob.glob('{}/*.json'.format(root))
            file_candidates.update(json_files)

        # Filter specifications
        for file in sorted(file_candidates):
            with open(file, encoding="utf8") as fh:
                try:
                    content = json.loads(fh.read())
                except json.decoder.JSONDecodeError as err:
                    raise ValueError("Cannot parse EMG specification file {!r}".format(os.path.abspath(file)))

            for tag in content:
                if "categories" in content[tag] or "kernel functions" in content[tag]:
                    logger.debug("Specification file {} is treated as interface categories specification".format(file))
                    interface_specifications.append(content)
                elif "environment processes" in content[tag] or "kernel model" in content[tag]:
                    logger.debug("Specification file {} is treated as event categories specification".format(file))
                    event_specifications.append(content)
                else:
                    logger.debug("File '{}' is not recognized as a EMG specification".format(file))
                break

        # Check presence of specifications
        if len(interface_specifications) == 0:
            raise FileNotFoundError("Environment model generator missed an interface categories specification")
        elif len(event_specifications) == 0:
            raise FileNotFoundError("Environment model generator missed an event categories specification")

        # Merge specifications
        interface_spec = self.__merge_spec_versions(interface_specifications,
                                                    get_necessary_conf_property(self.conf, 'specifications set'))
        self.__save_collection(logger, interface_spec, 'intf_spec.json')
        event_categories_spec = self.__merge_spec_versions(event_specifications,
                                                           get_necessary_conf_property(self.conf, 'specifications set'))
        self.__save_collection(logger, event_categories_spec, 'event_spec.json')

        # toso: search for module categories specification
        return interface_spec, event_categories_spec

    def __get_path(self, conf, prop):
        if prop in conf:
            spec_dir = core.utils.find_file_or_dir(self.logger,
                                                   get_necessary_conf_property(self.conf, "main working directory"),
                                                   get_necessary_conf_property(conf, prop))
            return spec_dir
        else:
            return None

    def __get_json_content(self, conf, prop):
        file = self.__get_path(conf, prop)
        if file:
            with open(file, encoding="utf8") as fh:
                content = json.loads(fh.read())
            return content
        else:
            return None

    def __merge_spec_versions(self, collection, user_tag):
        # Copy data to a final spec
        def import_specification(spec, final_spec):
            for tag in spec:
                if tag not in final_spec:
                    final_spec[tag] = spec[tag]
                else:
                    for new_tag in spec[tag]:
                        if new_tag in final_spec[tag]:
                            raise KeyError("Do not expect dublication of entry '{}' in '{}' while composing a final EMG"
                                           " specification".format(new_tag, tag))
                        final_spec[tag][new_tag] = spec[tag][new_tag]

        def match_default_tag(entry):
            dt = re.compile('\(base\)')

            for tag in entry:
                if dt.search(tag):
                    return tag

            return None

        final_specification = dict()

        # Import each entry
        for entry in collection:
            if user_tag in entry:
                # Find provided by a user tag
                import_specification(entry[user_tag], final_specification)
            else:
                # Search for a default tag
                dt = match_default_tag(entry)
                if dt:
                    import_specification(entry[dt], final_specification)

        # Return final specification
        return final_specification

    def __save_collection(self, logger, collection, file):
        logger.info("Print final merged specification to '{}'".format(file))
        with open(file, "w", encoding="utf8") as fh:
            json.dump(collection, fh, ensure_ascii=False, sort_keys=True, indent=4)

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
