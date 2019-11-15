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

import copy

from core.vtg.emg.common import get_or_die
from core.vtg.emg.common.process import Dispatch, Receive, ProcessCollection
from core.vtg.emg.generators.linuxModule.process import ExtendedAccess, Call, Action
from core.vtg.emg.generators.linuxModule.interface import Interface, Callback, Container, StructureContainer


def process_specifications(logger, conf, interfaces, original):
    # Generate intermediate model
    logger.info("Generate an intermediate model")
    chosen = __select_processes_and_models(logger, conf, interfaces, original)

    # Convert callback access according to container fields
    logger.info("Determine particular interfaces and their implementations for each label or its field")
    __resolve_accesses(logger, chosen, interfaces)

    # Sanity check
    for process in (p for p in chosen.processes if not p.category):
        raise ValueError("Found process without category {!r}".format(process.name))

    # Refine processes
    if conf.get("delete unregistered processes", True):
        __refine_processes(logger, chosen)
    return chosen


def __select_processes_and_models(logger, conf, interfaces, collection):
    chosen = ProcessCollection()

    # Import necessary kernel models
    logger.info("First, add relevant models of kernel functions")
    __import_kernel_models(logger, conf, interfaces, collection, chosen)

    for category in interfaces.categories:
        uncalled_callbacks = interfaces.uncalled_callbacks(category)
        logger.debug("There are {} callbacks in category {!r}".format(len(uncalled_callbacks), category))

        if uncalled_callbacks:
            logger.info("Try to find processes to call callbacks from category {!r}".format(category))
            new = __choose_processes(logger, conf, interfaces, category, chosen, collection)

            # Sanity check
            logger.info("Check again how many callbacks are not called still in category {!r}".format(category))
            uncalled_callbacks = interfaces.uncalled_callbacks(category)
            if uncalled_callbacks and not conf.get('ignore missed callbacks', True):
                raise RuntimeError("There are callbacks from category {!r} which are not called at all in the "
                                   "model: {}".format(category, ', '.join(map(str, uncalled_callbacks))))
            elif uncalled_callbacks:
                logger.warning("There are callbacks from category {!r} which are not called at all in the "
                               "model: {}. Disable option 'ignore missed callbacks' in intermediate model "
                               "configuration properties if you would like to terminate.".
                               format(category, ', '.join(map(str, uncalled_callbacks))))
            logger.info("Added process {!r} have unmatched signals, need to find factory or registration "
                        "and deregistration functions".format(new.name))
            __establish_signal_peers(logger, conf, interfaces, new, chosen, collection)
        else:
            logger.info("Ignore interface category {!r}, since it does not have callbacks to call".format(category))

    return chosen


def __import_kernel_models(logger, conf, interfaces, collection, chosen):
    for func, process in ((f.name, f) for f in collection.models.values()
                          if f.name in set(map(lambda i: i.name, interfaces.function_interfaces))):
        function_obj = interfaces.get_intf('functions models.{}'.format(func))
        logger.debug("Add model of function {!r} to an environment model".format(func))
        new_process = __add_process(logger, conf, interfaces, process, chosen, model=True)
        new_process.category = "functions models"

        logger.debug("Assign label interfaces according to function parameters for added process {!r}".
                     format(str(new_process)))
        for label in new_process.labels:
            # Assign label-parameters
            if new_process.labels[label].parameter and not new_process.labels[label].declaration:
                for index, parameter in enumerate(function_obj.param_interfaces):
                    declaration = function_obj.declaration.parameters[index]

                    if parameter and str(parameter) in new_process.labels[label].interfaces:
                        logger.debug("Set label {!r} signature according to interface {!r}".
                                     format(label, str(parameter)))
                        new_process.labels[label].set_declaration(str(parameter), declaration)
                        break
            elif new_process.labels[label].retval and not new_process.labels[label].declaration:
                if function_obj.rv_interface:
                    new_process.labels[label].set_declaration(str(function_obj.rv_interface),
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
                    new_process.labels[label].set_interface(interfaces.get_intf(interface))


def __choose_processes(logger, conf, interfaces, category, chosen, collection):
    estimations = {str(process): __match_labels(logger, interfaces, process, category)
                   for process in collection.environment.values()}

    logger.info("Choose process to call callbacks from category {!r}".format(category))
    # First random
    suits = [name for name in estimations if estimations[name] and
             estimations[name]["matched calls"] and not estimations[name]["unmatched labels"]]
    if not suits:
        raise RuntimeError("Cannot find any suitable process in specification for category {!r}".format(category))
    best_process = collection.environment[suits[0]]
    best_map = estimations[str(best_process)]

    for process in [collection.environment[name] for name in estimations]:
        label_map = estimations[str(process)]
        if label_map and label_map["matched calls"] and not label_map["unmatched labels"]:
            logger.info("Matching process {!r} for category {!r}, it has:".format(process.name, category))
            logger.info("Matching labels: {!r}".format(str(label_map["matched labels"])))
            logger.info("Unmatched labels: {!r}".format(str(label_map["unmatched labels"])))
            logger.info("Matched callbacks: {!r}".format(str(label_map["matched callbacks"])))
            logger.info("Unmatched callbacks: {!r}".format(str(label_map["unmatched callbacks"])))
            logger.info("Matched calls: {!r}".format(str(label_map["matched calls"])))
            logger.info("Native interfaces: {!r}".format(str(label_map["native interfaces"])))

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
                logger.debug("Set process {!r} for category {!r} as the best one at the moment".
                             format(process.name, category))

    if not best_process:
        raise RuntimeError("Cannot find suitable process in event categories specification for category {!r}"
                           .format(category))
    else:
        new = __add_process(logger, conf, interfaces, best_process, chosen, category, False, best_map)
        new.category = category
        logger.debug("Finally choose process {!r} for category {!r} as the best one".
                     format(best_process.name, category))
        return new


def __establish_signal_peers(logger, conf, interfaces, process, chosen, collection):
    for candidate in collection.environment.values():
        peers = process.get_available_peers(candidate)

        # Be sure that process have not been added yet
        peered_processes = set()
        for action in [a for a in process.actions.filter(include={Receive, Dispatch}) if a.peers]:
            peered_processes.update({str(p["process"]) for p in action.peers if p["process"].name == candidate.name})

        # Try to add process
        if peers and not peered_processes:
            logger.debug("Establish signal references between process {!r} and process {!r}".
                         format(str(process), str(candidate)))
            categories = __find_native_categories(candidate)
            if len(categories) > 1:
                raise ValueError('Process {!r} is a possible peer for {!r} but it allows adding for several '
                                 'possible categories {} which is too many'.
                                 format(candidate.name, process.name, ', '.join(categories)))
            elif len(categories) == 1:
                category = list(categories)[0]
                label_map = __match_labels(logger, interfaces, candidate, category)
            elif len(categories) == 0:
                category = process.category
                label_map = __match_labels(logger, interfaces, candidate, category)
            new = __add_process(logger, conf, interfaces, candidate, chosen, category, model=False, label_map=label_map,
                                peer=process)

            # Check if the category has uncalled callbacks and the process has unmatched labels
            uncalled_callbacks = interfaces.uncalled_callbacks(process.category)
            callback_labels = [l for l in new.labels.values() if l.callback and not l.interfaces and not l.declaration]
            if uncalled_callbacks and callback_labels:
                # Match unmatched callbacks
                for intf in uncalled_callbacks:
                    callback_labels[-1].set_interface(intf)

            if new and (new.actions.unmatched_receives or new.actions.unmatched_dispatches):
                __establish_signal_peers(logger, conf, interfaces, new, chosen, collection)


def __match_labels(logger, interfaces, process, category):
    logger.info("Try match process {!r} with interfaces of category {!r}".format(process.name, category))
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
    nc = __find_native_categories(process)
    ni = set()
    for label, intf in ((process.labels[n], i) for n in process.labels for i in process.labels[n].interfaces):
        intf_category, short_identifier = intf.split(".")

        if (intf in interfaces.interfaces or interfaces.is_removed_intf(intf)) and intf_category == category:
            ni.add(intf)
            __add_label_match(logger, interfaces, label_map, label, intf)
    label_map["native interfaces"] = len(ni)

    # Stop analysis if process tied with another category
    if len(nc) > 0 and len(ni) == 0:
        logger.debug("Process {} is intended to be matched with a category from the list: {}".
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
            if label.interfaces and label.name not in label_map["matched labels"]:
                for interface in (interface for interface in label.interfaces if interface in interfaces.interfaces
                                  or interfaces.is_removed_intf(interface)):
                    interface_obj = interfaces.get_intf(interface)

                    if interface_obj.category == category:
                        __add_label_match(logger, interfaces, label_map, label, interface)
            elif not label.interfaces and not label.declaration and tail and label.container and \
                    label.name not in label_map["matched labels"]:
                for cn in (c for c in interfaces.containers(category)
                           if __resolve_interface(logger, interfaces, c, tail)):
                    __add_label_match(logger, interfaces, label_map, label, str(cn))

            # Try to match callback itself
            functions = []
            if label.name in label_map["matched labels"] and label.container:
                for intf in label_map["matched labels"][label.name]:
                    intfs = __resolve_interface(logger, interfaces, interfaces.get_intf(intf), tail)
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
                        for cn in interfaces.containers(category):
                            intfs = __resolve_interface(logger, interfaces, cn, p_tail)
                            if intfs:
                                __add_label_match(logger, interfaces, label_map, p_label, str(cn))
                                pre_matched.add(str(intfs[-1]))

                    labels.append([p_label, p_tail])

                f_intfs = [pr for pr in func.param_interfaces if pr]
                for pr, par in enumerate(f_intfs):
                    matched = {str(l[0]) for l in labels if l[0].name in label_map['matched labels'] and
                               str(par) in label_map['matched labels'][l[0].name]} & \
                              set(map(lambda x: str(x[0]), labels))
                    if not matched and str(par) not in pre_matched:
                        unmatched = [label[0] for label in labels
                                     if label[0].name not in label_map['matched labels'] and not label[1]]
                        if unmatched:
                            __add_label_match(logger, interfaces, label_map, unmatched[0], str(par))
                        else:
                            rsrs = [label[0] for label in labels if label[0].resource]
                            if rsrs:
                                __add_label_match(logger, interfaces, label_map, rsrs[0], str(par))

        # After containers are matched try to match rest callbacks from category
        matched_containers = [cn for cn in process.containers if cn.name in label_map["matched labels"] and
                              isinstance(cn, StructureContainer)]
        unmatched_callbacks = [cl for cl in process.callbacks if cl.name not in label_map["matched labels"]]
        if matched_containers and unmatched_callbacks:
            for cl, cn in ((cl, cn) for cl in unmatched_callbacks for cn in matched_containers):
                for cn_intf, fn_intf in \
                        ((interfaces.get_intf(i), fn_intf) for i in label_map["matched labels"][cn.name] for fn_intf in
                         i.field_interfaces.values() if isinstance(fn_intf, Callback) and not fn_intf.called and
                         str(fn_intf) not in label_map['matched callbacks'] and str(fn_intf) in interfaces.interfaces):
                    __add_label_match(logger, interfaces, label_map, cl, str(fn_intf))

        for cl in unmatched_callbacks:
            for intf in [intf for intf in interfaces.callbacks(category)
                         if not intf.called and str(intf) not in label_map['matched callbacks']]:
                __add_label_match(logger, interfaces, label_map, cl, str(intf))

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

                for cl in callbacks:
                    if cl not in label_map["matched callbacks"]:
                        label_map["matched callbacks"].append(cl)
                    if action.callback not in label_map["matched calls"]:
                        label_map["matched calls"].append(action.callback)
            elif label.container and tail and label.name not in label_map["matched labels"] and \
                    action.callback not in label_map["unmatched callbacks"]:
                label_map["unmatched callbacks"].append(action.callback)
            elif label.container and tail and label.name in label_map["matched labels"]:
                for intf in label_map["matched labels"][label.name]:
                    intfs = __resolve_interface(logger, interfaces, interfaces.get_intf(intf), tail)

                    if not intfs and action.callback not in label_map["unmatched callbacks"]:
                        label_map["unmatched callbacks"].append(action.callback)
                    elif intfs and action.callback not in label_map["matched callbacks"]:
                        label_map["matched callbacks"].append(str(intfs[-1]))
                        if action.callback not in label_map["matched calls"]:
                            label_map["matched calls"].append(action.callback)

        # Discard uncalled callbacks and recalculate it
        label_map["uncalled callbacks"] = [str(cb) for cb in interfaces.callbacks(category)
                                           if str(cb) not in label_map["matched callbacks"]]

        if len(label_map["matched callbacks"]) + len(label_map["matched labels"]) - old_size > 0:
            success_on_iteration = True

    # Discard unmatched callbacks
    for action in process.calls:
        label, tail = process.extract_label_with_tail(action.callback)
        if label.container and tail and label.name in label_map["matched labels"]:
            for intf in label_map["matched labels"][label.name]:
                intfs = __resolve_interface(logger, interfaces, interfaces.get_intf(intf), tail)
                if intfs:
                    # Discard general callbacks match
                    for callback_label in [process.labels[name].name for name in process.labels.keys()
                                           if process.labels[name].callback and
                                           process.labels[name].name in label_map["matched labels"]]:
                        if str(intfs[-1]) in label_map["matched labels"][callback_label]:
                            label_map["matched labels"][callback_label].remove(str(intfs[-1]))

    # todo: It is a workaraound but it helps to match random scenarios where a container is never used
    for label in [l for l in label_map["unmatched labels"] if process.labels[l].container]:
        # Check that label is not used except Dispatches and Receives
        acceses = process.accesses(exclude=[Dispatch, Receive], no_labels=True)
        containers = interfaces.containers(category)
        if "%{}%".format(label) not in acceses and containers:
            # Try to match with random container
            __add_label_match(logger, interfaces, label_map, process.labels[label], str(containers[0]))
            label_map["unmatched labels"].remove(label)

    logger.info("Matched labels and interfaces:")
    logger.info("Number of native interfaces: {}".format(label_map["native interfaces"]))
    logger.info("Matched labels:")
    for label in label_map["matched labels"]:
        logger.info("{} --- {}".format(label, str(label_map["matched labels"][label])))
    logger.info("Unmatched labels:")
    for label in label_map["unmatched labels"]:
        logger.info(label)
    logger.info("Matched callbacks:")
    for cl in label_map["matched callbacks"]:
        logger.info(cl)
    logger.info("Uncalled callbacks:")
    for cl in label_map["uncalled callbacks"]:
        logger.info(cl)

    return label_map


def __add_label_match(logger, interfaces, label_map, label, interface):
    if interfaces.is_removed_intf(interface):
        interfaces.get_or_restore_intf(interface)

    if label.name not in label_map["matched labels"]:
        logger.debug("Match label {!r} with interface {!r}".format(label.name, interface))
        label_map["matched labels"][label.name] = {interface}
    else:
        label_map["matched labels"][label.name].add(interface)


def __find_native_categories(process):
    nc = set()
    for label in (process.labels[name] for name in process.labels.keys()):
        for intf in label.interfaces:
            intf_category, short_identifier = intf.split(".")
            nc.add(intf_category)
    return nc


def __add_process(logger, conf, interfaces, process, chosen, category=None, model=False, label_map=None, peer=None):
    logger.info("Add process {!r} to the model".format(process.name))
    logger.debug("Make copy of process {!r} before adding it to the model".format(process.name))
    new = copy.deepcopy(process)
    if not category:
        new.category = 'functions models'
        if not new.comment:
            raise KeyError("You must specify manually 'comment' attribute within the description of the following "
                           "function model process description: {!r}.".format(new.name))
    else:
        new.category = category
        if not new.comment:
            new.comment = get_or_die(conf, 'process comment')

    # Add comments
    comments_by_type = get_or_die(conf, 'action comments')
    for action in (a for a in new.actions.filter(include={Action}) if not a.comment):
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
            callback_comment = get_or_die(conf, 'callback comment').capitalize()
            if action.comment:
                action.comment += ' ' + callback_comment
            else:
                action.comment = callback_comment

    new.instance_number += len(chosen.models) + len(chosen.environment) + 1
    logger.info("Finally add process {!r} to the model".format(process.name))

    logger.debug("Set interfaces for given labels")
    if label_map:
        for label in label_map["matched labels"]:
            for interface in [interfaces.get_or_restore_intf(name) for name
                              in label_map["matched labels"][label]]:
                new.labels[label].set_interface(interface)
    else:
        for label, interface in ((l, i) for l in new.labels.values() for i in l.interfaces if not l.get_declaration(i)):
            try:
                label.set_interface(interfaces.get_or_restore_intf(interface))
            except KeyError:
                logger.warning("Process {!r} cannot be added, since it contains unknown interfaces for this "
                               "program fragment".format(str(new)))
                return None

    if model and not category:
        chosen.models[new] = new
    elif not model and category:
        chosen.environment[new] = new
    else:
        raise ValueError('Provide either model or category arguments but not simultaneously')

    if peer:
        logger.debug("Match signals with signals of process {!r}".format(str(peer)))
        new.establish_peers(peer)

    logger.info("Check is there exist any dispatches or receives after process addiction to tie".format(str(process)))
    __normalize_model(logger, chosen, interfaces)
    return new


def __normalize_model(logger, chosen, interfaces):
    # Peer processes with models
    logger.info("Try to establish connections between process dispatches and receivings")
    for process, model in ((p, m) for p in chosen.environment for m in chosen.models):
        logger.debug("Analyze signals of processes {} and {}".format(str(model), str(process)))
        model.establish_peers(process)

    # Peer processes with each other
    processes = list(chosen.environment.values())
    for index1, p1 in enumerate(processes):
        for index2 in range(index1 + 1, len(processes)):
            p2 = processes[index2]
            logger.debug("Analyze signals of processes {} and {}".format(p1.name, p2.name))
            p1.establish_peers(p2)

    logger.info("Check which callbacks can be called in the intermediate environment model")
    for process in chosen.processes:
        logger.debug("Check process callback calls at process {!r}".format(str(process)))

        for action in process.calls:
            # todo: refactoring #6565
            label, tail = process.extract_label_with_tail(action.callback)

            if label.interfaces:
                resolved = False
                for interface in label.interfaces:
                    interface_obj = interfaces.get_or_restore_intf(interface)
                    if isinstance(interface_obj, Container) and tail:
                        intfs = __resolve_interface(logger, interfaces, interface_obj, tail)
                        if intfs:
                            intfs[-1].called = True
                            resolved = True
                        else:
                            logger.warning("Cannot resolve callback {!r} in description of process {!r}".
                                           format(action.callback, str(process)))
                    elif isinstance(interface_obj, Callback):
                        logger.debug("Callback {!r} can be called in the model".format(str(interface_obj)))
                        interface_obj.called = True
                        resolved = True
                if not resolved:
                    raise ValueError("Cannot resolve callback {!r} in description of process {!r}".
                                     format(action.callback, process.name))


def __resolve_accesses(logger, chosen, interfaces):
    logger.info("Convert interfaces accesses to expressions on base of containers and their fields")
    for process in chosen.processes:
        # Get empty keys
        accesses = process.accesses()

        # Fill it out
        original_accesses = list(accesses.keys())
        for access in original_accesses:
            label, tail = process.extract_label_with_tail(access)

            if not label:
                raise ValueError("Expect a label in {!r} access in process {!r} description".
                                 format(access, process.name))
            elif label.interfaces:
                for interface in label.interfaces:
                    new = ExtendedAccess(access)
                    new.label = label

                    # Add label access if necessary
                    label_access = "%{}%".format(label.name)
                    if label_access not in original_accesses:
                        # Add also label itself
                        laccess = ExtendedAccess(label_access)
                        laccess.label = label
                        laccess.interface = interfaces.get_intf(interface)
                        laccess.list_interface = [interfaces.get_intf(interface)]
                        laccess.list_access = [label.name]

                        if laccess.expression not in accesses:
                            accesses[laccess.expression] = [laccess]
                        elif laccess.interface not in [a.interface for a in accesses[laccess.expression]]:
                            accesses[laccess.expression].append(laccess)

                    # Calculate interfaces for tail
                    if tail:
                        callback_actions = [a for a in process.calls if a.callback == access]
                        options = []
                        if callback_actions:
                            options = [__resolve_interface(logger, interfaces, interface, tail)
                                       for _ in callback_actions]
                        else:
                            options.append(__resolve_interface(logger, interfaces, interface, tail))

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
                        while to_process:
                            interface = to_process.pop()
                            category = new.interface.category

                            for container in (c for c in interfaces.containers(category)
                                              if c.weak_contains(interface) and c not in new_tail):
                                new_tail.append(container)
                                to_process.append(container)
                                break
                        new_tail.reverse()
                        new.complete_list_interface = new_tail

                    accesses[access].append(new)
            elif access not in accesses or not accesses[access]:
                new = ExtendedAccess(access)
                new.label = label
                new.list_access = [label.name]
                accesses[access].append(new)

                # Add also label itself
                label_access = "%{}%".format(label.name)
                if label_access not in original_accesses:
                    laccess = ExtendedAccess(label_access)
                    laccess.label = label
                    laccess.list_access = [label.name]
                    accesses[laccess.expression] = [laccess]

        # Save back updates collection of accesses
        process.accesses(accesses)


def __resolve_interface(logger, interfaces, interface, string):
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
        intf = [matched[-1].field_interfaces[name] for name in matched[-1].field_interfaces if name == field]

        # Match using an identifier
        if len(intf) == 0:
            intf = [matched[-1].field_interfaces[name] for name in matched[-1].field_interfaces
                    if matched[-1].field_interfaces[name].name == field]

        if len(intf) == 0:
            return None
        else:
            if index == (len(tail) - 1) or isinstance(intf[-1], Container):
                matched.append(intf[-1])
            else:
                return None

    logger.debug("Resolve string '{}' as '{}'".format(string, ', '.join([str(m) for m in matched])))
    return matched


def __refine_processes(logger, chosen):
    del_flag = True

    while del_flag:
        del_flag = False
        delete = []

        for process in chosen.environment:
            # Check replicative signals
            replicative = [a for a in process.actions.filter(include={Receive}) if a.replicative]
            if replicative and any([a for a in replicative if not a.peers]):
                # Remove the process from the collection
                delete.append(process)

                # Remove it from all the peers
                for action in process.actions.filter(include={Receive, Dispatch}):
                    for peer in action.peers:
                        peer_action = peer['action']
                        indexes = []
                        for index, pr in enumerate(peer_action.peers):
                            if pr['process'].instance_number == process.instance_number:
                                indexes.append(index)

                        for index in reversed(indexes):
                            del peer_action.peers[index]

        for p in delete:
            logger.info("Remove process {!r} as it cannot be registered".format(str(p)))
            del chosen.environment[p]

    return
