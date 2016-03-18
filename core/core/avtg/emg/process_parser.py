import re

from core.avtg.emg.common.signature import import_signature
from core.avtg.emg.common.process import Process, Label, Receive, Dispatch, Callback, CallbackRetval, Condition, \
    Subprocess


__process_grammar = \
'''
(* Main expression *)
FinalProcess = (Operators | Bracket)$;
Operators = Switch | Sequence;

(* Signle process *)
Process = Null | ReceiveProcess | SendProcess | SubprocessProcess | ConditionProcess | Bracket;
Null = null:'0';
ReceiveProcess = receive:Receive;
SendProcess = dispatch:Send;
SubprocessProcess = subprocess:Subprocess;
ConditionProcess = condition:Condition;
Receive = '('[replicative:'!']name:identifier[number:Repetition]')';
Send = '['[broadcast:'@']name:identifier[number:Repetition]']';
Condition = '<'name:identifier[number:Repetition]'>';
Subprocess = '{'name:identifier'}';

(* Operators *)
Sequence = sequence:SequenceExpr;
Switch = options:SwitchExpr;
SequenceExpr = @+:Process{'.'@+:Process}*;
SwitchExpr = @+:Sequence{'|'@+:Sequence}+;

(* Brackets *)
Bracket = process:BracketExpr;
BracketExpr = '('@:Operators')';

(* Basic expressions and terminals *)
Repetition = '['@:(number | label)']';
identifier = /\w+/;
number = /\d+/;
label = /%\w+%/;
'''
__process_model = None


def parse_event_specification(logger, raw):
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


def process_parse(string):
    __check_grammar()
    return __process_model.parse(string, ignorecase=True)


def __check_grammar():
    global __process_model

    if not __process_model:
        import grako
        __process_model = grako.genmodel('process', __process_grammar)


def __generate_regex_set(subprocess_name):
    dispatch_template = '\[@?{}(?:\[[^)]+\])?\]'
    receive_template = '\(!?{}(?:\[[^)]+\])?\)'
    condition_template = '<{}(?:\[[^)]+\])?>'
    subprocess_template = '{}'

    subprocess_re = re.compile('\{' + subprocess_template.format(subprocess_name) + '\}')
    receive_re = re.compile(receive_template.format(subprocess_name))
    dispatch_re = re.compile(dispatch_template.format(subprocess_name))
    condition_template_re = re.compile(condition_template.format(subprocess_name))
    regexes = [
        {'regex': subprocess_re, 'type': Subprocess},
        {'regex': dispatch_re, 'type': Dispatch},
        {'regex': receive_re, 'type': Receive},
        {'regex': condition_template_re, 'type': Condition}
    ]

    return regexes


def __import_process(name, dic):
    process = Process(name)

    if 'labels' in dic:
        for name in dic['labels']:
            label = Label(name)
            process.labels[name] = label

            for att in ['container', 'resource', 'callback', 'parameter', 'value', 'pointer']:
                if att in dic:
                    setattr(label, att, dic['labels'][name][att])

            if 'interface' in dic['labels'][name]:
                if type(dic['labels'][name]['interface']) is str:
                    label.set_declaration(dic['labels'][name]['interface'], None)
                elif type(dic['labels'][name]['interface']) is list:
                    for string in dic['labels'][name]['interface']:
                        label.set_declaration(string, None)
                else:
                    TypeError('Expect list or string with interface identifier')
            if 'signature' in dic:
                label.primary_signature = import_signature(dic['labels'][name]['signature'])

    # Import process
    process_strings = []
    if 'process' in dic:
        process.process = dic['process']
        process.process_ast = process_parse(process.process)

        process_strings.append(dic['process'])

    # Import subprocesses
    if 'actions' in dic:
        for name in dic['actions']:
            process.actions[name] = None

            if 'process' in dic['actions'][name]:
                process_strings.append(dic['actions'][name]['process'])

    for subprocess_name in process.actions:
        regexes = __generate_regex_set(subprocess_name)

        for regex in regexes:
            for string in process_strings:
                if regex['regex'].search(string):
                    process_type = regex['type']
                    if process_type is Dispatch and 'callback' in dic['actions'][subprocess_name]:
                        act = Callback(subprocess_name)
                    elif process_type is Receive and 'callback' in dic['actions'][subprocess_name]:
                        act = CallbackRetval(subprocess_name)
                    else:
                        act = process_type(subprocess_name)
                    process.actions[subprocess_name] = act
                    break

        # Values from dictionary
        if 'callback' in dic:
            process.actions[subprocess_name].callback = dic['callback']

        # Add parameters
        if 'parameters' in dic:
            process.actions[subprocess_name].parameters = dic['parameters']

        # Add callback return value
        if 'callback return value' in dic:
            process.actions[subprocess_name].callback_retval = dic['callback return value']

        # Import condition
        if 'condition' in dic:
            process.actions[subprocess_name].condition = dic['condition']

        # Import statements
        if 'statements' in dic:
            process.actions[subprocess_name].statements = dic['statements']

        # Import process
        if 'process' in dic:
            process.actions[subprocess_name].process = dic['process']

            # Parse process
            process.actions[subprocess_name].process_ast = process_parse(process.actions[subprocess_name].process)

    return process

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
