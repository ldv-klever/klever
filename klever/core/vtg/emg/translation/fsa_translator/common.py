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

from klever.core.vtg.emg.common.process import Action
from klever.core.vtg.emg.common.c.types import Pointer, Primitive


def extract_relevant_automata(logger, automata, automata_peers, peers, sb_type=None):
    """
    Determine which automata can receive signals from the given instance or send signals to it.

    :param logger: Logger object.
    :param automata: List with Automaton objects.
    :param automata_peers: Dictionary {'Automaton.identifier string' -> {'states': ['relevant State objects'],
                                                                        'automaton': 'Automaton object'}
    :param peers: List of relevant Peer objects.
    :param sb_type: Receive or Dispatch class to choose only those automata that receive or send signals to the
                    given one
    :return: None, since it modifies the first argument.
    """
    for peer in peers:
        relevant_automata = [a for a in automata if a.process == peer.process]
        if relevant_automata:
            for automaton in relevant_automata:
                if automaton not in automata_peers:
                    automata_peers[automaton] = {
                        "automaton": automaton,
                        "actions": sortedcontainers.SortedSet()
                    }
                for action in [n for n in automaton.process.actions.filter(include={Action}) if n == peer.action]:
                    if not sb_type or isinstance(action, sb_type):
                        automata_peers[automaton]["actions"].add(action)
        else:
            logger.debug("No automata peers found for {!r}, total available: {}".
                         format(str(peer.process), ', '.join({str(a.process) for a in automata})))


def initialize_automaton_variables(conf, automaton):
    """
    Initialize automaton variables with either external allocated function calls or some known explicit values. Print
    the code of such initialization.

    :param conf: Translator configuration dictionary.
    :param automaton: Automaton object.
    :return: List of C variables initializations.
    """
    initializations = []
    for var in automaton.variables():
        if isinstance(var.declaration, Pointer) and conf.get('allocate external', True):
            var.use += 1
            initializations.append("{} = external_allocated_data();".format(var.name))
        elif isinstance(var.declaration, Primitive) and var.value:
            var.use += 1
            initializations.append('{} = {};'.format(var.name, var.value))

    if len(initializations) > 0:
        initializations.insert(0, '/* Initialize automaton variables */')
    return initializations
