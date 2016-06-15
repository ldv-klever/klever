#!/usr/bin/python3

import glob
import json
import os
import re
import shutil
import tarfile
import time
from xml.dom import minidom

import core.components
import core.session
import core.utils


class ABKM(core.components.Component):
    def generate_verification_tasks(self):
        self.logger.info('Generate one verification task by merging all bug kinds')

        self.prepare_common_verification_task_desc()
        self.prepare_verifier_specific_verificition_task_desc()
        self.prepare_property_file()
        self.prepare_src_files()

        if self.conf['keep intermediate files']:
            self.logger.debug('Create verification task description file "task.json"')
            with open('task.json', 'w', encoding='ascii') as fp:
                json.dump(self.task_desc, fp, sort_keys=True, indent=4)

        self.prepare_verification_task_files_archive()
        self.decide_verification_task()

    main = generate_verification_tasks

    def prepare_common_verification_task_desc(self):
        self.logger.info('Prepare common verification task description')

        self.task_desc = {
            # Safely use id of corresponding abstract verification task since all bug kinds will be merged and each
            # abstract verification task will correspond to exactly one verificatoin task.
            'id': self.conf['abstract task desc']['id'],
            'format': 1,
        }
        # Copy attributes from parent job.
        for attr_name in ('priority', 'upload input files of static verifiers'):
            self.task_desc[attr_name] = self.conf[attr_name]

        # Use resource limits and verifier specified in job configuration.
        self.task_desc.update({name: self.conf['VTG strategy'][name] for name in ('resource limits', 'verifier')})

    def prepare_verifier_specific_verificition_task_desc(self):
        if self.task_desc['verifier']['name'] == 'CPAchecker':
            if 'options' not in self.task_desc['verifier']:
                self.task_desc['verifier']['options'] = []

            # To refer to original source files rather than to CIL ones.
            self.task_desc['verifier']['options'].append({'-setprop': 'parser.readLineDirectives=true'})

            # To allow to output multiple error traces if other options (configuration) will need this.
            self.task_desc['verifier']['options'].append({'-setprop': 'cpa.arg.errorPath.graphml=witness.%d.graphml'})

            # Adjust JAVA heap size for static memory (Java VM, stack, and native libraries e.g. MathSAT) to be 1/4 of
            # general memory size limit if users don't specify their own sizes.
            if '-heap' not in [list(opt.keys())[0] for opt in self.task_desc['verifier']['options']]:
                self.task_desc['verifier']['options'].append({'-heap': '{0}m'.format(
                    round(3 * self.task_desc['resource limits']['memory size'] / (4 * 1000 ** 2)))})

    def prepare_property_file(self):
        self.logger.info('Prepare verifier property file')

        if 'entry points' in self.conf['abstract task desc']:
            if len(self.conf['abstract task desc']['entry points']) > 1:
                raise NotImplementedError('Several entry points are not supported')

            with open('unreach-call.prp', 'w', encoding='ascii') as fp:
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
            self.logger.info('Ignore asm goto expressions')

            for extra_c_file in self.conf['abstract task desc']['extra C files']:
                trimmed_c_file = '{0}.trimmed.i'.format(os.path.splitext(os.path.basename(extra_c_file['C file']))[0])
                with open(os.path.join(self.conf['main working directory'], extra_c_file['C file']),
                          encoding='ascii') as fp_in, open(trimmed_c_file, 'w', encoding='ascii') as fp_out:
                    # Each such expression occupies individual line, so just get rid of them.
                    for line in fp_in:
                        fp_out.write(re.sub(r'asm volatile goto.*;', '', line))
                if not self.conf['keep intermediate files']:
                    os.remove(os.path.join(self.conf['main working directory'], extra_c_file['C file']))
                extra_c_file['C file'] = trimmed_c_file

            # TODO: CIL can't proces files with spaces in their names. Try to screen spaces.
            with open('cil input files.txt', 'w', encoding='ascii') as fp:
                for extra_c_file in self.conf['abstract task desc']['extra C files']:
                    fp.write('{0}\n'.format(extra_c_file['C file']))

            core.utils.execute(self.logger,
                               (
                                   'cilly.asm.exe',
                                   '--extrafiles', 'cil input files.txt',
                                   '--out', 'cil.i',
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
                                   '--rmUnusedInlines'
                               ))

            if not self.conf['keep intermediate files']:
                for extra_c_file in self.conf['abstract task desc']['extra C files']:
                    os.remove(extra_c_file['C file'])

            self.task_desc['files'].append('cil.i')

            self.logger.debug('Merged source files was outputted to "cil.i"')
        else:
            for extra_c_file in self.conf['abstract task desc']['extra C files']:
                self.task_desc['files'].append(extra_c_file['C file'])

    def prepare_verification_task_files_archive(self):
        self.logger.info('Prepare archive with verification task files')

        with tarfile.open('task files.tar.gz', 'w:gz') as tar:
            if os.path.isfile('unreach-call.prp'):
                tar.add('unreach-call.prp')
            for file in self.task_desc['files']:
                tar.add(file)
            self.task_desc['files'] = [os.path.basename(file) for file in self.task_desc['files']]

    def decide_verification_task(self):
        self.logger.info('Decide verification task')
        self.verification_status = None

        if not os.path.isfile('unreach-call.prp'):
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

                with open('task error.txt', 'w', encoding='ascii') as fp:
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

                with tarfile.open("decision result files.tar.gz") as tar:
                    tar.extractall()

                with open('decision results.json', encoding='ascii') as fp:
                    decision_results = json.load(fp)

                verification_report_id = '{0}/verification'.format(self.id)

                log_file = None

                if self.conf['VTG strategy']['merge source files']:
                    log_files = glob.glob(os.path.join('output', 'benchmark*logfiles/*'))

                    if len(log_files) != 1:
                        RuntimeError(
                            'Exactly one log file should be outputted when source files are merged (but "{0}" are given)'.format(
                                log_files))

                    log_file = log_files[0]
                else:
                    NotImplementedError('https://forge.ispras.ru/issues/6545')

                # TODO: specify the computer where the verifier was invoked (this information should be get from BenchExec or VerifierCloud web client.
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
                                      'log': log_file,
                                      'files': [log_file] + (
                                          (['benchmark.xml'] if os.path.isfile('benchmark.xml') else []) +
                                          [self.task_desc['property file']] + self.task_desc['files']
                                          if self.conf['upload input files of static verifiers']
                                          else []
                                      )
                                  },
                                  self.mqs['report files'],
                                  self.conf['main working directory'])

                self.logger.info('Verification task decision status is "{0}"'.format(decision_results['status']))

                if decision_results['status'] == 'safe':
                    core.utils.report(self.logger,
                                      'safe',
                                      {
                                          'id': verification_report_id + '/safe',
                                          'parent id': verification_report_id,
                                          'attrs': [],
                                          # TODO: just the same file as parent log, looks strange.
                                          'proof': log_file,
                                          'files': [log_file]
                                      },
                                      self.mqs['report files'],
                                      self.conf['main working directory'])
                else:
                    for index, witness in enumerate(glob.glob('output/witness.*.graphml')):
                        self.logger.info('Process error trace "{0}"'.format(witness))

                        with open(witness, encoding='ascii') as fp:
                            # TODO: try xml.etree (see https://svn.sosy-lab.org/trac/cpachecker/ticket/236).
                            dom = minidom.parse(fp)

                        graphml = dom.getElementsByTagName('graphml')[0]

                        self.logger.info('Get source files referred by error trace')
                        src_files = set()
                        for key in graphml.getElementsByTagName('key'):
                            if key.getAttribute('id') == 'originfile':
                                default = key.getElementsByTagName('default')[0]
                                default_src_file = default.firstChild.data
                                src_files.add(default_src_file)
                        graph = graphml.getElementsByTagName('graph')[0]
                        for edge in graph.getElementsByTagName('edge'):
                            for data in edge.getElementsByTagName('data'):
                                if data.getAttribute('key') == 'originfile':
                                    src_files.add(data.firstChild.data)

                        self.logger.info('Extract notes and warnings from source files referred by error trace')
                        notes = {}
                        warns = {}
                        for src_file in src_files:
                            if not os.path.isfile(src_file):
                                raise FileNotFoundError(
                                    'File "{0}" referred by error trace does not exist'.format(src_file))

                            with open(src_file, encoding='utf8') as fp:
                                src_line = 0
                                for line in fp:
                                    src_line += 1
                                    match = re.search(
                                        r'/\*\s+(MODEL_FUNC_DEF|ASSERT|CHANGE_STATE|RETURN|MODEL_FUNC_CALL|OTHER)\s+(.*)\s+\*/',
                                        line)
                                    if match:
                                        kind, comment = match.groups()

                                        if kind == 'MODEL_FUNC_DEF':
                                            # Get necessary function name located on following line.
                                            try:
                                                line = next(fp)
                                                # Don't forget to increase counter.
                                                src_line += 1
                                                match = re.search(r'(ldv_\w+)', line)
                                                if match:
                                                    func_name = match.groups()[0]
                                                else:
                                                    raise ValueError(
                                                        'Model function definition is not specified in "{0}"'.format(line))
                                            except StopIteration:
                                                raise ValueError('Model function definition does not exist')
                                            notes[func_name] = comment
                                        else:
                                            if src_file not in notes:
                                                notes[src_file] = {}
                                            notes[src_file][src_line + 1] = comment
                                            # Some assert(s) will become warning(s).
                                            if kind == 'ASSERT':
                                                if src_file not in warns:
                                                    warns[src_file] = {}
                                                warns[src_file][src_line + 1] = comment

                        self.logger.info('Add notes and warnings to error trace')
                        # Find out sequence of edges (violation path) from entry node to violation node.
                        violation_edges = []
                        entry_node_id = None
                        violation_node_id = None
                        for node in graph.getElementsByTagName('node'):
                            for data in node.getElementsByTagName('data'):
                                if data.getAttribute('key') == 'entry' and data.firstChild.data == 'true':
                                    entry_node_id = node.getAttribute('id')
                                elif data.getAttribute('key') == 'violation' and data.firstChild.data == 'true':
                                    violation_node_id = node.getAttribute('id')
                        src_edges = {}
                        for edge in graph.getElementsByTagName('edge'):
                            src_node_id = edge.getAttribute('source')
                            dst_node_id = edge.getAttribute('target')
                            src_edges[dst_node_id] = (src_node_id, edge)
                        cur_src_edge = src_edges[violation_node_id]
                        violation_edges.append(cur_src_edge[1])
                        ignore_edges_of_func = None
                        while True:
                            cur_src_edge = src_edges[cur_src_edge[0]]
                            # Do not add edges of intermediate functions.
                            for data in cur_src_edge[1].getElementsByTagName('data'):
                                if data.getAttribute('key') == 'returnFrom' and not ignore_edges_of_func:
                                    ignore_edges_of_func = data.firstChild.data
                            if not ignore_edges_of_func:
                                violation_edges.append(cur_src_edge[1])
                            for data in cur_src_edge[1].getElementsByTagName('data'):
                                if data.getAttribute('key') == 'enterFunction' and ignore_edges_of_func:
                                    if ignore_edges_of_func == data.firstChild.data:
                                        ignore_edges_of_func = None
                            if cur_src_edge[0] == entry_node_id:
                                break
                        for edge in graph.getElementsByTagName('edge'):
                            src_file, src_line, func_name = (None, None, None)

                            for data in edge.getElementsByTagName('data'):
                                if data.getAttribute('key') == 'originfile':
                                    src_file = data.firstChild.data
                                elif data.getAttribute('key') == 'startline':
                                    src_line = int(data.firstChild.data)
                                elif data.getAttribute('key') == 'enterFunction':
                                    func_name = data.firstChild.data

                            if not src_file:
                                src_file = default_src_file

                            if src_file and src_line:
                                if src_file in notes and src_line in notes[src_file]:
                                    self.logger.debug(
                                        'Add note "{0}" from "{1}:{2}"'.format(notes[src_file][src_line], src_file,
                                                                               src_line))
                                    note = dom.createElement('data')
                                    txt = dom.createTextNode(notes[src_file][src_line])
                                    note.appendChild(txt)
                                    note.setAttribute('key', 'note')
                                    edge.appendChild(note)

                                if func_name and func_name in notes:
                                    self.logger.debug(
                                        'Add note "{0}" for call of model function "{1}" from "{2}"'.format(
                                            notes[func_name], func_name, src_file))
                                    note = dom.createElement('data')
                                    txt = dom.createTextNode(notes[func_name])
                                    note.appendChild(txt)
                                    note.setAttribute('key', 'note')
                                    edge.appendChild(note)

                                if src_file in warns and src_line in warns[src_file] and edge.getAttribute(
                                        'target') == violation_node_id:
                                    self.logger.debug(
                                        'Add warning "{0}" from "{1}:{2}"'.format(warns[src_file][src_line], src_file,
                                                                                  src_line))
                                    warn = dom.createElement('data')
                                    txt = dom.createTextNode(warns[src_file][src_line])
                                    warn.appendChild(txt)
                                    warn.setAttribute('key', 'warning')
                                    # Add warning either to edge itself or to first edge that enters function and has
                                    # note at violation path. If don't do the latter warning will be hidden by error
                                    # trace visualizer.
                                    warn_edge = edge
                                    for cur_src_edge in violation_edges:
                                        is_func_entry = False
                                        for data in cur_src_edge.getElementsByTagName('data'):
                                            if data.getAttribute('key') == 'enterFunction':
                                                is_func_entry = True
                                        if is_func_entry:
                                            for data in cur_src_edge.getElementsByTagName('data'):
                                                if data.getAttribute('key') == 'note':
                                                    warn_edge = cur_src_edge
                                    # Remove note from node for what we are going to add warning if so. Otherwise error
                                    # trace visualizer will be confused.
                                    for data in warn_edge.getElementsByTagName('data'):
                                        if data.getAttribute('key') == 'note':
                                            warn_edge.removeChild(data)
                                    warn_edge.appendChild(warn)

                        processed_witness = 'witness{0}.processed.graphml'.format(index)

                        self.logger.info('Create processed error trace file "{0}"'.format(processed_witness))
                        with open(processed_witness, 'w', encoding='utf8') as fp:
                            graphml.writexml(fp)

                        core.utils.report(self.logger,
                                          'unsafe',
                                          {
                                              'id': verification_report_id + '/unsafe' + str(index),
                                              'parent id': verification_report_id,
                                              'attrs': [],
                                              'error trace': processed_witness,
                                              'files': [processed_witness] + list(src_files)
                                          },
                                          self.mqs['report files'],
                                          self.conf['main working directory'],
                                          index)

                    if decision_results['status'] != 'unsafe':
                        # Prepare file to send it with unknown report.
                        if decision_results['status'] in ('CPU time exhausted', 'memory exhausted'):
                            with open('error.txt', 'w', encoding='ascii') as fp:
                                fp.write(decision_results['status'])
                        core.utils.report(self.logger,
                                          'unknown',
                                          {
                                              'id': verification_report_id + '/unknown',
                                              'parent id': verification_report_id,
                                              # TODO: just the same file as parent log, looks strange.
                                              'problem desc': log_file if decision_results['status'] not in (
                                                  'CPU time exhausted', 'memory exhausted') else 'error.txt',
                                              'files': [log_file if decision_results['status'] not in (
                                                  'CPU time exhausted', 'memory exhausted') else 'error.txt']
                                          },
                                          self.mqs['report files'],
                                          self.conf['main working directory'])

                self.verification_status = decision_results['status']
                break

            time.sleep(1)

        self.logger.info('Remove verification task "{0}"'.format(task_id))
        session.remove_task(task_id)
