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

from core.vtg.emg.common import get_necessary_conf_property, check_or_set_conf_property
from core.vtg.emg.common.process import Receive, Dispatch, generate_regex_set
from core.vtg.emg.common.process.collection import ProcessCollection
from core.vtg.emg.processGenerator.linuxModule.process import AbstractProcess, AbstractLabel, Call, CallRetval


class AbstractProcessImporter(ProcessCollection):
    PROCESS_CONSTRUCTOR = AbstractProcess
    LABEL_CONSTRUCTOR = AbstractLabel
    REGEX_SET = generate_regex_set
    LABEL_ATTRIBUTES = {
        'container': None,
        'resource': None,
        'callback': None,
        'parameter': None,
        'pointer': None,
        'retval': None,
        'value': None,
        'declaration': None
    }
    PROCESS_ATTRIBUTES = {
        'headers': None,
        'declarations': None,
        'definitions': None,
    }
    ACTION_ATTRIBUTES = {
        'comment': None,
        'parameters': None,
        'condition': None,
        'statements': None,
        'process': None,
        'pre-call': 'pre_call',
        'post-call': 'post_call',
        'callback': None,
        'callback return value': 'retlabel'

    }

    def __init__(self, logger, conf):
        super(AbstractProcessImporter, self).__init__(logger, conf)
        check_or_set_conf_property(self.conf, "callback comment", default_value='Invoke callback {0!r} from {1!r}.',
                                   expected_type=str)

    def _import_process(self, name, dic):
        process = super(AbstractProcessImporter, self)._import_process(name, dic)

        unused_labels = process.unused_labels
        if len(unused_labels) > 0:
            raise RuntimeError("Found unused labels in process {!r}: {}".
                               format(process.name, ', '.join(unused_labels)))
        return process

    def _import_action(self, name, process_strings, dic):
        act = super(AbstractProcessImporter, self)._import_action(name, process_strings, dic)

        # Add comment if it is provided
        if 'comment' in dic:
            act.comment = dic['comment']
        elif not isinstance(act, Call):
            comments_by_type = get_necessary_conf_property(self.conf, 'action comments')
            tag = type(act).__name__.lower()
            if tag not in comments_by_type or \
                    not (isinstance(comments_by_type[tag], str) or
                         (isinstance(comments_by_type[tag], dict) and name in comments_by_type[tag])):
                raise KeyError(
                    "Cannot find comment for action {!r} of type {!r} at process {!r} description. You shoud either "
                    "specify in the corresponding environment model specification the comment text manually or set "
                    "the default comment text for all actions of the type {!r} at EMG plugin configuration properties "
                    "within 'action comments' attribute.".
                    format(name, tag, name, tag))
        return act

    def _import_label(self, name, dic):
        label = super(AbstractProcessImporter, self)._import_label(name, dic)

        if 'interface' in dic:
            if isinstance(dic['interface'], str):
                label.set_declaration(dic['interface'], None)
            elif isinstance(dic['interface'], list):
                for string in dic['interface']:
                    label.set_declaration(string, None)
            else:
                TypeError('Expect list or string with interface identifier')

        return label

    @staticmethod
    def _action_checker(proces_string, regex, name, dic):
        process_type = regex['type']
        if process_type is Dispatch and 'callback' in dic:
            act = Call(name)
        elif process_type is Receive and 'callback' in dic:
            act = CallRetval(name)
        elif process_type is Receive:
            act = process_type(name)
            if '!' in regex['regex'].search(proces_string).group(0):
                act.replicative = True
        elif process_type is Dispatch:
            act = process_type(name)
            if '@' in regex['regex'].search(proces_string).group(0):
                act.broadcast = True
        else:
            act = process_type(name)
        return act

    def establish_peers(self, strict=None):
        """There is no need in this method."""
        raise NotImplementedError("You cannot establish peers of abstract processes")
