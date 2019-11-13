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

from core.vtg.emg.common.c.types import import_declaration
from core.vtg.emg.common.process.parser import parse_process
from core.vtg.emg.common.process import Receive, Dispatch, Subprocess, Block, Label, Process, Action, Choice, \
    Concatenation, Parentheses, ProcessCollection


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
            "functions models": {p.name: self._export_process(p) for p in collection.models.values()},
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
                d['process'] = CollectionEncoder._serialize_fsa(action.action)
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
            'process': CollectionEncoder._serialize_fsa(process.actions.initial_action),
            'labels': {str(l): convert_label(l) for l in process.labels.values()},
            'actions': {str(a): convert_action(a) for a in
                        process.actions.filter(include={Action}, exclude={Subprocess})}
        }
        data['actions'].update({a.reference_name: convert_action(a)
                                for a in process.actions.filter(include={Subprocess})})

        if len(process.headers) > 0:
            data['headers'] = list(process.headers)
        if len(process.declarations.keys()) > 0:
            data['declarations'] = process.declarations
        if len(process.definitions.keys()) > 0:
            data['definitions'] = process.definitions

        return data

    @staticmethod
    def _serialize_fsa(initial):
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

        return _serialize_action(initial)


class CollectionDecoder:
    """
    This class is intended for importing processes from json to fulfilled collection.
    """

    PROCESS_CONSTRUCTOR = Process
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
        'entry point': 'trace_relevant'
    }
    LABEL_CONSTRUCTOR = Label
    LABEL_ATTRIBUTES = {
        'value': None,
        'declaration': None
    }

    def __init__(self, logger, conf):
        self.logger = logger
        self.conf = conf

    def parse_event_specification(self, source, raw):
        """
        Parse process descriptions and create corresponding objects to populate the collection.

        :param source: Source code collection.
        :param raw: Dictionary with content of JSON file.
        :return: ProcessCollection
        """
        collection = ProcessCollection()

        self.logger.info("Import processes from provided event categories specification")
        raise_exc = []
        if "functions models" in raw:
            self.logger.info("Import processes from 'kernel model'")
            for name_list, process_desc in raw["functions models"].items():
                names = name_list.split(", ")
                for name in names:
                    self.logger.debug("Import process which models {!r}".format(name))

                    # Set some default values
                    category = "functions models"
                    try:
                        process = self._import_process(source, name, category, process_desc)
                        collection.models[str(process)] = process
                    except Exception as err:
                        self.logger.warning("Cannot parse {!r}: {}".format(name, str(err)))
                        raise_exc.append(name)
        if "environment processes" in raw:
            self.logger.info("Import processes from 'environment processes'")
            for name, process_desc in raw["environment processes"].items():
                self.logger.debug("Import environment process {!r}".format(name))

                # This simplifies parsing of event specifications for Linux but actually this can be avoided by adding
                # categories to corresponding specifications.
                if '/' in name:
                    category, name = name.split('/')
                else:
                    category = None

                try:
                    process = self._import_process(source, name, category, process_desc)
                    if process in collection.environment:
                        raise ValueError("There is an already imported process {!r} in intermediate environment model".
                                         format(str(process)))
                    collection.environment[str(process)] = process
                except Exception as err:
                    self.logger.warning("Cannot parse {!r}: {}".format(name, str(err)))
                    raise_exc.append(name)

        if "main process" in raw and isinstance(raw["main process"], dict):
            self.logger.info("Import main process")
            try:
                entry_process = self._import_process(source, "entry", "entry process", raw["main process"])
                collection.entry = entry_process
            except Exception as err:
                self.logger.warning("Cannot main process: {}".format(str(err)))
                raise_exc.append('entry')
        else:
            collection.entry = None

        if raise_exc:
            raise RuntimeError("Some specifications cannot be parsed, inspect log to find problems with: {}".
                               format(', '.join(raise_exc)))

        return collection

    def _import_process(self, source, name, category, dic):
        process = self.PROCESS_CONSTRUCTOR(name, category)

        for label_name in dic.get('labels', {}):
            label = self._import_label(label_name, dic['labels'][label_name])
            process.labels[label_name] = label

        # Import process
        if 'process' in dic:
            parse_process(process, dic['process'])
        else:
            raise KeyError("Each process must have 'process' attribute, but {!r} misses it".format(name))

        # Then import subprocesses
        next_actions = {}
        for name, desc in dic.get('actions', {}).items():
            subp = desc.get('process')
            if subp:
                next_action = parse_process(process, subp)
                next_actions[name] = next_action

        # Connect actions
        for action in process.actions.filter(include={Subprocess}):
            action.action = next_actions[action.reference_name]

        # Import comments
        if 'comment' in dic:
            process.comment = dic['comment']
        else:
            raise KeyError(
                "You must specify manually 'comment' attribute within the description of {!r} kernel "
                "function model process".format(name))

        # Import actiones
        for act_name in dic.get('actions', {}):
            if not process.actions.get(act_name):
                if dic['actions'][act_name].get('process'):
                    for act in (a for a in process.actions.filter(include={Subprocess}) if a.reference_name == act_name):
                        self._import_action(process, act, dic['actions'][act_name])
                else:
                    raise ValueError('Action {!r} was not used in {!r} process'.format(act_name, str(process)))
            else:
                self._import_action(process, process.actions[act_name], dic['actions'][act_name])

        for att in self.PROCESS_ATTRIBUTES:
            if att in dic:
                if self.PROCESS_ATTRIBUTES[att]:
                    attname = self.PROCESS_ATTRIBUTES[att]
                else:
                    attname = att
                setattr(process, attname, dic[att])

        # Fix paths in manual specification
        for att in ('definitions', 'declarations'):
            # Avoid iterating over the dictionary that can change its content
            if att in dic:
                for def_file in dic[att].keys():
                    dic[att][source.find_file(def_file)] = dic[att].pop(def_file)
                # Update object to be sure that changes are saved there
                setattr(process, att, dic[att])

        unused_labels = {str(l) for l in process.unused_labels}
        if unused_labels:
            raise RuntimeError("Found unused labels in process {!r}: {}".format(str(process), ', '.join(unused_labels)))
        if process.file != 'entry point':
            process.file = source.find_file(process.file)
        if not process.actions.initial_action:
            raise RuntimeError('Process {!r} has no initial action'.format(str(process)))

        process.accesses()
        return process

    def _import_action(self, process, act, dic):
        for att in (att for att in self.ACTION_ATTRIBUTES if att in dic):
            if self.ACTION_ATTRIBUTES[att]:
                attname = self.ACTION_ATTRIBUTES[att]
            else:
                attname = att
            setattr(act, attname, dic[att])

    def _import_label(self, name, dic):
        label = self.LABEL_CONSTRUCTOR(name)

        for att in (att for att in self.LABEL_ATTRIBUTES if att in dic):
            if self.LABEL_ATTRIBUTES[att]:
                attname = self.LABEL_ATTRIBUTES[att]
            else:
                attname = att
            setattr(label, attname, dic[att])

        if label.declaration:
            label.declaration = import_declaration(label.declaration)

        return label
