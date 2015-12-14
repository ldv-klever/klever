import re
import copy

from psi.avtg.emg.interfaces import *


class EventModel:

    def __init__(self, logger, analysis, raw):
        self.logger = logger
        self.analysis = analysis
        self.model = {
            "models": {},
            "processes": []
        }
        self.events = {
            "kernel model": {},
            "environment processes": {}
        }

        for collection in self.events:
            # Import kernel models
            self.logger.info("Import {}".format(collection))
            self.__import_processes(raw, collection)

        # Import necessary kernel models
        self.logger.info("Add all relevant function models to an environment model")
        self.__import_kernel_models()

        # Complete model
        self.logger.info("Add rest processes for each interface category an its callbacks")
        self.__complete_model()

    def __import_processes(self, raw, category):
        if "kernel model" in raw:
            for name_list in raw[category]:
                names = name_list.split(", ")
                for name in names:
                    process = Process(name, raw[category][name_list])
                    self.events[category][name] = process

    def __import_kernel_models(self):
        for function in self.events["kernel model"]:
            if function in self.analysis.kernel_functions:
                self.logger.debug("Add model of '{}' to an environment model".format(function))
                self.model["models"][function] = copy.deepcopy(self.events["kernel model"][function])

                for label in self.model["models"][function].labels:
                    if self.model["models"][function].labels[label].parameter and \
                            not self.model["models"][function].labels[label].signature:
                        for parameter in self.analysis.kernel_functions[function]["signature"].parameters:
                            if parameter.interface and self.model["models"][function].labels[label].interface == \
                                    parameter.interface.full_identifier:
                                self.model["models"][function].labels[label].signature = parameter
                        if not self.model["models"][function].labels[label].signature:
                            raise ValueError("Cannot find suitable signature for label '{}' at function model '{}'".
                                             format(label, function))

        self.logger.info("Add references to given label interfaces in environment processes")
        for process in [self.events["environment processes"][name] for name in self.events["environment processes"]]:
            matched = 0
            category = None
            for label in process.labels:
                if self.events["environment processes"][process.name].labels[label].interface:
                    intf = self.events["environment processes"][process.name].labels[label].interface
                    if intf in self.analysis.interfaces:
                        matched += 1
                        category = self.analysis.interfaces[intf].category
                        self.events["environment processes"][process.name].labels[label].signature = \
                            self.analysis.interfaces[intf].signature

            # If at least one interface is matched add this process
            if matched:
                self.logger.debug("Add process '{}' to an environment model".format(process))
                self.add_process(process, category)

    def __complete_model(self):
        success = True
        self.__normalize_model()
        while success:
            success = False
            # Do until processes can be added to the model
            for category in self.analysis.categories:
                # Add processes matching input and output signals
                success = self.__populate_model(category) or success

                # Add processes matching them by labels
                success = self.__try_match_more_labels(category) or success

            # Add environmental processes which need peered
            success = self.__restore_process_chains() or success

        # Assign more callbacks
        self.__populate_callbacks()

        return

    def __populate_callbacks(self):
        for category in self.analysis.categories:
            uncalled_callbacks = [self.analysis.categories[category]["callbacks"][callback] for callback
                                  in self.analysis.categories[category]["callbacks"]
                                  if not self.analysis.categories[category]["callbacks"][callback].called_in_model]

            processes = [process for process in self.model["processes"] if process.category == category]

            while(len(uncalled_callbacks) > 0):
                if len(uncalled_callbacks) > 0 and len(processes) > 0:
                    for process in processes:
                        unmatched = [process.labels[name] for name in process.labels if not process.labels[name].interface
                                     and process.labels[name].callback]
                        if unmatched:
                            containers = [process.labels[name] for name in process.labels
                                          if process.labels[name].container and process.labels[name].interface
                                          and process.labels[name].interface in self.analysis.interfaces and
                                          self.analysis.interfaces[process.labels[name].interface].category == category]
                            if containers:
                                for container in containers:
                                    suitable = [callback for callback in uncalled_callbacks
                                                if callback.full_identifier
                                                in self.analysis.interfaces[container.interface].fields.values]
                                    unmatched[0].add_interfaces(suitable)
                                    for callback in suitable:
                                        callback.called_in_model = True
                            else:
                                unmatched[0].add_interfaces(uncalled_callbacks)
                                for callback in uncalled_callbacks:
                                    callback.called_in_model = True

                            uncalled_callbacks = \
                                [self.analysis.categories[category]["callbacks"][callback]
                                 for callback in self.analysis.categories[category]["callbacks"]
                                 if not self.analysis.categories[category]["callbacks"][callback].called_in_model]
                        else:
                            raise RuntimeError("Cannot find process to call callbacks {}".
                                               format(str([callback.full_identifier for callback in unmatched])))
                elif len(uncalled_callbacks) > 0 and len(processes) == 0:
                    raise RuntimeError("Cannot call callbacks '{}' because no process were selected for interface category".
                                       format(str([process.full_identifier for process in processes])))
        return

    def __try_match_more_labels(self, category):
        success = False

        max_map = {}
        max_process = None
        max_index = 0
        min_unmatched = 100
        for process in [self.events["environment processes"][name] for name in self.events["environment processes"]]:
            label_map = self._match_labels(process, category)

            index = 0
            for label in label_map:
                intf = self.analysis.interfaces[label_map[label]]
                if intf.callback and not intf.called_in_model:
                    index += 1
                elif intf.container:
                    for field in intf.fields.values():
                        name = "{}.{}".format(category, field)
                        if name in self.analysis.interfaces and self.analysis.interfaces[name].callback and \
                                not self.analysis.interfaces[name].called_in_model:
                            index += 1

            unmatched = len([name for name in process.labels if name not in label_map])

            if unmatched <= min_unmatched and index > max_index:
                max_process = process
                max_map = label_map
                max_index = index
                min_unmatched = unmatched

        if max_process:
            added = self.add_process(max_process, category)
            if added:
                for label in max_map:
                    added.labels[label].interface = max_map[label]
                success = True

        if success:
            self.__normalize_model()
        return success

    def __populate_model(self, category):
        success = self.__peer_check(self.model["models"].values(), category)

        if success:
            self.__normalize_model()
        return success

    def __restore_process_chains(self):
        success = self.__peer_check(self.model["processes"])

        if success:
            self.__normalize_model()
        return success

    def __peer_check(self, collection, category=None):
        success = False
        for process in collection:
            relevant_labels = [label for label in process.labels if process.labels[label].interface
                               and self.analysis.interfaces[process.labels[label].interface]
                               and (not category 
                                    or self.analysis.interfaces[process.labels[label].interface].category == category)]
                
            if len(relevant_labels) and len(process.unmatched_dispatches) > 0 or len(process.unmatched_receives) > 0:
                peer = None
                max_peer = 0
                for ep in [self.events["environment processes"][name] for name in self.events["environment processes"]]:
                    peers = len(process.get_available_peers(ep))
                    if max_peer < peers:
                        peer = ep
                        max_peer = peers
                if peer:
                    new = self.add_process_peered(peer, process, category)
                    if new:
                        success = True
        return success

    def __normalize_model(self):
        # Peer processes with models
        for model in self.model["models"]:
            for process in self.model["processes"]:
                self.model["models"][model].establish_peers(process)

        # Peer processes with each other
        for index1 in range(len(self.model["processes"])):
            p1 = self.model["processes"][index1]
            for index2 in range(index1 + 1, len(self.model["processes"])):
                p2 = self.model["processes"][index2]
                p1.establish_peers(p2)

        # Calculate callbacks which can be called in the model at the moment
        self._mark_called_callbacks()

    def _mark_called_callbacks(self):
        for process in [self.model["models"][name] for name in self.model["models"]] +\
                       [process for process in self.model["processes"]]:
            for callback_name in set([process.subprocesses[name].callback for name in process.subprocesses
                                      if process.subprocesses[name].callback
                                      and process.subprocesses[name].type == "dispatch"]):
                label, tail = process.extract_label_with_tail(callback_name)

                if label.interface:
                    interface = self.analysis.interfaces[label.interface]
                    if interface.container and len(tail) > 0:
                        intfs = self._resolve_interface(interface, tail)
                        if intfs and len(intfs) > 1:
                            callback = intfs[-1]
                        else:
                            self.logger.warning("Cannot resolve callback '{}' in description of process '{}'".
                                                format(callback_name, process.name))
                    elif interface.callback:
                        callback = interface
                    else:
                        raise ValueError("Cannot resolve callback '{}' in description of process '{}'".
                                         format(callback_name, process.name))

                # If it is exact callback
                if callback and not callback.called_in_model:
                    callback.called_in_model = True

    def add_process(self, process, category=None):
        if not category or (category and process.name not in self.analysis.categories[category]["processes black list"]):
            new = copy.deepcopy(process)
            # Keep signature and interface references
            for label in new.labels:
                new.labels[label].signature = process.labels[label].signature

            self.model["processes"].append(new)
            if category:
                self.analysis.categories[category]["processes black list"].append(process.name)
                new.category = category
            return new
        else:
            return None

    def add_process_peered(self, process, peered, category=None):
        if not category or (category and process.name not in self.analysis.categories[category]["processes black list"]):
            new = copy.deepcopy(process)
            peered.establish_peers(new)
            self.model["processes"].append(new)
            if category:
                self.analysis.categories[category]["processes black list"].append(process.name)
                new.category = category
            return new
        else:
            return None

    def _get_final_intf(self):
        pass

    def _match_labels(self, process, category):
        label_map = {}

        # Trivial match
        for subprocess in process.subprocesses:
            if process.subprocesses[subprocess].callback:
                label, tail = process.extract_label_with_tail(process.subprocesses[subprocess].callback)

                if label.name not in process.labels:
                    raise KeyError("Label '{}' is undefined in process description {}".format(label.name, process.name))
                elif label.name in process.labels and label.interface and label.name not in label_map:
                    if label.interface in self.analysis.interfaces \
                            and self.analysis.interfaces[label.interface].category == category:
                        label_map[label.name] = label.interface
                elif label.name in process.labels and not label.interface and label.name not in label_map:
                    if tail and len(tail) > 0:
                        for container in self.analysis.categories[category]["containers"]:
                            interfaces = \
                                self._resolve_interface(self.analysis.categories[category]["containers"][container],
                                                        tail)
                            if interfaces:
                                label_map[label.name] = \
                                    self.analysis.categories[category]["containers"][container].full_identifier
                    else:
                        if label.callback and label.name in self.analysis.categories[category]["callbacks"]:
                            label_map[label.name] = \
                                self.analysis.categories[category]["callbacks"][label].full_identifier
                        elif label.callback and len(self.analysis.categories[category]["callbacks"]) == 1:
                            keys = list(self.analysis.categories[category]["callbacks"].keys())
                            label_map[label.name] = \
                                self.analysis.categories[category]["callbacks"][keys[0]].full_identifier

        # Parameters match
        for subprocess in process.subprocesses:
            if process.subprocesses[subprocess].callback and process.subprocesses[subprocess].parameters:
                function = None
                container, tail = process.extract_label_with_tail(process.subprocesses[subprocess].callback)
                if tail and len(tail) > 0 and container.name in label_map:
                    intfs = self._resolve_interface(self.analysis.interfaces[label_map[container.name]], tail)
                    if intfs:
                        function = intfs[-1]

                for parameter in process.subprocesses[subprocess].parameters:
                    label, tail = process.extract_label_with_tail(parameter)

                    if label.name not in process.labels:
                        raise KeyError("Undefined label '{}' in process '{}'".format(label.name, process.name))
                    elif label.name in label_map or \
                            (label.interface and label.interface in self.analysis.interfaces \
                             and self.analysis.interfaces[label.interface].category != category):
                        pass
                    elif label.interface:
                        if label.interface in self.analysis.interfaces \
                                and self.analysis.interfaces[label.interface].category == category:
                            label_map[label.name] = label.interface
                    else:
                        if tail and len(tail) > 0:
                            for container in self.analysis.categories[category]["containers"]:
                                if self._resolve_interface(self.analysis.categories[category]["containers"][container],
                                                           tail):
                                    label_map[label.name] = \
                                        self.analysis.categories[category]["containers"][container].full_identifier
                        else:
                            if label.resource and label.name in self.analysis.categories[category]["resources"]:
                                label_map[label.name] = \
                                    self.analysis.categories[category]["resources"][label].full_identifier
                            elif label.callback and label.name in self.analysis.categories[category]["callbacks"]:
                                label_map[label.name] = \
                                    self.analysis.categories[category]["callbacks"][label].full_identifier
                            elif label.container and label.name in self.analysis.categories[category]["containers"]:
                                label_map[label.name] = \
                                    self.analysis.categories[category]["resources"][label].full_identifier
                            elif label.resource and function:
                                for pr in function.signature.parameters:
                                    if pr.interface and pr.interface.resource \
                                            and pr.interface not in label_map.values():
                                        label_map[label.name] = pr.interface.full_identifier
                                        break

        return label_map

    def _resolve_interface(self, interface, string):
        tail = string.split(".")
        # todo: get rid of starting dot
        if len(tail) == 1:
            raise RuntimeError("Cannot resolve interfae for access '{}'".format(string))
        else:
            tail = tail[1:]

        matched = [interface]
        for index in range(len(tail)):
            field = tail[index]
            if field not in matched[-1].fields.values():
                return None
            else:
                if index == (len(tail) - 1):
                    matched.append(self.analysis.interfaces["{}.{}".format(matched[-1].category, field)])
                elif self.analysis.interfaces["{}.{}".format(matched[-1].category, field)].container:
                    matched.append(self.analysis.interfaces["{}.{}".format(matched[-1].category, field)])
                else:
                    return None

        return matched


class Label:
    def __init__(self, name):
        self.container = False
        self.resource = False
        self.callback = False
        self.parameter = False
        self.parameters = []

        self.value = None
        self.signature = None
        self.interface = None
        self.name = name

    def _import_json(self, dic):
        for att in ["container", "resource", "callback", "parameter", "interface", "value"]:
            if att in dic:
                setattr(self, att, dic[att])

        if "signature" in dic:
            self.signature = Signature(dic["signature"])

    def compare_with(self, label):
        if self.interface and label.interface:
            if self.interface == label.interface:
                return "equal"
            else:
                return "different"
        elif label.interface or self.interface:
            if (self.container and label.container) or (self.resource and label.resource) or \
               (self.callback and label.callback):
                return "сompatible"
            else:
                return "different"
        elif self.signature and label.signature:
            ret = self.signature.compare_signature(label.signature)
            if not ret:
                return "different"
            else:
                return "equal"
        else:
            raise NotImplementedError("Cannot compare label '{}' with label '{}'".format(label.name, label.name))


class Process:

    label_re = re.compile("%(\w+)((?:\.\w*)*)%")

    def __init__(self, name, dic={}):
        # Default values
        self.process = None
        self.labels = {}
        self.subprocesses = {}
        self.category = None

        self.type = "process"
        self.name = name
        self._import_dictionary(dic)

    def _parse_process(self, root, expression):
        pass

    def _import_dictionary(self, dic):
        # Import labels
        if "labels" in dic:
            for name in dic["labels"]:
                label = Label(name)
                label._import_json(dic["labels"][name])
                self.labels[name] = label

        # Import subprocesses
        if "subprocesses" in dic:
            for name in dic["subprocesses"]:
                subprocess = Subprocess(name, dic["subprocesses"][name])
                self.subprocesses[name] = subprocess

        # Import process
        if "process" in dic:
            self.process = dic["process"]

        if "parameters" in dic:
            self.parameters = dic["parameters"]

        if self.type and self.type == "process" and len(self.subprocesses.keys()) > 0:
            self.__determine_subprocess_types()

    def __determine_subprocess_types(self):
        dispatch_template = "\[{}(?:\([^)]+\))?\]"
        receive_template = "\(!?{}(?:\([^)]+\))?\)"
        subprocess_template = "{}(?:\([^)]+\))?"

        processes = [self.subprocesses[process_name].process for process_name in self.subprocesses
                     if self.subprocesses[process_name].process]
        processes.append(self.process)

        for subprocess_name in self.subprocesses:
            subprocess_re = re.compile("\{" + subprocess_template.format(subprocess_name) + "\}")
            receive_re = re.compile(receive_template.format(subprocess_name))
            dispatch_re = re.compile(dispatch_template.format(subprocess_name))
            regexes = [
                {"regex": subprocess_re, "type": "subprocess"},
                {"regex": dispatch_re, "type": "dispatch"},
                {"regex": receive_re, "type": "receive"}
            ]

            match = 0
            process_type = None
            for regex in regexes:
                for process in processes:
                    if regex["regex"].search(process):
                        match += 1
                        process_type = regex["type"]
                        break

            if match == 0:
                raise KeyError("Subprocess '{}' from process '{}' is not used actually".
                               format(subprocess_name, self.name))
            elif match > 1:
                raise KeyError("Subprocess '{}' from process '{}' was used in different actions but it can be dispatch,"
                               " receive or subprocess at once".format(subprocess_name, self.name))
            else:
                self.subprocesses[subprocess_name].type = process_type

    @property
    def unmatched_receives(self):
        unmatched = [self.subprocesses[subprocess] for subprocess in self.subprocesses
                     if self.subprocesses[subprocess].type == "receive"
                     and len(self.subprocesses[subprocess].peers) == 0
                     and not self.subprocesses[subprocess].callback]
        return unmatched

    @property
    def unmatched_dispatches(self):
        unmatched = [self.subprocesses[subprocess] for subprocess in self.subprocesses
                     if self.subprocesses[subprocess].type == "dispatch"
                     and len(self.subprocesses[subprocess].peers) == 0
                     and not self.subprocesses[subprocess].callback]
        return unmatched

    @property
    def unmatched_labels(self):
        unmatched = [self.labels[label] for label in self.labels
                     if not self.labels[label].interface and not self.labels[label].signature]
        return unmatched

    def _extract_label(self, string):
        name, tail = self.extract_label_with_tail(string)
        return name

    def extract_label_with_tail(self, string):
        if self.label_re.fullmatch(string):
            name = self.label_re.fullmatch(string).group(1)
            tail = self.label_re.fullmatch(string).group(2)
            if name not in self.labels:
                raise ValueError("Cannot extract label name from string '{}': no such label".format(string))
            else:
                return self.labels[name], tail
        else:
            return None

    def establish_peers(self, process):
        peers = self.get_available_peers(process)
        for signals in peers:
            for index in range(len(self.subprocesses[signals[0]].parameters)):
                label1 = self._extract_label(self.subprocesses[signals[0]].parameters[index])
                label2 = process._extract_label(process.subprocesses[signals[1]].parameters[index])

                if (label1.interface or label2.interface) and not (label1.interface and label2.interface):
                    if label1.interface:
                        label2.interface = label1.interface
                    else:
                        label1.interface = label2.interface

            self.subprocesses[signals[0]].peers.append({"process": process, "subprocess": signals[1]})
            process.subprocesses[signals[1]].peers.append({"process": self, "subprocess": signals[0]})

    def get_available_peers(self, process):
        ret = []

        # Match dispatches
        for dispatch in self.unmatched_dispatches:
            for receive in process.unmatched_receives:
                match = self.compare_params(process, dispatch, receive)
                if match:
                    ret.append([dispatch.name, receive.name])

        # Match receives
        for receive in self.unmatched_receives:
            for dispatch in process.unmatched_dispatches:
                match = self.compare_params(process, receive, dispatch)
                if match:
                    ret.append([receive.name, dispatch.name])

        return ret

    def compare_params(self, process, first, second):
        if first.name == second.name and len(first.parameters) == len(second.parameters):
            match = True
            for index in range(len(first.parameters)):
                label = self._extract_label(first.parameters[index])
                if not label:
                    raise ValueError("Provide label in subprocess '{}' at position '{}' in process '{}'".
                                     format(first.name, index, self.name))
                pair = process._extract_label(second.parameters[index])
                if not pair:
                    raise ValueError("Provide label in subprocess '{}' at position '{}'".
                                     format(second.name, index, process.name))

                ret = label.compare_with(pair)
                if ret != "сompatible" and ret != "equal":
                    match = False
                    break
            return match
        else:
            return False


class Subprocess(Process):

    def __init__(self, name, dic={}):
        self.type = None
        self.name = name
        self.process = None
        self.callback = None
        self.parameters = []
        self._import_dictionary(dic)
        self.peers = []

        if "callback" in dic:
            self.callback = dic["callback"]

    def _import_dictionary(self, dic):
        super()._import_dictionary(dic)
        self.labels = {}
        self.subprocesses = {}
        return

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
