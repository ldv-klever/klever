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

from core.vtg.emg.common.process import Receive, Dispatch
from core.vtg.emg.common.process.serialization import CollectionDecoder
from core.vtg.emg.generators.linuxModule.process import ExtendedProcess, ExtendedLabel, Call, CallRetval


class ExtendedProcessDecoder(CollectionDecoder):

    PROCESS_CONSTRUCTOR = ExtendedProcess
    PROCESS_ATTRIBUTES = {
        'headers': None,
        'declarations': None,
        'definitions': None,
        'source files': 'cfiles'
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
        'entry point': 'trace_relevant'
    }
    LABEL_CONSTRUCTOR = ExtendedLabel
    LABEL_ATTRIBUTES = {
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

    def _import_action(self, process, act, dic):
        if 'callback' in dic:
            if isinstance(act, Dispatch) and 'callback' in dic:
                new = Call(act.name)
            elif isinstance(act, Receive):
                new = CallRetval(act.name)
            else:
                new = None

            if new:
                process.replace_action(act, new)
                del process.actions[str(act)]
                process.actions[str(new)] = new
                act = new
        super()._import_action(process, act, dic)

    def _import_label(self, name, dic):
        label = super()._import_label(name, dic)

        if 'interface' in dic:
            if isinstance(dic['interface'], str):
                label.set_declaration(dic['interface'], None)
            elif isinstance(dic['interface'], list):
                for string in dic['interface']:
                    label.set_declaration(string, None)
            else:
                TypeError('Expect list or string with interface identifier')

        return label
