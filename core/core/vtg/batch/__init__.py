#!/usr/bin/python3

from core.vtg.sbt import SR


# This strategy is aimed at creating 1 verification tasks for all
# specified rules.
class BATCH(SR):

    def perform_sanity_checks(self):
        if 'unite rule specifications' not in self.conf or not self.conf['unite rule specifications']:
            raise AttributeError("Current VTG strategy supports only united bug types")

    def print_strategy_information(self):
        self.logger.info('Launch strategy "Batch"')
        self.logger.info('Generate one verification task for all bug types')

    def prepare_property_automaton(self, bug_kind=None):
        # Unite all property automata into a single file.
        automaton_name = "batch.spc"
        with open(automaton_name, 'w', encoding='ascii') as fp_out:
            for extra_c_file in self.conf['abstract task desc']['extra C files']:
                if 'automaton' in extra_c_file:
                    original_automaton = extra_c_file['automaton']
                    with open(original_automaton) as fp_in:
                        for line in fp_in:
                            fp_out.write('{0}'.format(line))
                    fp_out.write('{0}'.format('\n'))

        self.conf['VTG strategy']['verifier']['options'].append({'-spec': automaton_name})
        self.automaton_file = automaton_name

    def set_separated_time_limit(self):
        # Get the number of asserts.
        asserts = 0
        for extra_c_file in self.conf['abstract task desc']['extra C files']:
            if 'bug kinds' in extra_c_file:
                asserts += 1

        # Set time limits for BATCH strategy.
        time_limit = self.cpu_time_limit_per_rule_per_module_per_entry_point
        # Soft time limit.
        self.conf['VTG strategy']['verifier']['options'].append({'-setprop': 'limits.time.cpu={0}s'.format(
            round(asserts * time_limit / 1000))})
        # Hard time limit.
        self.conf['VTG strategy']['resource limits']['CPU time'] = asserts * time_limit