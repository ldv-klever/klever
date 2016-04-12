#!/usr/bin/python3

from core.vtg.sbt import SBT


# This strategy is aimed at creating 1 verification tasks for all
# specified bug types.
class Batch(SBT):

    def perform_sanity_checks(self):
        if 'unite rule specifications' not in self.conf['abstract task desc']['AVTG'] \
                or not self.conf['abstract task desc']['AVTG']['unite rule specifications']:
            raise AttributeError("Current VTG strategy supports only united bug types")

    def print_strategy_information(self):
        self.logger.info('Launch strategy "Batch"')
        self.logger.info('Generate one verification task for all bug types')

    def prepare_property_automaton(self, bug_kind=None):
        # Unite all property automata into a single file.

        united_automaton = []
        for extra_c_file in self.conf['abstract task desc']['extra C files']:
            if 'automaton' in extra_c_file:
                automaton = extra_c_file['automaton']
                united_automaton = united_automaton.__add__(automaton)
                united_automaton.append('\n')

        automaton_name = self.conf['abstract task desc']['attrs'][1]['rule specification'] + ".spc"
        self.automaton_file = automaton_name

        with open(automaton_name, 'w', encoding='ascii') as fp:
            for line in united_automaton:
                fp.write('{0}'.format(line))
        self.conf['VTG strategy']['verifier']['options'].append({'-spec': automaton_name})
