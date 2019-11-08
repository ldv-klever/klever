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

from core.vtg.emg.generators.abstract import AbstractGenerator
from core.vtg.emg.common.process.serialization import CollectionDecoder


class ScenarioModelgenerator(AbstractGenerator):

    specifications_endings = {
        'manual event models': 'user model.json'
    }

    def make_scenarios(self, abstract_task_desc, collection, source, specifications):
        """
        This generator reads a manually prepared environment model description and some of them just adds to the already
        generated model and some generated processes with the same names it replaces by new manually prepared one. A user
        can just get an automatically generated model by setting option for a translator and modify it to rerun EMG next
        time to make it generate the model with desired properties without modifying any specifications.
        
        :param abstract_task_desc: Abstract task dictionary.
        :param collection: ProcessCollection.
        :param source: Source collection.
        :param specifications: dictionary with merged specifications.
        :return: Reports dict
        """
        # Import Specifications
        all_instance_maps = specifications.get("manual event models", [])
        fragment_name = abstract_task_desc['fragment']
        descriptions = None
        for imap in all_instance_maps:
            if fragment_name in imap.get('fragments', []):
                descriptions = imap.get("model", None)

        # Import manual process
        if descriptions and ("functions models" in descriptions or "environment processes" in descriptions or
                             "main process" in descriptions):

            parser = CollectionDecoder(self.logger, self.conf)
            manual_processes = parser.parse_event_specification(source, descriptions)

            # Decide on process replacements
            or_entry = collection.entry
            if manual_processes.entry:
                if (self.conf.get("enforce replacement") and collection.entry) or not collection.entry:
                    if self.conf.get("keep entry functions") and collection.entry:
                        for or_decl in collection.entry.declarations:
                            if or_decl in manual_processes.entry.declarations:
                                manual_processes.entry.declarations[or_decl] = {
                                    **manual_processes.entry.declarations[or_decl],
                                    **collection.entry.declarations[or_decl]
                                }
                            else:
                                manual_processes.entry.declarations[or_decl] = collection.entry.declarations[or_decl]
                        for or_def in collection.entry.definitions:
                            if or_def in manual_processes.entry.definitions:
                                manual_processes.entry.definitions[or_def] = {
                                    **manual_processes.entry.definitions[or_def],
                                    **collection.entry.definitions[or_def]
                                }
                            else:
                                manual_processes.entry.definitions[or_def] = collection.entry.definitions[or_def]

                    or_entry = manual_processes.entry

            # Replace rest processes
            if self.conf.get("enforce replacement"):
                for collection, manual in ((collection.models, manual_processes.models),
                                           (collection.environment, manual_processes.environment)):
                    collection.update(manual)

            collection.entry = or_entry
            collection.establish_peers(strict=True)
        else:
            self.logger.info("There is no specification for {!r} or it has invalid format".format(fragment_name))

        return {}

    def _merge_specifications(self, specifications_set, files):
        merged_specification = list()
        for file in files:
            with open(file, 'r', encoding='utf8') as fp:
                new_content = json.load(fp)

            for spec_set in new_content:
                if specifications_set and spec_set == specifications_set:
                    # This is our specification
                    merged_specification.extend(new_content[spec_set])
                else:
                    # Find reference ones
                    for specification in (s.get('model', {}) for s in new_content[spec_set]):
                        for subsection in specification:
                            for k, v in list(specification[subsection].items()):
                                if not v.get('reference'):
                                    del specification[subsection][k]
                    merged_specification.extend(new_content[spec_set])
        return merged_specification
