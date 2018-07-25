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

import json

from core.vtg.emg.common import get_conf_property
from core.vtg.emg.common.c.types import Pointer, Primitive


def model_comment(comment_type, text, other=None):
    """
    Print a model comment. This is a base function for some functions implemented below but sometimes it is necessary to
    use it directly.

    :param comment_type: Comment type string.
    :param text: Comment text.
    :param other: Additional existing dictionary with some data.
    :return: String with the model comment.
    """
    if other and isinstance(other, dict):
        comment = other
    else:
        comment = dict()

    comment['type'] = comment_type.upper()
    if text:
        comment['comment'] = text

    string = json.dumps(comment)
    return "/* LDV {} */".format(string)


def action_model_comment(action, text, begin=None):
    """
    Model comment for identifying an action.

    :param action: Action object.
    :param text: Action comment string.
    :param begin: True if this is a comment before the action and False otherwise.
    :param callback: If this action contains callback call.
    :return: Model comment string.
    """
    if action:
        if action.trace_relevant:
            type_comment = 'CALL'
        else:
            type_comment = type(action).__name__.upper()
        if begin is True:
            type_comment += '_BEGIN'
        elif begin is False:
            type_comment += '_END'

        name_comment = action.name.upper()
    else:
        type_comment = 'ARTIFICIAL'
        name_comment = None

    data = {'action': name_comment}
    if action and action.trace_relevant and begin is True:
        data['callback'] = True
    return model_comment(type_comment, text, data)


def control_function_comment_begin(function_name, comment, identifier=None):
    """
    Compose a comment at the beginning of a control function.

    :param function_name: Control function name.
    :param comment: Comment text.
    :param identifier: Thread identifier if necessary.
    :return: Model comment string.
    """
    data = {'function': function_name}
    if isinstance(identifier, int):
        data['thread'] = identifier + 1
    return model_comment('CONTROL_FUNCTION_BEGIN', comment, data)


def control_function_comment_end(function_name, name):
    """
    Compose a comment at the end of a control function.

    :param function_name: Control function name.
    :param name: Process or Automaton name.
    :return: Model comment string.
    """
    data = {'function': function_name}
    return model_comment('CONTROL_FUNCTION_END',
                         "End of control function based on process {!r}".format(name),
                         data)


def extract_relevant_automata(automata, automata_peers, peers, sb_type=None):
    """
    Determine which automata can receive signals from the given instance or send signals to it.

    :param automata: List with Automaton objects.
    :param automata_peers: Dictionary {'Automaton.identfier string' -> {'states': ['relevant State objects'],
                                                                        'automaton': 'Automaton object'}
    :param peers: List of relevant Process objects: [{'process': 'Process obj',
                                                     'subprocess': 'Receive or Dispatch obj'}]
    :param sb_type: Receive or Dispatch class to choose only those automata that reseive or send signals to the
                    given one
    :return: None, since it modifies the first argument.
    """
    for peer in peers:
        relevant_automata = [a for a in automata if a.process.pretty_id == peer["process"].pretty_id]
        for automaton in relevant_automata:
            if automaton.identifier not in automata_peers:
                automata_peers[automaton.identifier] = {
                    "automaton": automaton,
                    "states": set()
                }
            for state in [n for n in automaton.fsa.states if n.action and n.action.name == peer["subprocess"].name]:
                if not sb_type or isinstance(state.action, sb_type):
                    automata_peers[automaton.identifier]["states"].add(state)


def initialize_automaton_variables(conf, automaton):
    """
    Initalize automaton variables with either external allocated function calls or some known explicit values. Print
    the code of such initialization.

    :param conf: Translator configuration dictionary.
    :param automaton: Automaton object.
    :return: List of C variables initializations.
    """
    initializations = []
    for var in automaton.variables():
        if isinstance(var.declaration, Pointer) and get_conf_property(conf, 'allocate external'):
            var.use += 1
            initializations.append("{} = external_allocated_data();".format(var.name))
        elif isinstance(var.declaration, Primitive) and var.value:
            var.use += 1
            initializations.append('{} = {};'.format(var.name, var.value))

    if len(initializations) > 0:
        initializations.insert(0, '/* Initialize automaton variables */')
    return initializations


