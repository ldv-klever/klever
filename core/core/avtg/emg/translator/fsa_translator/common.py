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


def model_comment(action, text, begin=None):
        if action:
            type_comment = type(action).__name__.upper()
            if begin is True:
                type_comment += '_BEGIN'
            elif begin is False:
                type_comment += '_END'

            name_comment = action.name.upper()
        else:
            type_comment = 'ARTIFICIAL'

        if name_comment:
            return "/* {0} {2} {1} */".format(type_comment, text, name_comment)
        else:
            return "/* {0} {1} */".format(type_comment, text)


def extract_relevant_automata(self, automata_peers, peers, sb_type=None):
    """
    Determine which automata can receive signals from the given instance or send signals to it.

    :param automata_peers: Dictionary {'Automaton.identfier string' -> {'states': ['relevant State objects'],
                                                                        'automaton': 'Automaton object'}
    :param peers: List of relevant Process objects: [{'process': 'Process obj',
                                                     'subprocess': 'Receive or Dispatch obj'}]
    :param sb_type: Receive or Dispatch class to choose only those automata that reseive or send signals to the
                    given one
    :return: None, since it modifies the first argument.
    """
    self.logger.debug("Searching for a relevant automata")

    for peer in peers:
        relevant_automata = [automaton for automaton in self._callback_fsa + self._model_fsa + [self._entry_fsa]
                             if automaton.process.identifier == peer["process"].identifier]
        for automaton in relevant_automata:
            if automaton.identifier not in automata_peers:
                automata_peers[automaton.identifier] = {
                    "automaton": automaton,
                    "states": set()
                }
            for state in [node for node in automaton.fsa.states
                          if node.action and node.action.name == peer["subprocess"].name]:
                if not sb_type or isinstance(state.action, sb_type):
                    automata_peers[automaton.identifier]["states"].add(state)

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
