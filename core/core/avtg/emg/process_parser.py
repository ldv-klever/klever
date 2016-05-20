from core.avtg.emg.common.signature import import_signature
from core.avtg.emg.common.process import Process, Label, Access, Receive, Dispatch, Call, CallRetval,\
    generate_regex_set

####################################################################################################################
# PUBLIC FUNCTIONS
####################################################################################################################


def parse_event_specification(logger, raw):
    """
    Parse event categories specification and create all existing Process objects.

    :param logger: logging object.
    :param raw: Dictionary with content of JSON file of a specification.
    :return: [List of Process objects which correspond to kernel function models],
             [List of Process objects which correspond to processes with callback calls]
    """
    env_processes = {}
    models = {}

    logger.info("Import processes from provided event categories specification")
    if "kernel model" in raw:
        logger.info("Import processes from 'kernel model'")
        for name_list in raw["kernel model"]:
            names = name_list.split(", ")
            for name in names:
                logger.debug("Import process which models {}".format(name))
                models[name] = __import_process(name, raw["kernel model"][name_list])
    else:
        logger.warning("Kernel model is not provided")
    if "environment processes" in raw:
        logger.info("Import processes from 'environment processes'")
        for name in raw["environment processes"]:
            logger.debug("Import environment process {}".format(name))
            process = __import_process(name, raw["environment processes"][name])
            env_processes[name] = process
    else:
        raise KeyError("Model cannot be generated without environment processes")

    return models, env_processes

####################################################################################################################
# PRIVATE FUNCTIONS
####################################################################################################################


def __import_process(name, dic):
    process = Process(name)

    if 'labels' in dic:
        for name in dic['labels']:
            label = Label(name)
            process.labels[name] = label

            for att in ['container', 'resource', 'callback', 'parameter', 'value', 'pointer', 'file']:
                if att in dic['labels'][name]:
                    setattr(label, att, dic['labels'][name][att])

            if 'interface' in dic['labels'][name]:
                if type(dic['labels'][name]['interface']) is str:
                    label.set_declaration(dic['labels'][name]['interface'], None)
                elif type(dic['labels'][name]['interface']) is list:
                    for string in dic['labels'][name]['interface']:
                        label.set_declaration(string, None)
                else:
                    TypeError('Expect list or string with interface identifier')
            if 'signature' in dic['labels'][name]:
                label.prior_signature = import_signature(dic['labels'][name]['signature'])

    # Import process
    process_strings = []
    if 'process' in dic:
        process.process = dic['process']

        process_strings.append(dic['process'])

    # Import subprocesses
    if 'actions' in dic:
        for name in dic['actions']:
            process.actions[name] = None

            if 'process' in dic['actions'][name]:
                process_strings.append(dic['actions'][name]['process'])

    for subprocess_name in process.actions:
        regexes = generate_regex_set(subprocess_name)

        for regex in regexes:
            for string in process_strings:
                if regex['regex'].search(string):
                    process_type = regex['type']
                    if process_type is Dispatch and 'callback' in dic['actions'][subprocess_name]:
                        act = Call(subprocess_name)
                    elif process_type is Receive and 'callback' in dic['actions'][subprocess_name]:
                        act = CallRetval(subprocess_name)
                    else:
                        act = process_type(subprocess_name)
                    process.actions[subprocess_name] = act
                    break

        # Values from dictionary
        if 'callback' in dic['actions'][subprocess_name]:
            process.actions[subprocess_name].callback = dic['actions'][subprocess_name]['callback']

        # Add parameters
        if 'parameters' in dic['actions'][subprocess_name]:
            process.actions[subprocess_name].parameters = dic['actions'][subprocess_name]['parameters']

        # Add pre-callback operations
        if 'pre-call' in dic['actions'][subprocess_name]:
            process.actions[subprocess_name].pre_call = dic['actions'][subprocess_name]['pre-call']

        # Add post-callback operations
        if 'post-call' in dic['actions'][subprocess_name]:
            process.actions[subprocess_name].post_call = dic['actions'][subprocess_name]['post-call']

        # Add callback return value
        if 'callback return value' in dic['actions'][subprocess_name]:
            process.actions[subprocess_name].retlabel = dic['actions'][subprocess_name]['callback return value']

        # Import condition
        if 'condition' in dic['actions'][subprocess_name]:
            process.actions[subprocess_name].condition = dic['actions'][subprocess_name]['condition']

        # Import statements
        if 'statements' in dic['actions'][subprocess_name]:
            process.actions[subprocess_name].statements = dic['actions'][subprocess_name]['statements']

        # Import process
        if 'process' in dic['actions'][subprocess_name]:
            process.actions[subprocess_name].process = dic['actions'][subprocess_name]['process']

    return process

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
