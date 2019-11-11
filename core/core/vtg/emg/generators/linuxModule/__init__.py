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

import ujson
import re
import glob
import os

import core.utils
from core.vtg.emg.common import get_or_die
from core.vtg.emg.generators.abstract import AbstractGenerator
from core.vtg.emg.common.process.serialization import CollectionDecoder
from core.vtg.emg.generators.linuxModule.instances import generate_instances
from core.vtg.emg.generators.linuxModule.processes import process_specifications
from core.vtg.emg.generators.linuxModule.interface.analysis import import_specification
from core.vtg.emg.generators.linuxModule.interface.collection import InterfaceCollection
from core.vtg.emg.generators.linuxModule.process.serialization import ExtendedProcessDecoder
import core.vtg.utils


class ScenarioModelgenerator(AbstractGenerator):

    specifications_endings = {
        'event specifications': 'event spec.json',
        'interface specifications': 'interface spec.json',
        'instance maps': 'insance map.json'
    }

    def make_scenarios(self, abstract_task_desc, collection, source, specifications):
        """
        Make scenario models according to a custom implementation.

        :param abstract_task_desc: Abstract task dictionary.
        :param collection: ProcessCollection.
        :param source: Source collection.
        :param specifications: dictionary with merged specifications.
        :return: Reports dict
        """
        # Get instance maps if possible
        instance_maps = dict()
        all_instance_maps = specifications.get("instance maps", [])

        # Get fragment name
        task_name = abstract_task_desc['fragment']

        # Check availability of an instance map for it
        for imap in all_instance_maps.get('instance maps', []):
            if task_name in imap.get('fragments', []):
                instance_maps = imap.get('instance map', dict())

        self.logger.info("Import interface categories specification")
        interfaces = InterfaceCollection()
        import_specification(self.logger, self.conf, interfaces, source, specifications["interface specifications"])

        self.logger.info("Import event categories specification")
        decoder = ExtendedProcessDecoder(self.logger, self.conf)
        abstract_processes = decoder.parse_event_specification(source,
                                                               specifications["event specification"]["specification"])

        # Now check that we have all necessary interface specifications
        unspecified_functions = [func for func in abstract_processes.models
                                 if func in source.source_functions and
                                 func not in [i.short_identifier for i in interfaces.function_interfaces]]
        if len(unspecified_functions) > 0:
            raise RuntimeError("You need to specify interface specifications for the following function models: {}"
                               .format(', '.join(unspecified_functions)))

        chosen_processes = process_specifications(self.logger, self.conf, interfaces, abstract_processes)

        self.logger.info("Generate processes from abstract ones")
        instance_maps, data = generate_instances(self.logger, self.conf, source, interfaces, chosen_processes,
                                                 instance_maps)

        # Dump to disk instance map
        instance_map_file = 'instance map.json'
        self.logger.info("Dump information on chosen instances to file '{}'".format(instance_map_file))
        with open(instance_map_file, "w", encoding="utf8") as fd:
            fd.writelines(ujson.dumps(instance_maps, ensure_ascii=False, sort_keys=True, indent=4,
                                      escape_forward_slashes=False))

        puredecoder = CollectionDecoder(self.logger, self.conf)
        new_pure_collection = puredecoder.parse_event_specification(source, data)
        collection.environment.update(new_pure_collection.environment)
        collection.models.update(new_pure_collection.models)
        collection.establish_peers()

        return {}


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
                content = ujson.loads(fh.read())
            except ValueError:
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
                                           get_or_die(conf, 'specifications set'))
    __save_collection(logger, interface_spec, 'intf_spec.json')
    event_categories_spec = __merge_spec_versions(event_specifications,
                                                  get_or_die(conf, 'specifications set'))
    __save_collection(logger, event_categories_spec, 'event_spec.json')

    return interface_spec, event_categories_spec


def __merge_spec_versions(collection, user_tag):
    regex = re.compile(r'\(base\)')

    # Copy data to a final spec
    def import_specification(spec, final_spec):
        for tag in spec:
            if tag not in final_spec:
                final_spec[tag] = spec[tag]
            else:
                for new_tag in spec[tag]:
                    if new_tag in final_spec[tag]:
                        raise RuntimeError("Do not expect dublication of entry '{}' in '{}' while composing a final EMG"
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
        ujson.dump(collection, fh, ensure_ascii=False, sort_keys=True, indent=4, escape_forward_slashes=False)


def __get_path(logger, conf, prop):
    if prop in conf:
        spec_dir = core.vtg.utils.find_file_or_dir(logger,
                                                   get_or_die(conf, "main working directory"),
                                                   get_or_die(conf, prop))
        return spec_dir
    else:
        return None


def __get_json_content(logger, conf, prop):
    file = __get_path(logger, conf, prop)
    if file:
        with open(file, encoding="utf8") as fh:
            content = ujson.loads(fh.read())
        return content
    else:
        return None
