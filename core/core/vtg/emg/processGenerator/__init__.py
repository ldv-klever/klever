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
import importlib
from core.vtg.emg.common import get_necessary_conf_property


def generate_processes(emg, source):
    # In a specific order start proess generators
    generator_names = ('.vtg.emg.processGenerator.{}'.format(e) for e in
                       [list(e.keys())[0] for e in get_necessary_conf_property(emg.conf, "intermediate model options")])
    configurations = [list(e.values())[0] for e in get_necessary_conf_property(emg.conf, "intermediate model options")]
    generators = (importlib.import_module(name, 'core') for name in generator_names)

    processes_triple = [], [], None
    for index, generator in enumerate(generators):
        processes_triple = generator.generate_processes(emg, source, processes_triple, configurations[index])
    return processes_triple
