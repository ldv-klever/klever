import re
import copy

from psi.avtg.emg.interfaces import *


class EventModel:

    def __init__(self, logger, analysis, raw):
        self.logger = logger
        self.analysis = analysis
        self.model = {
            "models": [],
            "processes": []
        }
        self.events = {
            "kernel model": {},
            "environment processes": {}
        }

        self.logger.info("Import processes of event categories specification")
        for collection in self.events:
            # Import kernel models
            self.logger.info("Import processes from '{}'".format(collection))
            self.__import_processes(raw, collection)

        # Generate intermediate model
        self.logger.info("Generate an intermediate model")
        self.__select_processes_and_models()

        # Fill all signatures carefully
        self.logger.info("Assign process signatures")
        self.__assign_signatures()

    def __import_processes(self, raw, category):
        if "kernel model" in raw:
            for name_list in raw[category]:
                names = name_list.split(", ")
                for name in names:
                    process = Process(name, raw[category][name_list])
                    self.events[category][name] = process

    def __select_processes_and_models(self):
        # Import necessary kernel models
        self.logger.info("First, add relevant models of kernel functions")
        self.__import_kernel_models()

        for category in self.analysis.categories:
            uncalled_callbacks = self.__get_uncalled_callbacks(category)
            if uncalled_callbacks:
                self.logger.info("Try to find processes to call callbacks from interface category {}".format(category))
                new = self.__choose_processes(category)

                # Sanity check
                uncalled_callbacks = self.__get_uncalled_callbacks(category)
                if uncalled_callbacks:
                    names = str([callback.full_identifier for callback in uncalled_callbacks])
                    raise RuntimeError("There are callbacks from category {} which are not called at all in the "
                                       "model: {}".format(category, names))

                if new.unmatched_dispatches or new.unmatched_receives:
                    self.logger.info("Added process {} have unmatched signals, need to find factory or registration "
                                     "and deregistration functions")
                    self.__establish_signal_peers(new)
            else:
                self.logger.info("Ignore interface category {}, since it does not have callbacks to call".
                                 format(category))

    def __import_kernel_models(self):
        for function in self.events["kernel model"]:
            if function in self.analysis.kernel_functions:
                self.logger.debug("Add model of function '{}' to an environment model".format(function))
                new_process = self.__add_process(self.events["kernel model"][function], model=True)

                self.logger.debug("Assign label interfaces according to function parameters for added process {} "
                                  "with identifier {}".format(new_process.name, new_process.identifier))
                for label in new_process.labels:
                    if new_process.labels[label].parameter and \
                            not new_process.labels[label].signature:
                        for parameter in self.analysis.kernel_functions[function]["signature"].parameters:
                            if parameter.interface and new_process.labels[label].interface == \
                                    parameter.interface.full_identifier:
                                self.logger.debug("Set label {} signature according to interface {}".
                                                  format(label, parameter.interface.full_identifier))
                                new_process.labels[label].signature = parameter
                        if not new_process.labels[label].signature:
                            raise ValueError("Cannot find suitable signature for label '{}' at function model '{}'".
                                             format(label, function))

    def __get_uncalled_callbacks(self, category):
        self.logger.debug("Calculate callbacks which cannot be called in the model from category {}".format(category))
        callbacks = [self.analysis.categories[category]["callbacks"][callback] for callback
                     in self.analysis.categories[category]["callbacks"]
                     if not self.analysis.categories[category]["callbacks"][callback].called_in_model]
        self.logger.debug("There are {} callbacks are not called in the model from category {}, there are: {}".
                          format(len(callbacks), category, str([callback.full_identifier for callback in callbacks])))
        return callbacks

    def __choose_processes(self, category):
        estimations = self.__estimate_processes(category)

        self.logger.info("Search process with maximum implemented callbacks for category {}".format(category))
        best_process = None
        best_map = {
            "matched labels": {},
            "unmatched labels": [],
            "matched callbacks": [],
            "unmatched callbacks": [],
            "native interfaces": 0
        }
        for process in [self.events["environment processes"][name] for name in estimations]:
            label_map = estimations[process.name]
            if label_map and len(label_map["matched callbacks"]) > 0:
                if (len(label_map["unmatched labels"]) == 0\
                        and (not best_process or len(process.subprocesses) > len(best_process.subprocesses))
                        and label_map["native interfaces"] >= best_map["native interfaces"])\
                        or label_map["native interfaces"] > best_map["native interfaces"]:
                    best_map = label_map
                    best_process = process

        if not best_process:
            raise RuntimeError("Cannot find suitable process in event categories specification for category {}"
                               .format(category))
        else:
            new = self.__add_process(best_process, False, best_map)
            return new

    def __estimate_processes(self, category):
        maps = {}
        for process in [self.events["environment processes"][name] for name in self.events["environment processes"]]:
            self.logger.debug("Estimate correspondence between  process {} and category {}".
                              format(process.name, category))
            maps[process.name] = self.__match_labels(process, category)
        return maps

    def __add_process(self, process, model=False, label_map=None, peer=None):
        self.logger.info("Add process {} to the model".format(process.name))
        self.logger.debug("Make process {} copy before adding to the model".format(process.name))
        new = copy.deepcopy(process)

        # Keep signature and interface references
        for label in new.labels:
            self.logger.debug("Copy signature reference to label {} from original prcess {} to its copy".
                              format(label, process.name))
            new.labels[label].signature = process.labels[label].signature

        new.identifier = len(self.model["models"]) + len(self.model["processes"])
        self.logger.info("Finally add process {} to the model with identifier {}".
                         format(process.name, process.identifier))
        if model:
            self.model["models"].append(new)
        else:
            self.model["processes"].append(new)

        if label_map:
            self.logger.debug("Set interfaces for given labels")
            for label in label_map["matched labels"]:
                new.labels[label].interface = label_map["matched labels"][label]

        if peer:
            self.logger.debug("Match signals with signals of process {} with identifier {}".
                              format(peer.name, peer.identifier))
            new.establish_peers(peer)

        self.logger.info("Check is there exist any dispatches or receives after process addiction to tie".
                         format(process.name))
        self.__normalize_model()
        return new

    def __normalize_model(self):
        # Peer processes with models
        self.logger.info("Try to establish connections between process dispatches and receivings")
        for model in self.model["models"]:
            for process in self.model["processes"]:
                self.logger.debug("Analyze signals of processes {} and {} in the model with identifiers {} and {}".
                                  format(model.name, process.name, model.identifier, process.identifier))
                model.establish_peers(process)

        # Peer processes with each other
        for index1 in range(len(self.model["processes"])):
            p1 = self.model["processes"][index1]
            for index2 in range(index1 + 1, len(self.model["processes"])):
                p2 = self.model["processes"][index2]
                self.logger.debug("Analyze signals of processes {} and {} in the model with identifiers {} and {}".
                                  format(p1.name, p2.name, p1.identifier, p2.identifier))
                p1.establish_peers(p2)

        # Calculate callbacks which can be called in the model at the moment
        self.logger.info("Recalculate which callbacks can be now called in the model")
        self._mark_called_callbacks()

    def _mark_called_callbacks(self):
        for process in [process for process in self.model["models"]] +\
                       [process for process in self.model["processes"]]:
            self.logger.debug("Check process callback calls at process {} with identifier {}".
                              format(process.name, process.identifier))

            called = []
            for callback_name in set([process.subprocesses[name].callback for name in process.subprocesses
                                      if process.subprocesses[name].callback
                                      and process.subprocesses[name].type == "dispatch"]):
                label, tail = process.extract_label_with_tail(callback_name)

                if label.interface:
                    intfs = []
                    if type(label.interface) is str:
                        intfs = [label.interface]
                    else:
                        intfs = label.interface

                    for interface in [self.analysis.interfaces[name] for name in intfs]:
                        if interface.container and len(tail) > 0:
                            intfs = self.__resolve_interface(interface, tail)
                            if intfs and intfs[-1] not in called:
                                intfs[-1].called_in_model = True
                            else:
                                self.logger.warning("Cannot resolve callback '{}' in description of process '{}'".
                                                    format(callback_name, process.name))
                        elif interface.callback and interface not in called:
                            interface.called_in_model = True
                        else:
                            raise ValueError("Cannot resolve callback '{}' in description of process '{}'".
                                             format(callback_name, process.name))

    def __match_labels(self, process, category):
        label_map = {
            "matched labels": {},
            "unmatched labels": [],
            "matched callbacks": [],
            "unmatched callbacks": [],
            "native interfaces": len([label for label in process.labels if process.labels[label].interface
                                      and process.labels[label].interface in self.analysis.interfaces and
                                      self.analysis.interfaces[process.labels[label].interface].category == category])
        }
        old_size = 0
        new_size = 0
        start = True
        while((new_size - old_size) > 0 or start):
            # Match interfaces and containers
            for subprocess in [process.subprocesses[name] for name in process.subprocesses
                               if process.subprocesses[name].callback
                               and process.subprocesses[name].type == "dispatch"]:
                self.logger.debug("Match callback {}".format(subprocess.callback))
                label, tail = process.extract_label_with_tail(subprocess.callback)

                if label.name not in label_map["matched labels"] and label.interface:
                    if label.interface in self.analysis.interfaces \
                            and self.analysis.interfaces[label.interface].category == category:
                        self.logger.debug("Match label {} of process {} with an interface {}".
                                          format(label.name, process.name, label.interface))
                        label_map["matched labels"][label.name] = label.interface
                    else:
                        self.logger.debug("Process {} has label {} matched with interface {} which does not belong to "
                                          "category {}".format(process.name, label.name, label.interface, category))
                        return None
                elif not label.interface and not label.signature and tail and label.container and label.name \
                        not in label_map["matched labels"]:
                    for container in [self.analysis.categories[category]["containers"][name] for name
                                      in self.analysis.categories[category]["containers"]]:
                        interfaces = self.__resolve_interface(container, tail)
                        self.logger.debug("Trying to match label {} with a container {}".
                                          format(label.name, container.full_identifier))
                        if interfaces:
                            label_map["matched labels"][label.name] = container.full_identifier
                            self.logger.debug("Matched label {} of process {} with an interface {}".
                                              format(label.name, process.name, container.full_identifier))

                if subprocess.parameters:
                    functions = []
                    if label.name in label_map["matched labels"] and label.container:
                        intfs = self.__resolve_interface(
                            self.analysis.interfaces[label_map["matched labels"][label.name]], tail)
                        if intfs:
                            functions.append(intfs[-1])
                    elif label.name in label_map["matched labels"] and label.callback:
                        if type(label_map["matched labels"][label.name]) is list:
                            functions.extend([self.analysis.interfaces[name] for name in
                                             label_map["matched labels"][label.name]])
                        else:
                            functions = [self.analysis.interfaces[label_map["matched labels"][label.name]]]

                    for function in functions:
                        if len(subprocess.parameters) <= len(function.signature.parameters):
                            self.logger.debug("Try to match parameters of function '{}'".
                                              format(function.full_identifier))
                            for parameter in subprocess.parameters:
                                pl = process.extract_label(parameter)

                                for pr in function.signature.parameters:
                                    if pr.interface and pr.interface.resource and pl.resource \
                                            and pl.name not in label_map["matched labels"]:
                                        label_map["matched labels"][pl.name] = pr.interface.full_identifier
                                        break
                        else:
                            raise RuntimeError("Function {} has been incorrectly matched".
                                               format(function.full_identifier))

            # After containers are matched try to match callbacks
            matched_containers = [process.labels[name] for name in process.labels if process.labels[name].container and
                                  name in label_map["matched labels"]]
            unmatched_callbacks = [process.labels[name] for name in process.labels if process.labels[name].callback and
                                   name not in label_map["matched labels"]]
            if len(matched_containers) > 0 and len(unmatched_callbacks) > 0:
                for container in matched_containers:
                    container_intf = self.analysis.interfaces[container.interface]
                    for field in container_intf.fields.values:
                        name = "{}.{}".format(category, field)
                        if name in self.analysis.interfaces and self.analysis.interfaces[name].callback:
                            if unmatched_callbacks[0].name not in label_map["matched labels"]:
                                label_map["matched labels"][unmatched_callbacks[0].name] = []
                            if name not in label_map["matched labels"][unmatched_callbacks[0].name]:
                                label_map["matched labels"][unmatched_callbacks[0].name].append(name)
            elif len(unmatched_callbacks) > 0:
                for callback in [self.analysis.categories[category]["callbacks"][name] for name in
                                 self.analysis.categories[category]["callbacks"]
                                 if self.analysis.categories[category]["callbacks"][name].callback]:
                    if unmatched_callbacks[0].name not in label_map["matched labels"]:
                        label_map["matched labels"][unmatched_callbacks[0].name] = []
                    if callback.full_identifier not in label_map["matched labels"][unmatched_callbacks[0].name]:
                        label_map["matched labels"][unmatched_callbacks[0].name].append(callback.full_identifier)

            # Discard unmatched labels
            label_map["unmatched labels"] = [label for label in process.labels
                                             if label not in label_map["matched labels"]
                                             and not process.labels[label].interface
                                             and not process.labels[label].signature]

            # Discard unmatched callbacks
            label_map["unmatched callbacks"] = []
            label_map["matched callbacks"] = []
            for subprocess in [process.subprocesses[name] for name in process.subprocesses
                               if process.subprocesses[name].callback
                               and process.subprocesses[name].type == "dispatch"]:
                label, tail = process.extract_label_with_tail(subprocess.callback)
                if label.callback and label.name not in label_map["matched labels"] \
                        and subprocess.callback not in label_map["unmatched callbacks"]:
                    label_map["unmatched callbacks"].append(subprocess.callback)
                elif label.callback and label.name in label_map["matched labels"]:
                    callbacks = []
                    if type(label_map["matched labels"][label.name]) is list:
                        callbacks = label_map["matched labels"][label.name]
                    else:
                        callbacks = [label_map["matched labels"][label.name]]

                    for callback in callbacks:
                        if callback not in label_map["matched callbacks"]:
                            label_map["matched callbacks"].append(callback)
                elif label.container and tail and label.name not in label_map["matched labels"]:
                    if subprocess.callback not in label_map["unmatched callbacks"]:
                        label_map["unmatched callbacks"].append(subprocess.callback)
                elif label.container and tail and label.name in label_map["matched labels"]:
                    intfs = self.__resolve_interface(self.analysis.interfaces[label_map["matched labels"][label.name]],
                                                     tail)
                    if not intfs and subprocess.callback not in label_map["unmatched callbacks"]:
                        label_map["unmatched callbacks"].append(subprocess.callback)
                    elif intfs and subprocess.callback not in label_map["matched callbacks"]:
                        label_map["matched callbacks"].append(subprocess.callback)

            if start:
                start = False
            old_size = new_size
            new_size = len(label_map["matched callbacks"]) + len(label_map["matched labels"])

        return label_map

    def __resolve_interface(self, interface, string):
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

    def __establish_signal_peers(self, process):
        for candidate in [self.events["environment processes"][name] for name in self.events["environment processes"]]:
            peers = process.get_available_peers(candidate)
            if peers:
                self.logger.debug("Establish signal references between process {} with identifier {} and process {}".
                                  format(process.name, process.identifier, candidate.name))
                new = self.__add_process(candidate, model=False, label_map=None, peer=process)
                if new.unmatched_receives or new.unmatched_dispatches:
                    self.__establish_signal_peers(new)

        if process.unmatched_receives:
            for receive in process.unmatched_receives:
                if receive.name == "register":
                    pass
                elif receive.name == "deregister":
                    pass
                else:
                    self.logger.warning("Signal {} cannot be received by process {} with identifier {}, "
                                        "since nobody can send it".
                                        format(receive.name, process.name, process.identifier))
        for dispatch in process.unmatched_dispatches:
            self.logger.warning("Signal {} cannot be send by process {} with identifier {}, "
                                "since nobody can receive it".format(dispatch.name, process.name, process.identifier))

    def __assign_signatures(self):
        for process in self.model["models"] + self.model["processes"]:
            self.logger.debug("Analyze signatures of process {} with an identifier {}".
                              format(process.name, process.identifier))
            for subprocess in [process.subprocesses[name] for name in process.subprocesses
                               if process.subprocesses[name].type in ["dispatch", "receive"]]:
                for peer in subprocess.peers:
                    peer_subprocess = peer["process"].subprocesses[peer["subprocess"]]
                    if peer["process"].name in self.events["kernel model"]:
                        for index in range(len(peer_subprocess.parameters)):
                            peer_parameter = peer_subprocess.parameters[index]
                            peer_label = peer["process"].extract_label(peer_parameter)
                            parameter = subprocess.parameters[index]
                            label = process.extract_label(parameter)
                            if label and peer_label and label.signature and peer_label.signature:
                                if not peer_label.signature.compare_signature(label.signature):
                                    raise ValueError("Sgnatures of parameters at {} position of subprocess {} from "
                                                     "process {} with an identifier {} and same subprocess from process"
                                                     " {} with an identifier {} should be equal".
                                                     format(index, subprocess.name, process.name, process.identifier,
                                                            peer["process"].name, peer["process"].identifier))
                            elif label and peer_label and not label.signature and peer_label.signature:
                                label.signature = peer_label.signature
                    else:
                        for index in range(len(peer_subprocess.parameters)):
                            peer_parameter = peer_subprocess.parameters[index]
                            peer_label = peer["process"].extract_label(peer_parameter)
                            parameter = subprocess.parameters[index]
                            label = process.extract_label(parameter)
                            if label and peer_label:
                                peer_label.signature = label.signature





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
        self.identifier = None

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

    def extract_label(self, string):
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
                label1 = self.extract_label(self.subprocesses[signals[0]].parameters[index])
                label2 = process.extract_label(process.subprocesses[signals[1]].parameters[index])

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
                match = self.__compare_signals(process, dispatch, receive)
                if match:
                    ret.append([dispatch.name, receive.name])

        # Match receives
        for receive in self.unmatched_receives:
            for dispatch in process.unmatched_dispatches:
                match = self.__compare_signals(process, receive, dispatch)
                if match:
                    ret.append([receive.name, dispatch.name])

        return ret

    def __compare_signals(self, process, first, second):
        if first.name == second.name and len(first.parameters) == len(second.parameters):
            match = True
            for index in range(len(first.parameters)):
                label = self.extract_label(first.parameters[index])
                if not label:
                    raise ValueError("Provide label in subprocess '{}' at position '{}' in process '{}'".
                                     format(first.name, index, self.name))
                pair = process.extract_label(second.parameters[index])
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
