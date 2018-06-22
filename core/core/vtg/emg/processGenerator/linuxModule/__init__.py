#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
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

import json
import re
import glob
import os

import core.utils
from core.vtg.emg.common import get_conf_property, get_necessary_conf_property
from core.vtg.emg.processGenerator.linuxModule.processes import ProcessModel
from core.vtg.emg.processGenerator.linuxModule.instances import generate_instances
from core.vtg.emg.processGenerator.linuxModule.interface.collection import InterfaceCollection
from core.vtg.emg.processGenerator.linuxModule.process.procImporter import AbstractProcessImporter


def generate_processes(emg, source, processes, conf):
    """
    This generator generates processes for verifying Linux kernel modules and some parts of the Linux kernel itself.
     For instance, it adds function models for kernel functions and calls callbacks in the environment model.
     It uses interface categories specifications and event categories specifications to generate the model.

    :param emg: EMG Plugin object.
    :param source: Source collection object.
    :param processes: ProcessCollection object.
    :param conf: Configuration dictionary of this generator.
    :return: None.
    """
    # Get instance maps if possible
    instance_maps = dict()
    if get_conf_property(emg.conf, "EMG instances"):
        emg.logger.info('Looking for a file with an instance map {!r}'.
                        format(get_necessary_conf_property(emg.conf, "EMG instances")))
        with open(core.utils.find_file_or_dir(emg.logger,
                                              get_necessary_conf_property(emg.conf, "main working directory"),
                                              get_necessary_conf_property(emg.conf, "EMG instances")),
                  encoding='utf8') as fp:
            instance_maps = json.load(fp)

    # Import Specifications
    emg.logger.info("Search for interface and event specifications")
    spec_dir = __get_path(emg.logger, emg.conf, "specifications directory")
    interface_spec, event_spec = __get_specs(emg.logger, emg.conf, spec_dir)

    emg.logger.info("Import interface categories specification")
    interfaces = InterfaceCollection(emg.logger, conf)
    interfaces.fill_up_collection(source, interface_spec)

    emg.logger.info("Import event categories specification")
    abstract_processes = AbstractProcessImporter(emg.logger, conf)
    abstract_processes.parse_event_specification(event_spec)
    roles_file = core.utils.find_file_or_dir(emg.logger,
                                             get_necessary_conf_property(emg.conf, "main working directory"),
                                             get_necessary_conf_property(conf, "roles map file"))

    # Now check that we have all necessary interface specifications
    unspecified_functions = [func for func in abstract_processes.models
                             if func in source.source_functions and
                             func not in [i.short_identifier for i in interfaces.function_interfaces]]
    if len(unspecified_functions) > 0:
        raise RuntimeError("You need to specify interface specifications for the following function models: {}"
                           .format(', '.join(unspecified_functions)))

    with open(roles_file, encoding="utf8") as fh:
        roles_map = json.loads(fh.read())
    process_model = ProcessModel(emg.logger, conf, interfaces, abstract_processes, roles_map)
    abstract_processes.environment = {p.identifier: p for p in process_model.event_processes}
    abstract_processes.models = {p.identifier: p for p in process_model.model_processes}

    emg.logger.info("Generate processes from abstract ones")
    instance_maps, data = generate_instances(emg.logger, conf, source, interfaces, abstract_processes, instance_maps)

    # Send data to the server
    emg.logger.info("Send data about generated instances to the server")
    core.utils.report(emg.logger,
                      'data',
                      {
                          'id': emg.id,
                          'data': instance_maps
                      },
                      emg.mqs['report files'],
                      emg.vals['report id'],
                      get_necessary_conf_property(emg.conf, "main working directory"))
    emg.logger.info("An intermediate environment model has been prepared")

    # Dump to disk instance map
    instance_map_file = 'instance map.json'
    emg.logger.info("Dump information on chosen instances to file '{}'".format(instance_map_file))
    with open(instance_map_file, "w", encoding="utf8") as fd:
        fd.writelines(json.dumps(instance_maps, ensure_ascii=False, sort_keys=True, indent=4))

    processes.parse_event_specification(data)
    processes.establish_peers()


def __get_specs(logger, conf, directory):
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
    for file in file_candidates:
        with open(file, encoding="utf8") as fh:
            try:
                content = json.loads(fh.read())
            except json.decoder.JSONDecodeError:
                raise ValueError("Cannot parse EMG specification file {!r}".format(os.path.abspath(file)))

        if isinstance(content, dict):
            for tag in (t for t in content if isinstance(content[t], dict)):
                if "categories" in content[tag]:
                    logger.debug("Specification file {} is treated as interface categories specification".format(file))
                    interface_specifications.append(content)
                elif "environment processes" in content[tag]:
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
    interface_spec = __merge_spec_versions(interface_specifications,
                                           get_necessary_conf_property(conf, 'specifications set'))
    __save_collection(logger, interface_spec, 'intf_spec.json')
    event_categories_spec = __merge_spec_versions(event_specifications,
                                                  get_necessary_conf_property(conf, 'specifications set'))
    __save_collection(logger, event_categories_spec, 'event_spec.json')

    return interface_spec, event_categories_spec


def __merge_spec_versions(collection, user_tag):
    regex = re.compile('\(base\)')

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

    def match_default_tag(e):
        for tag in e:
            if regex.search(tag):
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


def __save_collection(logger, collection, file):
    logger.info("Print final merged specification to '{}'".format(file))
    with open(file, "w", encoding="utf8") as fh:
        json.dump(collection, fh, ensure_ascii=False, sort_keys=True, indent=4)


def __get_path(logger, conf, prop):
    if prop in conf:
        spec_dir = core.utils.find_file_or_dir(logger,
                                               get_necessary_conf_property(conf, "main working directory"),
                                               get_necessary_conf_property(conf, prop))
        return spec_dir
    else:
        return None


def __get_json_content(logger, conf, prop):
    file = __get_path(logger, conf, prop)
    if file:
        with open(file, encoding="utf8") as fh:
            content = json.loads(fh.read())
        return content
    else:
        return None
