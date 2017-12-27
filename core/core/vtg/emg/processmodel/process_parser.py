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
from core.vtg.emg.common import get_necessary_conf_property, check_or_set_conf_property, \
    check_necessary_conf_property
from core.vtg.emg.common.signature import import_declaration
from core.vtg.emg.common.process import Process, Label, Receive, Dispatch, Call, CallRetval, Condition, \
    generate_regex_set


####################################################################################################################
# PUBLIC FUNCTIONS
####################################################################################################################


def parse_event_specification(logger, conf, raw):
    """
    Parse event categories specification and create all existing Process objects.

    :param logger: logging object.
    :param conf: Configuration dictionary with options for intermediate model.
    :param raw: Dictionary with content of JSON file of a specification.
    :return: [List of Process objects which correspond to kernel function models],
             [List of Process objects which correspond to processes with callback calls]
    """
    env_processes = {}
    models = {}

    # Check necessary configuration options
    check_or_set_conf_property(conf, "process comment", default_value='Invocation scenario for {0!r} callbacks',
                               expected_type=str)
    check_or_set_conf_property(conf, "callback comment", default_value='Invoke callback {0!r} from {1!r}.',
                               expected_type=str)
    check_necessary_conf_property(conf, "action comments", expected_type=dict)

    logger.info("Import processes from provided event categories specification")
    if "kernel model" in raw:
        logger.info("Import processes from 'kernel model'")
        for name_list in raw["kernel model"]:
            names = name_list.split(", ")
            for name in names:
                logger.debug("Import process which models {!r}".format(name))
                models[name] = __import_process(name, raw["kernel model"][name_list], conf, True)
    else:
        logger.warning("Kernel model is not provided")
    if "environment processes" in raw:
        logger.info("Import processes from 'environment processes'")
        for name in raw["environment processes"]:
            logger.debug("Import environment process {}".format(name))
            process = __import_process(name, raw["environment processes"][name], conf, False)
            env_processes[name] = process
    else:
        raise KeyError("Model cannot be generated without environment processes")

    return models, env_processes

####################################################################################################################
# PRIVATE FUNCTIONS
####################################################################################################################


def __import_process(name, dic, conf, model_flag=False):
    process = Process(name)

    if 'self parallelism' in dic:
        process.self_parallelism = False

    if 'labels' in dic:
        for label_name in dic['labels']:
            label = Label(label_name)
            process.labels[label_name] = label

            for att in ['container', 'resource', 'callback', 'parameter', 'value', 'pointer', 'file', 'retval']:
                if att in dic['labels'][label_name]:
                    setattr(label, att, dic['labels'][label_name][att])

            if 'interface' in dic['labels'][label_name]:
                if type(dic['labels'][label_name]['interface']) is str:
                    label.set_declaration(dic['labels'][label_name]['interface'], None)
                elif type(dic['labels'][label_name]['interface']) is list:
                    for string in dic['labels'][label_name]['interface']:
                        label.set_declaration(string, None)
                else:
                    TypeError('Expect list or string with interface identifier')
            if 'signature' in dic['labels'][label_name]:
                label.prior_signature = import_declaration(dic['labels'][label_name]['signature'])

    # Import process
    process_strings = []
    if 'process' in dic:
        process.process = dic['process']

        process_strings.append(dic['process'])

    # Import comments
    if 'comment' in dic:
        process.comment = dic['comment']
    else:
        raise KeyError("You must specify manually 'comment' attribute within the description of {!r} kernel "
                       "function model process".format(name))

    # Import subprocesses
    if 'actions' in dic:
        for action_name in dic['actions']:
            process.actions[action_name] = None

            if 'process' in dic['actions'][action_name]:
                process_strings.append(dic['actions'][action_name]['process'])

    if 'headers' in dic:
        process.headers = dic['headers']

    for action_name in process.actions:
        regexes = generate_regex_set(action_name)
        matched = False

        for regex in regexes:
            for string in process_strings:
                if regex['regex'].search(string):
                    process_type = regex['type']
                    if process_type is Dispatch and 'callback' in dic['actions'][action_name]:
                        act = Call(action_name)
                    elif process_type is Receive and 'callback' in dic['actions'][action_name]:
                        act = CallRetval(action_name)
                    elif process_type is Receive:
                        act = process_type(action_name)
                        if '!' in regex['regex'].search(string).group(0):
                            act.replicative = True
                    elif process_type is Dispatch:
                        act = process_type(action_name)
                        if '@' in regex['regex'].search(string).group(0):
                            act.broadcast = True
                    else:
                        act = process_type(action_name)
                    process.actions[action_name] = act
                    matched = True
                    break

        if not matched:
            raise ValueError("Action '{}' is not used in process description {!r}".
                             format(action_name, name))

        # Add comment if it is provided
        if 'comment' in dic['actions'][action_name]:
            process.actions[action_name].comment = dic['actions'][action_name]['comment']
        elif not isinstance(act, Call):
            comments_by_type = get_necessary_conf_property(conf, 'action comments')
            tag = type(act).__name__.lower()
            if tag not in comments_by_type or \
               not (isinstance(comments_by_type[tag], str) or
                    (isinstance(comments_by_type[tag], dict) and action_name in comments_by_type[tag])):
                raise KeyError(
                    "Cannot find comment for action {!r} of type {!r} at process {!r} description. You shoud either "
                    "specify in the corresponding environment model specification the comment text manually or set "
                    "the default comment text for all actions of the type {!r} at EMG plugin configuration properties "
                    "within 'action comments' attribute.".
                    format(action_name, tag, name, tag))

        # Values from dictionary
        if 'callback' in dic['actions'][action_name]:
            process.actions[action_name].callback = dic['actions'][action_name]['callback']

        # Add parameters
        if 'parameters' in dic['actions'][action_name]:
            process.actions[action_name].parameters = dic['actions'][action_name]['parameters']

        # Add pre-callback operations
        if 'pre-call' in dic['actions'][action_name]:
            process.actions[action_name].pre_call = dic['actions'][action_name]['pre-call']

        # Add post-callback operations
        if 'post-call' in dic['actions'][action_name]:
            process.actions[action_name].post_call = dic['actions'][action_name]['post-call']

        # Add callback return value
        if 'callback return value' in dic['actions'][action_name]:
            process.actions[action_name].retlabel = dic['actions'][action_name]['callback return value']

        # Import condition
        if 'condition' in dic['actions'][action_name]:
            process.actions[action_name].condition = dic['actions'][action_name]['condition']

        # Import statements
        if 'statements' in dic['actions'][action_name]:
            process.actions[action_name].statements = dic['actions'][action_name]['statements']

        # Import process
        if 'process' in dic['actions'][action_name]:
            process.actions[action_name].process = dic['actions'][action_name]['process']

    used_labels = set()

    def extract_labels(expr):
        for m in process.label_re.finditer(expr):
            used_labels.add(m.group(1))

    for action in process.actions.values():
        if isinstance(action, Call) or isinstance(action, CallRetval) and action.callback:
            extract_labels(action.callback)
        if isinstance(action, Call):
            for param in action.parameters:
                extract_labels(param)
        if isinstance(action, Receive) or isinstance(action, Dispatch):
            for param in action.parameters:
                extract_labels(param)
        if isinstance(action, CallRetval) and action.retlabel:
            extract_labels(action.retlabel)
        if isinstance(action, Condition):
            for statement in action.statements:
                extract_labels(statement)
        if action.condition:
            for statement in action.condition:
                extract_labels(statement)

    unused_labels = set(process.labels.keys()).difference(used_labels)
    if len(unused_labels) > 0:
        raise RuntimeError("Found unused labels in process {!r}: {}".format(process.name, ', '.join(unused_labels)))

    return process
