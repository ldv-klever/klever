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

import os
import json
import importlib
from klever.core.utils import get_search_dirs
from klever.core.vtg.emg.common import get_or_die
from klever.core.vtg.emg.common.process.serialization import CollectionEncoder


def generate_processes(logger, conf, collection, abstract_task_desc, source):
    """
    This is the main function for generating processes of the environment model in the intermediate representation.
    From the configuration, the function reads the list of generators names and runs them one by one to obtain a final
    set of processes before translation them into C code.

    :param logger: logging.Logger plugin object.
    :param conf: EMG configuration dict.
    :param collection: ProcessCollection object.
    :param abstract_task_desc: Description dict.
    :param source: Source collection object.
    :return: None
    """
    # In a specific order start process generators
    generator_names = ((e, '.vtg.emg.generators.{}'.format(e)) for e in
                       [list(e.keys())[0] for e in get_or_die(conf, "generators options")])
    configurations = [list(e.values())[0] for e in get_or_die(conf, "generators options")]
    specifications_set = get_or_die(conf, "specifications set")

    # Find generators
    modules = [(shortname, importlib.import_module(name, 'klever.core')) for shortname, name in generator_names]

    # Get specifications for each kind of a generator
    possible_locations = [root for root, *_ in os.walk(os.path.dirname(conf['specifications dir']))] + \
                         list(get_search_dirs(conf['main working directory']))

    for index, (shortname, generator_module) in enumerate(modules):
        # Set debug option
        configurations[index]['keep intermediate files'] = conf.get('keep intermediate files')

        generator = generator_module.ScenarioModelgenerator(logger, configurations[index])
        specifications = generator.import_specifications(specifications_set, possible_locations)
        generator.make_scenarios(abstract_task_desc, collection, source, specifications)

        # Now save specifications
        if conf.get('keep intermediate files'):
            # Save specifications
            for kind in specifications:
                file_name = "{} {}.json".format(shortname, kind)
                generator.save_specification(specifications[kind], file_name)

            # Save processes
            with open('%s intermediate model.json' % str(shortname), mode='w', encoding='utf-8') as fp:
                json.dump(collection, fp, cls=CollectionEncoder, sort_keys=True, indent=2)

            # Save images of processes
            collection.save_digraphs('images')
