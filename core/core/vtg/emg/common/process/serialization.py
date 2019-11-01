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

from core.vtg.emg.common.process import Action, Choice, Concatenation, Parentheses, ProcessCollection
from core.vtg.emg.common.process import Receive, Dispatch, Subprocess, Block, Label, Process


class CollectionEncoder(json.JSONEncoder):

    def default(self, o):
        try:
            return super(CollectionEncoder, self).default(0)
        except TypeError:
            if isinstance(o, ProcessCollection):
                return self._serialize_collection(o)
            else:
                raise

    def _serialize_collection(self, collection):
        data = {
            "functions models": {str(p): self._export_process(p) for p in collection.models.values()},
            "environment processes": {str(p): self._export_process(p) for p in collection.environment.values()},
            "main process": self._export_process(collection.entry) if collection.entry else None
        }
        return data

    @staticmethod
    def _export_process(process):
        def convert_label(label):
            d = dict()
            if label.declaration:
                d['declaration'] = label.declaration.to_string(label.name, typedef='complex_and_params')
            if label.value:
                d['value'] = label.value

            return d

        def convert_action(action):
            d = dict()
            if action.comment:
                d['comment'] = action.comment
            if action.condition:
                d['condition'] = action.condition
            if action.trace_relevant:
                d['entry point'] = action.trace_relevant

            if isinstance(action, Subprocess):
                d['process'] = action.process
            elif isinstance(action, Dispatch) or isinstance(action, Receive):
                d['parameters'] = action.parameters

                if len(action.peers) > 0:
                    d['peers'] = list()
                    for p in action.peers:
                        d['peers'].append(str(p['process']))

                    # Remove duplicates
                    d['peers'] = list(set(d['peers']))
            elif isinstance(action, Block):
                if action.statements:
                    d["statements"] = action.statements
            return d

        data = {
            'category': process.category,
            'comment': process.comment,
            'process': CollectionEncoder._serialize_fsa(process.actions),
            'labels': {str(l): convert_label(l) for l in process.labels.values()},
            'actions': {str(a): convert_action(a) for a in process.actions.filter(include={Action})}
        }
        if len(process.headers) > 0:
            data['headers'] = list(process.headers)
        if len(process.declarations.keys()) > 0:
            data['declarations'] = process.declarations
        if len(process.definitions.keys()) > 0:
            data['definitions'] = process.definitions

        return data

    @staticmethod
    def _serialize_fsa(actions):
        def _serialize_action(action):
            if isinstance(action, Action):
                return repr(action)
            elif isinstance(action, Choice):
                return ' | '.join(_serialize_action(a) for a in action.actions)
            elif isinstance(action, Concatenation):
                return '.'.join(_serialize_action(a) for a in action.actions)
            elif isinstance(action, Parentheses):
                return '(%s)' % _serialize_action(action.action)
            else:
                raise NotImplementedError

        return _serialize_action(actions.initial_action)
