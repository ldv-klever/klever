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

from core.vtg.emg.common.c.types import import_declaration
from core.vtg.emg.common.process import Receive, Dispatch, Subprocess, Condition, generate_regex_set, Label, Process


class ProcessCollection:
    """
    This class represents collection of processes for an environment model generation. Also it contains methods to
    import or export processes in the JSON format. The collection contains function models processes, generic
    environment model processes that acts as soon as they receives replicative signals and a main process.

    """

    PROCESS_CONSTRUCTOR = Process
    LABEL_CONSTRUCTOR = Label
    REGEX_SET = generate_regex_set
    LABEL_ATTRIBUTES = {
        'value': None,
        'declaration': None
    }
    PROCESS_ATTRIBUTES = {
        'headers': None,
        'declarations': None,
        'definitions': None,
        'category': None,
        'identifier': 'pretty_id'
    }
    ACTION_ATTRIBUTES = {
        'comment': None,
        'parameters': None,
        'condition': None,
        'statements': None,
        'process': None,
        'peers': None,
        'pre-call': 'pre_call',
        'post-call': 'post_call',
    }

    def __init__(self, logger, conf):
        self.logger = logger
        self.conf = conf
        self.entry = None
        self.models = dict()
        self.environment = dict()

    def parse_event_specification(self, raw):
        """
        Parse process descriptions and create corresponding objects to populate the collection.

        :param raw: Dictionary with content of JSON file.
        :return: None
        """
        env_processes = dict()
        models = dict()

        self.logger.info("Import processes from provided event categories specification")
        if "functions models" in raw:
            self.logger.info("Import processes from 'kernel model'")
            for name_list in raw["functions models"]:
                names = name_list.split(", ")
                for name in names:
                    self.logger.debug("Import process which models {!r}".format(name))
                    models[name] = self._import_process(name, raw["functions models"][name_list])
        if "environment processes" in raw:
            self.logger.info("Import processes from 'environment processes'")
            for name in raw["environment processes"]:
                self.logger.debug("Import environment process {}".format(name))
                process = self._import_process(name, raw["environment processes"][name])
                env_processes[name] = process
        if "main process" in raw and isinstance(raw["main process"], dict):
            self.logger.info("Import main process")
            entry_process = self._import_process("entry", raw["main process"])
        else:
            entry_process = None

        self.models = models
        self.environment = env_processes
        self.entry = entry_process

    def save_collection(self, filename=None):
        """
        Export the collection to the file.

        :param filename: File to save process descriptions in the JSON format.
        :return: Return a dictionary that can easily be saved as a JSON file.
        """
        data = dict()
        data["functions models"] = {p.pretty_id: self._export_process(p) for p in self.models.values()}
        data["environment processes"] = {p.pretty_id: self._export_process(p) for p in self.environment.values()}
        data["main process"] = None if not self.entry else self._export_process(self.entry)
        if filename:
            with open(filename, "w", encoding="utf8") as fh:
                fh.writelines(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=4))
        return data

    def establish_peers(self, strict=False):
        """
        Get processes and guarantee that all peers are correctly set for both receivers and dispatchers. The function
        replaces dispatches expressed by strings to object references as it is expected in translators.

        :param strict: Raise exception if a peer process identifier is unknown (True) or just ignore it (False).
        :return: None
        """
        # Then check peers. This is becouse in generated processes there no peers set for manually written processes
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
            tokens = process.pretty_id.split('/')
            if len(tokens) < 2:
                raise ValueError('Cannot extract category/name/ prefix from process identifier {!r}'.
                                 format(process.pretty_id))
            else:
                process.category = tokens[0]
                process.name = tokens[1]

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

            if isinstance(action, Subprocess):
                d['process'] = action.process
            elif isinstance(action, Dispatch) or isinstance(action, Receive):
                d['parameters'] = action.parameters

                if len(action.peers) > 0:
                    d['peers'] = list()
                    for p in action.peers:
                        d['peers'].append(p['process'].pretty_id)
                        if not p['process'].pretty_id:
                            raise ValueError('Any peer must have an external identifier')
                    # Remove dublicates
                    d['peers'] = list(set(d['peers']))

                if isinstance(action, Dispatch) and action.broadcast:
                    d['broadcast'] = action.broadcast
                elif isinstance(action, Receive) and action.replicative:
                    d['replicative'] = action.replicative
            elif isinstance(action, Condition):
                if action.statements:
                    d["statements"] = action.statements

            return d

        data = {
            'identifier': process.pretty_id,
            'category': process.category,
            'comment': process.comment,
            'process': process.process,
            'labels': {l.name: convert_label(l) for l in process.labels.values()},
            'actions': {a.name: convert_action(a) for a in process.actions.values()}
        }
        if len(process.headers) > 0:
            data['headers'] = list(process.headers)
        if len(process.declarations.keys()) > 0:
            data['declarations'] = process.declarations
        if len(process.definitions.keys()) > 0:
            data['definitions'] = process.definitions

        return data

    def _import_process(self, name, dic):
        process = self.PROCESS_CONSTRUCTOR(name)

        if 'labels' in dic:
            for label_name in dic['labels']:
                label = self._import_label(label_name, dic['labels'][label_name])
                process.labels[label_name] = label

        # Import process
        process_strings = []
        if 'process' in dic:
            process.process = dic['process']
            process_strings.append(dic['process'])
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
            process_strings.extend([dic['actions'][n]['process'] for n in dic['actions']
                                    if 'process' in dic['actions'][n]])

            for action_name in dic['actions']:
                action = self._import_action(action_name, process_strings, dic['actions'][action_name])
                process.actions[action_name] = action

                if 'process' in dic['actions'][action_name]:
                    process_strings.append(dic['actions'][action_name]['process'])

        for att in self.PROCESS_ATTRIBUTES:
            if att in dic:
                if self.PROCESS_ATTRIBUTES[att]:
                    attname = self.PROCESS_ATTRIBUTES[att]
                else:
                    attname = att
                setattr(process, attname, dic[att])

        unused_labels = process.unused_labels
        if len(unused_labels) > 0:
            raise RuntimeError("Found unused labels in process {!r}: {}".
                               format(process.name, ', '.join(unused_labels)))
        process.accesses()
        return process

    def _import_action(self, name, process_strings, dic):
        act = None
        for regex in self.REGEX_SET(name):
            for string in process_strings:
                if regex['regex'].search(string):
                    act = self._action_checker(string, regex, name, dic)
                    break
        if not act:
            raise ValueError("Action '{!r}' is not used in process description {!r}".format(name, name))

        # Add comment if it is provided
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

    @staticmethod
    def _action_checker(proces_string, regex, name, dic):
        process_type = regex['type']
        act = process_type(name)
        if process_type is Receive:
            if '!' in regex['regex'].search(proces_string).group(0):
                act.replicative = True
        elif process_type is Dispatch:
            if '@' in regex['regex'].search(proces_string).group(0):
                act.broadcast = True
        return act
