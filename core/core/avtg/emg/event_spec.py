import copy

from core.avtg.emg.representations import Signature, Interface, Process, Subprocess, Label, Access, process_parse


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

        self.logger.info("Import processes from provided event categories specification")
        for collection in self.events:
            # Import kernel models
            self.logger.info("Import processes from '{}'".format(collection))
            self.__import_processes(raw, collection)

        # todo: will work with multi-module analysis?
        self.logger.info("Generate model processes for Init and Exit module functions")
        self.__generate_entry()

        # Generate intermediate model
        self.logger.info("Generate an intermediate model")
        self.__select_processes_and_models()

        # Fill all signatures carefully
        self.logger.info("Assign process signatures")
        self.__assign_signatures()

        # Convert callback access according to container fields
        self.logger.info("Determine particular interfaces and their implementations for each label or its field")
        self.resolve_accesses()

    def __import_processes(self, raw, category):
        if "kernel model" in raw:
            for name_list in raw[category]:
                names = name_list.split(", ")
                for name in names:
                    self.logger.debug("Import process which models {}".format(name))
                    process = Process(name, raw[category][name_list])
                    self.events[category][name] = process
        else:
            self.logger.warning("Cannot find 'kernel model' section in event categories specification")

    def __generate_entry(self):
        # todo: Implement multimodule processes creation
        self.logger.info("Generate artificial process description to call Init and Exit module functions 'EMGentry'")
        ep = Process("EMGentry")
        ep.category = "entry"
        self.model["entry"] = ep

        # Generate init subprocess
        init_subprocess = Subprocess('init', {})
        init_subprocess.type = "dispatch"
        init_subprocess.callback = "%init%"
        init_subprocess.parameters = []

        if len(self.analysis.inits) == 0:
            raise RuntimeError('Module does not have Init function')
        init_name = list(self.analysis.inits.values())[0]
        init_label = Label('init')
        init_label.value = "& {}".format(init_name)
        init_label.signature(Signature("int (*%s)(void)"))
        self.logger.debug("Found init function {}".format(init_name))

        ret_label = Label('ret')
        ret_label.signature(Signature("int %s"))
        ret_init = Subprocess('ret_init', {})
        ret_init.type = "receive"
        ret_init.callback_retval = "%ret%"
        ret_init.callback = init_subprocess.callback

        # Generate exit subprocess
        exit_subprocess = Subprocess('exit', {})
        exit_subprocess.type = "dispatch"
        exit_subprocess.callback = "%exit%"
        exit_subprocess.parameters = []

        exit_label = Label('exit')
        exit_label.signature(Signature("void (*%s)(void)".format()))
        if len(self.analysis.exits) != 0:
            exit_name = list(self.analysis.exits.values())[0]
            exit_label.value = "& {}".format(exit_name)
            self.logger.debug("Found exit function {}".format(exit_name))
        else:
            self.logger.debug("Not found exit function")
            exit_label.value = None

        ep.labels['init'] = init_label
        ep.labels['exit'] = exit_label
        ep.labels['ret'] = ret_label
        ep.subprocesses['init'] = init_subprocess
        ep.subprocesses['exit'] = exit_subprocess
        ep.subprocesses['ret_init'] = ret_init
        self.logger.debug("Artificial process for invocation of Init and Exit module functions is generated")

    def __finish_entry(self):
        self.logger.info("Add signal dispatched for that processes which have no known registration and deregistration"
                         " kernel functions")
        # Retval check
        # todo: it can be done much, much better ...
        dispatches = ['[init_success]']
        # All default registrations and then deregistrations
        names = [name for name in self.model["entry"].subprocesses if name not in ["init", "exit"] and
                 self.model["entry"].subprocesses[name].type == "dispatch"]
        for name in names:
            self.model["entry"].subprocesses[name].broadcast = True
        names.sort()
        names.reverse()
        dispatches.extend(["[@{}]".format(name) for name in names])

        # Generate conditions
        success = Subprocess('init_success', {})
        success.type = "condition"
        success.condition = ["%ret% == 0"]
        self.model["entry"].subprocesses['init_success'] = success

        failed = Subprocess('init_failed', {})
        failed.type = "condition"
        failed.condition = ["%ret% != 0"]
        self.model["entry"].subprocesses['init_failed'] = failed

        stop = Subprocess('stop', {})
        stop.type = "condition"
        stop.statements = ["ldv_stop();"]
        self.model["entry"].subprocesses['stop'] = stop

        # Add subprocesses finally
        self.model["entry"].process = "[init].(ret_init).({} | <init_failed>).[exit].<stop>".\
                                      format('.'.join(dispatches))
        self.model["entry"].process_ast = process_parse(self.model["entry"].process)

    def __select_processes_and_models(self):
        # Import necessary kernel models
        self.logger.info("First, add relevant models of kernel functions")
        self.__import_kernel_models()

        for category in self.analysis.categories:
            uncalled_callbacks = self.__get_uncalled_callbacks(category)
            self.logger.debug("There are {} callbacks in category {}".format(len(uncalled_callbacks), category))

            if uncalled_callbacks:
                self.logger.info("Try to find processes to call callbacks from category {}".format(category))
                new = self.__choose_processes(category)

                # Sanity check
                self.logger.info("Check again how many callbacks are not called still in category {}".format(category))
                uncalled_callbacks = self.__get_uncalled_callbacks(category)
                if uncalled_callbacks:
                    names = str([callback.full_identifier for callback in uncalled_callbacks])
                    raise RuntimeError("There are callbacks from category {} which are not called at all in the "
                                       "model: {}".format(category, names))

                if new.unmatched_dispatches or new.unmatched_receives:
                    self.logger.info("Added process {} have unmatched signals, need to find factory or registration "
                                     "and deregistration functions".format(new.name))
                    self.__establish_signal_peers(new)
            else:
                self.logger.info("Ignore interface category {}, since it does not have callbacks to call".
                                 format(category))

        # Finish entry point process generation
        self.__finish_entry()

    def __import_kernel_models(self):
        for function in self.events["kernel model"]:
            if function in self.analysis.kernel_functions:
                self.logger.debug("Add model of function '{}' to an environment model".format(function))
                new_process = self.__add_process(self.events["kernel model"][function], model=True)
                new_process.category = "kernel models"

                self.logger.debug("Assign label interfaces according to function parameters for added process {} "
                                  "with an identifier {}".format(new_process.name, new_process.identifier))
                for label in new_process.labels:
                    if new_process.labels[label].parameter and not new_process.labels[label].signature():
                        for parameter in self.analysis.kernel_functions[function]["signature"].parameters:
                            if parameter.interface and parameter.interface.full_identifier in \
                                    new_process.labels[label].interfaces:
                                self.logger.debug("Set label {} signature according to interface {}".
                                                  format(label, parameter.interface.full_identifier))
                                new_process.labels[label].signature(parameter)
                                new_process.labels[label].signature(parameter, parameter.interface.full_identifier)
                        if not new_process.labels[label].signature():
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

        self.logger.info("Choose process to call callbacks from category {}".format(category))
        # First random
        best_process = self.events["environment processes"][[name for name in estimations if estimations[name]][0]]
        best_map = estimations[best_process.name]

        for process in [self.events["environment processes"][name] for name in estimations]:
            label_map = estimations[process.name]
            if label_map and len(label_map["matched callbacks"]) > 0 and len(label_map["uncalled callbacks"]) == 0 and \
                             len(label_map["unmatched labels"]) == 0:
                self.logger.info("Matching process {} for category {}, it has:".format(process.name, category))
                self.logger.info("Matching labels: {}".format(str(label_map["matched labels"])))
                self.logger.info("Unmatched labels: {}".format(str(label_map["unmatched labels"])))
                self.logger.info("Matched callbacks: {}".format(str(label_map["matched callbacks"])))
                self.logger.info("Unmatched callbacks: {}".format(str(label_map["unmatched callbacks"])))
                self.logger.info("Native interfaces: {}".format(str(label_map["native interfaces"])))

                if label_map["native interfaces"] > best_map["native interfaces"]:
                    do = True
                elif len(label_map["matched callbacks"]) > len(best_map["matched callbacks"]) and \
                        len(label_map["unmatched callbacks"]) <= len(best_map["unmatched callbacks"]):
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
            new = self.__add_process(best_process, False, best_map)
            new.category = category
            self.logger.debug("Finally choose process {} for category {} as the best one".
                              format(best_process.name, category))
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
        self.logger.debug("Make copy of process {} before adding it to the model".format(process.name))
        new = copy.deepcopy(process)

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
                new.labels[label].interfaces = label_map["matched labels"][label]

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
        self.logger.info("Check which callbacks can be called in the intermediate environment model")
        for process in [process for process in self.model["models"]] +\
                       [process for process in self.model["processes"]]:
            self.logger.debug("Check process callback calls at process {} with category {}".
                              format(process.name, process.category))

            called = []
            for callback_name in set([process.subprocesses[name].callback for name in process.subprocesses
                                      if process.subprocesses[name].callback and
                                      process.subprocesses[name].type == "dispatch"]):
                label, tail = process.extract_label_with_tail(callback_name)

                if label.interfaces:
                    for interface in [self.analysis.interfaces[name] for name in label.interfaces]:
                        if interface.container and len(tail) > 0:
                            intfs = self.__resolve_interface(interface, tail)
                            if intfs and intfs[-1] not in called:
                                self.logger.debug("Callback {} can be called in the model".
                                                  format(intfs[-1].full_identifier))
                                intfs[-1].called_in_model = True
                            else:
                                self.logger.warning("Cannot resolve callback '{}' in description of process '{}'".
                                                    format(callback_name, process.name))
                        elif interface.callback and interface not in called:
                            self.logger.debug("Callback {} can be called in the model".
                                              format(interface.full_identifier))
                            interface.called_in_model = True
                        else:
                            raise ValueError("Cannot resolve callback '{}' in description of process '{}'".
                                             format(callback_name, process.name))

    def add_label_match(self, label_map, label, interface):
        if label.name not in label_map["matched labels"]:
            self.logger.debug("Match label '{}' with interface '{}'".format(label.name, interface))
            label_map["matched labels"][label.name] = [interface]
        else:
            if interface not in label_map["matched labels"][label.name]:
                label_map["matched labels"][label.name].append(interface)

    def __match_labels(self, process, category):
        self.logger.info("Try match process {} with interfaces of category {}".format(process.name, category))
        label_map = {
            "matched labels": {},
            "unmatched labels": [],
            "uncalled callbacks": [],
            "matched callbacks": [],
            "unmatched callbacks": [],
            "native interfaces": []
        }

        # Collect native categories first
        nc = []
        for label in process.labels.values():
            if label.interfaces:
                for intf in label.interfaces:
                    intf_category, short_identifier = intf.split(".")
                    nc.append(intf_category)
        if len(nc) > 0 and category not in nc:
            self.logger.debug("Process {} is intended to be matched with a category from the list: {}".
                              format(process.name, str(nc)))
            return None

        # Calculate native interfaces
        ni = []
        for label in process.labels.values():
            if label.interfaces:
                for intf in label.interfaces:
                    if intf in self.analysis.interfaces and self.analysis.interfaces[intf].category == category:
                        ni.append(intf)
                        self.add_label_match(label_map, label, intf)
            label_map["native interfaces"] = len(ni)

        old_size = 0
        new_size = 0
        start = True
        while (new_size - old_size) > 0 or start:
            self.logger.debug("Begin comparison iteration")

            # Match interfaces and containers
            for subprocess in [process.subprocesses[name] for name in process.subprocesses
                               if process.subprocesses[name].callback and
                               process.subprocesses[name].type == "dispatch"]:
                self.logger.debug("Match callback call {} with interfaces".format(subprocess.callback))
                label, tail = process.extract_label_with_tail(subprocess.callback)

                if label.name not in label_map["matched labels"] and label.interfaces:
                    for interface in label.interfaces:
                        if interface in self.analysis.interfaces \
                                and self.analysis.interfaces[interface].category == category:
                            self.add_label_match(label_map, label, interface)
                elif not label.interfaces and not label.signature() and tail and label.container and label.name \
                        not in label_map["matched labels"]:
                    for container in [self.analysis.categories[category]["containers"][name] for name
                                      in self.analysis.categories[category]["containers"]]:
                        interfaces = self.__resolve_interface(container, tail)
                        self.logger.debug("Trying to match label {} with a container {}".
                                          format(label.name, container.full_identifier))
                        if interfaces:
                            self.add_label_match(label_map, label, container.full_identifier)

                self.logger.debug("Try to match parameters of callback {} in process {} with interfaces of category"
                                  " {}".format(subprocess.callback, process.name, category))
                functions = []
                if label.name in label_map["matched labels"] and label.container:
                    for intf in label_map["matched labels"][label.name]:
                        intfs = self.__resolve_interface(
                            self.analysis.interfaces[intf], tail)
                        if intfs:
                            functions.append(intfs[-1])
                elif label.name in label_map["matched labels"] and label.callback:
                    if type(label_map["matched labels"][label.name]) is list:
                        functions.extend([self.analysis.interfaces[name] for name in
                                         label_map["matched labels"][label.name]])
                    else:
                        functions.append(self.analysis.interfaces[label_map["matched labels"][label.name]])

                for function in functions:
                    if len(subprocess.parameters) <= len(function.signature.parameters):
                        self.logger.debug("Try to match parameters of callback {}".
                                          format(function.full_identifier))
                        for parameter in subprocess.parameters:
                            pl = process.extract_label(parameter)

                            for pr in function.signature.parameters:
                                if pr.interface and pr.interface.resource and pl.resource \
                                        and (not pl.callback or pr.interface.callback == pl.callback)\
                                        and (not pl.container or pr.interface.container == pl.container):
                                    unmatched_resources = [re for re in process.resources
                                                           if re.name not in label_map["matched labels"]]
                                    if len(unmatched_resources) == 0 or \
                                            (len(unmatched_resources) > 0 and pl in unmatched_resources):
                                        self.add_label_match(label_map, pl, pr.interface.full_identifier)

                    containers = [cn for cn in process.containers
                                  if cn.name not in label_map["matched labels"]]
                    self.logger.debug("Try to match containers for callback {}".format(function))
                    containers_intfs = [self.analysis.categories[category]["containers"][name] for name in
                                        self.analysis.categories[category]["containers"] if
                                        function.identifier in
                                        self.analysis.categories[category]["containers"][name].fields]
                    for intf in containers_intfs:
                        for container in containers:
                            self.add_label_match(label_map, container, intf.full_identifier)

            # After containers are matched try to match callbacks
            matched_containers = [cn for cn in process.containers if cn.name in label_map["matched labels"]]
            unmatched_callbacks = [cl for cl in process.callbacks if cl.name not in label_map["matched labels"]]
            if len(matched_containers) > 0 and len(unmatched_callbacks) > 0:
                for callback in unmatched_callbacks:
                    for container in matched_containers:
                        for container_intf in [self.analysis.interfaces[intf] for intf in
                                               label_map["matched labels"][container.name]]:
                            for field in container_intf.fields.values():
                                name = "{}.{}".format(category, field)
                                if name in self.analysis.interfaces and self.analysis.interfaces[name].callback:
                                    self.add_label_match(label_map, callback, name)
            elif len(unmatched_callbacks) > 0:
                for callback in unmatched_callbacks:
                    for intf in [self.analysis.categories[category]["callbacks"][name] for name in
                                     self.analysis.categories[category]["callbacks"]
                                     if self.analysis.categories[category]["callbacks"][name].callback]:
                        self.add_label_match(label_map, callback, intf.full_identifier)

            # Discard unmatched labels
            label_map["unmatched labels"] = [label for label in process.labels
                                             if label not in label_map["matched labels"] and not
                                             process.labels[label].interfaces and not
                                             process.labels[label].signature()]

            # Discard unmatched callbacks
            label_map["unmatched callbacks"] = []
            label_map["matched callbacks"] = []
            for subprocess in [process.subprocesses[name] for name in process.subprocesses
                               if process.subprocesses[name].callback and
                               process.subprocesses[name].type == "dispatch"]:
                label, tail = process.extract_label_with_tail(subprocess.callback)
                if label.callback and label.name not in label_map["matched labels"] \
                        and subprocess.callback not in label_map["unmatched callbacks"]:
                    label_map["unmatched callbacks"].append(subprocess.callback)
                elif label.callback and label.name in label_map["matched labels"]:
                    callbacks = label_map["matched labels"][label.name]

                    for callback in callbacks:
                        if callback not in label_map["matched callbacks"]:
                            label_map["matched callbacks"].append(callback)
                elif label.container and tail and label.name not in label_map["matched labels"] and \
                            subprocess.callback not in label_map["unmatched callbacks"]:
                        label_map["unmatched callbacks"].append(subprocess.callback)
                elif label.container and tail and label.name in label_map["matched labels"]:
                    for intf in label_map["matched labels"][label.name]:
                        intfs = self.__resolve_interface(self.analysis.interfaces[intf],
                                                         tail)
                        if not intfs and subprocess.callback not in label_map["unmatched callbacks"]:
                            label_map["unmatched callbacks"].append(subprocess.callback)
                        elif intfs and subprocess.callback not in label_map["matched callbacks"]:
                            label_map["matched callbacks"].append(subprocess.callback)

            # Discard uncalled callbacks and recalculate it
            label_map["uncalled callbacks"] = [self.analysis.categories[category]["callbacks"][name].full_identifier
                                               for name in self.analysis.categories[category]["callbacks"] if
                                               self.analysis.categories[category]["callbacks"][name].full_identifier
                                               not in label_map["matched callbacks"]]

            if start:
                start = False
            old_size = new_size
            new_size = len(label_map["matched callbacks"]) + len(label_map["matched labels"])

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

    def __resolve_interface(self, interface, string):
        tail = string.split(".")
        # todo: get rid of leading dot
        if len(tail) == 1:
            raise RuntimeError("Cannot resolve interface for access '{}'".format(string))
        else:
            tail = tail[1:]

        if type(interface) is Interface:
            matched = [interface]
        elif type(interface) is str and interface in self.analysis.interfaces:
            matched = [self.analysis.interfaces[interface]]
        elif type(interface) is str and interface not in self.analysis.interfaces:
            return None
        else:
            raise TypeError("Expect Interface object but not {}".format(str(type(interface))))

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

        self.logger.debug("Resolve string '{}' as '{}'".format(string, str(matched)))
        return matched

    def __establish_signal_peers(self, process):
        for candidate in [self.events["environment processes"][name] for name in self.events["environment processes"]]:
            peers = process.get_available_peers(candidate)
            if peers:
                self.logger.debug("Establish signal references between process {} with category {} and process {} with "
                                  "category {}".
                                  format(process.name, process.category, candidate.name, candidate.category))
                new = self.__add_process(candidate, model=False, label_map=None, peer=process)
                if new.unmatched_receives or new.unmatched_dispatches:
                    self.__establish_signal_peers(new)

        if process.unmatched_receives:
            for receive in process.unmatched_receives:
                if receive.name == "register":
                    self.logger.info("Generate default registration for process {} with category {}".
                                     format(process.name, process.category))
                    self.add_default_dispatch(process, receive)
                elif receive.name == "deregister":
                    self.logger.info("Generate default deregistration for process {} with category {}".
                                     format(process.name, process.category))
                    self.add_default_dispatch(process, receive)
                else:
                    self.logger.warning("Signal {} cannot be received by process {} with category {}, "
                                        "since nobody can send it".
                                        format(receive.name, process.name, process.category))
        for dispatch in process.unmatched_dispatches:
            self.logger.warning("Signal {} cannot be send by process {} with category {}, "
                                "since nobody can receive it".format(dispatch.name, process.name, process.category))

    def add_default_dispatch(self, process, receive):
        # Change name
        new_subprocess_name = "{}_{}_{}".format(receive.name, process.name, process.identifier)
        process.rename_subprocess(receive.name, new_subprocess_name)

        # Deregister dispatch
        self.logger.debug("Generate copy of receive {} and make dispatch from it".format(receive.name))
        new_dispatch = copy.deepcopy(receive)
        new_dispatch.type = "dispatch"

        self.logger.debug("Add dispatch {} to process {}".format(new_dispatch.name, self.model["entry"].name))
        self.model["entry"].subprocesses[new_dispatch.name] = new_dispatch

        # todo: implement it taking into account that each parameter may have sevaral implementations
        # Add labels if necessary
        #for index in range(len(new_dispatch.parameters)):
        #    parameter = new_dispatch.parameters[index]
        #
        #    # Get label
        #    label, tail = process.extract_label_with_tail(parameter)
        #
        #    # Copy label to add to dispatcher process
        #    new_label_name = "{}_{}_{}".format(process.name, label.name, process.identifier)
        #    if new_label_name not in self.model["entry"].labels:
        #        new_label = copy.deepcopy(label)
        #        new_label.name = new_label_name
        #        self.logger.debug("To process {} add new label {}".format(self.model["entry"].name, new_label_name))
        #        self.model["entry"].labels[new_label.name] = new_label
        #    else:
        #        self.logger.debug("Process {} already has label {}".format(self.model["entry"].name, new_label_name))
        #
        #    # Replace parameter
        #    new_dispatch.parameters[index] = parameter.replace(label.name, new_label_name)
        new_dispatch.parameters = []
        receive.parameters = []

        # Replace condition
        if new_dispatch.condition:
            new_dispatch.condition = None

    def __assign_signatures(self):
        for process in self.model["models"] + self.model["processes"] + [self.model["entry"]]:
            self.logger.info("Assign signatures of process {} with category {} to labels with given interfaces".
                             format(process.name, process.category))
            for label in [process.labels[name] for name in process.labels]:
                if label.interfaces:
                    for interface in label.interfaces:
                        # Assign matched signature
                        # TODO: KeyError('interrupt.line',) - drivers/usb/gadget/g_printer.ko, drivers/usb/gadget/gr_udc.ko.
                        self.logger.debug("Add signature {} to a label {}".
                                          format(self.analysis.interfaces[interface].signature.expression, label.name))
                        label.signature(self.analysis.interfaces[interface].signature, interface)

        for process in self.model["models"] + self.model["processes"] + [self.model["entry"]]:
            self.logger.info("Assign signatures of process {} with category {} to labels according to signal "
                             "parameters".format(process.name, process.category))

            # Analyze peers
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

                            # Set new interfaces from peer signals
                            if peer_label.interfaces:
                                for interface in peer_label.interfaces:
                                    self.logger.debug("Add signature {} to a label {}".
                                                      format(peer_label.signature(None, interface).expression,
                                                             label.name))
                                    label.signature(peer_label.signature(None, interface), interface)
                            elif peer_label.signature():
                                peer_signature = peer_label.signature()
                                self.logger.debug("Add signature {} to a label {}".
                                                  format(peer_signature.expression, label.name))
                                label.signature(peer_signature)
                    else:
                        for index in range(len(peer_subprocess.parameters)):
                            peer_parameter = peer_subprocess.parameters[index]
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
                            elif peer_label.signature():
                                peer_signature = peer_label.signature()
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
                            elif label.signature():
                                label_signature = label.signature()
                                self.logger.debug("Add signature {} to a label {} of process {}".
                                                  format(label_signature.expression, peer_label.name,
                                                         peer["process"].name))
                                peer_label.signature(label_signature)

        for process in self.model["models"] + self.model["processes"] + [self.model["entry"]]:
            # Assign interface signatures
            self.logger.debug("Assign pointer flag of process {} with category {} to labels signatures".
                              format(process.name, process.category))
            for label in process.labels.values():
                if label.interfaces:
                    for interface in label.interfaces:
                        if label.signature(None, interface).type_class in ["struct", "function"]:
                            label.signature(None, interface).pointer = True

                if label.signature():
                    sign = label.signature()
                    if sign.type_class in ["struct", "function"]:
                        sign.pointer = True

    def resolve_accesses(self):
        self.logger.info("Convert interfaces access by expressions on base of containers and their fields")
        for process in self.model["models"] + self.model["processes"] + [self.model["entry"]]:
            self.logger.debug("Analyze subprocesses of process {} with category {}".
                              format(process.name, process.category))

            # Get empty keys
            accesses = process.accesses()

            # Fill it out
            for access in accesses:
                label, tail = process.extract_label_with_tail(access)

                if not label:
                    raise ValueError("Expect label in {} in access in process description".format(access, process.name))
                else:
                    if label.interfaces:
                        for interface in label.interfaces:
                            new = Access(access)
                            new.label = label

                            if len(tail) > 0:
                                intfs = self.__resolve_interface(interface, tail)
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
                                    new.list_interface = intfs
                                else:
                                    raise ValueError("Cannot resolve access {} with a base interface {} in process {}".
                                                     format(access, interface, process.name))
                            else:
                                new.interface = self.analysis.interfaces[interface]
                                new.list_access = [label.name]
                                new.list_interface = [self.analysis.interfaces[interface]]

                            accesses[access].append(new)
                    else:
                        new = Access(access)
                        new.label = label
                        new.list_access = [label.name]
                        accesses[access].append(new)

            # Save back updates collection of accesses
            process.accesses(accesses)

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
