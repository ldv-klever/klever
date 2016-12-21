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

import glob
import json
import os
import re
from abc import abstractclassmethod, ABCMeta
import sys

import core.components
import core.session
import core.utils
from core.vtg.mea import MEA
from core.vtg.et import import_error_trace


# This is an abstract class for VTG strategy.
# It includes basic abstrcat operations and common actions.
class CommonStrategy(core.components.Component):

    __metaclass__ = ABCMeta

    mpv = False  # Property automata specifications.
    mea = None  # Processes MEA action.
    path_to_error_traces = 'output/witness.*.graphml'  # Common path to all error traces.

    # This function performs all sanity checks corresponding VTG strategy.
    # In case of any violations VTG strategy will be terminated.
    @abstractclassmethod
    def perform_sanity_checks(self):
        pass

    # This function performs all preprocess actions for corresponding strategy
    # (before starting to solve verification tasks).
    @abstractclassmethod
    def perform_preprocess_actions(self):
        pass

    # This function performs all postprocess actions for corresponding strategy
    # (after solving verification tasks).
    @abstractclassmethod
    def perform_postprocess_actions(self):
        pass

    # Main cycle, in which verification tasks are prepared and solved.
    @abstractclassmethod
    def main_cycle(self):
        pass

    # This function executes VTG strategy.
    def execute(self):
        self.set_common_options()
        self.check_for_mpv()
        self.perform_sanity_checks()
        self.perform_preprocess_actions()
        self.main_cycle()
        self.perform_postprocess_actions()
        self.perform_general_postprocess_actions()

    main = execute

    def prepare_common_verification_task_desc(self):
        self.logger.debug('Prepare common verification task description')

        self.task_desc = {
            # Safely use id of corresponding abstract verification task since all bug kinds will be merged and each
            # abstract verification task will correspond to exactly one verificatoin task.
            'id': self.conf['abstract task desc']['id'],
            'format': 1,
        }
        # Copy attributes from parent job.
        for attr_name in ('priority', 'upload input files of static verifiers'):
            self.task_desc[attr_name] = self.conf[attr_name]

        for attr in self.conf['abstract task desc']['attrs']:
            attr_name = list(attr.keys())[0]
            attr_val = attr[attr_name]
            if attr_name == 'rule specification':
                self.rule_specification = attr_val

        # Use resource limits and verifier specified in job configuration.
        self.task_desc.update({name: self.conf['VTG strategy'][name] for name in ('resource limits', 'verifier')})

    def prepare_src_files(self):
        self.task_desc['files'] = []

        if self.conf['VTG strategy']['merge source files']:
            self.logger.info('Merge source files by means of CIL')

            # CIL doesn't support asm goto (https://forge.ispras.ru/issues/1323).
            self.logger.debug('Ignore asm goto expressions')

            c_files = ()
            for extra_c_file in self.conf['abstract task desc']['extra C files']:
                if 'C file' not in extra_c_file:
                    continue
                trimmed_c_file = '{0}.trimmed.i'.format(os.path.splitext(os.path.basename(extra_c_file['C file']))[0])
                with open(os.path.join(self.conf['main working directory'], extra_c_file['C file']),
                          encoding='utf8') as fp_in, open(trimmed_c_file, 'w', encoding='utf8') as fp_out:
                    # Specify original location to avoid references to *.trimmed.i files in error traces.
                    fp_out.write('# 1 "{0}"\n'.format(extra_c_file['C file']))
                    # Each such expression occupies individual line, so just get rid of them.
                    for line in fp_in:
                        fp_out.write(re.sub(r'asm volatile goto.*;', '', line))
                extra_c_file['new C file'] = trimmed_c_file
                c_files += (trimmed_c_file, )

            args = (
                       'cilly.asm.exe',
                       '--printCilAsIs',
                       '--domakeCFG',
                       '--decil',
                       '--noInsertImplicitCasts',
                       # Now supported by CPAchecker frontend.
                       '--useLogicalOperators',
                       '--ignore-merge-conflicts',
                       # Don't transform simple function calls to calls-by-pointers.
                       '--no-convert-direct-calls',
                       # Don't transform s->f to pointer arithmetic.
                       '--no-convert-field-offsets',
                       # Don't transform structure fields into variables or arrays.
                       '--no-split-structs',
                       '--rmUnusedInlines',
                       '--out', 'cil.i',
                   ) + c_files
            core.utils.execute_external_tool(self.logger, args=args)

            if not self.conf['keep intermediate files']:
                for extra_c_file in self.conf['abstract task desc']['extra C files']:
                    if 'new C file' in extra_c_file:
                        os.remove(extra_c_file['new C file'])

            self.task_desc['files'].append('cil.i')

            self.logger.debug('Merged source files was outputted to "cil.i"')
        else:
            for extra_c_file in self.conf['abstract task desc']['extra C files']:
                self.task_desc['files'].append(extra_c_file['C file'])

    def perform_general_postprocess_actions(self):
        # Remove all extra C files.
        if not self.conf['keep intermediate files']:
            for extra_c_file in self.conf['abstract task desc']['extra C files']:
                if 'C file' in extra_c_file:
                    if os.path.isfile(extra_c_file['C file']):
                        os.remove(extra_c_file['C file'])

    # This function creates 'verification' report.
    @abstractclassmethod
    def create_verification_report(self, verification_report_id, decision_results, bug_kind=None):
        pass

    # This function creates 'verification finish' report.
    def create_verification_finish_report(self, verification_report_id, bug_kind=None):
        core.utils.report(self.logger,
                          'verification finish',
                          {'id': verification_report_id},
                          self.mqs['report files'],
                          self.conf['main working directory'],
                          bug_kind)

    # If report is false, then it will be used for verifer report.
    def get_verifier_log_file(self, verifier=True):
        log_files = glob.glob(os.path.join('output', 'benchmark*logfiles/*'))

        if len(log_files) != 1:
            RuntimeError(
                'Exactly one log file should be outputted when source files are merged (but "{0}" are given)'.format(
                    log_files))

        if self.logger.disabled and verifier:
            return None
        else:
            return log_files[0]

    def parse_bug_kind(self, bug_kind):
        match = re.search(r'(.+)::(.*)', bug_kind)
        if match:
            return match.groups()[0]
        else:
            return ''

    def process_single_verdict(self, decision_results, verification_report_id,
                               assertion=None, specified_error_trace=None):
        if not assertion:
            assertion = self.rule_specification
        added_attrs = [{"Rule specification": assertion}]
        path_to_witness = None
        if decision_results['status'] == 'unsafe':
            verification_report_id_unsafe = "{0}/unsafe/{1}".\
                format(verification_report_id, assertion or '')

            # If strategy may produce more than 1 witness, it should be specified in 'specified_witness'.
            if specified_error_trace:
                path_to_witness = specified_error_trace
            # Default place for witness, if we consider only 1 possible witness for verification task.
            else:
                path_to_witness = glob.glob(os.path.join('output', 'witness.*.graphml'))[0]

            if self.mea:
                if self.mea.error_trace_filter(path_to_witness, assertion):
                    self.logger.debug('Processing error trace "{0}"'.format(path_to_witness, assertion))
                    new_error_trace_number = self.mea.get_current_error_trace_number(assertion)
                    verification_report_id_unsafe = "{0}/{1}".\
                        format(verification_report_id_unsafe, new_error_trace_number)
                    if not assertion:
                        assertion = ''
                    assertion += "{0}".format(new_error_trace_number)
                    self.logger.info(assertion)
                    added_attrs.append({"Error trace number": "{0}".format(new_error_trace_number)})
                else:
                    self.logger.info('Error trace "{0}" is equivalent to one of the already processed'.
                                     format(path_to_witness))
                    return

        self.logger.info('Verification task decision status is "{0}"'.format(decision_results['status']))

        if decision_results['status'] == 'safe':
            core.utils.report(self.logger,
                              'safe',
                              {
                                  'id': verification_report_id + '/safe/{0}'.format(assertion or ''),
                                  'parent id': verification_report_id,
                                  'attrs': added_attrs,
                                  # TODO: at the moment it is unclear what are verifier proofs.
                                  'proof': None
                              },
                              self.mqs['report files'],
                              self.conf['main working directory'],
                              assertion)
        elif decision_results['status'] == 'unsafe':
            self.logger.info('Process witness')
            et = import_error_trace(self.logger, path_to_witness)

            self.logger.info('Write processed witness to "error trace.json"')
            with open('error trace.json', 'w', encoding='utf8') as fp:
                json.dump(et, fp, ensure_ascii=False, sort_keys=True, indent=4)

            core.utils.report(self.logger,
                              'unsafe',
                              {
                                  'id': verification_report_id_unsafe,
                                  'parent id': verification_report_id,
                                  'attrs': added_attrs,
                                  'error trace': 'error trace.json',
                                  'files': ['error trace.json'] + et['files']
                              },
                              self.mqs['report files'],
                              self.conf['main working directory'],
                              assertion)
        else:
            # Prepare file to send it with unknown report.
            if decision_results['status'] in ('CPU time exhausted', 'memory exhausted'):
                with open('error.txt', 'w', encoding='utf8') as fp:
                    fp.write(decision_results['status'])
            else:
                log_file = self.get_verifier_log_file(False)
            core.utils.report(self.logger,
                              'unknown',
                              {
                                  'id': verification_report_id + '/unknown/{0}'.format(assertion or ''),
                                  'parent id': verification_report_id,
                                  'attrs': added_attrs,
                                  # TODO: just the same file as parent log, looks strange.
                                  'problem desc': log_file if decision_results['status'] not in (
                                      'CPU time exhausted', 'memory exhausted') else 'error.txt',
                                  'files': [log_file if decision_results['status'] not in (
                                      'CPU time exhausted', 'memory exhausted') else 'error.txt']
                              },
                              self.mqs['report files'],
                              self.conf['main working directory'],
                              assertion)
        self.rule_specification = assertion or self.rule_specification
        self.verification_status = decision_results['status']

    def print_mea_stats(self):
        if self.mea:
            # We treat MEA as a pseudo-component: it does not have a "main" function,
            # but it consumes resources and has some attributes.
            wall_time = self.mea.get_consuimed_wall_time()
            internal_filter = self.mea.get_number_of_error_traces_before_external_filter()
            external_filter = self.mea.get_number_of_error_traces_after_external_filter()
            self.logger.info('MEA external filtering was taken "{0}s"'.
                             format(wall_time))
            self.logger.info('The number of error traces before external filtering is "{0}"'.
                             format(internal_filter))
            self.logger.info('The number of error traces after external filtering is "{0}"'.
                             format(external_filter))
            resources = {
                "CPU time": round(1000 * wall_time),
                "memory size": 0,
                "wall time": round(1000 * wall_time)}
            core.utils.report(self.logger,
                              'verification',
                              {
                                  'id': self.id + "MEA",
                                  'parent id': self.id,
                                  'attrs': [{"Internal filter": "{0}".format(internal_filter)},
                                            {"External filter": "{0}".format(external_filter)}],
                                  'name': "MEA",
                                  'resources': resources,
                                  'log': None
                              },
                              self.mqs['report files'],
                              self.conf['main working directory'],
                              "MEA")

    def get_all_bug_kinds(self):
        bug_kinds = []
        for extra_c_file in self.conf['abstract task desc']['extra C files']:
            if 'bug kinds' in extra_c_file:
                for bug_kind in extra_c_file['bug kinds']:
                    if bug_kind not in bug_kinds:
                        bug_kinds.append(bug_kind)
        bug_kinds.sort()
        return bug_kinds

    def create_mea(self):
        if 'mea' in self.conf['VTG strategy']['verifier'] and self.conf['VTG strategy']['verifier']['mea']:
            self.mea = MEA(self.conf, self.logger)
        # Do not set this very useful option until it will be fully supported by all analyses
        # (https://forge.ispras.ru/issues/7342).
        # # Very useful option for all strategies.
        # self.conf['VTG strategy']['verifier']['options'].append(
        #     {'-setprop': 'cpa.arg.errorPath.exportImmediately=true'})

    def check_for_mpv(self):
        if 'RSG strategy' in self.conf and self.conf['RSG strategy'] == 'property automaton':
            self.mpv = True
            self.logger.info('Using property automata as specifications')

    def set_common_options(self):
        if self.conf['VTG strategy']['verifier']['name'] == 'CPAchecker':
            if 'options' not in self.conf['VTG strategy']['verifier']:
                self.conf['VTG strategy']['verifier']['options'] = []

            self.conf['VTG strategy']['verifier']['options'].append({'-setprop': 'limits.time.cpu={0}s'.format(
                round(self.conf['VTG strategy']['resource limits']['CPU time'] / 1000))})

            if 'value analysis' in self.conf['VTG strategy']:
                self.conf['VTG strategy']['verifier']['options'] = [{'-valueAnalysis': ''}]
            elif 'caching' in self.conf['VTG strategy']:
                self.conf['VTG strategy']['verifier']['options'] = [{'-ldv-bam': ''}]
            elif 'recursion support' in self.conf['VTG strategy']:
                self.conf['VTG strategy']['verifier']['options'] = [{'-valuePredicateAnalysis-bam-rec': ''}]

            # To refer to original source files rather than to CIL ones.
            self.conf['VTG strategy']['verifier']['options'].append({'-setprop': 'parser.readLineDirectives=true'})

            # To allow to output multiple error traces if other options (configuration) will need this.
            self.conf['VTG strategy']['verifier']['options'].append(
                {'-setprop': 'counterexample.export.graphml=witness.%d.graphml'})

            # Do not compress witnesses as, say, CPAchecker r20376 we still used did.
            self.conf['VTG strategy']['verifier']['options'].append(
                {'-setprop': 'counterexample.export.compressWitness=false'})

            # Adjust JAVA heap size for static memory (Java VM, stack, and native libraries e.g. MathSAT) to be 1/4 of
            # general memory size limit if users don't specify their own sizes.
            if '-heap' not in [list(opt.keys())[0] for opt in self.conf['VTG strategy']['verifier']['options']]:
                self.conf['VTG strategy']['verifier']['options'].append({'-heap': '{0}m'.format(
                    round(3 * self.conf['VTG strategy']['resource limits']['memory size'] / (4 * 1000 ** 2)))})

            if 'bit precision analysis' in self.conf['VTG strategy']:
                self.conf['VTG strategy']['verifier']['options'].extend([
                    {'-setprop': 'cpa.predicate.encodeBitvectorAs=BITVECTOR'},
                    {'-setprop': 'solver.solver=MATHSAT5'}
                ])

            if 'graph traversal algorithm' in self.conf['VTG strategy'] \
                    and self.conf['VTG strategy']['graph traversal algorithm'] != 'Default':
                algo_map = {'Depth-first search': 'DFS', 'Breadth-first search': 'BFS', 'Random': 'RAND'}
                self.conf['VTG strategy']['verifier']['options'].append(
                    {'-setprop': 'analysis.traversal.order={0}'.format(
                        algo_map[self.conf['VTG strategy']['graph traversal algorithm']])}
                )

    def add_option_for_entry_point(self):
        if 'entry points' in self.conf['abstract task desc']:
            if len(self.conf['abstract task desc']['entry points']) > 1:
                raise NotImplementedError('Several entry points are not supported')
            self.conf['VTG strategy']['verifier']['options'].append(
                {'-entryfunction': self.conf['abstract task desc']['entry points'][0]})
