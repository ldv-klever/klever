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

from core.vtg.emg.common import get_conf_property
from core.vtg.emg.common.process import ProcessCollection
from core.vtg.emg.processGenerator.generators import AbstractGenerator


class genericManual(AbstractGenerator):

    specifications_endings = {
        'intermediate specifications': {"intermediate spec.json"}
    }

    def generate_processes(self, emg, source, processes, conf, specifications):
        """
        This generator reads a manually prepared environment model description and some of them just adds to the already
        generated model and some generated processes with the same names it replaces by new manually prepared one. A user
        can just get an automatically generated model by setting option for a translator and modify it to rerun EMG next
        time to make it generate the model with desired properties without modifying any specifications.

        :param emg: EMG Plugin object.
        :param source: Source collection object.
        :param processes: ProcessCollection object.
        :param conf: Configuration dictionary of this generator.
        :return: None.
        """
        # Import Specifications
        or_models = list(processes.models.values())
        or_processes = list(processes.environment.values())
        or_entry = processes.entry

        all_instance_maps = specifications["manual event models"].get("specification")
        fragment_name = emg.abstract_task_desc['fragment']
        descriptions = None
        for imap in all_instance_maps.get("manual event models", []):
            if fragment_name in imap.get('fragments', []):
                descriptions = imap.get("model", None)

        # Import manual process
        if descriptions and ("functions models" in descriptions or "environment processes" in descriptions or
                             "main process" in descriptions):

            manual_processes = ProcessCollection(emg.logger, emg.conf)
            manual_processes.parse_event_specification(descriptions)

            # Decide on process replacements
            if manual_processes.entry:
                if (get_conf_property(conf, "enforce replacement") and or_entry) or not or_entry:
                    if get_conf_property(conf, "keep entry functions") and or_entry:
                        for or_decl in or_entry.declarations:
                            if or_decl in manual_processes.entry.declarations:
                                manual_processes.entry.declarations[or_decl] = {**manual_processes.entry.declarations[or_decl],
                                                                                **or_entry.declarations[or_decl]}
                            else:
                                manual_processes.entry.declarations[or_decl] = or_entry.declarations[or_decl]
                        for or_def in or_entry.definitions:
                            if or_def in manual_processes.entry.definitions:
                                manual_processes.entry.definitions[or_def] = {**manual_processes.entry.definitions[or_def],
                                                                              **or_entry.definitions[or_def]}
                            else:
                                manual_processes.entry.definitions[or_def] = or_entry.definitions[or_def]

                    or_entry = manual_processes.entry

            # Replace rest processes
            for collection, manual in ((or_models, manual_processes.models.values()),
                                       (or_processes, manual_processes.environment.values())):
                for process in manual:
                    if process.pretty_id in {p.pretty_id for p in collection} and \
                            get_conf_property(conf, "enforce replacement"):
                        collection[[p.pretty_id for p in collection].index(process.pretty_id)] = process
                    elif process.pretty_id not in {p.pretty_id for p in collection}:
                        collection.insert(0, process)
        else:
            emg.logger.info("There is no specification for {!r} or it has invalid format".format(fragment_name))

        processes.entry = or_entry
        processes.models = {p.pretty_id: p for p in or_models}
        processes.environment = {p.pretty_id: p for p in or_processes}
        processes.establish_peers(strict=True)
