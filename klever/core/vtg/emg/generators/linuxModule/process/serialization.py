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

from klever.core.vtg.emg.common.process import Receive, Dispatch
from klever.core.vtg.emg.common.process.serialization import CollectionDecoder
from klever.core.vtg.emg.generators.linuxModule.process import ExtendedProcess, ExtendedLabel, Call, CallRetval


class ExtendedProcessDecoder(CollectionDecoder):

    PROCESS_CONSTRUCTOR = ExtendedProcess
    PROCESS_ATTRIBUTES = {
        'headers': None,
        'declarations': None,
        'definitions': None,
        'source files': 'cfiles',
        'peers': None
    }
    ACTION_ATTRIBUTES = {
        'comment': None,
        'parameters': None,
        'condition': None,
        'statements': None,
        'peers': None,
        'pre-call': 'pre_call',
        'post-call': 'post_call',
        'callback': None,
        'callback return value': 'retlabel',
        'trace relevant': 'trace_relevant'
    }
    LABEL_CONSTRUCTOR = ExtendedLabel
    LABEL_ATTRIBUTES = {
        'match only implemented interfaces': 'match_implemented',
        'value': None,
        'declaration': None,
        'container': None,
        'resource': None,
        'callback': None,
        'parameter': None,
        'pointer': None,
        'retval': None
    }

    def __init__(self, logger, conf):
        super().__init__(logger, conf)
        self.conf.setdefault("callback comment", 'Invoke callback {0!r} from {1!r}.')

    def _import_action(self, process, name, dic):
        super()._import_action(process, name, dic)
        act = process.actions[name]
        if 'callback' in dic:
            if isinstance(act, Dispatch) and 'callback' in dic:
                new = Call(name)
            elif isinstance(act, Receive):
                new = CallRetval(name)
            else:
                new = None

            if new:
                new.__dict__.update(act.__dict__)
                process.actions[str(new)] = new

    def _import_label(self, name, dic):
        label = super()._import_label(name, dic)

        if 'interface' in dic:
            if not (dic.get('resource') or dic.get('container') or dic.get('callback') or dic.get('parameter')):
                self.logger.warning(f'Specify kind of an interface (container, resource, callback or parameter) for'
                                    f' label {name}')

            if isinstance(dic['interface'], str):
                label.set_declaration(dic['interface'], None)
            elif isinstance(dic['interface'], list):
                for string in dic['interface']:
                    label.set_declaration(string, None)
            else:
                raise TypeError('Expect list or string with interface identifier')

        return label

    def _import_process(self, source, name, category, dic):
        process = super()._import_process(source, name, category, dic)

        # Now we need to extract category from labels
        if not process.category:
            labels = filter(lambda x: x.interfaces, process.labels.values())
            popular = {}
            for interface in (i for l in labels for i in l.interfaces):
                category, _ = interface.split('.')
                popular.setdefault(category, 0)
                popular[category] += 1

            popular = list(reversed(sorted(popular.keys(), key=lambda x: popular[x])))
            if not popular:
                self.logger.warning(f'Cannot determine category of the process {process.name}')
                process.category = 'undefined'
            else:
                process.category = popular[0]
        return process
