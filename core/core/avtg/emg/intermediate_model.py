import copy

from core.avtg.emg.common.signature import import_signature
from core.avtg.emg.common.interface import Interface, Callback, Resource, Container
from core.avtg.emg.common.process import Access, Process, Label, Call, CallRetval, Subprocess, Condition, \
    rename_subprocess


class ProcessModel:

    def __init__(self, logger, models, processes):
        self.logger = logger
        self.__abstr_model_processes = models
        self.__abstr_event_processes = processes
        self.model_processes = []
        self.event_processes = []
        self.entry_process = None

    def generate_event_model(self, analysis):
        # todo: should work with multi-module analysis (issues #6558, #6563)
        self.logger.info("Generate model processes for Init and Exit module functions")
        self.__generate_entry(analysis)

        # Generate intermediate model
        self.logger.info("Generate an intermediate model")
        self.__select_processes_and_models(analysis)

        # Finish entry point process generation
        self.__finish_entry()

        # Fill all signatures carefully
        self.logger.info("Assign process signatures")
        self.__assign_signatures(analysis)

        # Convert callback access according to container fields
        self.logger.info("Determine particular interfaces and their implementations for each label or its field")
        self.__resolve_accesses(analysis)

    def __generate_entry(self, analysis):
        # todo: Implement multimodule processes creation (issues #6563, #6571, #6558)
        self.logger.info("Generate artificial process description to call Init and Exit module functions 'EMGentry'")
        ep = Process("EMGentry")
        ep.category = "entry"
        self.entry_process = ep

        # Generate init subprocess
        init_subprocess = Call('init')
        init_subprocess.callback = "%init%"

        if len(analysis.inits) == 0:
            raise RuntimeError('Module does not have Init function')
        # todo: Add none instead of particular name (relevant to #6571)
        init_name = list(analysis.inits.values())[0]
        init_label = Label('init')
        init_label.value = "& {}".format(init_name)
        init_label.prior_signature = import_signature("int (*f)(void)")
        self.logger.debug("Found init function {}".format(init_name))

        ret_label = Label('ret')
        ret_label.prior_signature = import_signature("int label")
        ret_init = CallRetval('ret_init')
        ret_init.retlabel = "%ret%"
        ret_init.callback = init_subprocess.callback

        # Generate exit subprocess
        exit_subprocess = Call('exit')
        exit_subprocess.callback = "%exit%"

        exit_label = Label('exit')
        exit_label.prior_signature = import_signature("void (*f)(void)")
        # todo: Add none instead of particular name (relevant to #6571)
        if len(analysis.exits) != 0:
            exit_name = list(analysis.exits.values())[0]
            exit_label.value = "& {}".format(exit_name)
            self.logger.debug("Found exit function {}".format(exit_name))
        else:
            self.logger.debug("There is no exit function found")
            exit_label.value = None

        ep.labels['init'] = init_label
        ep.labels['exit'] = exit_label
        ep.labels['ret'] = ret_label
        ep.actions['init'] = init_subprocess
        ep.actions['exit'] = exit_subprocess
        ep.actions['ret_init'] = ret_init
        self.logger.debug("Artificial process for invocation of Init and Exit module functions is generated")

    def __finish_entry(self):
        self.logger.info("Add signal dispatched for that processes which have no known registration and deregistration"
                         " kernel functions")
        # Retval check
        # todo: it can be done much, much better (relevant to issue #6566)
        dispatches = ['[init_success]']
        # All default registrations and then deregistrations
        names = [name for name in self.entry_process.actions if name not in ["init", "exit"] and
                 self.entry_process.actions[name].type == "dispatch"]
        for name in names:
            self.entry_process.actions[name].broadcast = True
        names.sort()
        names.reverse()
        dispatches.extend(["[@{}]".format(name) for name in names])

        # Generate conditions
        success = Condition('init_success', {})
        success.type = "condition"
        success.condition = ["%ret% == 0"]
        self.entry_process.actions['init_success'] = success

        failed = Condition('init_failed', {})
        failed.type = "condition"
        failed.condition = ["%ret% != 0"]
        self.entry_process.actions['init_failed'] = failed

        stop = Condition('stop', {})
        stop.type = "condition"
        stop.statements = ["ldv_check_final_state();"]
        self.entry_process.actions['stop'] = stop

        none = Condition('none', {})
        none.type = "condition"
        self.entry_process.actions['none'] = none

        # Add subprocesses finally
        self.entry_process.process = "[init].(ret_init).(<init_failed>.<stop> | <init_success>.({} | <none>).[exit]." \
                                      "<stop>)".format('.'.join(dispatches))

    def __select_processes_and_models(self, analysis):
        # Import necessary kernel models
        self.logger.info("First, add relevant models of kernel functions")
        self.__import_kernel_models(analysis)

        for category in analysis.categories:
            uncalled_callbacks = analysis.uncalled_callbacks(category)
            self.logger.debug("There are {} callbacks in category {}".format(len(uncalled_callbacks), category))

            if uncalled_callbacks:
                self.logger.info("Try to find processes to call callbacks from category {}".format(category))
                new = self.__choose_processes(analysis, category)

                # Sanity check
                self.logger.info("Check again how many callbacks are not called still in category {}".format(category))
                uncalled_callbacks = analysis.uncalled_callbacks(category)
                if uncalled_callbacks:
                    names = str([callback.identifier for callback in uncalled_callbacks])
                    raise RuntimeError("There are callbacks from category {} which are not called at all in the "
                                       "model: {}".format(category, names))

                if len(new.unmatched_dispatches) > 0 or len(new.unmatched_receives) > 0:
                    self.logger.info("Added process {} have unmatched signals, need to find factory or registration "
                                     "and deregistration functions".format(new.name))
                    self.__establish_signal_peers(analysis, new)
            else:
                self.logger.info("Ignore interface category {}, since it does not have callbacks to call".
                                 format(category))

    def __import_kernel_models(self, analysis):
        for function in self.__abstr_model_processes:
            if function in analysis.kernel_functions:
                self.logger.debug("Add model of function '{}' to an environment model".format(function))
                new_process = self.__add_process(analysis, self.__abstr_model_processes[function], model=True)
                new_process.category = "kernel models"

                self.logger.debug("Assign label interfaces according to function parameters for added process {} "
                                  "with an identifier {}".format(new_process.name, new_process.identifier))
                for label in new_process.labels:
                    if new_process.labels[label].parameter and not new_process.labels[label].prior_signature:
                        for index in range(len(analysis.kernel_functions[function].param_interfaces)):
                            parameter = analysis.kernel_functions[function].param_interfaces[index]
                            signature = analysis.kernel_functions[function].declaration.parameters[index]
                            if parameter and parameter.identifier in new_process.labels[label].interfaces:
                                self.logger.debug("Set label {} signature according to interface {}".
                                                  format(label, parameter.identifier))
                                new_process.labels[label].set_declaration(parameter.identifier, signature)
                            else:
                                raise ValueError("Cannot find suitable signature for label '{}' at function model '{}'".
                                                 format(label, function))

    def __choose_processes(self, analysis, category):
        estimations = {}
        for process in [self.__abstr_event_processes[name] for name in self.__abstr_event_processes]:
            self.logger.debug("Estimate correspondence between  process {} and category {}".
                              format(process.name, category))
            estimations[process.name] = self.__match_labels(analysis, process, category)

        self.logger.info("Choose process to call callbacks from category {}".format(category))
        # First random
        best_process = self.__abstr_event_processes[[name for name in estimations if estimations[name]][0]]
        best_map = estimations[best_process.name]

        for process in [self.__abstr_event_processes[name] for name in estimations]:
            label_map = estimations[process.name]
            if label_map and len(label_map["matched calls"]) > 0 and len(label_map["unmatched labels"]) == 0:
                self.logger.info("Matching process {} for category {}, it has:".format(process.name, category))
                self.logger.info("Matching labels: {}".format(str(label_map["matched labels"])))
                self.logger.info("Unmatched labels: {}".format(str(label_map["unmatched labels"])))
                self.logger.info("Matched callbacks: {}".format(str(label_map["matched callbacks"])))
                self.logger.info("Unmatched callbacks: {}".format(str(label_map["unmatched callbacks"])))
                self.logger.info("Matched calls: {}".format(str(label_map["matched calls"])))
                self.logger.info("Native interfaces: {}".format(str(label_map["native interfaces"])))

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
                    self.logger.debug("Set process {} for category {} as the best one at the moment".
                                      format(process.name, category))

        if not best_process:
            raise RuntimeError("Cannot find suitable process in event categories specification for category {}"
                               .format(category))
        else:
            new = self.__add_process(analysis, best_process, category, False, best_map)
            new.category = category
            self.logger.debug("Finally choose process {} for category {} as the best one".
                              format(best_process.name, category))
            return new

    def __add_process(self, analysis, process, category=None, model=False, label_map=None, peer=None):
        self.logger.info("Add process {} to the model".format(process.name))
        self.logger.debug("Make copy of process {} before adding it to the model".format(process.name))
        new = copy.deepcopy(process)

        # todo: Assign category for each new process not even for that which have callbacks (issue #6564)
        new.identifier = len(self.model_processes) + len(self.event_processes)
        self.logger.info("Finally add process {} to the model".
                         format(process.name))

        if model and not category:
            new.category = 'kernel model'
            self.model_processes.append(new)
        elif not model and category:
            new.category = category
            self.event_processes.append(new)
        else:
            raise ValueError('Provide either model or category arguments but not simultaneously')

        if label_map:
            self.logger.debug("Set interfaces for given labels")
            for label in label_map["matched labels"]:
                for interface in [analysis.interfaces[name] for name in label_map["matched labels"][label]]:
                    if type(interface) is Container:
                        new.labels[label].set_declaration(interface.identifier, interface.declaration.take_pointer)
                    else:
                        new.labels[label].set_declaration(interface.identifier, interface.declaration)

        if peer:
            self.logger.debug("Match signals with signals of process {} with identifier {}".
                              format(peer.name, peer.identifier))
            new.peer_with_process(peer, True)

        self.logger.info("Check is there exist any dispatches or receives after process addiction to tie".
                         format(process.name))
        self.__normalize_model(analysis)
        return new

    def __normalize_model(self, analysis):
        # Peer processes with models
        self.logger.info("Try to establish connections between process dispatches and receivings")
        for model in self.model_processes:
            for process in self.event_processes:
                self.logger.debug("Analyze signals of processes {} and {} in the model with identifiers {} and {}".
                                  format(model.name, process.name, model.identifier, process.identifier))
                model.peer_with_process(process, True)

        # Peer processes with each other
        for index1 in range(len(self.event_processes)):
            p1 = self.event_processes[index1]
            for index2 in range(index1 + 1, len(self.event_processes)):
                p2 = self.event_processes[index2]
                self.logger.debug("Analyze signals of processes {} and {}".format(p1.name, p2.name))
                p1.peer_with_process(p2, True)

        self.logger.info("Check which callbacks can be called in the intermediate environment model")
        self.__called_callbacks = []
        self.__uncalled_callbacks = []
        for process in [process for process in self.model_processes] +\
                       [process for process in self.event_processes]:
            self.logger.debug("Check process callback calls at process {} with category {}".
                              format(process.name, process.category))

            for callback_name in set([cb.callback for cb in process.callbacks]):
                # todo: refactoring #6565
                label, tail = process.extract_label_with_tail(callback_name)

                if len(label.interfaces) > 0:
                    for interface in [analysis.interfaces[name] for name in label.interfaces]:
                        if interface.container and len(tail) > 0:
                            intfs = self.__resolve_interface(interface, tail)
                            if intfs and intfs[-1] not in self.__called_callbacks:
                                self.logger.debug("Callback {} can be called in the model".
                                                  format(intfs[-1].identifier))
                                self.__called_callbacks.append(intfs[-1])
                            else:
                                self.logger.warning("Cannot resolve callback '{}' in description of process '{}'".
                                                    format(callback_name, process.name))
                        elif interface.callback and interface not in self.__called_callbacks:
                            self.logger.debug("Callback {} can be called in the model".
                                              format(interface.identifier))
                            self.__called_callbacks.append(interface)
                        else:
                            raise ValueError("Cannot resolve callback '{}' in description of process '{}'".
                                             format(callback_name, process.name))

    def __add_label_match(self, label_map, label, interface):
        if label.name not in label_map["matched labels"]:
            self.logger.debug("Match label '{}' with interface '{}'".format(label.name, interface))
            label_map["matched labels"][label.name] = [interface]
        else:
            if interface not in label_map["matched labels"][label.name]:
                label_map["matched labels"][label.name].append(interface)

    def __match_labels(self, analysis, process, category):
        self.logger.info("Try match process {} with interfaces of category {}".format(process.name, category))
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
        nc = []
        ni = []
        for label in process.labels.values():
            for intf in label.interfaces:
                intf_category, short_identifier = intf.split(".")
                if intf_category not in nc:
                    nc.append(intf_category)

                if intf in analysis.interfaces and intf not in ni and intf_category == category:
                    ni.append(intf)
                    self.__add_label_match(label_map, label, intf)
            label_map["native interfaces"] = len(ni)

        # Stop analysis if process tied with another category
        if len(nc) > 0 and category not in nc:
            self.logger.debug("Process {} is intended to be matched with a category from the list: {}".
                              format(process.name, str(nc)))
            return None

        # todo: Code below doesn't choose best match it is a bit greedy
        # todo: Code below doesb't support arrays in access sequences
        success_on_iteration = True
        while success_on_iteration:
            self.logger.debug("Begin comparison iteration")
            success_on_iteration = False
            old_size = len(label_map["matched callbacks"]) + len(label_map["matched labels"])

            # Match interfaces and containers
            for action in [act for act in process.actions.values() if type(act) is Call]:
                self.logger.debug("Match callback call {} with interfaces".format(action.callback))
                label, tail = process.extract_label_with_tail(action.callback)

                if label.name not in label_map["matched labels"]:
                    for interface in label.interfaces:
                        if interface in analysis.interfaces and analysis.interfaces[interface].category == category:
                            self.__add_label_match(label_map, label, interface)
                elif len(label.interfaces) == 0 and not label.prior_signature and tail and label.container and \
                                label.name not in label_map["matched labels"]:
                    for container in [analysis.categories[category]["containers"][name] for name
                                      in analysis.categories[category]["containers"]]:
                        interfaces = self.__resolve_interface(analysis, container, tail)
                        self.logger.debug("Trying to match label {} with a container {}".
                                          format(label.name, container.identifier))
                        if interfaces:
                            self.__add_label_match(label_map, label, container.identifier)

                self.logger.debug("Try to match parameters of callback {} in process {} with interfaces of category"
                                  " {}".format(action.callback, process.name, category))
                functions = []
                if label.name in label_map["matched labels"] and label.container:
                    for intf in label_map["matched labels"][label.name]:
                        intfs = self.__resolve_interface(analysis, analysis.interfaces[intf], tail)
                        if intfs:
                            functions.append(intfs[-1])
                elif label.name in label_map["matched labels"] and label.callback:
                    if type(label_map["matched labels"][label.name]) is list:
                        functions.extend([analysis.interfaces[name] for name in
                                         label_map["matched labels"][label.name]])
                    else:
                        functions.append(analysis.interfaces[label_map["matched labels"][label.name]])

                for function in functions:
                    if len(action.parameters) <= len(function.param_interfaces):
                        self.logger.debug("Try to match parameters of callback {}".
                                          format(function.identifier))
                        for parameter in action.parameters:
                            pl = process.extract_label(parameter)

                            for pr in [pr for pr in function.param_interfaces if pr]:
                                if pl.resource and (not pl.callback or (type(pr) is Callback and pl.callback))\
                                        and (not pl.container or (type(pr) is Container and pl.container)):
                                    unmatched_resources = [re for re in process.resources
                                                           if re.name not in label_map["matched labels"]]
                                    if len(unmatched_resources) == 0 or \
                                            (len(unmatched_resources) > 0 and pl in unmatched_resources):
                                        self.__add_label_match(label_map, pl, pr.identifier)

                    containers = [cn for cn in process.containers
                                  if cn.name not in label_map["matched labels"]]
                    self.logger.debug("Try to match containers for callback {}".format(function))
                    containers_intfs = [cn for cn in analysis.containers(category) if cn.contains(function)]
                    for intf in containers_intfs:
                        for container in containers:
                            self.__add_label_match(label_map, container, intf.identifier)

            # After containers are matched try to match callbacks
            matched_containers = [cn for cn in process.containers if cn.name in label_map["matched labels"]]
            unmatched_callbacks = [cl for cl in process.callbacks if cl.name not in label_map["matched labels"]]
            if len(matched_containers) > 0 and len(unmatched_callbacks) > 0:
                for callback in unmatched_callbacks:
                    for container in matched_containers:
                        for container_intf in [analysis.interfaces[intf] for intf in
                                               label_map["matched labels"][container.name]]:
                            for field in container_intf.fields.values():
                                name = "{}.{}".format(category, field)
                                if name in analysis.interfaces and analysis.interfaces[name].callback:
                                    self.__add_label_match(label_map, callback, name)
            elif len(unmatched_callbacks) > 0:
                for callback in unmatched_callbacks:
                    for intf in analysis.callbacks(category):
                        self.__add_label_match(label_map, callback, intf.identifier)

            # Discard unmatched labels
            label_map["unmatched labels"] = [label for label in process.labels
                                             if label not in label_map["matched labels"] and
                                             len(process.labels[label].interfaces) == 0 and not
                                             process.labels[label].prior_signature]

            # Discard unmatched callbacks
            label_map["unmatched callbacks"] = []
            label_map["matched callbacks"] = []

            for action in [act for act in process.actions.values() if type(act) is Call]:
                label, tail = process.extract_label_with_tail(action.callback)
                if label.callback and label.name not in label_map["matched labels"] \
                        and action.callback not in label_map["unmatched callbacks"]:
                    label_map["unmatched callbacks"].append(action.callback)
                elif label.callback and label.name in label_map["matched labels"]:
                    callbacks = label_map["matched labels"][label.name]

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
                        intfs = self.__resolve_interface(analysis, analysis.interfaces[intf], tail)

                        if not intfs and action.callback not in label_map["unmatched callbacks"]:
                            label_map["unmatched callbacks"].append(action.callback)
                        elif intfs and action.callback not in label_map["matched callbacks"]:
                            label_map["matched callbacks"].append(intfs[-1].identifier)
                            if action.callback not in label_map["matched calls"]:
                                label_map["matched calls"].append(action.callback)

            # Discard uncalled callbacks and recalculate it
            label_map["uncalled callbacks"] = [cb.identifier for cb in analysis.callbacks(category)
                                               if cb.identifier not in label_map["matched callbacks"]]

            if len(label_map["matched callbacks"]) + len(label_map["matched labels"]) - old_size > 0:
                success_on_iteration = True

        # Discard unmatched callbacks
        for action in [act for act in process.actions.values() if type(act) is Call]:
            label, tail = process.extract_label_with_tail(action.callback)
            if label.container and tail and label.name in label_map["matched labels"]:
                for intf in label_map["matched labels"][label.name]:
                    intfs = self.__resolve_interface(analysis, analysis.interfaces[intf], tail)
                    if intfs:
                        # Discard general callbacks match
                        for callback_label in [label.name for label in process.labels.values() if label.callback and
                                               label.name in label_map["matched labels"]]:
                            if intfs[-1].identifier in label_map["matched labels"][callback_label]:
                                index = label_map["matched labels"][callback_label].index(intfs[-1].identifier)
                                del label_map["matched labels"][callback_label][index]

        self.logger.info("Matched labels and interfaces:")
        self.logger.info("Number of native interfaces: {}".format(label_map["native interfaces"]))
        self.logger.info("Matched labels:")
        for label in label_map["matched labels"]:
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

    def __establish_signal_peers(self, analysis, process):
        for candidate in [self.__abstr_event_processes[name] for name in self.__abstr_event_processes]:
            peers = process.peer_with_process(candidate)

            # Be sure that process have not been added yet
            peered_processes = []
            for subprocess in [subp for subp in process.actions.values() if subp.peers and len(subp.peers) > 0]:
                peered_processes.extend([peer["process"] for peer in subprocess.peers
                                         if peer["process"].name == candidate.name])

            # Try to add process
            if peers and len(peered_processes) == 0:
                self.logger.debug("Establish signal references between process {} with category {} and process {} with "
                                  "category {}".
                                  format(process.name, process.category, candidate.name, candidate.category))
                new = self.__add_process(analysis, candidate, process.category, model=False, label_map=None, peer=process)
                if len(new.unmatched_receives) > 0 or len(new.unmatched_dispatches) > 0:
                    self.__establish_signal_peers(analysis, new)

        if len(process.unmatched_receives) > 0:
            for receive in process.unmatched_receives:
                if receive.name == "register":
                    self.logger.info("Generate default registration for process {} with category {}".
                                     format(process.name, process.category))
                    self.__add_default_dispatch(process, receive)
                elif receive.name == "deregister":
                    self.logger.info("Generate default deregistration for process {} with category {}".
                                     format(process.name, process.category))
                    self.__add_default_dispatch(process, receive)
                else:
                    self.logger.warning("Signal {} cannot be received by process {} with category {}, "
                                        "since nobody can send it".
                                        format(receive.name, process.name, process.category))
        for dispatch in process.unmatched_dispatches:
            self.logger.warning("Signal {} cannot be send by process {} with category {}, "
                                "since nobody can receive it".format(dispatch.name, process.name, process.category))

    def __add_default_dispatch(self, process, receive):
        # Change name
        new_subprocess_name = "{}_{}_{}".format(receive.name, process.name, process.identifier)
        rename_subprocess(process, receive.name, new_subprocess_name)

        # Deregister dispatch
        self.logger.debug("Generate copy of receive {} and make dispatch from it".format(receive.name))
        new_dispatch = copy.deepcopy(receive)
        new_dispatch.type = "dispatch"

        # Peer these subprocesses
        new_dispatch.peers.append(
            {
                "process": process,
                "subprocess": process.actions[new_dispatch.name]
            })
        process.actions[new_dispatch.name].peers.append(
            {
                "process": self.entry_process,
                "subprocess": new_dispatch
            })

        self.logger.debug("Add dispatch {} to process {}".format(new_dispatch.name, self.entry_process.name))
        self.entry_process.actions[new_dispatch.name] = new_dispatch

        # todo: implement it taking into account that each parameter may have sevaral implementations
        # todo: relevant to issue #6566
        # Add labels if necessary
        #for index in range(len(new_dispatch.parameters)):
        #    parameter = new_dispatch.parameters[index]
        #
        #    # Get label
        #    label, tail = process.extract_label_with_tail(parameter)
        #
        #    # Copy label to add to dispatcher process
        #    new_label_name = "{}_{}_{}".format(process.name, label.name, process.identifier)
        #    if new_label_name not in self.entry_process.labels:
        #        new_label = copy.deepcopy(label)
        #        new_label.name = new_label_name
        #        self.logger.debug("To process {} add new label {}".format(self.entry_process.name, new_label_name))
        #        self.entry_process.labels[new_label.name] = new_label
        #    else:
        #        self.logger.debug("Process {} already has label {}".format(self.entry_process.name, new_label_name))
        #
        #    # Replace parameter
        #    new_dispatch.parameters[index] = parameter.replace(label.name, new_label_name)
        new_dispatch.parameters = []
        receive.parameters = []

        # Replace condition
        # todo: do this according to parameters (relevant to issue #6566)
        if new_dispatch.condition:
            new_dispatch.condition = None
            process.actions[new_dispatch.name].condition = None

    def __resolve_interface(self, analysis, interface, string):
        tail = string.split(".")
        # todo: get rid of leading dot
        if len(tail) == 1:
            raise RuntimeError("Cannot resolve interface for access '{}'".format(string))
        else:
            tail = tail[1:]

        if issubclass(type(interface), Interface):
            matched = [interface]
        elif type(interface) is str and interface in analysis.interfaces:
            matched = [analysis.interfaces[interface]]
        elif type(interface) is str and interface not in analysis.interfaces:
            return None
        else:
            raise TypeError("Expect Interface object but not {}".format(str(type(interface))))

        for index in range(len(tail)):
            field = tail[index]
            if field not in matched[-1].field_interfaces:
                return None
            else:
                if index == (len(tail) - 1) or type(matched[-1].field_interfaces[field]) is Container:
                    matched.append(matched[-1].field_interfaces[field])
                else:
                    return None

        self.logger.debug("Resolve string '{}' as '{}'".format(string, str(matched)))
        return matched

    def __assign_signatures(self, analysis):
        for process in self.model_processes + self.event_processes + [self.entry_process]:
            self.logger.info("Assign signatures of process {} with category {} to labels with given interfaces".
                             format(process.name, process.category))
            for label in [process.labels[name] for name in process.labels]:
                if label.interfaces:
                    for interface in label.interfaces:
                        # Assign matched signature
                        self.logger.debug("Add signature {} to a label {}".
                                          format(analysis.interfaces[interface].signature.expression, label.name))
                        label.signature(analysis.interfaces[interface].signature, interface)

        for process in self.model_processes + self.event_processes + [self.entry_process]:
            self.logger.info("Assign signatures of process {} with category {} to labels according to signal "
                             "parameters".format(process.name, process.category))

            # Analyze peers
            for subprocess in [process.actions[name] for name in process.actions
                               if process.actions[name].type in ["dispatch", "receive"]]:
                for peer in subprocess.peers:
                    if peer["process"].name in self.__abstr_model_processes:
                        for index in range(len(peer["subprocess"].parameters)):
                            peer_parameter = peer["subprocess"].parameters[index]
                            peer_label = peer["process"].extract_label(peer_parameter)

                            parameter = subprocess.parameters[index]
                            label = process.extract_label(parameter)

                            # Set new interfaces from peer signals
                            if peer_label.interfaces:
                                for interface in peer_label.interfaces:
                                    self.logger.debug("Add signature {} to a label {}".
                                                      format(peer_label.signature(None, interface).expression,
                                                             label.name))
                                    label.signature(peer_label.signature(None, interface), interface)
                            elif peer_label.prior_signature:
                                peer_signature = peer_label.prior_signature
                                self.logger.debug("Add signature {} to a label {}".
                                                  format(peer_signature.expression, label.name))
                                label.signature(peer_signature)
                    else:
                        for index in range(len(peer["subprocess"].parameters)):
                            peer_parameter = peer["subprocess"].parameters[index]
                            peer_label = peer["process"].extract_label(peer_parameter)

                            parameter = subprocess.parameters[index]
                            label = process.extract_label(parameter)

                            # Set new interfaces from peer signals
                            if peer_label.interfaces:
                                for interface in peer_label.interfaces:
                                    self.logger.debug("Add signature {} to a label {}".
                                                      format(peer_label.signature(None, interface).expression,
                                                             label.name))
                                    label.signature(peer_label.signature(None, interface), interface)
                            elif peer_label.prior_signature:
                                peer_signature = peer_label.prior_signature
                                self.logger.debug("Add signature {} to a label {}".
                                                  format(peer_signature.expression, label.name))
                                label.signature(peer_signature)

                            # Set new interfaces for peer signals
                            if label.interfaces:
                                for interface in label.interfaces:
                                    self.logger.debug("Add signature {} to a label {} of process {}".
                                                      format(label.signature(None, interface).expression,
                                                             peer_label.name, peer["process"].name))
                                    peer_label.signature(label.signature(None, interface), interface)
                            elif label.prior_signature:
                                label_signature = label.prior_signature
                                self.logger.debug("Add signature {} to a label {} of process {}".
                                                  format(label_signature.expression, peer_label.name,
                                                         peer["process"].name))
                                peer_label.signature(label_signature)

        for process in self.model_processes + self.event_processes + [self.entry_process]:
            # Assign interface signatures
            self.logger.debug("Assign pointer flag of process {} with category {} to labels signatures".
                              format(process.name, process.category))
            for label in process.labels.values():
                if label.interfaces:
                    for interface in label.interfaces:
                        if label.signature(None, interface).type_class in ["struct", "function"]:
                            label.signature(None, interface).pointer = True

                if label.prior_signature:
                    sign = label.prior_signature
                    if sign.type_class in ["struct", "function"]:
                        sign.pointer = True

    def __resolve_accesses(self, analysis):
        self.logger.info("Convert interfaces access by expressions on base of containers and their fields")
        for process in self.model_processes + self.event_processes + [self.entry_process]:
            self.logger.debug("Analyze subprocesses of process {} with category {}".
                              format(process.name, process.category))

            # Get empty keys
            accesses = process.accesses()

            # Additional accesses
            additional_accesses = accesses

            # Fill it out
            original_accesses = list(accesses.keys())
            for access in original_accesses:
                label, tail = process.extract_label_with_tail(access)

                if not label:
                    raise ValueError("Expect label in {} in access in process description".format(access, process.name))
                else:
                    if label.interfaces:
                        for interface in label.interfaces:
                            new = Access(access)
                            new.label = label

                            # Add label access if necessary
                            label_access = "%{}%".format(label.name)
                            if label_access not in original_accesses:
                                # Add also label itself
                                laccess = Access(label_access)
                                laccess.label = label
                                laccess.interface = analysis.interfaces[interface]
                                laccess.list_interface = [analysis.interfaces[interface]]
                                laccess.list_access = [label.name]

                                if laccess.expression not in accesses:
                                    accesses[laccess.expression] = [laccess]
                                elif laccess.interface not in [a.interface for a in accesses[laccess.expression]]:
                                    accesses[laccess.expression].append(laccess)

                            # Calculate interfaces for tail
                            if len(tail) > 0:
                                intfs = self.__resolve_interface(analysis, interface, tail)
                                if intfs:
                                    list_access = []
                                    for index in range(len(intfs)):
                                        if index == 0:
                                            list_access.append(label.name)
                                        else:
                                            field = list(intfs[index - 1].fields.keys()) \
                                                [list(intfs[index - 1].fields.values()).index(intfs[index].identifier)]
                                            list_access.append(field)
                                    new.interface = intfs[-1]
                                    new.list_access = list_access
                                    new.list_interface = intfs
                                else:
                                    raise ValueError("Cannot resolve access {} with a base interface {} in process {}".
                                                     format(access, interface, process.name))
                            else:
                                new.interface = analysis.interfaces[interface]
                                new.list_access = [label.name]
                                new.list_interface = [analysis.interfaces[interface]]

                            # Complete list accesses if possible
                            if new.interface:
                                new_tail = [new.interface]
                                to_process = [new.interface]
                                while len(to_process) > 0:
                                    interface = to_process.pop()
                                    category = new.interface.category

                                    for container in analysis.categories[category]["containers"].values():
                                        if interface.identifier in list(container.fields.values()):
                                            new_tail.append(container)
                                            to_process.append(container)
                                new_tail.reverse()
                                new.complete_list_interface = new_tail

                            accesses[access].append(new)
                    else:
                        new = Access(access)
                        new.label = label
                        new.list_access = [label.name]
                        accesses[access].append(new)

                        # Add also label itself
                        label_access = "%{}%".format(label.name)
                        if label_access not in original_accesses:
                            laccess = Access(label_access)
                            laccess.label = label
                            laccess.list_access = [label.name]
                            accesses[laccess.expression] = [laccess]

            # Save back updates collection of accesses
            process.accesses(accesses)

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
