#!/usr/bin/python3

import re

from core.vtg.mpv import MPV


# Multy-Property Verification with Bug Kinds.
class MPVBK(MPV):

    def print_strategy_information(self):
        self.logger.info('Launch Multy-Property Verification')
        self.logger.info('Generate one verification task and check all asserts at once by means of MPV')

    def create_asserts(self):
        for extra_c_file in self.conf['abstract task desc']['extra C files']:
            if 'bug kinds' in extra_c_file:
                counter = 0
                automaton = extra_c_file['automaton']
                for bug_kind in extra_c_file['bug kinds']:
                    counter += 1
                    preprocessed_automaton = "{0}.spc".format(bug_kind)

                    with open(preprocessed_automaton, 'w', encoding='ascii') as fp_out, \
                            open(automaton, encoding='ascii') as fp_in:
                        cur_state = None

                        # TODO: in general case there may be more than 1 internal variable
                        internal_var = None
                        for line in fp_in:
                            # Current pattern for internal vars: ENTRY -> ENCODE {<type> <var><...>}
                            if not internal_var:
                                res = re.search(r'ENTRY(\s+)->(\s+)ENCODE(\s+)\{(\w+)(\s+)(\w+)(.*)\}', line)
                                if res:
                                    internal_var = res.group(6)
                            if internal_var:
                                line = re.sub(internal_var, '{0}_{1}'.format(internal_var, counter), line)
                            # Current pattern for state declaration: STATE USEALL|USEFIRST <name> :
                            res = re.search(r'STATE(\s*)(\w+)(\s*)(\w+)(\s*):', line)
                            if res:
                                cur_state = res.group(4)
                            res = re.search(r'ERROR\(\"(.+)\"\);', line)
                            if res:
                                current_bug_kind = res.group(1)
                                if not current_bug_kind == bug_kind:
                                    line = re.sub(r'ERROR\(\"(.+)\"\);', 'GOTO {0};'.format(cur_state), line)
                                    self.logger.debug('Removing bug kind {0}'.format(current_bug_kind))
                            res = re.search(r'OBSERVER AUTOMATON (.+)', line)
                            if res:
                                old_name = res.group(1)
                                new_name = old_name + '_' + '{0}'.format(counter)
                                line = re.sub(old_name, new_name, line)
                            fp_out.write(line)
                    self.property_automata[bug_kind] = preprocessed_automaton
        self.logger.debug('Multi-Property Verification will check "{0}" properties'.
                          format(self.property_automata.__len__()))

    def create_property_automata(self):
        pass
