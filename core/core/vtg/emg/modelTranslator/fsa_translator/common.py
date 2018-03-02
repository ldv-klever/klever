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
import json

from core.vtg.emg.common import get_conf_property
from core.vtg.emg.common.c.types import Pointer, Primitive


def model_comment(comment_type, text, other=None):
    if other and isinstance(other, dict):
        comment = other
    else:
        comment = dict()

    comment['type'] = comment_type.upper()
    if text:
        comment['comment'] = text

    string = json.dumps(comment)
    return "/* LDV {} */".format(string)


def action_model_comment(action, text, begin=None, callback=False):
    if action:
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
    if callback:
        data['callback'] = True
    return model_comment(type_comment, text, data)


def control_function_comment_begin(function_name, comment, identifier=None):
    data = {'function': function_name}
    if identifier:
        data['thread'] = identifier
    return model_comment('CONTROL_FUNCTION_BEGIN',
                         comment,
                         data)


def control_function_comment_end(function_name, name):
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


def model_relevant_files(analysis, cmodel, automaton):
    files = set()
    # Add declarations to files with explicit calls
    kf = analysis.get_source_function(automaton.process.name)
    files.update(kf.files_called_at)
    # Then check where we added relevant headers that may contain calls potentially
    if kf.header and len(kf.header) > 0:
        for header in (h for h in kf.header if h in cmodel.extra_headers):
            files.update(cmodel.extra_headers[header])
    return files


def add_model_function(analysis, cmodel, automaton, model):
    files = model_relevant_files(analysis, cmodel, automaton)
    for file in files:
        cmodel.add_function_declaration(file, model, extern=True)
