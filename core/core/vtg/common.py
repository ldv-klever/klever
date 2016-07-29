#!/usr/bin/python3

import os
import re
import glob
from abc import abstractclassmethod, ABCMeta
from xml.dom import minidom

import core.components
import core.session
import core.utils
from core.vtg.mea import MEA


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

            for extra_c_file in self.conf['abstract task desc']['extra C files']:
                trimmed_c_file = '{0}.trimmed.i'.format(os.path.splitext(os.path.basename(extra_c_file['C file']))[0])
                with open(os.path.join(self.conf['main working directory'], extra_c_file['C file']),
                          encoding='ascii') as fp_in, open(trimmed_c_file, 'w', encoding='ascii') as fp_out:
                    # Specify original location to avoid references to *.trimmed.i files in error traces.
                    fp_out.write('# 1 "{0}"\n'.format(extra_c_file['C file']))
                    # Each such expression occupies individual line, so just get rid of them.
                    for line in fp_in:
                        fp_out.write(re.sub(r'asm volatile goto.*;', '', line))
                extra_c_file['new C file'] = trimmed_c_file

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
                                   '--out', 'cil.i',
                               ) +
                               tuple(extra_c_file['new C file']
                                     for extra_c_file in self.conf['abstract task desc']['extra C files']))
            if not self.conf['keep intermediate files']:
                for extra_c_file in self.conf['abstract task desc']['extra C files']:
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
                if os.path.isfile(extra_c_file['C file']):
                    os.remove(extra_c_file['C file'])

    # This function creates 'verification' report.
    @abstractclassmethod
    def create_verification_report(self, verification_report_id, decision_results, bug_kind=None):
        pass

    def get_verifier_log_file(self):
        log_files = glob.glob(os.path.join('output', 'benchmark*logfiles/*'))
        if len(log_files) != 1:
            RuntimeError(
                'Exactly one log file should be outputted when source files are merged (but "{0}" are given)'.format(
                    log_files))
        return log_files[0]

    def clear_safe_logs(self, log_file):
        if 'upload safe proofs' not in self.conf['VTG strategy'] or \
                not self.conf['VTG strategy']['upload safe proofs']:
            log_file = "empty"
            open(log_file, 'w')
        return log_file

    def parse_bug_kind(self, bug_kind):
        match = re.search(r'(.+)::(.*)', bug_kind)
        if match:
            return match.groups()[0]
        else:
            return ''

    def process_single_verdict(self, decision_results, verification_report_id,
                               assertion=None, specified_error_trace=None):
        # Add assertion if it was specified.
        if decision_results['status'] == 'checking':
            # Do not print any verdict for still checking tasks
            return
        added_attrs = []
        if assertion:
            added_attrs.append({"Rule specification": assertion})
        path_to_witness = None
        if decision_results['status'] == 'unsafe':
            # Default place for witness, if we consider only 1 possible witness for verification task.
            # Is strategy may produce more than 1 witness, it should be specified in 'specified_witness'.
            verification_report_id_unsafe = "{0}/unsafe/{1}".\
                format(verification_report_id, assertion or '')
            path_to_witness = 'output/witness.0.graphml'
            if specified_error_trace:
                path_to_witness = specified_error_trace
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

        log_file = self.get_verifier_log_file()
        if decision_results['status'] == 'safe':
            log_file = self.clear_safe_logs(log_file)

            core.utils.report(self.logger,
                              'safe',
                              {
                                  'id': verification_report_id + '/safe/{0}'.format(assertion or ''),
                                  'parent id': verification_report_id,
                                  'attrs': added_attrs,
                                  # TODO: just the same file as parent log, looks strange.
                                  'proof': log_file,
                                  'files': [log_file]
                              },
                              self.mqs['report files'],
                              self.conf['main working directory'],
                              assertion)
        elif decision_results['status'] == 'unsafe':
            path_to_processed_witness = path_to_witness + ".processed"
            with open(path_to_witness, encoding='ascii') as fp:
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
                        # Internal automaton variables do not have a source file.
                        if data.firstChild:
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

            # Two stages are required since for marking edges with warnings we need to know whether there
            # notes at violation path below.
            warn_edges = []
            for stage in ('notes', 'warns'):
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
                        if stage == 'notes' and src_file in notes and src_line in notes[src_file]:
                            self.logger.debug(
                                'Add note "{0}" from "{1}:{2}"'.format(notes[src_file][src_line], src_file,
                                                                       src_line))
                            note = dom.createElement('data')
                            txt = dom.createTextNode(notes[src_file][src_line])
                            note.appendChild(txt)
                            note.setAttribute('key', 'note')
                            edge.appendChild(note)

                        if stage == 'notes' and func_name and func_name in notes:
                            self.logger.debug(
                                'Add note "{0}" for call of model function "{1}" from "{2}"'.format(
                                    notes[func_name], func_name, src_file))
                            note = dom.createElement('data')
                            txt = dom.createTextNode(notes[func_name])
                            note.appendChild(txt)
                            note.setAttribute('key', 'note')
                            edge.appendChild(note)

                        if stage == 'warns' and src_file in warns and src_line in warns[src_file]:
                            # Add warning just if there are no more edges with notes at violation path
                            # below.
                            track_notes = False
                            note_found = False
                            for violation_edge in reversed(violation_edges):
                                if track_notes:
                                    for data in violation_edge.getElementsByTagName('data'):
                                        if data.getAttribute('key') == 'note':
                                            note_found = True
                                            break
                                if note_found:
                                    break
                                if violation_edge == edge:
                                    track_notes = True

                            if not note_found:
                                self.logger.debug(
                                    'Add warning "{0}" from "{1}:{2}"'.format(warns[src_file][src_line],
                                                                              src_file, src_line))

                                warn = dom.createElement('data')
                                txt = dom.createTextNode(warns[src_file][src_line])
                                warn.appendChild(txt)
                                warn.setAttribute('key', 'warning')

                                # Add warning either to edge itself or to first edge that enters function
                                # and has note at violation path. If don't do the latter warning will be
                                # hidden by error trace visualizer.
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

                                warn_edge.appendChild(warn)
                                warn_edges.append(warn_edge)

                                # Remove added warning to avoid its addition one more time.
                                del warns[src_file][src_line]

            # Remove notes from edges marked with warnings. Otherwise error trace visualizer will be
            # confused.
            for warn_edge in warn_edges:
                for data in warn_edge.getElementsByTagName('data'):
                    if data.getAttribute('key') == 'note':
                        warn_edge.removeChild(data)

            self.logger.info('Create processed error trace file "{0}"'.format(path_to_processed_witness))
            with open(path_to_processed_witness, 'w', encoding='utf8') as fp:
                graphml.writexml(fp)

            core.utils.report(self.logger,
                              'unsafe',
                              {
                                  'id': verification_report_id_unsafe,
                                  'parent id': verification_report_id,
                                  'attrs': added_attrs,
                                  'error trace': path_to_processed_witness,
                                  'files': [path_to_processed_witness] + list(src_files)
                              },
                              self.mqs['report files'],
                              self.conf['main working directory'],
                              assertion)
        else:
            # Prepare file to send it with unknown report.
            if decision_results['status'] in ('CPU time exhausted', 'memory exhausted'):
                with open('error.txt', 'w', encoding='ascii') as fp:
                    fp.write(decision_results['status'])
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
                {'-setprop': 'cpa.arg.errorPath.graphml=witness.%d.graphml'})

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
