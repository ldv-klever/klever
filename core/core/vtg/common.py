#!/usr/bin/python3

import json
import os
import re
import shutil
import tarfile
import time
from abc import abstractclassmethod
from xml.dom import minidom
import glob

import core.components
import core.session
import core.utils


class CommonStrategy(core.components.Component):
    @abstractclassmethod
    def generate_verification_tasks(self):
        None

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

    def prepare_src_files(self):
        self.task_desc['files'] = []

        if self.conf['VTG strategy']['merge source files']:
            self.logger.info('Merge source files by means of CIL')

            # CIL doesn't support asm goto (https://forge.ispras.ru/issues/1323).
            self.logger.info('Ignore asm goto expressions')

            for extra_c_file in self.conf['abstract task desc']['extra C files']:
                trimmed_c_file = '{0}.trimmed.i'.format(os.path.splitext(extra_c_file['C file'])[0])
                with open(os.path.join(self.conf['source tree root'], extra_c_file['C file']),
                          encoding='ascii') as fp_in, open(os.path.join(self.conf['source tree root'], trimmed_c_file),
                                                           'w', encoding='ascii') as fp_out:
                    # Specify original location to avoid references to *.trimmed.i files in error traces.
                    fp_out.write('# 1 "{0}"\n'.format(extra_c_file['C file']))
                    # Each such expression occupies individual line, so just get rid of them.
                    for line in fp_in:
                        fp_out.write(re.sub(r'asm volatile goto.*;', '', line))
                extra_c_file['C file'] = trimmed_c_file

            cil_out_file = os.path.relpath('cil.i', os.path.realpath(self.conf['source tree root']))

            core.utils.execute(self.logger,
                               (
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
                                   '--out', cil_out_file,
                               ) +
                               tuple(extra_c_file['C file']
                                     for extra_c_file in self.conf['abstract task desc']['extra C files']),
                               cwd=self.conf['source tree root'])

            self.task_desc['files'].append(cil_out_file)

            self.logger.debug('Merged source files was outputted to "cil.i"')
        else:
            for extra_c_file in self.conf['abstract task desc']['extra C files']:
                self.task_desc['files'].append(extra_c_file['C file'])

    def process_single_verdict(self, decision_results, suffix=None, specified_witness=None):
        verification_report_id = '{0}/verification{1}'.format(self.id, suffix)
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
                              'log': 'cil.i.log',
                              'files': ['cil.i.log'] + (
                                  ['benchmark.xml', self.task_desc['property file']] + self.task_desc['files']
                                  if self.conf['upload input files of static verifiers']
                                  else []
                              )
                          },
                          self.mqs['report files'],
                          self.conf['main working directory'],
                          suffix)

        self.logger.info('Verification task decision status is "{0}"'.format(decision_results['status']))

        if decision_results['status'] == 'safe':
            core.utils.report(self.logger,
                              'safe',
                              {
                                  'id': verification_report_id + '/safe',
                                  'parent id': verification_report_id,
                                  'attrs': [],
                                  # TODO: just the same file as parent log, looks strange.
                                  'proof': 'cil.i.log',
                                  'files': ['cil.i.log']
                              },
                              self.mqs['report files'],
                              self.conf['main working directory'],
                              suffix)
        elif decision_results['status'] == 'unsafe':
            self.logger.info('Get source files referred by error trace')
            src_files = set()

            # Default place for witness, if we consider only 1 possible witness for verification task.
            # Is strategy may produce more than 1 witness, it should be specified in 'specified_witness'.
            path_to_witness = 'output/witness.0.graphml'
            if specified_witness:
                path_to_witness = specified_witness
            path_to_processed_witness = path_to_witness + ".processed"
            with open(path_to_witness, encoding='ascii') as fp:
                # TODO: try xml.etree (see https://svn.sosy-lab.org/trac/cpachecker/ticket/236).
                dom = minidom.parse(fp)
            graphml = dom.getElementsByTagName('graphml')[0]
            for key in graphml.getElementsByTagName('key'):
                if key.getAttribute('id') == 'originfile':
                    default = key.getElementsByTagName('default')[0]
                    default_src_file = self.__normalize_path(default.firstChild)
                    src_files.add(default_src_file)
            graph = graphml.getElementsByTagName('graph')[0]
            for edge in graph.getElementsByTagName('edge'):
                for data in edge.getElementsByTagName('data'):
                    if data.getAttribute('key') == 'originfile':
                        src_files.add(self.__normalize_path(data.firstChild))

            self.logger.info('Extract notes and warnings from source files referred by error trace')
            notes = {}
            warns = {}
            for src_file in src_files:
                with open(os.path.join(self.conf['source tree root'], src_file), encoding='utf8') as fp:
                    i = 0
                    for line in fp:
                        i += 1
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
                                    i += 1
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
                                notes[src_file][i + 1] = comment
                                # Some assert(s) will become warning(s).
                                if kind == 'ASSERT':
                                    if src_file not in warns:
                                        warns[src_file] = {}
                                    warns[src_file][i + 1] = comment

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
                src_file, i, func_name = (None, None, None)

                for data in edge.getElementsByTagName('data'):
                    if data.getAttribute('key') == 'originfile':
                        src_file = data.firstChild.data
                    elif data.getAttribute('key') == 'startline':
                        i = int(data.firstChild.data)
                    elif data.getAttribute('key') == 'enterFunction':
                        func_name = data.firstChild.data

                if not src_file:
                    src_file = default_src_file

                if src_file and i:
                    if src_file in notes and i in notes[src_file]:
                        self.logger.debug(
                            'Add note "{0}" from "{1}:{2}"'.format(notes[src_file][i], src_file, i))
                        note = dom.createElement('data')
                        txt = dom.createTextNode(notes[src_file][i])
                        note.appendChild(txt)
                        note.setAttribute('key', 'note')
                        edge.appendChild(note)

                    if func_name and func_name in notes:
                        self.logger.debug('Add note "{0}" for call of model function "{1}" from "{2}"'.format(
                            notes[func_name], func_name, src_file))
                        note = dom.createElement('data')
                        txt = dom.createTextNode(notes[func_name])
                        note.appendChild(txt)
                        note.setAttribute('key', 'note')
                        edge.appendChild(note)

                    if src_file in warns and i in warns[src_file] and edge.getAttribute(
                            'target') == violation_node_id:
                        self.logger.debug(
                            'Add warning "{0}" from "{1}:{2}"'.format(warns[src_file][i], src_file, i))
                        warn = dom.createElement('data')
                        txt = dom.createTextNode(warns[src_file][i])
                        warn.appendChild(txt)
                        warn.setAttribute('key', 'warning')
                        # Add warning either to edge itself or to first edge that enters function and has note
                        # at violation path. If don't do the latter warning will be hidden by error trace
                        # visualizer.
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

            self.logger.info('Create processed error trace file "{0}"'.format(path_to_processed_witness))
            with open(path_to_processed_witness, 'w', encoding='utf8') as fp:
                graphml.writexml(fp)

            # TODO: copy is done just to create unsafe report later, so get rid of it sometime.
            # Copy all source files referred by error trace to working directory.
            if src_files:
                self.logger.debug('Source files referred by error trace are: "{}"'.format(src_files))
                for src_file in src_files:
                    os.makedirs(os.path.dirname(src_file), exist_ok=True)
                    shutil.copy(os.path.join(self.conf['source tree root'], src_file), src_file)

            core.utils.report(self.logger,
                              'unsafe',
                              {
                                  'id': verification_report_id + '/unsafe',
                                  'parent id': verification_report_id,
                                  'attrs': [],
                                  'error trace': path_to_processed_witness,
                                  'files': [path_to_processed_witness] + list(src_files)
                              },
                              self.mqs['report files'],
                              self.conf['main working directory'],
                              suffix)
        else:
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
                                  'problem desc': 'cil.i.log' if decision_results['status'] not in (
                                      'CPU time exhausted', 'memory exhausted') else 'error.txt',
                                  'files': ['cil.i.log' if decision_results['status'] not in (
                                      'CPU time exhausted', 'memory exhausted') else 'error.txt']
                              },
                              self.mqs['report files'],
                              self.conf['main working directory'],
                              suffix)

        self.verification_status = decision_results['status']

    def __normalize_path(self, path):
        # Each file is specified via absolute path or path relative to source tree root or it is placed to current
        # working directory. Make all paths relative to source tree root.
        if os.path.isabs(path.data) or os.path.isfile(path.data):
            path.data = os.path.relpath(path.data, os.path.realpath(self.conf['source tree root']))

        if not os.path.isfile(os.path.join(self.conf['source tree root'], path.data)):
            raise FileNotFoundError('File "{0}" referred by error trace does not exist'.format(path.data))

        return path.data
