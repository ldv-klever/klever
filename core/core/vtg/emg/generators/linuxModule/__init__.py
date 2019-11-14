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

from core.vtg.emg.generators.abstract import AbstractGenerator
from core.vtg.emg.common.process.serialization import CollectionDecoder
from core.vtg.emg.generators.linuxModule.instances import generate_instances
from core.vtg.emg.generators.linuxModule.processes import process_specifications
from core.vtg.emg.generators.linuxModule.interface.analysis import import_specification
from core.vtg.emg.generators.linuxModule.interface.collection import InterfaceCollection
from core.vtg.emg.generators.linuxModule.process.serialization import ExtendedProcessDecoder


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
        abstract_processes = decoder.parse_event_specification(source, specifications["event specifications"])

        # Now check that we have all necessary interface specifications
        unspecified_functions = [func for func in abstract_processes.models if func in source.source_functions and
                                 func not in [i.name for i in interfaces.function_interfaces]]
        if unspecified_functions:
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
        new_pure_collection = puredecoder.parse_event_specification(source, ujson.loads(data))
        collection.environment.update(new_pure_collection.environment)
        collection.models.update(new_pure_collection.models)
        collection.establish_peers()

        return {}
