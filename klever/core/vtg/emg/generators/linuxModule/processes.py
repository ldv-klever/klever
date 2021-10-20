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

import sortedcontainers

from klever.core.vtg.emg.common import get_or_die
from klever.core.vtg.emg.common.process.actions import Dispatch, Receive
from klever.core.vtg.emg.generators.linuxModule.interface import Interface, Callback, Container, StructureContainer
from klever.core.vtg.emg.generators.linuxModule.process import ExtendedAccess, Call, CallRetval, \
    ExtendedProcessCollection


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
    chosen = ExtendedProcessCollection()

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

            # Assign rest parameters
            if new_process.labels[label].interfaces and len(new_process.labels[label].interfaces) > 0:
                for interface in (i for i in new_process.labels[label].interfaces
                                  if i in interfaces.interfaces):
                    new_process.labels[label].set_interface(interfaces.get_intf(interface))


def __choose_processes(logger, conf, interfaces, category, chosen, collection):
    estimations = sortedcontainers.SortedDict(
        {str(process): __match_labels(logger, interfaces, chosen, process, category)
         for process in collection.environment.values()})

    logger.info("Choose process to call callbacks from category {!r}".format(category))
    # First random
    suits = [name for name in estimations if estimations[name] and
             estimations[name]["matched calls"] and not estimations[name]["unmatched labels"]]
    if not suits:
        raise RuntimeError("Cannot find any suitable process in specification for category {!r}".format(category))
    best_process = collection.environment[suits[0]]
    best_map = estimations[str(best_process)]

    # Keep only that with matched callbacks
    estimations = {name: estimations[name] for name in estimations
                   if estimations[name] and estimations[name]["matched calls"] and
                   not estimations[name]["unmatched labels"]}

    # Filter by native interfaces
    reduced_estimations = {name: estimations[name] for name in estimations
                           if estimations[name]["native interfaces"] > 0}
    if reduced_estimations:
        logger.info('Consider only processes with relevant interfaces: {}'.format(', '.join(reduced_estimations.keys())))
        estimations = reduced_estimations

    # Filter by send relationships
    signal_maps = {}
    for process in (collection.environment[name] for name in estimations):
        for sending in process.actions.filter(include=[Dispatch], exclude={Call}):
            params = str(len(sending.parameters))
            logger.debug(f"Found dispatch '{str(sending)}' with parameters: {params}")
            nname = str(sending) + '_' + params
            signal_maps.setdefault(nname, {'send': set(), 'receive': set()})
            signal_maps[nname]['send'].add(str(process))
        for receive in process.actions.filter(include=[Receive], exclude={CallRetval}):
            params = str(len(receive.parameters))
            logger.debug(f"Found dispatch '{str(receive)}' with parameters: {params}")
            nname = str(receive) + '_' + str(len(receive.parameters))
            signal_maps.setdefault(nname, {'send': set(), 'receive': set()})
            signal_maps[nname]['receive'].add(str(process))

    # Now filter processes to take into account dependencies
    to_remove = set()
    for nname in (n for n in signal_maps if len(signal_maps[n]['send']) > 0):
        for dependant in signal_maps[nname]['receive']:
            to_remove.add(dependant)
    if len(to_remove) < len(list(estimations.keys())):
        # Do not remove them all!
        logger.debug("Going to remove the following signal depending processes: {}".
                     format(', '.format(list(to_remove))))
        estimations = {n: estimations[n] for n in estimations if n not in to_remove}
    else:
        logger.warning('Loop dependencies between processes: {}'.format(', '.join(list(to_remove))))

    for process in (collection.environment[name] for name in estimations):
        label_map = estimations[str(process)]
        do = False
        if label_map["native interfaces"] > best_map["native interfaces"]:
            do = True
        elif label_map["native interfaces"] == best_map["native interfaces"] or best_map["native interfaces"] == 0:
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

    if not best_process:
        raise RuntimeError("Cannot find suitable process in event categories specification for category {!r}"
                           .format(category))
    else:
        new = __add_process(logger, conf, interfaces, best_process, chosen, category, False, best_map)
        new.category = category
        logger.debug("Finally choose process {!r} for category {!r} as the best one".
                     format(best_process.name, category))
        for tag in best_map:
            if isinstance(best_map[tag], list) and best_map[tag]:
                value = ', '.join(best_map[tag])
            elif isinstance(best_map[tag], list):
                value = None
            else:
                value = str(best_map[tag])
            if value is not None:
                logger.debug(f"{tag.capitalize()}: {value}")
        return new


def __establish_signal_peers(logger, conf, interfaces, process, chosen, collection):
    for candidate in collection.environment.values():
        peers = process.get_available_peers(candidate)

        # This is because category can be changed after adding to the model
        valid_peers = chosen.peers(process, {s for p in peers for s in p})
        names = {p.process.name for p in valid_peers}

        # Try to add process
        if peers and candidate.name not in names:
            logger.debug("Establish signal references between process {!r} and process {!r}".
                         format(str(process), str(candidate)))
            categories = __find_native_categories(candidate)
            if len(categories) > 1:
                raise ValueError('Process {!r} is a possible peer for {!r} but it allows adding to several '
                                 'possible categories which is too mush: {}'.
                                 format(candidate.name, process.name, ', '.join(categories)))
            elif len(categories) == 1:
                category = list(categories)[0]
                label_map = __match_labels(logger, interfaces, chosen, candidate, category)
            elif len(categories) == 0:
                category = process.category
                label_map = __match_labels(logger, interfaces, chosen, candidate, category)
            else:
                raise NotImplementedError
            new = __add_process(logger, conf, interfaces, candidate, chosen, category, model=False, label_map=label_map,
                                peer=process)

            # Check if the category has uncalled callbacks and the process has unmatched labels
            uncalled_callbacks = interfaces.uncalled_callbacks(process.category)
            callback_labels = [l for l in new.labels.values() if l.callback and not l.interfaces and not l.declaration]
            if uncalled_callbacks and callback_labels:
                # Match unmatched callbacks
                for intf in uncalled_callbacks:
                    callback_labels[-1].set_interface(intf)

            if new and new.unmatched_signals():
                __establish_signal_peers(logger, conf, interfaces, new, chosen, collection)


def __match_labels(logger, interfaces, chosen, process, category):
    label_map = {
        "matched labels": {},
        "unmatched labels": [],
        "uncalled callbacks": [],
        "matched callbacks": [],
        "unmatched callbacks": [],
        "matched calls": [],
        "native interfaces": [],
        "signal labels": []
    }

    # Collect native categories and interfaces
    nc = __find_native_categories(process)
    ni = set()
    for label, intf in ((process.labels[n], i) for n in process.labels for i in process.labels[n].interfaces):
        intf_category, short_identifier = intf.split(".")

        if (intf in interfaces.interfaces or interfaces.is_removed_intf(intf)) and intf_category == category:
            ni.add(intf)
            __add_label_match(label_map, label, interfaces.get_or_restore_intf(intf))
    label_map["native interfaces"] = len(ni)

    # Stop analysis if process tied with another category
    if len(nc) > 0 and len(ni) == 0:
        return None

    # todo: Code below is a bit greedy and it doesn't support arrays in access sequences
    # todo: better to rewrite it totally and implement comparison on the base of signatures
    success_on_iteration = True
    while success_on_iteration:
        success_on_iteration = False
        old_size = len(label_map["matched callbacks"]) + len(label_map["matched labels"])

        # First, check signals related to the native category and match parameters
        for model in chosen.models.values():
            for name in model.unmatched_signals(kind=Dispatch):
                if name in process.actions and isinstance(process.actions[name], Receive) and \
                        len(model.actions[name].parameters) == len(process.actions[name].parameters):
                    for i, l in enumerate(model.actions[name].parameters):
                        model_label, _ = model.extract_label_with_tail(l)
                        for intf in model_label.interfaces:
                            intf = interfaces.get_intf(intf)
                            if intf.category == category:
                                p_label, _ = process.extract_label_with_tail(process.actions[name].parameters[i])
                                __add_label_match(label_map, p_label, intf)
                                label_map["signal labels"].append(p_label.name)
                                break

        # Match interfaces and containers
        for action in process.calls:
            label, tail = process.extract_label_with_tail(action.callback)

            # Try to match container
            if label.interfaces and label.name not in label_map["matched labels"]:
                for interface in (interface for interface in label.interfaces if interface in interfaces.interfaces
                                  or interfaces.is_removed_intf(interface)):
                    interface_obj = interfaces.get_intf(interface)

                    if interface_obj.category == category:
                        __add_label_match(label_map, label, interface_obj)
            elif not label.interfaces and not label.declaration and tail and label.container and \
                    label.name not in label_map["matched labels"]:
                for cn in (c for c in interfaces.containers(category)
                           if __resolve_interface(logger, interfaces, c, tail)):
                    __add_label_match(label_map, label, cn)

            # Try to match callback itself
            callbacks = []
            if label.name in label_map["matched labels"] and label.container:
                for intf in label_map["matched labels"][label.name]:
                    intfs = __resolve_interface(logger, interfaces, interfaces.get_intf(intf), tail)
                    if intfs and isinstance(intfs[-1], Callback):
                        callbacks.append(intfs[-1])
            elif label.name in label_map["matched labels"] and label.callback:
                if isinstance(label_map["matched labels"][label.name], set) or \
                        isinstance(label_map["matched labels"][label.name], sortedcontainers.SortedSet):
                    callbacks.extend([interfaces.get_or_restore_intf(name) for name in
                                      label_map["matched labels"][label.name]
                                      if name in interfaces.interfaces or interfaces.is_deleted_intf(name)])
                elif label_map["matched labels"][label.name] in interfaces.interfaces or \
                        interfaces.is_removed_intf(label_map["matched labels"][label.name]):
                    callbacks.append(interfaces.get_intf(label_map["matched labels"][label.name]))

            # Restore interfaces if necessary
            for intf in (f for f in callbacks if interfaces.is_removed_intf(f)):
                interfaces.get_or_restore_intf(intf)

            # Match parameters
            for callback in callbacks:
                labels_tails = []
                pre_matched_intfs = set()
                for par_intf in action.parameters:
                    p_label, p_tail = process.extract_label_with_tail(par_intf)
                    if p_tail:
                        for cn in interfaces.containers(category):
                            intfs = __resolve_interface(logger, interfaces, cn, p_tail)
                            if intfs:
                                __add_label_match(label_map, p_label, cn)
                                pre_matched_intfs.add(str(intfs[-1]))

                    labels_tails.append([p_label, p_tail])

                for par_intf in (par_intf for par_intf in callback.param_interfaces if par_intf):
                    matched = {str(label) for label, _ in labels_tails if label.name in label_map['matched labels'] and
                               str(par_intf) in label_map['matched labels'][label.name]}
                    if not matched and str(par_intf) not in pre_matched_intfs:
                        unmatched = [label for label, tail in labels_tails
                                     if not tail and label.name not in label_map['matched labels']]
                        if unmatched:
                            # todo: This is nasty to get the first one
                            __add_label_match(label_map, unmatched[0], par_intf)
                        else:
                            # Check that the interface is not already matched
                            matched_interfaces = {i for x in label_map['matched labels'].values() for i in x}
                            if str(par_intf) in matched_interfaces:
                                continue

                            rsrs = [label[0] for label in labels_tails if label[0].resource]
                            if rsrs:
                                __add_label_match(label_map, rsrs[0], par_intf)

        unmatched_callbacks = [cl for cl in process.callbacks if cl.name not in label_map["matched labels"]]
        for cl in unmatched_callbacks:
            for intf in [intf for intf in interfaces.callbacks(category)
                         if not intf.called and str(intf) not in label_map['matched callbacks']]:
                __add_label_match(label_map, cl, intf)

        # Discard unmatched labels
        label_map["unmatched labels"] = [str(label) for label in process.labels.values()
                                         if str(label) not in label_map["matched labels"] and not label.interfaces
                                         and not label.declaration and not label.callback]

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

    # todo: It is a workaround but it helps to match random scenarios where a container is never used
    for label in [l for l in label_map["unmatched labels"] if process.labels[l].container]:
        # Check that label is not used except Dispatches and Receives
        accesses = process.accesses(exclude=[Dispatch, Receive], no_labels=True)
        containers = interfaces.containers(category)
        if "%{}%".format(label) not in accesses and containers:
            # Try to match with random container
            __add_label_match(label_map, process.labels[label], containers[0])
            label_map["unmatched labels"].remove(label)

    # todo: This is not useful at this moment
    # logger.info("Matched labels and interfaces:")
    # logger.info("The number of native interfaces: {}".format(label_map["native interfaces"]))
    # logger.info("Matched labels: {}".format(', '.join("{}-{}".format(label, str(label_map["matched labels"][label]))
    #                                                   for label in label_map["matched labels"])))
    # for tag in ("unmatched labels", "matched callbacks", "uncalled callbacks"):
    #     logger.info("{}: {}".format(tag.capitalize(), ', '.join(label_map[tag])))

    return label_map


def __add_label_match(label_map, label, interface):
    if label.name not in label_map["signal labels"]:
        if label.name not in label_map["matched labels"]:
            # todo: Comment this out until we do not debug interface matching
            # logger.debug("Match label {!r} with interface {!r}".format(label.name, str(interface)))
            label_map["matched labels"][label.name] = {str(interface)}
        else:
            label_map["matched labels"][label.name].add(str(interface))

        if isinstance(interface, Callback):
            label_map["matched callbacks"].append(str(interface))


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
    new = process.clone()
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
    for action in (a for a in new.actions.values() if not a.comment):
        tag = type(action).__name__.lower()
        if tag in comments_by_type and isinstance(comments_by_type[tag], str):
            action.comment = comments_by_type[tag]
        elif tag in comments_by_type and isinstance(comments_by_type[tag], dict) and \
                action.name in comments_by_type[tag]:
            action.comment = comments_by_type[tag][action.name]
        elif not isinstance(action, Call):
            raise KeyError(
                "Cannot find a comment for action {0!r} of type {2!r} at new {1!r} description. You "
                "should either specify in the corresponding environment model specification the comment "
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
        chosen.models[new.name] = new
    elif not model and category:
        chosen.environment[str(new)] = new
    else:
        raise ValueError("Provide either model or category arguments but not simultaneously")

    if peer:
        logger.debug("Match signals with signals of process {!r}".format(str(peer)))
        new.establish_peers(peer)

    __normalize_model(logger, chosen, interfaces)
    return new


def __normalize_model(logger, chosen, interfaces):
    # Peer processes with models
    chosen.establish_peers()

    logger.info("Check which callbacks can be called in the intermediate environment model")
    for process in chosen.processes:
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
                raise ValueError(f"Expect a label in '{access}' access in process '{process.name}' description")
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

                        options = [o for o in options if isinstance(o, list) and o and o[-1]]
                        if options:
                            for intfs in options:
                                list_access = []
                                for index, par in enumerate(intfs):
                                    if index == 0:
                                        list_access.append(label.name)
                                    else:
                                        field = list(intfs[index - 1].field_interfaces.keys()
                                                     )[list(intfs[index - 1].field_interfaces.values()).index(par)]
                                        list_access.append(field)
                                new.list_access = list_access
                                new.interface = intfs[-1]
                                if len(intfs) > 1:
                                    new.base_interface = intfs[0]
                                # todo: This log is too verbose
                                #     logger.debug(f'Match {str(new)} with base interface {str(new.base_interface)}')
                                # logger.debug(f'Match {str(new)} with {str(new.interface)}')
                        else:
                            logger.warning(f'Cannot determine interface of tail {str(tail)} of access {str(new)}')
                    elif interfaces.get_intf(interface):
                        # todo: disable logging
                        # logger.debug(f'Trying to match {str(new)} with interface {interface}')
                        new.interface = interfaces.get_intf(interface)
                        new.list_access = [label.name]
                    else:
                        logger.debug(f"Cannot match '{str(new)}' with missing interface '{interface}'")
                        continue

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


def __resolve_interface(logger, interfaces, interface, tail_string):
    tail = tail_string.split(".")
    # todo: get rid of leading dot and support arrays
    if len(tail) == 1:
        raise RuntimeError("Cannot resolve interface for access '{}'".format(tail_string))
    else:
        tail = tail[1:]

    if issubclass(type(interface), Interface):
        matched = [interface]
    elif isinstance(interface, str) and interface in interfaces.interfaces:
        matched = [interfaces.get_intf(interface)]
    elif isinstance(interface, str) and interface not in interfaces.interfaces:
        return None
    else:
        raise TypeError("Expect Interface object but not {!r}".format(str(type(interface))))

    # Be sure the first interface is a container
    if not isinstance(matched[-1], Container) and tail:
        return None

    # Collect interface list
    for index, field in enumerate(tail):
        # Match using a container field name
        if isinstance(matched[-1], StructureContainer):
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
        else:
            return None

    # todo: comment out this until we will do not need to debug interface matching
    # logger.debug("Resolve string '{}' as '{}'".format(tail_string, ', '.join(map(str, matched))))
    return matched


def __refine_processes(logger, chosen):
    del_flag = True

    while del_flag:
        del_flag = False
        delete = []

        for process in chosen.environment.values():
            # Check replicative signals
            replicative = [a for a in process.actions.filter(include={Receive}, exclude={CallRetval}) if a.replicative]
            assert len(replicative) == 1, \
                f"Process '{str(process)}' should have a single replicative signal but has" \
                f" the following: {', '.join(map(str, replicative))}"
            signal = replicative.pop()
            if str(signal) in process.unmatched_signals(Receive):
                # Remove the process from the collection
                delete.append(str(process))
            else:
                # Check that processes are not send and required by anybody
                irrelevant_dispatches = process.unmatched_signals(kind=Dispatch)
                models = list(map(str, chosen.models.values()))
                model_senders = [p for p in process.peers if p in models and str(signal) in process.peers[p]]
                if len(model_senders) == 0 and \
                        len(irrelevant_dispatches) == len(process.actions.filter(include={Dispatch}, exclude={Call})):
                    logger.debug(f"Process '{str(process)}' do not have dispatches to anybody else in the model")
                    # Then check that there is no any interface implementations which are relevant to the the process
                    accesses = [a for many in process.accesses().values() for a in many if a.interface]
                    implemented = [a for a in accesses if a.interface.implementations]
                    if not implemented:
                        logger.debug(
                            f"Delete process '{str(process)}' as it does not have any relevant implemented interfaces")
                        delete.append(str(process))

        for p in delete:
            logger.info("Remove process {!r} as it cannot be registered".format(str(p)))
            del chosen.environment[p]
        chosen.establish_peers()

    return
