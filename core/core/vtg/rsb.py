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
from xml.etree import ElementTree
from xml.dom import minidom

import core.components
import core.session
import core.utils
from core.vtg.et import import_error_trace
from core.vtg import coverage_parser


class RSB(core.components.Component):
    def generate_verification_tasks(self):
        if 'verifier version' in self.conf['abstract task desc']:
            self.conf['VTG strategy']['verifier']['version'] = self.conf['abstract task desc']['verifier version']
        # Read max restrictions for tasks
        restrictions_file = core.utils.find_file_or_dir(self.logger, self.conf["main working directory"], "tasks.json")
        with open(restrictions_file, 'r', encoding='utf8') as fp:
            self.restrictions = json.loads(fp.read())

        # Whether coverage should be collected.
        self.is_coverage = self.conf['VTG strategy']['collect coverage'] != 'none'

        self.set_common_verifier_options()
        self.prepare_common_verification_task_desc()
        self.prepare_bug_kind_functions_file()
        property_file = self.prepare_property_file()
        files = self.prepare_src_files()
        benchmark = self.prepare_benchmark_description(files, property_file)
        self.files = files + [property_file] + [benchmark]
        self.shadow_src_dir = os.path.abspath(os.path.join(self.conf['main working directory'],
                                                           self.conf['shadow source tree']))

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

    def prepare_benchmark_description(self, files, property_file):
        # Property file may not be specified.
        self.logger.debug("Prepare benchmark.xml file")
        benchmark = ElementTree.Element("benchmark", {
            "tool": self.conf['VTG strategy']['verifier']['name'].lower()
        })
        rundefinition = ElementTree.SubElement(benchmark, "rundefinition")
        for opt in self.conf['VTG strategy']['verifier']['options']:
            for name in opt:
                ElementTree.SubElement(rundefinition, "option", {"name": name}).text = opt[name]
        ElementTree.SubElement(benchmark, "propertyfile").text = property_file

        tasks = ElementTree.SubElement(benchmark, "tasks")
        # TODO: in this case verifier is invoked per each such file rather than per all of them.
        for file in files:
            ElementTree.SubElement(tasks, "include").text = file
        with open("benchmark.xml", "w", encoding="utf8") as fp:
            fp.write(minidom.parseString(ElementTree.tostring(benchmark)).toprettyxml(indent="    "))

        return "benchmark.xml"

    def set_common_verifier_options(self):
        if self.conf['VTG strategy']['verifier']['name'] == 'CPAchecker':
            if 'options' not in self.conf['VTG strategy']['verifier']:
                self.conf['VTG strategy']['verifier']['options'] = []

            ldv_bam_optimized = False
            if 'verifier configuration' in self.conf['abstract task desc']:
                self.conf['VTG strategy']['verifier']['options'].append(
                    {self.conf['abstract task desc']['verifier configuration']: ''}
                )
            elif 'value analysis' in self.conf['VTG strategy']:
                self.conf['VTG strategy']['verifier']['options'] = [{'-valueAnalysis': ''}]
            elif 'recursion support' in self.conf['VTG strategy']:
                self.conf['VTG strategy']['verifier']['options'] = [{'-valuePredicateAnalysis-bam-rec': ''}]
            # Specify default CPAchecker configuration.
            else:
                ldv_bam_optimized = True
                if self.is_coverage:
                    self.conf['VTG strategy']['verifier']['options'].append({'-ldv-bam-optimized-coverage': ''})
                else:
                    self.conf['VTG strategy']['verifier']['options'].append({'-ldv-bam-optimized': ''})

            # Remove internal CPAchecker timeout.
            self.conf['VTG strategy']['verifier']['options'].append({'-setprop': 'limits.time.cpu={0}s'.format(
                round(self.restrictions['CPU time'] / 1000))})

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
                    round(3 * self.restrictions['memory size'] / (4 * 1000 ** 2)))})

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

            if self.is_coverage and not ldv_bam_optimized:
                self.conf['VTG strategy']['verifier']['options'].append({'-setprop': 'coverage.file=coverage.info'})
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
        self.task_desc.update(
            {
                'verifier': {
                    'name': self.conf['VTG strategy']['verifier']['name'],
                    'version': self.conf['VTG strategy']['verifier']['version']
                },
                'resource limits': self.restrictions
            }
        )

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
                property_file = 'spec.prp'

                self.logger.debug('Verifier property file was outputted to "spec.prp"')
            else:
                with open('unreach-call.prp', 'w', encoding='utf8') as fp:
                    fp.write('CHECK( init({0}()), LTL(G ! call(__VERIFIER_error())) )'.format(
                    self.conf['abstract task desc']['entry points'][0]))

                property_file = 'unreach-call.prp'

                self.logger.debug('Verifier property file was outputted to "unreach-call.prp"')
        else:
            raise ValueError('Verifier property file was not prepared since entry points were not specified')

        return property_file

    def prepare_src_files(self):
        regex = re.compile('# 40 ".*/arm-unknown-linux-gnueabi/4.6.0/include/stdarg.h"')
        files = []

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
                    trigger = False

                    # Specify original location to avoid references to *.trimmed.i files in error traces.
                    fp_out.write('# 1 "{0}"\n'.format(extra_c_file['C file']))
                    # Each such expression occupies individual line, so just get rid of them.
                    for line in fp_in:

                        # Asm volatile goto
                        l = re.sub(r'asm volatile goto.*;', '', line)

                        if not trigger and regex.match(line):
                            trigger = True
                        elif trigger:
                            l = line.replace('typedef __va_list __gnuc_va_list;',
                                             'typedef __builtin_va_list __gnuc_va_list;')
                            trigger = False

                        fp_out.write(l)

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

            files.append('cil.i')

            self.logger.debug('Merged source files was outputted to "cil.i"')
        else:
            for extra_c_file in self.conf['abstract task desc']['extra C files']:
                files.append(extra_c_file['C file'])

        return files

    def prepare_verification_task_files_archive(self):
        self.logger.info('Prepare archive with verification task files')

        with zipfile.ZipFile('task files.zip', mode='w', compression=zipfile.ZIP_DEFLATED) as zfp:
            for file in self.files:
                zfp.write(file)

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

        self.verdict = None

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

                self.verdict = 'unknown'
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

                if self.witness_processing_exception:
                    raise self.witness_processing_exception

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

        report = {
          # TODO: replace with something meaningful, e.g. tool name + tool version + tool configuration.
          'id': verification_report_id,
          'parent id': self.id,
          # TODO: replace with something meaningful, e.g. tool name + tool version + tool configuration.
          'attrs': [],
          'name': self.conf['VTG strategy']['verifier']['name'],
          'resources': decision_results['resources'],
          'log': None if self.logger.disabled else self.log_file,
          'coverage': 'coverage.json',
          'files': {'report': ([] if self.logger.disabled else [self.log_file]) +
                              (self.files if self.conf['upload input files of static verifiers'] else [])}
        }

        if self.is_coverage:
            cov = coverage_parser.LCOV(self.logger, os.path.join('output', 'coverage.info'), self.shadow_src_dir,
                                       self.conf['main working directory'],
                                       self.conf['VTG strategy']['collect coverage'])
            with open('coverage.json', 'w', encoding='utf-8') as fp:
                json.dump(cov.get_coverage(), fp, ensure_ascii=True, sort_keys=True, indent=4)

            arcnames = cov.get_arcnames()

            report['files']['coverage'] = ['coverage.json'] + list(arcnames.keys())
            report['arcname'] = arcnames

        core.utils.report(self.logger,
                          'verification',
                          report,
                          self.mqs['report files'],
                          self.conf['main working directory'])

    def process_single_verdict(self, decision_results, verification_report_id):
        # Parse reports and determine status
        benchexec_reports = glob.glob(os.path.join('output', '*.results.xml'))
        if len(benchexec_reports) != 1:
            raise FileNotFoundError('Expect strictly single BenchExec XML report file, but found {}'.
                                    format(len(benchexec_reports)))

        # Expect single report file
        with open(benchexec_reports[0], encoding="utf8") as fp:
            result = ElementTree.parse(fp).getroot()

            run = result.findall("run")[0]
            for column in run.iter("column"):
                name, value = [column.attrib.get(name) for name in ("title", "value")]
                if name == "status":
                    decision_results["status"] = value

        # Check that we have set status
        if "status" not in decision_results:
            raise KeyError("There is no solution status in BenchExec XML report")

        self.logger.info('Verification task decision status is "{0}"'.format(decision_results['status']))

        # Do not fail immediately in case of witness processing failures that often take place. Otherwise we will
        # not upload all witnesses that can be properly processed as well as information on all such failures.
        # Necessary verificaiton finish report also won't be uploaded causing Bridge to corrupt the whole job.
        self.witness_processing_exception = None

        if re.match('true', decision_results['status']):
            self.verdict = 'safe'
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
        else:
            witnesses = glob.glob(os.path.join('output', 'witness.*.graphml'))

            # Create unsafe reports independently on status. Later we will create unknown report in addition if status
            # is not "unsafe".
            if self.rule_specification == 'sync:race' and len(witnesses) != 0:
                for witness in witnesses:
                    try:
                        et = import_error_trace(self.logger, witness)

                        result = re.search(r'witness\.(.*)\.graphml', witness)
                        trace_id = result.groups()[0]
                        error_trace_name = 'error trace_' + trace_id + '.json'

                        self.logger.info('Write processed witness to "' + error_trace_name + '"')
                        arcnames = self.trim_file_names(et['files'])
                        et['files'] = [arcnames[file] for file in et['files']]
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
                                              'files': [error_trace_name] + list(arcnames.keys()),
                                              'arcname': arcnames
                                          },
                                          self.mqs['report files'],
                                          self.conf['main working directory'],
                                          trace_id)
                    except Exception as e:
                        if self.witness_processing_exception:
                            try:
                                raise e from self.witness_processing_exception
                            except Exception as e:
                                self.witness_processing_exception = e
                        else:
                            self.witness_processing_exception = e

                self.verdict = 'unsafe'

            if re.match('false', decision_results['status']) and self.rule_specification != 'sync:race':
                try:
                    if len(witnesses) != 1:
                        NotImplementedError('Just one witness is supported (but "{0}" are given)'.format(len(witnesses)))

                    et = import_error_trace(self.logger, witnesses[0])
                    self.logger.info('Write processed witness to "error trace.json"')

                    arcnames = self.trim_file_names(et['files'])
                    et['files'] = [arcnames[file] for file in et['files']]
                    with open('error trace.json', 'w', encoding='utf8') as fp:
                        json.dump(et, fp, ensure_ascii=False, sort_keys=True, indent=4)

                    core.utils.report(self.logger,
                                      'unsafe',
                                      {
                                          'id': verification_report_id + '/unsafe',
                                          'parent id': verification_report_id,
                                          'attrs': [{"Rule specification": self.rule_specification}],
                                          'error trace': 'error trace.json',
                                          'files': ['error trace.json'] + list(arcnames.keys()),
                                          'arcname': arcnames
                                      },
                                      self.mqs['report files'],
                                      self.conf['main working directory'])
                except Exception as e:
                    self.witness_processing_exception = e

                self.verdict = 'unsafe'
            elif not re.match('false', decision_results['status']):
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

                self.verdict = 'unknown'

    def create_verification_finish_report(self, verification_report_id):
        core.utils.report(self.logger,
                          'verification finish',
                          {'id': verification_report_id},
                          self.mqs['report files'],
                          self.conf['main working directory'])

    def trim_file_names(self, file_names):
        arcnames = {}
        for file_name in file_names:
            if file_name.startswith(self.shadow_src_dir):
                new_file_name = os.path.relpath(file_name, self.shadow_src_dir)
            else:
                new_file_name = core.utils.make_relative_path(self.logger, self.conf['main working directory'], file_name)
            arcnames[file_name] = new_file_name
        return arcnames
