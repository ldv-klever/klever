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
import os
import json

from core.vtg.emg.common.c.types import import_declaration
from core.vtg.emg.common.process.parser import parse_process
from core.vtg.emg.common.process import Receive, Dispatch, Subprocess, Block, Label, Process


from core.vtg.emg.common.process import Action, Choice, Concatenation, Parentheses, ProcessCollection
from core.vtg.emg.common.process import Receive, Dispatch, Subprocess, Block


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


class CollectionDecoder:
    """
    This class is intended for importing processes from json to fulfilled collection.
    """

    PROCESS_CONSTRUCTOR = Process
    LABEL_CONSTRUCTOR = Label
    PROCESS_ATTRIBUTES = {
        'source files': 'cfiles'
    }
    ACTION_ATTRIBUTES = {
        'pre-call': 'pre_call',
        'post-call': 'post_call',
        'entry point': 'trace_relevant'
    }

    def __init__(self, logger, conf):
        self.logger = logger
        self.conf = conf

    def parse_event_specification(self, Source, raw):
        """
        Parse process descriptions and create corresponding objects to populate the collection.

        :param Source: Source code coollection.
        :param raw: Dictionary with content of JSON file.
        :return: ProcessCollection
        """
        env_processes = dict()
        models = dict()

        self.logger.info("Import processes from provided event categories specification")
        if "functions models" in raw:
            self.logger.info("Import processes from 'kernel model'")
            for name_list, process_desc in raw["functions models"].items():
                names = name_list.split(", ")
                for name in names:
                    self.logger.debug("Import process which models {!r}".format(name))
                    models[name] = self._import_process(name, process_desc)

                    # Set some default values
                    if not models[name]._category:
                        models[name]._category = "functions models"
                    if models[name]._category != "functions models":
                        raise ValueError("Each function model specification should has category 'functions models' but "
                                         "process {!r} has name {!r}".format(str(models[name]), models[name]._category))
                    models[short_name].pretty_id = "functions models/{}".format(short_name)
        if "environment processes" in raw:
            self.logger.info("Import processes from 'environment processes'")
            for name, process_desc in raw["environment processes"].items():
                self.logger.debug("Import environment process {!r}".format(name))

                category, pname = get_short_name(name, process_desc)
                process = self._import_process(pname, process_desc)
                if not process._category:
                    process._category = category
                if pname in env_processes:
                    raise ValueError("There is already imported process {!r} with identifier {!r} in intermediate "
                                     "environment model with name {!r} and category {!r} and identifier {!r}".
                                     format(pname, process.identifier, env_processes[pname]._name,
                                            env_processes[pname]._category, env_processes[pname].identifier))
                env_processes[pname] = process
                process.pretty_id = "{}/{}".format(process._category, process._name)
        if "main process" in raw and isinstance(raw["main process"], dict):
            self.logger.info("Import main process")
            entry_process = self._import_process("entry", raw["main process"])
            if not entry_process._category:
                entry_process._category = 'entry process'
            if not entry_process.pretty_id:
                entry_process.pretty_id = "{}/entry".format(entry_process._category)
        else:
            entry_process = None

        self.models = models
        self.environment = env_processes
        self.entry = entry_process



    def establish_peers(self, strict=False):
        """
        Get processes and guarantee that all peers are correctly set for both receivers and dispatchers. The function
        replaces dispatches expressed by strings to object references as it is expected in translation.

        :param strict: Raise exception if a peer process identifier is unknown (True) or just ignore it (False).
        :return: None
        """
        # Then check peers. This is because in generated processes there no peers set for manually written processes
        processes = list(self.models.values()) + list(self.environment.values()) + ([self.entry] if self.entry else [])
        process_map = {p.pretty_id: p for p in processes}
        for process in processes:
            for action in [process.actions[a] for a in process.actions
                           if isinstance(process.actions[a], Receive) or isinstance(process.actions[a], Dispatch) and
                           len(process.actions[a].peers) > 0]:
                new_peers = []
                for peer in action.peers:
                    if isinstance(peer, str):
                        if peer in process_map:
                            target = process_map[peer]
                            new_peer = {'process': target, 'subprocess': target.actions[action.name]}
                            new_peers.append(new_peer)

                            opposite_peers = [p['process'].pretty_id if isinstance(p, dict) else p
                                              for p in target.actions[action.name].peers]
                            if process.pretty_id not in opposite_peers:
                                target.actions[action.name].peers.append({'process': process, 'subprocess': action})
                        elif strict:
                            raise KeyError("Process {!r} tries to send a signal {!r} to {!r} but there is no such "
                                           "process in the model".format(process.pretty_id, action.name, peer))
                    else:
                        new_peers.append(peer)

                action.peers = new_peers

            # Set names
            tokens = process.pretty_id.split('/', maxsplit=1)
            if len(tokens) < 2:
                raise ValueError('Cannot extract category/name prefix from process identifier {!r}'.
                                 format(process.pretty_id))
            else:
                process.category = tokens[0]
                process.name = tokens[1]



    def _import_process(self, name, dic):
        process = self.PROCESS_CONSTRUCTOR(name)

        def get_abspath(path):
            if path == 'environment model' or os.path.isfile(path):
                return path
            for spath in self.conf["working source trees"]:
                abspath = os.path.join(spath, path)
                storabspath = self._clade.get_storage_path(abspath)
                if os.path.isfile(storabspath):
                    return abspath
            else:
                raise FileNotFoundError('There is no file {!r} in the build base or the correct path to source files'
                                        ' is not provided'.format(path))

        if 'labels' in dic:
            for label_name in dic['labels']:
                label = self._import_label(label_name, dic['labels'][label_name])
                process.labels[label_name] = label

        # Import process
        if 'process' in dic:
            process.process = parse_process(process, dic['process'])
        else:
            raise KeyError("Each process must have 'process' attribute, but {!r} misses it".format(name))

        # Import comments
        if 'comment' in dic:
            process.comment = dic['comment']
        else:
            raise KeyError(
                "You must specify manually 'comment' attribute within the description of {!r} kernel "
                "function model process".format(name))

        # Import subprocesses
        if 'actions' in dic:
            for action_name in dic['actions']:
                action = self._import_action(process, action_name, dic['actions'][action_name])
                process.actions[action_name] = action

                if 'process' in dic['actions'][action_name]:
                    parse_process(process, dic['actions'][action_name]['process'])

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
                    dic[att][get_abspath(def_file)] = dic[att].pop(def_file)
                # Update object to be sure that changes are saved there
                setattr(process, att, dic[att])

        unused_labels = process.unused_labels
        if len(unused_labels) > 0:
            raise RuntimeError("Found unused labels in process {!r}: {}".
                               format(process._name, ', '.join(unused_labels)))
        if process.file != 'entry point':
            process.file = get_abspath(process.file)

        process.accesses()
        return process

    def _import_action(self, process, name, dic):
        act = process.actions.get(name)
        if not act:
            raise KeyError('Action %s is not used in process %s' % (name, process))

        for att in self.ACTION_ATTRIBUTES:
            if att in dic:
                if self.ACTION_ATTRIBUTES[att]:
                    attname = self.ACTION_ATTRIBUTES[att]
                else:
                    attname = att
                setattr(act, attname, dic[att])
        return act

    def _import_label(self, name, dic):
        label = self.LABEL_CONSTRUCTOR(name)

        for att in self.LABEL_ATTRIBUTES:
            if att in dic:
                if self.LABEL_ATTRIBUTES[att]:
                    attname = self.LABEL_ATTRIBUTES[att]
                else:
                    attname = att
                setattr(label, attname, dic[att])

        if label.declaration:
            label.declaration = import_declaration(label.declaration)

        return label
