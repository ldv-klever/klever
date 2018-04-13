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
from core.vtg.emg.common.process.collection import ProcessCollection


def generate_processes(emg, source, processes, conf):
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

    # Import manual process
    filename = get_necessary_conf_property(conf, "process descriptions file")
    emg.logger.info("Import manually prepared processes descriptions from {!r} and add them to the model".
                    format(filename))
    with open(core.utils.find_file_or_dir(emg.logger, get_necessary_conf_property(emg.conf, "main working directory"),
                                          filename),
              encoding='utf8') as fp:
        descriptions = json.load(fp)
    manual_processes = ProcessCollection(emg.logger, emg.conf)
    manual_processes.parse_event_specification(descriptions)

    # Decide on process replacements
    if manual_processes.entry:
        if (get_conf_property(conf, "enforce replacement") and or_entry) or not or_entry:
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

    processes.entry = or_entry
    processes.models = {p.pretty_id: p for p in or_models}
    processes.environment = {p.pretty_id: p for p in or_processes}
    processes.establish_peers(strict=True)
