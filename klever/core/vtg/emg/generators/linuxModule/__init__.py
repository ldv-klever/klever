#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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
import sortedcontainers

from klever.core.vtg.emg.common.process import ProcessCollection
from klever.core.vtg.emg.generators.abstract import AbstractGenerator
from klever.core.vtg.emg.common.process.serialization import CollectionDecoder
from klever.core.vtg.emg.generators.linuxModule.instances import generate_instances
from klever.core.vtg.emg.generators.linuxModule.processes import process_specifications
from klever.core.vtg.emg.generators.linuxModule.process import ExtendedProcessCollection
from klever.core.vtg.emg.generators.linuxModule.interface.analysis import import_specification
from klever.core.vtg.emg.generators.linuxModule.interface.collection import InterfaceCollection
from klever.core.vtg.emg.generators.linuxModule.process.serialization import ExtendedProcessDecoder


DEFAULT_COMMENTS = {
    "dispatch": {
        "register": "Register {} callbacks.",
        "instance_register": "Register {} callbacks.",
        "deregister": "Deregister {} callbacks.",
        "instance_deregister": "Deregister {} callbacks.",
        "irq_register": "Register {} interrupt handler.",
        "irq_deregister": "Deregister {} interrupt handler."
    },
    "receive": {
        "register": "Begin {} callbacks invocations scenario.",
        "instance_register": "Begin {} callbacks invocations scenario.",
        "deregister": "Finish {} callbacks invocations scenario.",
        "instance_deregister": "Finish {} callbacks invocations scenario."
    }
}


class ScenarioModelgenerator(AbstractGenerator):

    specifications_endings = {
        'event specifications': 'event spec.json',
        'interface specifications': 'interface spec.json',
        'instance maps': 'instance map.json'
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
        instance_maps = sortedcontainers.SortedDict()
        all_instance_maps = specifications.get("instance maps", [])
        self.conf.setdefault("action comments", DEFAULT_COMMENTS)
        self.conf.setdefault("callback comment", "Invoke callback {0} from {1}.")

        # Get fragment name
        task_name = abstract_task_desc['fragment']

        # Check availability of an instance map for it
        for imap in all_instance_maps.get('instance maps', []):
            if task_name in imap.get('fragments', []):
                instance_maps = imap.get('instance map', sortedcontainers.SortedDict())

        self.logger.info("Import interface categories specification")
        interfaces = InterfaceCollection()
        import_specification(self.logger, self.conf, interfaces, source, specifications["interface specifications"])

        self.logger.info("Import event categories specification")
        decoder = ExtendedProcessDecoder(self.logger, self.conf)
        abstract_processes = decoder.parse_event_specification(source, specifications["event specifications"],
                                                               ExtendedProcessCollection())

        # Remove deleted models
        deleted_models = [func for func in abstract_processes.models if func in source.source_functions and
                          interfaces.is_removed_function(func)]
        if deleted_models:
            self.logger.info("Found deleted models: {}".format(', '.join(deleted_models)))

            for name in deleted_models:
                del abstract_processes.models[name]

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
        self.logger.info("Dump information on chosen instances to file {!r}".format(instance_map_file))
        with open(instance_map_file, "w", encoding="utf-8") as fd:
            fd.writelines(ujson.dumps(instance_maps, ensure_ascii=False, sort_keys=True, indent=4,
                                      escape_forward_slashes=False))

        puredecoder = CollectionDecoder(self.logger, self.conf)
        new_pure_collection = puredecoder.parse_event_specification(source, ujson.loads(data), ProcessCollection())
        collection.environment.update(new_pure_collection.environment)
        collection.models.update(new_pure_collection.models)
        collection.establish_peers()

        return {}

    def _merge_specifications(self, specifications_set, files):
        merged_specification = sortedcontainers.SortedDict()
        for file in files:
            with open(file, 'r', encoding='utf-8') as fp:
                new_content = ujson.load(fp)

            # This preprocessing helps if only a single function in specification is replaced
            for spec_set in new_content:
                for kind in new_content[spec_set]:
                    for item in sorted(list(new_content[spec_set][kind].keys())):
                        if ', ' in item:
                            new_content[spec_set][kind].update(
                                {i: new_content[spec_set][kind][item] for i in item.split(', ')})
                            del new_content[spec_set][kind][item]

            for spec_set in new_content:
                if specifications_set and spec_set == specifications_set:
                    # This is our specification
                    for title in new_content[spec_set]:
                        merged_specification.setdefault(title, sortedcontainers.SortedDict())
                        merged_specification[title].update(new_content[spec_set][title])
                else:
                    # Find reference ones
                    for title in new_content[spec_set]:
                        merged_specification.setdefault(title, sortedcontainers.SortedDict())
                        for k, v in new_content[spec_set][title].items():
                            # Do not replace already imported process descriptions
                            if v.get('reference') and not merged_specification[title].get(k):
                                merged_specification[title][k] = v

        return merged_specification
