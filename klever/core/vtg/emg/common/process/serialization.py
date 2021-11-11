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

import copy
import json
import traceback
import sortedcontainers

from klever.core.vtg.emg.common.process.labels import Label
from klever.core.vtg.emg.common.c.types import import_declaration
from klever.core.vtg.emg.common.process.parser import parse_process
from klever.core.vtg.emg.common.process import Process, ProcessCollection, Peer
from klever.core.vtg.emg.common.process.actions import Action, Receive, Dispatch, Subprocess, Block, Savepoint, Signal,\
    Requirements, WeakRequirements


class CollectionEncoder(json.JSONEncoder):

    logger = None

    def default(self, o):
        if self.logger:
            # This is a helpful debug printing, turn it on when necessary
            self.logger.info(f"Test print: {str(o)}")
        if isinstance(o, ProcessCollection):
            return self._serialize_collection(o)
        elif isinstance(o, Process):
            return self._serialize_process(o)
        elif isinstance(o, Label):
            return self._serialize_label(o)
        elif isinstance(o, Action):
            return self._serialize_action(o)
        elif isinstance(o, Savepoint):
            return self._serialize_savepoint(o)
        elif isinstance(o, set):
            return list(o)
        elif isinstance(o, Peer):
            raise NotImplementedError
        elif isinstance(o, (list, dict, str, int, float, bool, type(None))):
            return o
        else:
            raise TypeError(f"Cannot serialize object '{str(o)}' of type '{type(o).__name__}'")

    def _serialize_collection(self, collection):
        data = {
            "name": str(collection.name),
            "functions models": {p.name: self.default(p) for p in collection.models.values()},
            "environment processes": {str(p): self.default(p) for p in collection.environment.values()},
            "main process": self.default(collection.entry) if collection.entry else None
        }
        return data

    def _serialize_label(self, label):
        dict_repr = sortedcontainers.SortedDict()
        if label.declaration:
            dict_repr['declaration'] = label.declaration.to_string(label.name, typedef='complex_and_params')
        if label.value:
            dict_repr['value'] = label.value
        return dict_repr

    def _serialize_savepoint(self, point):
        sp = sortedcontainers.SortedDict()
        sp.setdefault("statements", list())
        if point.statements:
            sp["statements"] = point.statements
        if point.comment:
            sp["comment"] = point.comment
        if point.requirements:
            sp['require'] = dict(point.requirements)
        if point.weak_requirements:
            sp['weak require'] = dict(point.weak_requirements)

        return sp

    def _serialize_action(self, action):
        ict_action = sortedcontainers.SortedDict()
        if action.comment:
            ict_action['comment'] = action.comment
        if action.condition:
            ict_action['condition'] = self.default(action.condition)
        if action.trace_relevant:
            ict_action['trace relevant'] = action.trace_relevant
        if action.savepoints:
            ict_action['savepoints'] = {
                str(point): self.default(point) for point in action.savepoints}
        if action.requirements:
            ict_action['require'] = dict(action.requirements)
        if action.weak_requirements:
            ict_action['weak require'] = dict(action.weak_requirements)
        if isinstance(action, Subprocess):
            if action.action:
                ict_action['process'] = repr(action.action)
            else:
                ict_action['process'] = ''
        elif isinstance(action, Signal) or isinstance(action, Receive):
            ict_action['parameters'] = self.default(list(action.parameters))
            if isinstance(action, Dispatch) and action.broadcast:
                ict_action['broadcast'] = True
            if isinstance(action, Receive) and not action.replicative:
                ict_action['replicative'] = False
        elif isinstance(action, Block):
            if action.statements:
                ict_action["statements"] = self.default(action.statements)
        return ict_action

    def _serialize_process(self, process):
        ict_action = sortedcontainers.SortedDict()
        ict_action['category']  = process.category
        ict_action['comment'] = process.comment
        ict_action['process'] = repr(process.actions.initial_action)
        ict_action['labels'] = {str(label): self.default(label) for label in process.labels.values()}
        ict_action['actions'] = {str(action): self.default(action) for action in process.actions.values()}
        ict_action['peers'] = {k: self.default(list(sorted(v))) for k, v in process.peers.items()}

        if len(process.headers) > 0:
            ict_action['headers'] = self.default(list(process.headers))
        if len(process.declarations.keys()) > 0:
            ict_action['declarations'] = self.default(process.declarations)
        if len(process.definitions.keys()) > 0:
            ict_action['definitions'] = self.default(process.definitions)

        return ict_action


class CollectionDecoder:
    """
    This class is intended for importing processes from json to fulfilled collection.
    """

    PROCESS_CONSTRUCTOR = Process
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
        'pre-call': 'pre_call',
        'post-call': 'post_call',
        'trace relevant': 'trace_relevant'
    }
    LABEL_CONSTRUCTOR = Label
    LABEL_ATTRIBUTES = {
        'value': None,
        'declaration': None
    }

    def __init__(self, logger, conf):
        self.logger = logger
        self.conf = conf

    def parse_event_specification(self, source, raw, collection):
        """
        Parse process descriptions and create corresponding objects to populate the collection.

        :param source: Source code collection.
        :param raw: Dictionary with content of JSON file.
        :param collection: ProcessCollection.
        :return: ProcessCollection
        """
        if 'name' in raw:
            assert isinstance(raw['name'], str)
            collection.name = raw['name']

        self.logger.info(f"Import processes from provided event categories specification '{collection.name}'")
        raise_exc = []
        if "functions models" in raw:
            self.logger.info("Import processes from 'kernel model', there are "
                             f"{len(raw['functions models'].keys())} of them")
            for name_list, process_desc in raw["functions models"].items():
                names = name_list.split(", ")
                for name in names:
                    # Set some default values
                    category = "functions models"
                    try:
                        process = self._import_process(source, name, category, process_desc)
                        collection.models[process.name] = process
                    except Exception as err:
                        self.logger.warning("Cannot parse {!r}: {}".format(name, str(err)))
                        raise_exc.append(name)
        else:
            self.logger.info("There is no 'functions models' description")
        if "environment processes" in raw:
            self.logger.info(f"Import processes from 'environment processes', there are "
                             f"{len(raw['environment processes'].keys())} of them")
            for name, process_desc in raw["environment processes"].items():
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
                except Exception:
                    self.logger.warning("Cannot parse {!r}: {}".format(name, traceback.format_exc()))
                    raise_exc.append(name)
        else:
            self.logger.info("There is no 'environment processes' description")

        if "main process" in raw and isinstance(raw["main process"], dict):
            self.logger.info("Import main process")
            try:
                entry_process = self._import_process(source, "entry", "main", raw["main process"])
                collection.entry = entry_process
            except Exception as err:
                self.logger.warning("Cannot parse the main process: {}".format(str(err)))
                raise_exc.append('entry')
        else:
            collection.entry = None

        if raise_exc:
            raise RuntimeError("Some specifications cannot be parsed, inspect log to find problems with: {}".
                               format(', '.join(raise_exc)))

        # Check savepoint's uniqueness
        if collection.entry and collection.entry.savepoints:
            raise ValueError('The entry process {!r} is not allowed to have savepoints'.format(str(collection.entry)))
        for model_process in collection.models.values():
            if model_process.savepoints:
                raise ValueError('The function model {!r} is not allowed to have savepoints'.format(str(model_process)))
        savepoints = set()
        for process in collection.environment.values():
            for action in process.actions.values():
                if action.savepoints:
                    sp = set(map(str, action.savepoints))
                    if sp.intersection(savepoints):
                        intr = ', '.join(sp.intersection(savepoints))
                        raise ValueError(f'Savepoints cannot be used twice: {intr}')
                    else:
                        savepoints.update(sp)

                    for savepoint in action.savepoints:
                        for name in savepoint.requirements.required_processes:
                            if name not in collection.environment:
                                raise ValueError(f"Savepoint '{str(savepoint)}' requires unknown process '{name}'")

                            required_actions = savepoint.requirements.required_actions(name)
                            for act in required_actions:
                                if act not in collection.environment[name].actions:
                                    raise ValueError(
                                        f"Savepoint '{str(savepoint)}' requires unknown action '{act}' of "
                                        f"process '{name}'")

                for name in action.requirements.relevant_processes:
                    if collection.entry and name == str(collection.entry):
                        required = collection.entry
                    elif name in collection.models.keys():
                        required = collection.models[name]
                    elif name in map(str, collection.environment.values()):
                        required = collection.environment[name]
                    else:
                        raise ValueError(f"There is no process '{name}' required by '{str(process)}' in"
                                         f" action '{str(action)}'")

                    for action_name in action.requirements.required_actions(name):
                        if action_name not in required.actions:
                            raise ValueError(f"Process '{str(process)}' in action '{str(action)}' requires action "
                                             f"'{action_name}' which is missing in process '{name}'")

        self.logger.debug(f'Imported function models: {", ".join(collection.models.keys())}')
        self.logger.debug(f'Imported environment processes: {", ".join(collection.environment.keys())}')

        return collection

    def _import_process(self, source, name, category, dic):
        # This helps to avoid changing the original specification
        dic = copy.deepcopy(dic)
        process = self.PROCESS_CONSTRUCTOR(name, category)

        for label_name in dic.get('labels', dict()):
            label = self._import_label(label_name, dic['labels'][label_name])
            process.labels[label_name] = label

        # Import process
        if 'process' in dic:
            parse_process(process, dic['process'])
        else:
            raise KeyError("Each process must have 'process' attribute, but {!r} misses it".format(name))

        # Then import subprocesses
        next_actions = sortedcontainers.SortedDict()
        for name, desc in dic.get('actions', dict()).items():
            subp = desc.get('process')
            if subp:
                next_action = parse_process(process, subp)
                next_actions[name] = next_action

        # Import comments
        if 'comment' in dic and isinstance(dic['comment'], str):
            process.comment = dic['comment']
        else:
            raise KeyError(
                "You must specify manually 'comment' attribute within the description of {!r} kernel "
                "function model process".format(name))

        # Import actions
        for some_name, description in dic.get('actions', {}).items():
            names = some_name.split(", ")
            for act_name in names:
                if act_name not in (x.name for x in process.actions.final_actions):
                    raise ValueError(f"Action '{act_name}' was not used in '{str(process)}' process")
                self._import_action(process, act_name, description)

        # Connect actions
        for name in next_actions:
            process.actions[name].action = next_actions[name]

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
                dic_copy = dict(dic[att])
                for def_file in dic[att]:
                    dic_copy[source.find_file(def_file)] = dic_copy.pop(def_file)
                # Update object to be sure that changes are saved there
                setattr(process, att, dic_copy)

        # Check unused recursive subprocesses
        reachable_actions = process.actions.used_actions(enter_subprocesses=True)
        unrechable_actions = {a.name for a in process.actions.final_actions}.difference(reachable_actions)
        if unrechable_actions:
            raise RuntimeError("Process {!r} has unreachable actions: {}".\
                               format(str(process), ', '.join(sorted(unrechable_actions))))

        unused_labels = {str(label) for label in process.unused_labels}
        if unused_labels:
            raise RuntimeError("Found unused labels in process {!r}: {}".format(str(process), ', '.join(unused_labels)))
        if process.file != 'entry point':
            process.file = source.find_file(process.file)
        if not process.actions.initial_action:
            raise RuntimeError('Process {!r} has no initial action'.format(str(process)))

        intrs = set(process.actions.keys()).intersection(process.actions.savepoints)
        assert not intrs, "Process must not have savepoints with the same names as actions, but there is an" \
                          " intersection: %s" % ', '.join(intrs)

        process.accesses()
        return process

    def _import_action(self, process, name, dic):
        act = process.actions.behaviour(name).pop().kind(name)
        process.actions[name] = act

        for att in (att for att in self.ACTION_ATTRIBUTES if att in dic):
            if self.ACTION_ATTRIBUTES[att]:
                attname = self.ACTION_ATTRIBUTES[att]
            else:
                attname = att
            setattr(act, attname, dic[att])

        if 'savepoints' in dic:
            for sp_name, sp_dic in dic['savepoints'].items():
                savepoint = Savepoint(sp_name, str(process), sp_dic.get('statements', []), sp_dic.get('comment'))

                # Add requirements
                if 'require' in sp_dic:
                    try:
                        savepoint._require = Requirements.from_dict(sp_dic['require'])
                    except (ValueError, AssertionError) as err:
                        raise ValueError(f"Cannot parse requirements of savepoint '{sp_name}': {str(err)}")

                if 'weak require' in sp_dic:
                    try:
                        savepoint._weak_require = WeakRequirements.from_dict(sp_dic['weak require'])
                    except (ValueError, AssertionError) as err:
                        raise ValueError(f"Cannot parse weak requirements of savepoint '{sp_name}': {str(err)}")

                act.savepoints.add(savepoint)

        if 'require' in dic:
            try:
                act._require = Requirements.from_dict(dic['require'])
            except (ValueError, AssertionError) as err:
                raise ValueError(f"Cannot parse requirements of '{name}' in '{str(process)}': {str(err)}")

        if 'weak require' in dic:
            try:
                act._weak_require = WeakRequirements.from_dict(dic['weak require'])
            except (ValueError, AssertionError) as err:
                raise ValueError(f"Cannot parse weak requirements of '{name}' in '{str(process)}': {str(err)}")

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
