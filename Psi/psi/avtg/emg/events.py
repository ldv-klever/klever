import re
import copy

from psi.avtg.emg.interfaces import *


class EventModel:

    def __init__(self, logger, analysis, raw):
        self.logger = logger
        self.analysis = analysis
        self.models = {}
        self.processes = {}
        self.functions = {}
        self.events = {
            "kernel model": {},
            "environment processes": {}
        }

        for category in self.events:
            # Import kernel models
            self.logger.info("Import {}".format(category))
            self.__import_processes(raw, category)

        # Import necessary kernel models
        self.__import_kernel_models()

        # Complete model
        self.__complete_model()

        return

    def __import_processes(self, raw, category):
        if "kernel model" in raw:
            for name_list in raw[category]:
                names = name_list.split(", ")
                for name in names:
                    process = Process(name, raw[category][name_list])
                    self.events[category][name] = process

    def __import_kernel_models(self):
        self.logger.info("Add kernel models to an intermediate environment model")
        for function in self.events["kernel model"]:
            if function in self.analysis.kernel_functions:
                self.logger.debug("Add model of '{}' to an environment model".format(function))
                self.models[function] = copy.deepcopy(self.events["kernel model"][function])

                for label in self.models[function].labels:
                    if self.models[function].labels[label].parameter and \
                            not self.models[function].labels[label].signature:
                        for parameter in self.analysis.kernel_functions[function]["signature"].parameters:
                            if parameter.interface and self.models[function].labels[label].interface == \
                                    parameter.interface.full_identifier:
                                self.models[function].labels[label].signature = parameter
                        if not self.models[function].labels[label].signature:
                            raise ValueError("Cannot find suitable signature for label '{}' at function model '{}'".
                                             format(label, function))

        self.logger.info("Add references to given label interfaces in environment processes")
        for process in self.events["environment processes"]:
            matched = 0
            for label in self.events["environment processes"][process].labels:
                if self.events["environment processes"][process].labels[label].interface:
                    intf = self.events["environment processes"][process].labels[label].interface
                    if intf in self.analysis.interfaces:
                        matched += 1
                        self.events["environment processes"][process].labels[label].signature = \
                            self.analysis.interfaces[intf].signature

            # If at least one interface is matched add this process
            if matched:
                self.logger.debug("Add process '{}' to an environment model".format(process))
                self.add_process(process)

    def __complete_model(self):
        for category in self.analysis.categories:
            unmatched_callbacks = [self.analysis.categories[category]["callbacks"][callback] for callback in
                                   self.analysis.categories[category]["callbacks"]
                                   if not self.analysis.categories[category]["callbacks"][callback].called_in_model]

            if len(unmatched_callbacks) > 0:
                # Add processes matching input and output signals
                success = self.__populate_model(self.models)
                # Add processes matching input and output signals
                success = self.__populate_model(self.processes)
                # Attempt to add more interfaces to existing processes
                success = self.__try_match_more_labels(category, unmatched_callbacks)
                success = self.__try_match_according_kernel_models(category, unmatched_callbacks)
                success = self.__try_match_according_default_models(category, unmatched_callbacks)

    def __try_match_according_kernel_models(self, category, callbacks):
        success = False

        if success:
            self.__normalize_model()
        return success

    def __try_match_according_default_models(self, category, callbacks):
        success = False
        if success:
            self.__normalize_model()
        return success

    def __try_match_more_labels(self, category, callbacks):
        success = False

        max_map = {}
        max_process = None
        for process in self.events["environment processes"]:
            label_map = self._match_labels(self.events["environment processes"][process], category)
            if len(label_map) > len(max_map):
                max_process = process
                max_map = label_map

        if max_process:
            self.add_process(max_process)
            for label in max_map:
                self.processes[max_process].labels[label].interface = max_map[label]
            success = True

        if success:
            self.__normalize_model()
        return success

    def __populate_model(self, collection):
        success = False

        for model in collection:
            if len(collection[model].unmatched_dispatches) > 0 or len(collection[model].unmatched_receives) > 0:
                peer = None
                max_peer = 0
                for process in self.events["environment processes"]:
                    peers = len(collection[model].get_available_peers(self.events["environment processes"][process]))
                    if max_peer < peers:
                        peer = process
                        max_peer = peers
                if peer:
                    self.add_process_peered(peer, collection[model])
                    success = True

        if success:
            self.__normalize_model()
        return success

    def __normalize_model(self):
        # Peer processes with models
        for model in self.models:
            for process in self.processes:
                self.models[model].establish_peers(self.processes[process])

        # Peer processes with each other
        keys = list(self.processes.keys())
        for index1 in range(len(keys)):
            p1 = self.processes[keys[index1]]
            for index2 in range(index1 + 1, len(keys)):
                p2 = self.processes[keys[index2]]
                p1.establish_peers(p2)

    def add_process(self, name):
        process = copy.deepcopy(self.events["environment processes"][name])
        # Keep signature and interface references
        for label in self.events["environment processes"][name].labels:
            process.labels[label].signature = self.events["environment processes"][name].labels[label].signature

        self.processes[name] = process

    def add_process_peered(self, name, peered):
        process = copy.deepcopy(self.events["environment processes"][name])
        peered.establish_peers(process)
        self.processes[name] = process

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
                    if label.interface in self.analysis.interfaces and self.analysis.interfaces[label.interface].category == category:
                        label_map[label.name] = label.interface
                elif label.name in process.labels and not label.interface and label.name not in label_map:
                    if tail and len(tail) > 0:
                        for container in self.analysis.categories[category]["containers"]:
                            interfaces = self._resolve_interface(self.analysis.categories[category]["containers"][container],
                                                                 tail)
                            if interfaces:
                                label_map[label.name] = self.analysis.categories[category]["containers"][container].full_identifier
                    else:
                        if label.callback and label.name in self.analysis.categories[category]["callbacks"]:
                            label_map[label.name] = self.analysis.categories[category]["callbacks"][label].full_identifier
                        elif label.callback and len(self.analysis.categories[category]["callbacks"]) == 1:
                            keys = list(self.analysis.categories[category]["callbacks"].keys())
                            label_map[label.name] = self.analysis.categories[category]["callbacks"][keys[0]].full_identifier
                        #else:
                        #    random_match.append(label)

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
                        raise KeyError("Label '{}' is undefined in process description {}".format(label.name, process.name))
                    elif label.name in label_map or \
                            (label.interface and label.interface in self.analysis.interfaces and self.analysis.interfaces[label.interface].category != category):
                        pass
                    elif label.interface:
                        if label.interface in self.analysis.interfaces and self.analysis.interfaces[label.interface].category == category:
                            label_map[label.name] = label.interface
                    else:
                        if tail and len(tail) > 0:
                            for container in self.analysis.categories[category]["containers"]:
                                if self._resolve_interface(self.analysis.categories[category]["containers"][container],
                                                           tail):
                                    label_map[label.name] = self.analysis.categories[category]["containers"][container].full_identifier
                        else:
                            if label.resource and label.name in self.analysis.categories[category]["resources"]:
                                label_map[label.name] = self.analysis.categories[category]["resources"][label].full_identifier
                            elif label.callback and label.name in self.analysis.categories[category]["callbacks"]:
                                label_map[label.name] = self.analysis.categories[category]["callbacks"][label].full_identifier
                            elif label.container and label.name in self.analysis.categories[category]["containers"]:
                                label_map[label.name] = self.analysis.categories[category]["resources"][label].full_identifier
                            elif label.resource and function:
                                for pr in function.signature.parameters:
                                    if pr.interface and pr.interface.resource and pr.interface not in label_map.values():
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
        if self.signature and label.signature:
            ret = self.signature.compare_signature(label.signature)
            if not ret:
                return "different"
            else:
                return "equal"
        elif self.interface and label.interface:
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
        else:
            raise NotImplementedError("Cannot compare label '{}' with label '{}'".format(label.name, label.name))


class Process:

    label_re = re.compile("%(\w+)((?:\.\w*)*)%")

    def __init__(self, name, dic={}):
        # Default values
        self.process = None
        self.labels = {}
        self.subprocesses = {}

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
                     and len(self.subprocesses[subprocess].peers) == 0]
        return unmatched

    @property
    def unmatched_dispatches(self):
        unmatched = [self.subprocesses[subprocess] for subprocess in self.subprocesses
                     if self.subprocesses[subprocess].type == "dispatch"
                     and len(self.subprocesses[subprocess].peers) == 0]
        return unmatched

    @property
    def unmatched_labels(self):
        unmatched = [self.labels[label] for label in self.labels
                     if not self.labels[label].interface]
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

    def establish_my_peers(self, process):
        peers = self.get_available_peers(process)
        for signals in peers:
            for index in range(len(self.subprocesses[signals[0]].parameters)):
                label1 = self._extract_label(self.subprocesses[signals[0]].parameters[index])
                label2 = process._extract_label(process.subprocesses[signals[1]].parameters[index])

                if (label1.interface or label2.interface) and not (label1.interface and label2.interface):
                    if not label1.interface:
                        label1.interface = label2.interface

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
                if ret not in ["compatible", "equal"]:
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
