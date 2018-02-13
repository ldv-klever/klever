#
# Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
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
import json

import core.utils
from core.vtg.emg.common import get_necessary_conf_property, get_conf_property
from core.vtg.emg.common.process import Receive, Dispatch
from core.vtg.emg.common.process.procImporter import ProcessImporter


def generate_processes(emg, source, processes_triple, conf):
    # Import Specifications
    emg.logger.info("Import manually prepared process descriptions and add them to the generated processes")
    # Import manual process
    filename = get_necessary_conf_property(conf, "process descriptions file")
    with open(core.utils.find_file_or_dir(emg.logger, get_necessary_conf_property(emg.conf, "main working directory"),
                                          filename),
              encoding='utf8') as fp:
        descriptions = json.load(fp)
    importer = ProcessImporter(emg.logger, emg.conf)
    model_processes, env_processes, entry = importer.parse_event_specification(descriptions)
    or_models, or_processes, or_entry = processes_triple

    # Convert dispatches to the simple form for each process
    for process in or_models + or_processes + ([or_entry] if or_entry else []):
        for action in (a for a in process.actions.values() if isinstance(a, Dispatch) or isinstance(a, Receive)):
            if len(action.peers) > 0:
                peers = list()
                for p in action.peers:
                    if isinstance(p, dict):
                        peers.append(p['process'].pretty_id)
                        if not p['process'].pretty_id:
                            raise ValueError('Any peer must have an external identifier')
                    else:
                        peers.append(p)
                action.peers = peers

    # Decide on process replacements
    if get_conf_property(conf, "enforce replacement"):
        if or_entry and entry:
            or_entry = entry

    # Replace rest processes
    for collection, generated in ((or_models, model_processes), (or_processes, env_processes)):
        for process in generated.values():
            if process.pretty_id in (p.pretty_id for p in collection) and get_conf_property(conf, "enforce replacement"):
                collection[[p.pretty_id for p in collection].index(process.pretty_id)] = process
            elif process.pretty_id not in (p.pretty_id for p in collection):
                collection.insert(0, process)

    importer.establish_peers(or_models, or_processes, or_entry, strict=True)

    return or_models, or_processes, or_entry
