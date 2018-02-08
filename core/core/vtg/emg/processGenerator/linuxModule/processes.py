#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
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
import copy
import re

from core.vtg.emg.common import get_necessary_conf_property, check_or_set_conf_property
from core.vtg.emg.common.process import Dispatch, Receive
from core.vtg.emg.processGenerator.linuxModule.interface import Interface, Callback, Container
from core.vtg.emg.processGenerator.linuxModule.process import AbstractAccess, Call


class ProcessModel:
    def __init__(self, logger, conf, interfaces, models, processes, roles_map):
        self.logger = logger
        self.conf = conf
        self.__abstr_model_processes = models
        self.__abstr_event_processes = processes
        self.__roles_map = dict()
        self.__functions_map = dict()
        self.__default_dispatches = list()

        if "roles map" in roles_map:
            self.__roles_map = roles_map["roles map"]
        if "functions map" in roles_map:
            self.__functions_map = roles_map["functions map"]
            for tp in self.__functions_map:
                self.__functions_map[tp] = [re.compile(pattern) for pattern in self.__functions_map[tp]]

        self.model_processes = []
        self.event_processes = []

        # Generate intermediate model
        self.logger.info("Generate an intermediate model")
        self.__select_processes_and_models(interfaces)

        # Convert callback access according to container fields
        self.logger.info("Determine particular interfaces and their implementations for each label or its field")
        self.__resolve_accesses(interfaces)

        # Sanity check
        for process in self.model_processes + self.event_processes:
            if not process.category:
                raise ValueError("Found process without category {!r}".format(process.name))

        # Refine processes
        self.__refine_processes()

    def __select_processes_and_models(self, interfaces):
        # Import necessary kernel models
        self.logger.info("First, add relevant models of kernel functions")
        self.__import_kernel_models(interfaces)

        for category in interfaces.categories:
            uncalled_callbacks = interfaces.uncalled_callbacks(category)
            self.logger.debug("There are {} callbacks in category {!r}".format(len(uncalled_callbacks), category))

            if uncalled_callbacks:
                self.logger.info("Try to find processes to call callbacks from category {!r}".format(category))
                new = self.__choose_processes(interfaces, category)

                # Sanity check
                self.logger.info("Check again how many callbacks are not called still in category {!r}".
                                 format(category))
                uncalled_callbacks = interfaces.uncalled_callbacks(category)
                if uncalled_callbacks and not ('ignore missed callbacks' in self.conf and
                                               self.conf['ignore missed callbacks']):
                    names = str([callback.identifier for callback in uncalled_callbacks])
                    raise RuntimeError("There are callbacks from category {!r} which are not called at all in the "
                                       "model: {}".format(category, names))
                elif uncalled_callbacks:
                    names = str([callback.identifier for callback in uncalled_callbacks])
                    self.logger.warning("There are callbacks from category {!r} which are not called at all in the "
                                        "model: {}. Disable option 'ignore missed callbacks' in intermediate model "
                                        "configuration properties if you would like to terminate.".
                                        format(category, names))

                if len(new.unmatched_dispatches) > 0 or len(new.unmatched_receives) > 0:
                    self.logger.info("Added process {!r} have unmatched signals, need to find factory or registration "
                                     "and deregistration functions".format(new.name))
                    self.__establish_signal_peers(interfaces, new)
            else:
                self.logger.info("Ignore interface category {!r}, since it does not have callbacks to call".
                                 format(category))

    def __import_kernel_models(self, interfaces):
        for func in (f for f in self.__abstr_model_processes.keys()
                     if f in (i.short_identifier for i in interfaces.function_interfaces)):
            # todo: Or we should use complete identifier?
            function_obj = interfaces.get_intf('functions models.{}'.format(func))
            self.logger.debug("Add model of function {!r} to an environment model".format(func))
            new_process = self.__add_process(interfaces, self.__abstr_model_processes[func], model=True)
            new_process.category = "functions models"

            self.logger.debug("Assign label interfaces according to function parameters for added process {!r} "
                              "with an identifier {!r}".format(new_process.name, new_process.identifier))
            for label in new_process.labels.keys():
                # Assign label-parameters
                if new_process.labels[label].parameter and not new_process.labels[label].declaration:
                    for index, parameter in enumerate(function_obj.param_interfaces):
                        declaration = function_obj.declaration.parameters[index]

                        if parameter and parameter.identifier in new_process.labels[label].interfaces:
                            self.logger.debug("Set label {!r} signature according to interface {!r}".
                                              format(label, parameter.identifier))
                            new_process.labels[label].set_declaration(parameter.identifier, declaration)
                            break
                elif new_process.labels[label].retval and not new_process.labels[label].declaration:
                    if function_obj.rv_interface:
                        new_process.labels[label].set_declaration(function_obj.rv_interface.identifier,
                                                                  function_obj.rv_interface.declaration)
                    else:
                        new_process.labels[label].declaration = function_obj.declaration.return_value
                elif not (new_process.labels[label].parameter or new_process.labels[label].retval) and \
                        new_process.labels[label].interfaces:
                    for interface in new_process.labels[label].interfaces:
                        interface_obj = interfaces.get_intf(interface)
                        new_process.labels[label].set_declaration(interface, interface_obj.declaration)

                if new_process.labels[label].parameter and len(new_process.labels[label].interfaces) == 0:
                    raise ValueError("Cannot find a suitable signature for label {!r} at function model {!r}".
                                     format(label, func))

                # Asssign rest parameters
                if new_process.labels[label].interfaces and len(new_process.labels[label].interfaces) > 0:
                    for interface in (i for i in new_process.labels[label].interfaces
                                      if i in interfaces.interfaces):
                        self.__assign_label_interface(new_process.labels[label], interfaces.get_intf(interface))

    def __choose_processes(self, interfaces, category):
        estimations = {}
        for process in [self.__abstr_event_processes[name] for name in self.__abstr_event_processes.keys()]:
            self.logger.debug("Estimate correspondence between  process {} and category {}".
                              format(process.name, category))
            estimations[process.name] = self.__match_labels(interfaces, process, category)

        self.logger.info("Choose process to call callbacks from category {}".format(category))
        # First random
        suits = [name for name in estimations if estimations[name] and
                 len(estimations[name]["matched calls"]) > 0 and len(estimations[name]["unmatched labels"]) == 0]
        if len(suits) == 0:
            raise RuntimeError("Cannot find any suitable process in specification for category {!r}".format(category))
        best_process = self.__abstr_event_processes[suits[0]]
        best_map = estimations[best_process.name]

        for process in [self.__abstr_event_processes[name] for name in estimations]:
            label_map = estimations[process.name]
            if label_map and len(label_map["matched calls"]) > 0 and len(label_map["unmatched labels"]) == 0:
                self.logger.info("Matching process {!r} for category {!r}, it has:".format(process.name, category))
                self.logger.info("Matching labels: {!r}".format(str(label_map["matched labels"])))
                self.logger.info("Unmatched labels: {!r}".format(str(label_map["unmatched labels"])))
                self.logger.info("Matched callbacks: {!r}".format(str(label_map["matched callbacks"])))
                self.logger.info("Unmatched callbacks: {!r}".format(str(label_map["unmatched callbacks"])))
                self.logger.info("Matched calls: {!r}".format(str(label_map["matched calls"])))
                self.logger.info("Native interfaces: {!r}".format(str(label_map["native interfaces"])))

                do = False
                if label_map["native interfaces"] > best_map["native interfaces"]:
                    do = True
                elif best_map["native interfaces"] == 0:
                    if len(label_map["matched calls"]) > len(best_map["matched calls"]) and \
                                    len(label_map["unmatched callbacks"]) <= len(best_map["unmatched callbacks"]):
                        do = True
                    elif len(label_map["matched calls"]) >= len(best_map["matched calls"]) and \
                            len(label_map["unmatched callbacks"]) <= len(best_map["unmatched callbacks"]) and \
                            len(label_map["unmatched labels"]) < len(best_map["unmatched labels"]):
                        do = True
                    elif len(label_map["unmatched callbacks"]) < len(best_map["unmatched callbacks"]):
                        do = True
                    else:
                        do = False

                if do:
                    best_map = label_map
                    best_process = process
                    self.logger.debug("Set process {!r} for category {!r} as the best one at the moment".
                                      format(process.name, category))

        if not best_process:
            raise RuntimeError("Cannot find suitable process in event categories specification for category {!r}"
                               .format(category))
        else:
            new = self.__add_process(interfaces, best_process, category, False, best_map)
            new.category = category
            self.logger.debug("Finally choose process {!r} for category {!r} as the best one".
                              format(best_process.name, category))
            return new

    @staticmethod
    def __assign_label_interface(label, interface):
        if isinstance(interface, Container):
            label.set_declaration(interface.identifier, interface.declaration.take_pointer)
        else:
            label.set_declaration(interface.identifier, interface.declaration)

    def __add_process(self, interfaces, process, category=None, model=False, label_map=None, peer=None):
        self.logger.info("Add process {!r} to the model".format(process.name))
        self.logger.debug("Make copy of process {!r} before adding it to the model".format(process.name))
        new = copy.deepcopy(process)
        if not category:
            new.category = 'functions models'
            if not new.comment:
                raise KeyError("You must specify manually 'comment' attribute within the description of the following "
                               "function model process description: {!r}.".format(new.name))
        else:
            new.category = category
            if not new.comment:
                new.comment = get_necessary_conf_property(self.conf, 'process comment')

        # Add comments
        comments_by_type = get_necessary_conf_property(self.conf, 'action comments')
        for action in new.actions.values():
            # Add comment if it is provided
            if not action.comment:
                tag = type(action).__name__.lower()
                if tag in comments_by_type and isinstance(comments_by_type[tag], str):
                    action.comment = comments_by_type[tag]
                elif tag in comments_by_type and isinstance(comments_by_type[tag], dict) and \
                        action.name in comments_by_type[tag]:
                    action.comment = comments_by_type[tag][action.name]
                elif not isinstance(action, Call):
                    raise KeyError(
                        "Cannot find a comment for action {0!r} of type {2!r} at new {1!r} description. You "
                        "shoud either specify in the corresponding environment model specification the comment "
                        "text manually or set the default comment text for all actions of the type {2!r} at EMG "
                        "plugin configuration properties within 'action comments' attribute.".
                        format(action.name, new.name, tag))

            # Add callback comment
            if isinstance(action, Call):
                callback_comment = get_necessary_conf_property(self.conf, 'callback comment').capitalize()
                if action.comment:
                    action.comment += ' ' + callback_comment
                else:
                    action.comment = callback_comment

        # todo: Assign category for each new process not even for that which have callbacks (issue #6564)
        new.identifier = len(self.model_processes) + len(self.event_processes) + 1
        self.logger.info("Finally add process {} to the model".
                         format(process.name))

        self.logger.debug("Set interfaces for given labels")
        if label_map:
            for label in label_map["matched labels"].keys():
                for interface in [interfaces.get_or_restore_intf(name) for name
                                  in label_map["matched labels"][label]]:
                    self.__assign_label_interface(new.labels[label], interface)
        else:
            for label in new.labels.values():
                for interface in label.interfaces:
                    if not label.get_declaration(interface):
                        try:
                            self.__assign_label_interface(label, interfaces.get_or_restore_intf(interface))
                        except KeyError:
                            self.logger.warning("Process '{}' for category '{}' cannot be added, since it contains"
                                                "unknown interfaces for this verification object".
                                                format(new.name, new.category))
                            return None

        if model and not category:
            self.model_processes.append(new)
        elif not model and category:
            self.event_processes.append(new)
        else:
            raise ValueError('Provide either model or category arguments but not simultaneously')

        if peer:
            self.logger.debug("Match signals with signals of process {} with identifier {}".
                              format(peer.name, peer.identifier))
            new.establish_peers(peer)

        self.logger.info("Check is there exist any dispatches or receives after process addiction to tie".
                         format(process.name))
        self.__normalize_model(interfaces)
        return new

    def __normalize_model(self, interfaces):
        # Peer processes with models
        self.logger.info("Try to establish connections between process dispatches and receivings")
        for process in self.event_processes:
            for model in self.model_processes:
                self.logger.debug("Analyze signals of processes {} and {} in the model with identifiers {} and {}".
                                  format(model.name, process.name, model.identifier, process.identifier))
                model.establish_peers(process)

        # Peer processes with each other
        for index1, p1 in enumerate(self.event_processes):
            for index2 in range(index1 + 1, len(self.event_processes)):
                p2 = self.event_processes[index2]
                self.logger.debug("Analyze signals of processes {} and {}".format(p1.name, p2.name))
                p1.establish_peers(p2)

        self.logger.info("Check which callbacks can be called in the intermediate environment model")
        for process in [process for process in self.model_processes] + \
                [process for process in self.event_processes]:
            self.logger.debug("Check process callback calls at process {!r} with category {!r}".
                              format(process.name, process.category))

            for action in process.calls:
                # todo: refactoring #6565
                label, tail = process.extract_label_with_tail(action.callback)

                if len(label.interfaces) > 0:
                    resolved = False
                    for interface in label.interfaces:
                        interface_obj = interfaces.get_or_restore_intf(interface)
                        if isinstance(interface_obj, Container) and len(tail) > 0:
                            intfs = self.__resolve_interface(interfaces, interface_obj, tail, process, action)
                            if intfs:
                                intfs[-1].called = True
                                resolved = True
                            else:
                                self.logger.warning("Cannot resolve callback {!r} in description of process {!r}".
                                                    format(action.callback, process.name))
                        elif isinstance(interface_obj, Callback):
                            self.logger.debug("Callback {!r} can be called in the model".
                                              format(interface_obj.identifier))
                            interface_obj.called = True
                            resolved = True
                    if not resolved:
                        raise ValueError("Cannot resolve callback {!r} in description of process {!r}".
                                         format(action.callback, process.name))

    def __add_label_match(self, interfaces, label_map, label, interface):
        if interfaces.is_removed_intf(interface):
            interfaces.get_or_restore_intf(interface)

        if label.name not in label_map["matched labels"]:
            self.logger.debug("Match label {!r} with interface {!r}".format(label.name, interface))
            label_map["matched labels"][label.name] = {interface}
        else:
            label_map["matched labels"][label.name].add(interface)

    def __match_labels(self, interfaces, process, category):
        self.logger.info("Try match process {!r} with interfaces of category {!r}".format(process.name, category))
        label_map = {
            "matched labels": {},
            "unmatched labels": [],
            "uncalled callbacks": [],
            "matched callbacks": [],
            "unmatched callbacks": [],
            "matched calls": [],
            "native interfaces": []
        }

        # Collect native categories and interfaces
        nc = set()
        ni = set()
        for label in (process.labels[name] for name in process.labels.keys()):
            for intf in label.interfaces:
                intf_category, short_identifier = intf.split(".")
                nc.add(intf_category)

                if (intf in interfaces.interfaces or interfaces.is_removed_intf(intf)) and intf_category == category:
                    ni.add(intf)
                    self.__add_label_match(interfaces, label_map, label, intf)
        label_map["native interfaces"] = len(ni)

        # Stop analysis if process tied with another category
        if len(nc) > 0 and len(ni) == 0:
            self.logger.debug("Process {} is intended to be matched with a category from the list: {}".
                              format(process.name, str(nc)))
            return None

        # todo: Code below is a bit greedy and it doesn't support arrays in access sequences
        # todo: better to rewrite it totally and implement comparison on the base of signatures
        success_on_iteration = True
        while success_on_iteration:
            success_on_iteration = False
            old_size = len(label_map["matched callbacks"]) + len(label_map["matched labels"])

            # Match interfaces and containers
            for action in process.calls:
                label, tail = process.extract_label_with_tail(action.callback)

                # Try to match container
                if len(label.interfaces) > 0 and label.name not in label_map["matched labels"]:
                    for interface in (interface for interface in label.interfaces if interface in interfaces.interfaces
                                      or interfaces.is_removed_intf(interface)):
                        interface_obj = interfaces.get_intf(interface)

                        if interface_obj.category == category:
                            self.__add_label_match(interfaces, label_map, label, interface)
                elif len(label.interfaces) == 0 and not label.declaration and tail and label.container and \
                        label.name not in label_map["matched labels"]:
                    for container in interfaces.containers(category):
                        intfs = self.__resolve_interface(interfaces, container, tail, process, action)
                        if intfs:
                            self.__add_label_match(interfaces, label_map, label, container.identifier)

                # Try to match callback itself
                functions = []
                if label.name in label_map["matched labels"] and label.container:
                    for intf in label_map["matched labels"][label.name]:
                        intfs = self.__resolve_interface(interfaces, interfaces.get_intf(intf), tail, process, action)
                        if intfs and isinstance(intfs[-1], Callback):
                            functions.append(intfs[-1])
                elif label.name in label_map["matched labels"] and label.callback:
                    if isinstance(label_map["matched labels"][label.name], set):
                        functions.extend([interfaces.get_or_restore_intf(name) for name in
                                          label_map["matched labels"][label.name]
                                          if name in interfaces.interfaces or interfaces.is_deleted_intf(name)])
                    elif label_map["matched labels"][label.name] in interfaces.interfaces or \
                            interfaces.is_removed_intf(label_map["matched labels"][label.name]):
                        functions.append(interfaces.get_intf(label_map["matched labels"][label.name]))

                # Restore interfaces if necesary
                for intf in (f for f in functions if interfaces.is_removed_intf(f)):
                    interfaces.get_or_restore_intf(intf)

                # Match parameters
                for func in functions:
                    labels = []
                    pre_matched = set()
                    for par in action.parameters:
                        p_label, p_tail = process.extract_label_with_tail(par)
                        if p_tail:
                            for container in interfaces.containers(category):
                                intfs = self.__resolve_interface(interfaces, container, p_tail)
                                if intfs:
                                    self.__add_label_match(intfs, label_map, p_label, container.identifier)
                                    pre_matched.add(intfs[-1].identifier)

                        labels.append([p_label, p_tail])

                    f_intfs = [pr for pr in func.param_interfaces if pr]
                    for pr, par in enumerate(f_intfs):
                        matched = set([label[0] for label in labels
                                       if label[0].name in label_map['matched labels'] and
                                       par.identifier in label_map['matched labels'][label[0].name]]) & \
                                  set([label[0] for label in labels])
                        if len(matched) == 0 and par.identifier not in pre_matched:
                            if len(labels) == len(f_intfs):
                                self.__add_label_match(interfaces, label_map, labels[pr][0], par.identifier)
                            else:
                                unmatched = [label[0] for label in labels
                                             if label[0].name not in label_map['matched labels'] and len(label[1]) == 0]
                                if len(unmatched) > 0:
                                    self.__add_label_match(interfaces, label_map, unmatched[0], par.identifier)
                                else:
                                    rsrs = [label[0] for label in labels if label[0].resource]
                                    if len(rsrs) > 0:
                                        self.__add_label_match(interfaces, label_map, rsrs[-1], par.identifier)

            # After containers are matched try to match rest callbacks from category
            matched_containers = [cn for cn in process.containers if cn.name in label_map["matched labels"]]
            unmatched_callbacks = [cl for cl in process.callbacks if cl.name not in label_map["matched labels"]]
            if len(matched_containers) > 0 and len(unmatched_callbacks) > 0:
                for callback in unmatched_callbacks:
                    for container in matched_containers:
                        for container_intf in [interfaces.get_intf(intf) for intf in
                                               label_map["matched labels"][container.name]]:
                            for f_intf in [intf for intf in container_intf.field_interfaces.values()
                                           if isinstance(intf, Callback) and not intf.called and
                                           intf.identifier not in label_map['matched callbacks'] and
                                           intf.identifier in interfaces.interfaces]:
                                self.__add_label_match(interfaces, label_map, callback, f_intf.identifier)
            if len(unmatched_callbacks) > 0:
                for callback in unmatched_callbacks:
                    for intf in [intf for intf in interfaces.callbacks(category)
                                 if not intf.called and intf.identifier not in label_map['matched callbacks']]:
                        self.__add_label_match(interfaces, label_map, callback, intf.identifier)

            # Discard unmatched labels
            label_map["unmatched labels"] = [label for label in process.labels.keys()
                                             if label not in label_map["matched labels"] and
                                             len(process.labels[label].interfaces) == 0 and not
                                             process.labels[label].declaration]

            # Discard unmatched callbacks
            label_map["unmatched callbacks"] = []
            label_map["matched callbacks"] = []

            # Check which callbacks are matched totally
            for action in process.calls:
                label, tail = process.extract_label_with_tail(action.callback)
                if label.callback and label.name not in label_map["matched labels"] \
                        and action.callback not in label_map["unmatched callbacks"]:
                    label_map["unmatched callbacks"].append(action.callback)
                elif label.callback and label.name in label_map["matched labels"]:
                    callbacks = list(label_map["matched labels"][label.name])

                    for callback in callbacks:
                        if callback not in label_map["matched callbacks"]:
                            label_map["matched callbacks"].append(callback)
                        if action.callback not in label_map["matched calls"]:
                            label_map["matched calls"].append(action.callback)
                elif label.container and tail and label.name not in label_map["matched labels"] and \
                        action.callback not in label_map["unmatched callbacks"]:
                    label_map["unmatched callbacks"].append(action.callback)
                elif label.container and tail and label.name in label_map["matched labels"]:
                    for intf in label_map["matched labels"][label.name]:
                        intfs = self.__resolve_interface(interfaces, interfaces.get_intf(intf), tail, process, action)

                        if not intfs and action.callback not in label_map["unmatched callbacks"]:
                            label_map["unmatched callbacks"].append(action.callback)
                        elif intfs and action.callback not in label_map["matched callbacks"]:
                            label_map["matched callbacks"].append(intfs[-1].identifier)
                            if action.callback not in label_map["matched calls"]:
                                label_map["matched calls"].append(action.callback)

            # Discard uncalled callbacks and recalculate it
            label_map["uncalled callbacks"] = [cb.identifier for cb in interfaces.callbacks(category)
                                               if cb.identifier not in label_map["matched callbacks"]]

            if len(label_map["matched callbacks"]) + len(label_map["matched labels"]) - old_size > 0:
                success_on_iteration = True

        # Discard unmatched callbacks
        for action in process.calls:
            label, tail = process.extract_label_with_tail(action.callback)
            if label.container and tail and label.name in label_map["matched labels"]:
                for intf in label_map["matched labels"][label.name]:
                    intfs = self.__resolve_interface(interfaces, interfaces.get_intf(intf), tail, process, action)
                    if intfs:
                        # Discard general callbacks match
                        for callback_label in [process.labels[name].name for name in process.labels.keys()
                                               if process.labels[name].callback and
                                               process.labels[name].name in label_map["matched labels"]]:
                            if intfs[-1].identifier in label_map["matched labels"][callback_label]:
                                label_map["matched labels"][callback_label].remove(intfs[-1].identifier)

        # todo: It is a workaraound but it helps to match random scenarios where a container is never used
        for label in [l for l in label_map["unmatched labels"] if process.labels[l].container]:
            # Check that label is not used except Dispatches and Receives
            acceses = process.accesses(exclude=[Dispatch, Receive], no_labels=True)
            containers = interfaces.containers(category)
            if "%{}%".format(label) not in acceses and len(containers) > 0:
                # Try to match with random container
                self.__add_label_match(interfaces, label_map, process.labels[label], containers[0].identifier)
                label_map["unmatched labels"].remove(label)

        self.logger.info("Matched labels and interfaces:")
        self.logger.info("Number of native interfaces: {}".format(label_map["native interfaces"]))
        self.logger.info("Matched labels:")
        for label in label_map["matched labels"].keys():
            self.logger.info("{} --- {}".
                             format(label, str(label_map["matched labels"][label])))
        self.logger.info("Unmatched labels:")
        for label in label_map["unmatched labels"]:
            self.logger.info(label)
        self.logger.info("Matched callbacks:")
        for callback in label_map["matched callbacks"]:
            self.logger.info(callback)
        self.logger.info("Uncalled callbacks:")
        for callback in label_map["uncalled callbacks"]:
            self.logger.info(callback)

        return label_map

    def __establish_signal_peers(self, interfaces, process):
        for candidate in [self.__abstr_event_processes[name] for name in self.__abstr_event_processes.keys()]:
            peers = process.get_available_peers(candidate)

            # Be sure that process have not been added yet
            peered_processes = set()
            for subprocess in [process.actions[name] for name in process.actions.keys()
                               if (isinstance(process.actions[name], Receive) or
                                   isinstance(process.actions[name], Dispatch))
                               and len(process.actions[name].peers) > 0]:
                peered_processes.update([peer["process"] for peer in subprocess.peers
                                         if peer["process"].name == candidate.name])

            # Try to add process
            if peers and len(peered_processes) == 0:
                self.logger.debug("Establish signal references between process {} with category {} and process {} with "
                                  "category {}".
                                  format(process.name, process.category, candidate.name, candidate.category))
                new = self.__add_process(interfaces, candidate, process.category, model=False, label_map=None,
                                         peer=process)
                if new and (len(new.unmatched_receives) > 0 or len(new.unmatched_dispatches) > 0):
                    self.__establish_signal_peers(interfaces, new)

    def __resolve_interface(self, interfaces, interface, string, process=None, action=None):
        tail = string.split(".")
        # todo: get rid of leading dot and support arrays
        if len(tail) == 1:
            raise RuntimeError("Cannot resolve interface for access '{}'".format(string))
        else:
            tail = tail[1:]

        if issubclass(type(interface), Interface):
            matched = [interface]
        elif isinstance(interface, str) and interface in interfaces.interfaces:
            matched = [interfaces.get_intf(interface)]
        elif isinstance(interface, str) and interface not in interfaces.interfaces:
            return None
        else:
            raise TypeError("Expect Interface object but not {}".format(str(type(interface))))

        # Be sure the first interface is a container
        if not isinstance(matched[-1], Container) and len(tail) > 0:
            return None

        # Collect interface list
        for index in range(len(tail)):
            field = tail[index]

            # Match using a container field name
            intf = [matched[-1].field_interfaces[name] for name in matched[-1].field_interfaces.keys()
                    if name == field]

            # Match using an identifier
            if len(intf) == 0:
                intf = [matched[-1].field_interfaces[name] for name in matched[-1].field_interfaces.keys()
                        if matched[-1].field_interfaces[name].short_identifier == field]

            # Math using an interface role
            if process and action and isinstance(action, Call) and len(intf) == 0 and self.__roles_map and \
                    field in self.__roles_map:
                intf = [matched[-1].field_interfaces[name] for name in matched[-1].field_interfaces.keys()
                        if matched[-1].field_interfaces[name].short_identifier in self.__roles_map[field] and
                        isinstance(matched[-1].field_interfaces[name], Callback)]

                # Filter by retlabel
                if action.retlabel and len(intf) > 0:
                    ret_label, ret_tail = process.extract_label_with_tail(action.retlabel)
                    if ret_tail == '' and ret_label and len(ret_label.declarations) > 0:
                        intf = [i for i in intf if len([r for r in ret_label.declarations
                                                        if i.declaration.points.return_value.compare(r)]) > 0]
                    else:
                        intf = []

                # filter parameters
                if len(intf) > 0:
                    # Collect parameters with declarations
                    param_match = []
                    for parameter in action.parameters:
                        p_label, p_tail = process.extract_label_with_tail(parameter)

                        if p_tail == '' and p_label and len(p_label.declarations) > 0:
                            param_match.append(p_label.declarations)

                    # Match parameters
                    new_intf = []
                    for interface in intf:
                        suits = 0
                        for indx in range(len(param_match)):
                            found = 0
                            for param in interface.declaration.points.parameters[indx:]:
                                for option in param_match[indx]:
                                    if option.compare(param):
                                        found += 1
                                        break
                                if found:
                                    break
                            if found:
                                suits += 1
                        if suits == len(param_match):
                            new_intf.append(interface)
                    intf = new_intf

            if len(intf) == 0:
                return None
            else:
                if index == (len(tail) - 1) or isinstance(intf[-1], Container):
                    matched.append(intf[-1])
                else:
                    return None

        self.logger.debug("Resolve string '{}' as '{}'".format(string, str(matched)))
        return matched

    def __resolve_accesses(self, interfaces):
        self.logger.info("Convert interfaces accesses to expressions on base of containers and their fields")
        for process in self.model_processes + self.event_processes:
            self.logger.debug("Analyze subprocesses of process {!r} having category {!r}".
                              format(process.name, process.category))

            # Get empty keys
            accesses = process.accesses()

            # Fill it out
            original_accesses = list(accesses.keys())
            for access in original_accesses:
                label, tail = process.extract_label_with_tail(access)

                if not label:
                    raise ValueError("Expect a label in {!r} access in process {!r} description".
                                     format(access, process.name))
                else:
                    if len(label.interfaces) > 0:
                        for interface in label.interfaces:
                            new = AbstractAccess(access)
                            new.label = label

                            # Add label access if necessary
                            label_access = "%{}%".format(label.name)
                            if label_access not in original_accesses:
                                # Add also label itself
                                laccess = AbstractAccess(label_access)
                                laccess.label = label
                                laccess.interface = interfaces.get_intf(interface)
                                laccess.list_interface = [interfaces.get_intf(interface)]
                                laccess.list_access = [label.name]

                                if laccess.expression not in accesses:
                                    accesses[laccess.expression] = [laccess]
                                elif laccess.interface not in [a.interface for a in accesses[laccess.expression]]:
                                    accesses[laccess.expression].append(laccess)

                            # Calculate interfaces for tail
                            if len(tail) > 0:
                                callback_actions = [a for a in process.calls if a.callback == access]
                                options = []
                                if len(callback_actions) > 0:
                                    options = []
                                    for action in callback_actions:
                                        options.append(self.__resolve_interface(interfaces, interface, tail, process,
                                                                                action))
                                else:
                                    options.append(self.__resolve_interface(interfaces, interface, tail))

                                for intfs in (o for o in options if isinstance(o, list) and len(o) > 0):
                                    list_access = []
                                    for index, par in enumerate(intfs):
                                        if index == 0:
                                            list_access.append(label.name)
                                        else:
                                            field = list(intfs[index - 1].field_interfaces.keys()
                                                         )[list(intfs[index - 1].field_interfaces.values()).
                                                           index(par)]
                                            list_access.append(field)
                                    new.interface = intfs[-1]
                                    new.list_access = list_access
                                    new.list_interface = intfs
                            else:
                                new.interface = interfaces.get_intf(interface)
                                new.list_access = [label.name]
                                new.list_interface = [interfaces.get_intf(interface)]

                            # Complete list accesses if possible
                            if new.interface:
                                new_tail = [new.interface]
                                to_process = [new.interface]
                                while len(to_process) > 0:
                                    interface = to_process.pop()
                                    category = new.interface.category

                                    for container in interfaces.containers(category):
                                        if container.weak_contains(interface) and container not in new_tail:
                                            new_tail.append(container)
                                            to_process.append(container)
                                            break
                                new_tail.reverse()
                                new.complete_list_interface = new_tail

                            accesses[access].append(new)
                    elif access not in accesses or len(accesses[access]) == 0:
                        new = AbstractAccess(access)
                        new.label = label
                        new.list_access = [label.name]
                        accesses[access].append(new)

                        # Add also label itself
                        label_access = "%{}%".format(label.name)
                        if label_access not in original_accesses:
                            laccess = AbstractAccess(label_access)
                            laccess.label = label
                            laccess.list_access = [label.name]
                            accesses[laccess.expression] = [laccess]

            # Save back updates collection of accesses
            process.accesses(accesses)

    def __refine_processes(self):
        del_flag = True

        while del_flag:
            del_flag = False
            delete = []

            for process in self.event_processes:
                # Check replicative signals
                replicative = [process.actions[a] for a in process.actions if isinstance(process.actions[a], Receive)
                               and process.actions[a].replicative]
                if len(replicative) > 0:
                    # This is an ordinary process that should be registered and if it cannot be so, then we can safely
                    # remove it
                    if any([a for a in replicative if len(a.peers) == 0]):
                        # Remove the process from the collection
                        delete.append(process)

                        # Remove it from all the peers
                        for action in [process.actions[a] for a in process.actions if
                                       isinstance(process.actions[a], Receive) or
                                       isinstance(process.actions[a], Dispatch)]:
                            for peer in action.peers:
                                peer_action = peer['subprocess']
                                indexes = []
                                for index, pr in enumerate(peer_action.peers):
                                    if pr['process'].identifier == process.identifier:
                                        indexes.append(index)

                                for index in indexes:
                                    del peer_action.peers[index]

            for p in delete:
                self.logger.info("Remove process {!r} of cantegory {!r} as it cannot be registered".
                                 format(p.name, p.category))
                self.event_processes.remove(p)

        return
