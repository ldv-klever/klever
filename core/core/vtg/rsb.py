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
import time
import zipfile

import core.components
import core.session
import core.utils
from core.vtg.et import import_error_trace


class RSB(core.components.Component):
    def generate_verification_tasks(self):
        self.set_common_verifier_options()
        self.prepare_common_verification_task_desc()
        self.prepare_bug_kind_functions_file()
        self.prepare_property_file()
        self.prepare_src_files()

        if self.conf['keep intermediate files']:
            self.logger.debug('Create verification task description file "task.json"')
            with open('task.json', 'w', encoding='utf8') as fp:
                json.dump(self.task_desc, fp, ensure_ascii=False, sort_keys=True, indent=4)

        self.prepare_verification_task_files_archive()
        self.decide_verification_task()

        # Remove all extra C files.
        if not self.conf['keep intermediate files']:
            for extra_c_file in self.conf['abstract task desc']['extra C files']:
                if 'C file' in extra_c_file:
                    if os.path.isfile(extra_c_file['C file']):
                        os.remove(extra_c_file['C file'])

    main = generate_verification_tasks

    def set_common_verifier_options(self):
        if self.conf['VTG strategy']['verifier']['name'] == 'CPAchecker':
            if 'options' not in self.conf['VTG strategy']['verifier']:
                self.conf['VTG strategy']['verifier']['options'] = []

            self.conf['VTG strategy']['verifier']['options'].append({'-setprop': 'limits.time.cpu={0}s'.format(
                round(self.conf['VTG strategy']['resource limits']['CPU time'] / 1000))})

            if 'verifier configuration' in self.conf['abstract task desc']:
                self.conf['VTG strategy']['verifier']['options'].append(
                    {self.conf['abstract task desc']['verifier configuration']: ''}
                )
            elif 'value analysis' in self.conf['VTG strategy']:
                self.conf['VTG strategy']['verifier']['options'] = [{'-valueAnalysis': ''}]
            elif 'caching' in self.conf['VTG strategy']:
                self.conf['VTG strategy']['verifier']['options'] = [{'-ldv-bam-svcomp': ''}]
            elif 'recursion support' in self.conf['VTG strategy']:
                self.conf['VTG strategy']['verifier']['options'] = [{'-valuePredicateAnalysis-bam-rec': ''}]
            # Specify default CPAchecker configuration.
            #else:
            #    self.conf['VTG strategy']['verifier']['options'].append({'-ldv': ''})

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

            if 'verifier options' in self.conf['abstract task desc']:
                self.conf['VTG strategy']['verifier']['options'].extend(
                    self.conf['abstract task desc']['verifier options']
                )
        else:
            raise NotImplementedError(
                'Verifier {0} is not supported'.format(self.conf['VTG strategy']['verifier']['name']))

    def prepare_common_verification_task_desc(self):
        self.logger.debug('Prepare common verification task description')

        self.task_desc = {
            # Safely use id of corresponding abstract verification task since all bug kinds will be merged and each
            # abstract verification task will correspond to exactly one verificatoin task.
            'id': self.conf['abstract task desc']['id'],
            'job id': self.conf['identifier'],
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

    def prepare_bug_kind_functions_file(self):
        self.logger.debug('Prepare bug kind functions file "bug kind funcs.c"')

        bug_kinds = []
        for extra_c_file in self.conf['abstract task desc']['extra C files']:
            if 'bug kinds' in extra_c_file:
                for bug_kind in extra_c_file['bug kinds']:
                    if bug_kind not in bug_kinds:
                        bug_kinds.append(bug_kind)
        bug_kinds.sort()

        # Create bug kind function definitions that all call __VERIFIER_error() since this strategy doesn't distinguish
        # different bug kinds.
        with open('bug kind funcs.c', 'w', encoding='utf8') as fp:
            fp.write('/* http://sv-comp.sosy-lab.org/2015/rules.php */\nvoid __VERIFIER_error(void);\n')
            for bug_kind in bug_kinds:
                fp.write('void ldv_assert_{0}(int expr) {{\n\tif (!expr)\n\t\t__VERIFIER_error();\n}}\n'.format(
                    re.sub(r'\W', '_', bug_kind)))

        # Add bug kind functions file to other abstract verification task files. Absolute file path is required to get
        # absolute path references in error traces.
        self.conf['abstract task desc']['extra C files'].append({'C file': os.path.abspath('bug kind funcs.c')})

    def prepare_property_file(self):
        self.logger.info('Prepare verifier property file')

        if 'entry points' in self.conf['abstract task desc']:
            if len(self.conf['abstract task desc']['entry points']) > 1:
                raise NotImplementedError('Several entry points are not supported')

            if 'verifier specifications' in self.conf['abstract task desc']:
                with open('spec.prp', 'w', encoding='utf8') as fp:
                    for spec in self.conf['abstract task desc']['verifier specifications']:
                        fp.write('CHECK( init({0}()), {1} )\n'.format(
                            self.conf['abstract task desc']['entry points'][0], spec))
                self.task_desc['property file'] = 'spec.prp'

                self.logger.debug('Verifier property file was outputted to "spec.prp"')
            else:
                with open('unreach-call.prp', 'w', encoding='utf8') as fp:
                    fp.write('CHECK( init({0}()), LTL(G ! call(__VERIFIER_error())) )'.format(
                    self.conf['abstract task desc']['entry points'][0]))

                self.task_desc['property file'] = 'unreach-call.prp'

                self.logger.debug('Verifier property file was outputted to "unreach-call.prp"')
        else:
            self.logger.warning('Verifier property file was not prepared since entry points were not specified')

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

    def prepare_verification_task_files_archive(self):
        self.logger.info('Prepare archive with verification task files')

        with zipfile.ZipFile('task files.zip', mode='w') as zfp:
            if self.task_desc['property file']:
                zfp.write(self.task_desc['property file'])
            for file in self.task_desc['files']:
                zfp.write(file)
            self.task_desc['files'] = [os.path.basename(file) for file in self.task_desc['files']]

    def decide_verification_task(self):
        self.logger.info('Decide verification task')

        core.utils.report(self.logger,
                          'data',
                          {
                              'id': self.id,
                              'data': {'the number of verification tasks prepared for abstract verification task': 1}
                          },
                          self.mqs['report files'],
                          self.conf['main working directory'])

        self.verification_status = None

        if not self.task_desc['property file']:
            self.logger.warning('Verification task will not be decided since verifier property file was not prepared')
            return

        session = core.session.Session(self.logger, self.conf['Klever Bridge'], self.conf['identifier'])
        task_id = session.schedule_task(self.task_desc)

        while True:
            task_status = session.get_task_status(task_id)
            self.logger.info('Status of verification task "{0}" is "{1}"'.format(task_id, task_status))

            if task_status == 'ERROR':
                task_error = session.get_task_error(task_id)

                self.logger.warning('Failed to decide verification task: {0}'.format(task_error))

                with open('task error.txt', 'w', encoding='utf8') as fp:
                    fp.write(task_error)

                core.utils.report(self.logger,
                                  'unknown',
                                  {
                                      'id': self.id + '/unknown',
                                      'parent id': self.id,
                                      'problem desc': 'task error.txt',
                                      'files': ['task error.txt']
                                  },
                                  self.mqs['report files'],
                                  self.conf['main working directory'])

                self.verification_status = 'unknown'
                break

            if task_status == 'FINISHED':
                self.logger.info('Verification task was successfully decided')

                session.download_decision(task_id)

                with zipfile.ZipFile('decision result files.zip') as zfp:
                    zfp.extractall()

                with open('decision results.json', encoding='utf8') as fp:
                    decision_results = json.load(fp)

                verification_report_id = '{0}/verification'.format(self.id)

                self.create_verification_report(verification_report_id, decision_results)

                self.process_single_verdict(decision_results, verification_report_id)

                self.create_verification_finish_report(verification_report_id)

                break

            time.sleep(1)

    def create_verification_report(self, verification_report_id, decision_results):
        # TODO: specify the computer where the verifier was invoked (this information should be get from BenchExec or VerifierCloud web client.
        log_files = glob.glob(os.path.join('output', 'benchmark*logfiles/*'))

        if len(log_files) != 1:
            RuntimeError(
                'Exactly one log file should be outputted when source files are merged (but "{0}" are given)'.format(
                    log_files))

        self.log_file = log_files[0]

        core.utils.report(self.logger,
                          'verification',
                          {
                              # TODO: replace with something meaningful, e.g. tool name + tool version + tool configuration.
                              'id': verification_report_id,
                              'parent id': self.id,
                              # TODO: replace with something meaningful, e.g. tool name + tool version + tool configuration.
                              'attrs': [],
                              'name': self.conf['VTG strategy']['verifier']['name'],
                              'resources': decision_results['resources'],
                              'log': None if self.logger.disabled else self.log_file,
                              'files': ([] if self.logger.disabled else [self.log_file]) + (
                                  (['benchmark.xml'] if os.path.isfile('benchmark.xml') else []) +
                                  [self.task_desc['property file']] + self.task_desc['files']
                                  if self.conf['upload input files of static verifiers']
                                  else []
                              )
                          },
                          self.mqs['report files'],
                          self.conf['main working directory'])

    def process_single_verdict(self, decision_results, verification_report_id):
        self.logger.info('Verification task decision status is "{0}"'.format(decision_results['status']))

        if decision_results['status'] == 'safe':
            core.utils.report(self.logger,
                              'safe',
                              {
                                  'id': verification_report_id + '/safe',
                                  'parent id': verification_report_id,
                                  'attrs': [{"Rule specification": self.rule_specification}],
                                  # TODO: at the moment it is unclear what are verifier proofs.
                                  'proof': None
                              },
                              self.mqs['report files'],
                              self.conf['main working directory'])
        #elif decision_results['status'] == 'unsafe':
        else:
            self.logger.info('Process witness')

            witnesses = glob.glob(os.path.join('output', 'witness.*.graphml'))

            if self.rule_specification == 'linux:races' and len(witnesses) != 0:

                for i in range(0, len(witnesses)):
                    et = import_error_trace(self.logger, witnesses[0])

                    result = re.search(r'witness\.(.*)\.graphml', witnesses[i])
                    trace_id = result.groups()[0]
                    error_trace_name = 'error trace_' + trace_id + '.json'

                    self.logger.info('Write processed witness to "' + error_trace_name + '"')
                    with open(error_trace_name, 'w', encoding='utf8') as fp:
                        json.dump(et, fp, ensure_ascii=False, sort_keys=True, indent=4)

                    core.utils.report(self.logger,
                                      'unsafe',
                                      {
                                          'id': verification_report_id + '/unsafe' + '_' + trace_id,
                                          'parent id': verification_report_id,
                                          'attrs': [
                                              {"Rule specification": self.rule_specification},
                                              {"Error trace identifier": trace_id}],
                                          'error trace': error_trace_name,
                                          'files': [error_trace_name] + et['files']
                                      },
                                      self.mqs['report files'],
                                      self.conf['main working directory'],
                                      trace_id)

            elif decision_results['status'] == 'unsafe':
                if len(witnesses) != 1:
                    NotImplementedError('Just one witness is supported (but "{0}" are given)'.format(len(witnesses)))

                et = import_error_trace(self.logger, witnesses[0])
                self.logger.info('Write processed witness to "error trace.json"')
                with open('error trace.json', 'w', encoding='utf8') as fp:
                    json.dump(et, fp, ensure_ascii=False, sort_keys=True, indent=4)

                core.utils.report(self.logger,
                                  'unsafe',
                                  {
                                      'id': verification_report_id + '/unsafe',
                                      'parent id': verification_report_id,
                                      'attrs': [{"Rule specification": self.rule_specification}],
                                      'error trace': 'error trace.json',
                                      'files': ['error trace.json'] + et['files']
                                  },
                                  self.mqs['report files'],
                                  self.conf['main working directory'])
            else:
                # Prepare file to send it with unknown report.
                # TODO: otherwise just the same file as parent log is reported, looks strange.

                if decision_results['status'] in ('CPU time exhausted', 'memory exhausted'):
                    self.log_file = 'error.txt'

                with open(self.log_file, 'w', encoding='utf8') as fp:
                    fp.write(decision_results['status'])

                core.utils.report(self.logger,
                                  'unknown',
                                  {
                                      'id': verification_report_id + '/unknown',
                                      'parent id': verification_report_id,
                                      'attrs': [{"Rule specification": self.rule_specification}],
                                      'problem desc': self.log_file,
                                      'files': [self.log_file]
                                  },
                                  self.mqs['report files'],
                                  self.conf['main working directory'])



        self.verification_status = decision_results['status']

    def create_verification_finish_report(self, verification_report_id):
        core.utils.report(self.logger,
                          'verification finish',
                          {'id': verification_report_id},
                          self.mqs['report files'],
                          self.conf['main working directory'])
