import os
import re
import xml.etree.ElementTree as ET


def import_error_trace(logger, witness):
    parser = ErrorTraceParser(logger, witness)
    return parser.error_trace.serialize()


class ErrorTrace:

    def __init__(self):
        self._nodes = dict()
        self._files = list()
        self._funcs = list()
        self._entry_node_id = None
        self._violation_node_ids = set()

    @property
    def functions(self):
        return enumerate(self._funcs)

    @property
    def files(self):
        return enumerate(self._files)

    @property
    def violation_nodes(self):
        return ([key, self._nodes[key]] for key in sorted(self._violation_node_ids))

    @property
    def entry_node(self):
        if self._entry_node_id:
            return self._nodes[self._entry_node_id]
        else:
            raise KeyError('Entry node has not been set yet')

    def serialize(self):
        edge_id = 0
        edges = list()
        # The first
        nodes = [[None]]
        for edge in list(self.trace_iterator()):
            edges.append(edge)
            edge['source node'] = len(nodes) - 1
            edge['target node'] = len(nodes)

            nodes[-1].append(edge_id)
            nodes.append([edge_id])
            edge_id += 1
        # The last
        nodes[-1].append(None)

        data = {
            'nodes': nodes,
            'edges': edges,
            'entry node': 0,
            'violation nodes': [self._nodes[i]['in'][0]['target node'] for i in sorted(self._violation_node_ids)],
            'files': self._files,
            'funcs': self._funcs
        }
        return data

    def add_entry_node_id(self, node_id):
        self._entry_node_id = node_id

    def add_node(self, node_id):
        if node_id in self._nodes:
            raise ValueError('There is already added node with an identifier {!r}'.format(node_id))
        self._nodes[node_id] = {'in': list(), 'out': list()}
        return self._nodes[node_id]

    def add_edge(self, source, target):
        source_node = self._nodes[source]
        target_node = self._nodes[target]

        edge = {'source node': source_node, 'target node': target_node}
        source_node['out'].append(edge)
        target_node['in'].append(edge)
        return edge

    def add_violation_node_id(self, identifier):
        self._violation_node_ids.add(identifier)

    def add_file(self, file_name):
        if file_name not in self._files:
            self._files.append(file_name)
            return self.resolve_file_id(file_name)
        else:
            return self.resolve_file_id(file_name)

    def add_function(self, name):
        if name not in self._funcs:
            self._funcs.append(name)
            return self.resolve_function_id(name)
        else:
            return self.resolve_function_id(name)

    def resolve_file_id(self, file):
        return self._files.index(file)

    def resolve_file(self, identifier):
        return self._files[identifier]

    def resolve_function_id(self, name):
        return self._funcs.index(name)

    def resolve_function(self, identifier):
        return self._funcs[identifier]

    def trace_iterator(self, begin=None, end=None, backward=False):
        # todo: Warning! This does work only if you guarantee:
        # *having no nore than one input edge for all nodes
        # *existance of at least one violation node and at least one input node
        if not begin:
            begin = self.entry_node['out'][0]
        if not end:
            end = self.violation_nodes.__next__()[1]['in'][0]
        if backward:
            getter = self.previous_edge
        else:
            getter = self.next_edge

        current = None
        while True:
            if not current:
                current = begin
                yield current
            if current is end:
                raise StopIteration
            else:
                current = getter(current)
                if not current:
                    raise StopIteration
                else:
                    yield current

    @staticmethod
    def insert_edge_and_target_node(edge):
        raise NotImplementedError

    @staticmethod
    def remove_edge_and_target_node(edge):
        source = edge['source node']
        target = edge['target node']

        source['out'].remove(edge)
        target['in'].remove(edge)
        for out_edge in target['out']:
            out_edge['source node'] = source
            source['out'].append(out_edge)
        del target

    @staticmethod
    def next_edge(edge):
        if len(edge['target node']['out']) > 0:
            return edge['target node']['out'][0]
        else:
            return None

    @staticmethod
    def previous_edge(edge):
        if len(edge['source node']['in']) > 0:
            return edge['source node']['in'][0]
        else:
            return None


class ErrorTraceParser:
    WITNESS_NS = {'graphml': 'http://graphml.graphdrawing.org/xmlns'}
    MODEL_COMMENT_TYPES = 'AUX_FUNC|MODEL_FUNC|NOTE|ASSERT'
    EMG_COMMENTS = 'CONTROL_FUNCTION_BEGIN|CONTROL_FUNCTION_END|CALLBACK|CONTROL_FUNCTION_INIT_BEGIN|' \
                   'CONTROL_FUNCTION_INIT_END|CALL_BEGIN|CALL_END|DISPATCH_BEGIN|DISPATCH_END|RECEIVE_BEGIN|' \
                   'RECEIVE_END|SUBPROCESS_BEGIN|SUBPROCESS_END|CONDITION_BEGIN|CONDITION_END'

    def __init__(self, logger, witness):
        self._logger = logger
        self._violation_edges = list()
        self._aux_funcs = dict()
        self._model_funcs = dict()
        self._notes = dict()
        self._emg_comments = dict()
        self._asserts = dict()

        # Start parsing
        self.error_trace = ErrorTrace()
        self._parse_witness(witness)
        # Do processing
        self._find_violation_path()
        self._parse_model_comments()
        self._mark_witness()
        self._simplify()

    def _parse_witness(self, witness):
        self._logger.info('Parse witness {!r}'.format(witness))

        with open(witness, encoding='utf8') as fp:
            tree = ET.parse(fp)

        root = tree.getroot()

        # Parse default file.
        for key in root.findall('graphml:key', self.WITNESS_NS):
            if key.attrib['id'] == 'originfile':
                self.error_trace.add_file(key.find('graphml:default', self.WITNESS_NS).text)

        graph = root.find('graphml:graph', self.WITNESS_NS)

        sink_nodes_map = self.__parse_witness_nodes(graph)
        self.__parse_witness_edges(graph, sink_nodes_map)

    def __parse_witness_nodes(self, graph):
        sink_nodes_map = dict()
        unsupported_node_data_keys = dict()
        nodes_number = 0

        for node in graph.findall('graphml:node', self.WITNESS_NS):
            is_sink = False

            for data in node.findall('graphml:data', self.WITNESS_NS):
                data_key = data.attrib['key']
                if data_key == 'entry':
                    self.error_trace.add_entry_node_id(node.attrib['id'])
                    self._logger.debug('Parse entry node {!r}'.format(node.attrib['id']))
                elif data_key == 'sink':
                    is_sink = True
                    self._logger.debug('Parse sink node {!r}'.format(node.attrib['id']))
                elif data_key == 'violation':
                    if len(list(self.error_trace.violation_nodes)) > 0:
                        raise NotImplementedError('Several violation nodes are not supported')
                    self.error_trace.add_violation_node_id(node.attrib['id'])
                    self._logger.debug('Parse violation node {!r}'.format(node.attrib['id']))
                elif data_key not in unsupported_node_data_keys:
                    self._logger.warning('Node data key {!r} is not supported'.format(data_key))
                    unsupported_node_data_keys[data_key] = None

            # Do not track sink nodes as all other nodes. All edges leading to sink nodes will be excluded as well.
            if is_sink:
                sink_nodes_map[node.attrib['id']] = None
            else:
                nodes_number += 1
                self.error_trace.add_node(node.attrib['id'])

        # Sanity checks.
        if not self.error_trace.entry_node:
            raise KeyError('Entry node was not found')
        if len(list(self.error_trace.violation_nodes)) == 0:
            raise KeyError('Violation nodes were not found')

        self._logger.debug('Parse {0} nodes and {1} sink nodes'.format(nodes_number, len(sink_nodes_map)))
        return sink_nodes_map

    def __parse_witness_edges(self, graph, sink_nodes_map):
        unsupported_edge_data_keys = dict()

        # Use maps for source files and functions as for nodes. Add artificial map to 0 for default file without
        # explicitly specifying its path.
        # The number of edges leading to sink nodes. Such edges will be completely removed.
        sink_edges_num = 0
        edges_num = 0

        for edge in graph.findall('graphml:edge', self.WITNESS_NS):
            # Sanity checks.
            if 'source' not in edge.attrib:
                raise KeyError('Source node was not found')
            if 'target' not in edge.attrib:
                raise KeyError('Destination node was not found')

            source_node_id = edge.attrib['source']

            if edge.attrib['target'] in sink_nodes_map:
                sink_edges_num += 1
                continue

            target_node_id = edge.attrib['target']

            # Update lists of input and output edges for source and target nodes.
            _edge = self.error_trace.add_edge(source_node_id, target_node_id)

            for data in edge.findall('graphml:data', self.WITNESS_NS):
                data_key = data.attrib['key']
                if data_key == 'originfile':
                    identifier = self.error_trace.add_file(data.text)
                    _edge['file'] = identifier
                elif data_key == 'startline':
                    _edge['start line'] = int(data.text)
                elif data_key == 'endline':
                    _edge['end line'] = int(data.text)
                elif data_key == 'sourcecode':
                    _edge['source'] = data.text
                elif data_key == 'enterFunction' or data_key == 'returnFrom' or data_key == 'assumption.scope':
                    self.error_trace.add_function(data.text)
                    if data_key == 'enterFunction':
                        _edge['enter'] = self.error_trace.resolve_function_id(data.text)
                    elif data_key == 'returnFrom':
                        _edge['return'] = self.error_trace.resolve_function_id(data.text)
                    else:
                        _edge['assumption scope'] = self.error_trace.resolve_function_id(data.text)
                elif data_key == 'control':
                    _edge['condition'] = True
                elif data_key == 'assumption':
                    _edge['assumption'] = data.text
                elif data_key in ('startoffset', 'endoffset'):
                    pass
                elif data_key not in unsupported_edge_data_keys:
                    self._logger.warning('Edge data key {!r} is not supported'.format(data_key))
                    unsupported_edge_data_keys[data_key] = None

            if 'file' not in _edge:
                _edge['file'] = 0
            edges_num += 1

        self._logger.debug('Parse {0} edges and {1} sink edges'.format(edges_num, sink_edges_num))

    def _find_violation_path(self):
        self._logger.info('Get violation path')
        ignore_edges_of_func_id = None
        for edge in self.error_trace.trace_iterator(backward=True):
            if not ignore_edges_of_func_id and 'return' in edge:
                ignore_edges_of_func_id = edge['return']

            if 'enter' in edge and edge['enter'] == ignore_edges_of_func_id:
                ignore_edges_of_func_id = None

            if not ignore_edges_of_func_id:
                self._violation_edges.append(edge)

    def _parse_model_comments(self):
        self._logger.info('Parse model comments from source files referred by witness')

        for file_id, file in self.error_trace.files:
            if not os.path.isfile(file):
                raise FileNotFoundError('File {!r} referred by witness does not exist'.format(file))

            self._logger.debug('Parse model comments from {!r}'.format(file))

            with open(file, encoding='utf8') as fp:
                line = 0
                for text in fp:
                    line += 1

                    # Try match EMG comment
                    # Expect comment like /* TYPE Instance Text */
                    if file_id not in self._emg_comments:
                        self._emg_comments[file_id] = dict()
                    match = re.search(r'/\*\s({0})\s(\w+)\s(.*)\s\*/'.format(self.EMG_COMMENTS), text)
                    if match:
                        self._emg_comments[file_id][line] = {
                            'type': match.group(1),
                            'instance': match.group(2),
                            'comment': match.group(3),
                        }
                    else:
                        # Expect comment like /* TYPE Text */
                        match = re.search(r'/\*\s({0})\s(.*)\s\*/'.format(self.EMG_COMMENTS), text)
                        if match:
                            self._emg_comments[file_id][line] = {
                                'type': match.group(1),
                                'comment': match.group(2),
                            }

                    # Match rest comments
                    match = re.search(r'/\*\s+({0})\s+(.*)\*/'.format(self.MODEL_COMMENT_TYPES), text)
                    if match:
                        kind, comment = match.groups()

                        comment = comment.rstrip()

                        if kind == 'AUX_FUNC' or kind == 'MODEL_FUNC':
                            # Get necessary function name located on following line.
                            try:
                                text = next(fp)
                                # Don't forget to increase counter.
                                line += 1
                                match = re.search(r'(ldv_\w+)', text)
                                if match:
                                    func_name = match.groups()[0]
                                else:
                                    raise ValueError(
                                        'Auxiliary/model function definition is not specified in {!r}'.format(text))
                            except StopIteration:
                                raise ValueError('Auxiliary/model function definition does not exist')

                            # Deal with functions referenced by witness.
                            for func_id, ref_func_name in self.error_trace.functions:
                                if ref_func_name == func_name:
                                    if kind == 'AUX_FUNC':
                                        self._aux_funcs[func_id] = None
                                        self._logger.debug("Get auxiliary function '{0}' from '{1}:{2}'".
                                                           format(func_name, file, line))
                                    else:
                                        self._model_funcs[func_id] = comment
                                        self._logger.debug("Get note 'dict()' for model function '{1}' from '{2}:{3}'".
                                                           format(comment, func_name, file, line))

                                    break
                        else:
                            if file_id not in self._notes:
                                self._notes[file_id] = dict()
                            self._notes[file_id][line + 1] = comment
                            self._logger.debug(
                                "Get note '{0}' for statement from '{1}:{2}'".format(comment, file, line + 1))
                            # Some assertions will become warnings.
                            if kind == 'ASSERT':
                                if file_id not in self._asserts:
                                    self._asserts[file_id] = dict()
                                self._asserts[file_id][line + 1] = comment
                                self._logger.debug("Get assertiom '{0}' for statement from '{1}:{2}'".
                                                   format(comment, file, line + 1))

    def _mark_witness(self):
        self._logger.info('Mark witness with model comments')

        # Two stages are required since for marking edges with warnings we need to know whether there notes at violation
        # path below.
        warn_edges = list()
        for stage in ('notes', 'warns'):
            for edge in self.error_trace.trace_iterator():
                file_id = edge['file']
                file = self.error_trace.resolve_file(file_id)
                start_line = edge['start line']

                if stage == 'notes':
                    if 'enter' in edge:
                        func_id = edge['enter']
                        if func_id in self._model_funcs:
                            note = self._model_funcs[func_id]
                            edge['note'] = note

                    if file_id in self._notes and start_line in self._notes[file_id]:
                        note = self._notes[file_id][start_line]
                        self._logger.debug("Add note {!r} for statement from '{1}:{2}'".format(note, file, start_line))
                        edge['note'] = note

                if stage == 'warns':
                    if file_id in self._asserts and start_line in self._asserts[file_id]:
                        # Add warning just if there are no more edges with notes at violation path below.
                        track_notes = False
                        note_found = False
                        for violation_edge in reversed(self._violation_edges):
                            if track_notes:
                                if 'note' in violation_edge:
                                    note_found = True
                                    break
                            if violation_edge == edge:
                                track_notes = True

                        if not note_found:
                            warn = self._asserts[file_id][start_line]
                            self._logger.debug(
                                "Add warning {!r} for statement from '{1}:{2}'".format(warn, file, start_line))
                            # Add warning either to edge itself or to first edge that enters function and has note at
                            # violation path. If don't do the latter warning will be hidden by error trace visualizer.
                            warn_edge = edge
                            for violation_edge in self._violation_edges:
                                if 'enter' in violation_edge and 'note' in violation_edge:
                                    warn_edge = violation_edge
                            warn_edge['warn'] = warn
                            warn_edges.append(warn_edge)

                            # Remove added warning to avoid its addition one more time.
                            del self._asserts[file_id][start_line]

        # Remove notes from edges marked with warnings. Otherwise error trace visualizer will be confused.
        for warn_edge in warn_edges:
            if 'note' in warn_edge:
                del warn_edge['note']

        del self._violation_edges, self._model_funcs, self._notes, self._asserts

    def _simplify(self):
        self._logger.info('Simplify witness')

        # Simple transformations.
        for edge in self.error_trace.trace_iterator():
            # Make source code more human readable.
            if 'source' in edge:
                # Remove "[...]" around conditions.
                if 'condition' in edge:
                    edge['source'] = edge['source'].strip('list()')

                # Get rid of continues spaces if they aren't placed at line beginnings.
                edge['source'] = re.sub(r'(\S) +', '\g<1> ', edge['source'])

                # Remove space before trailing ";".
                edge['source'] = re.sub(r' ;$', ';', edge['source'])

                # Remove space before "," and ")".
                edge['source'] = re.sub(r' (,|\))', '\g<1>', edge['source'])

                # Replace "!(... ==/!=/</> ...)" with "... !=/==/>/< ...".
                edge['source'] = re.sub(r'^!\((.+)==(.+)\)$', '\g<1>!=\g<2>', edge['source'])
                edge['source'] = re.sub(r'^!\((.+)!=(.+)\)$', '\g<1>==\g<2>', edge['source'])
                edge['source'] = re.sub(r'^!\((.+)<(.+)\)$', '\g<1>>\g<2>', edge['source'])
                edge['source'] = re.sub(r'^!\((.+)>(.+)\)$', '\g<1><\g<2>', edge['source'])

            # Make source code and assumptions more human readable (common improvements).
            for source_kind in ('source', 'assumption'):
                if source_kind in edge:
                    # Replace unnessary "(...)" around integers and identifiers.
                    edge[source_kind] = re.sub(r' \((-?\w+)\)', ' \g<1>', edge[source_kind])

                    # Replace "& " with "&".
                    edge[source_kind] = re.sub(r'& ', '&', edge[source_kind])

        # More advanced transformations.
        # Get rid of artificial edges added after returning from functions.
        removed_edges_num = 0
        for edge in self.error_trace.trace_iterator():
            if 'return' in edge:
                next_edge = self.error_trace.next_edge(edge)
                self.error_trace.remove_edge_and_target_node(next_edge)
                removed_edges_num += 1
        if removed_edges_num:
            self._logger.debug('{0} useless edges were removed'.format(removed_edges_num))

        # Get rid of temporary variables. Replace:
        #   ... tmp...;
        #   ...
        #   tmp... = func(...);
        #   ... tmp... ...;
        # with (removing first and last statements):
        #   ...
        #   ... func(...) ...;
        # Provide first function enter edge
        enter_edge = None
        for edge in self.error_trace.trace_iterator():
            if 'enter' in edge:
                enter_edge = edge
                break
        removed_tmp_vars_num = self.__remove_tmp_vars(enter_edge)[0]

        if removed_tmp_vars_num:
            self._logger.debug('{0} temporary variables were removed'.format(removed_tmp_vars_num))

        # Get rid of auxiliary functions if possible. Replace:
        #   ... = aux_func(...)
        #     return func(...)
        # with:
        #   ... = func(...)
        # accurately replacing arguments if required.
        removed_aux_funcs_num = 0
        for edge in self.error_trace.trace_iterator():
            enter_edge = edge

            if 'enter' in enter_edge:
                func_id = enter_edge['enter']
                if func_id in self._aux_funcs:
                    return_edge = self.error_trace.next_edge(edge)
                    if return_edge.get('return') == func_id and 'enter' in return_edge:
                        # Get lhs and actual arguments of called auxiliary function.
                        m = re.search(r'^(.*){0}\s*\((.+)\);$'.format(self.error_trace.resolve_function(func_id)),
                                      enter_edge['source'].replace('\n', ' '))
                        if m:
                            lhs = m.group(1)
                            aux_actual_args = [aux_actual_arg.strip() for aux_actual_arg in m.group(2).split(',')]

                            # Get name and actual arguments of called function.
                            m = re.search(r'^return (.+)\s*\((.*)\);$', return_edge['source'].replace('\n', ' '))
                            if m:
                                func_name = m.group(1)
                                actual_args = [actual_arg.strip() for actual_arg in m.group(2).split(',')]\
                                    if m.group(2) else None

                                if not actual_args \
                                        or all([re.match(r'arg\d+', actual_arg) for actual_arg in actual_args]):
                                    is_replaced = True
                                    if actual_args:
                                        for i, actual_arg in enumerate(actual_args):
                                            m = re.match(r'arg(\d+)', actual_arg)
                                            if m:
                                                if int(m.group(1)) >= len(aux_actual_args):
                                                    is_replaced = False
                                                    break
                                                actual_args[i] = aux_actual_args[int(m.group(1))]
                                            else:
                                                is_replaced = False
                                                break

                                    if is_replaced:
                                        enter_edge['source'] = lhs + func_name + '(' + \
                                                               (', '.join(actual_args) if actual_args else '') + ');'
                                        enter_edge['enter'] = return_edge['enter']

                                        if 'note' in return_edge:
                                            enter_edge['note'] = return_edge['note']

                                        next_edge = self.error_trace.next_edge(edge)
                                        self.error_trace.remove_edge_and_target_node(next_edge)

                                        removed_aux_funcs_num += 1

        if removed_aux_funcs_num:
            self._logger.debug('{0} auxiliary functions were removed'.format(removed_aux_funcs_num))

        # Remove non-action code from control functions
        self.__remove_aux_deg_code()

    def __remove_tmp_vars(self, edge):
        removed_tmp_vars_num = 0

        # Normal function scope.
        if 'enter' in edge:
            func_id = edge['enter']
            # Move forward to declarations or statements.
            edge = self.error_trace.next_edge(edge)

        # Scan variable declarations to find temporary variable names and corresponding edge ids.
        tmp_var_names = dict()
        edges_map = dict()
        while True:
            # Declarations are considered to finish when returning from current function, some function is entered, some
            # condition is checked or some assigment is performed (except for entry point which "contains" many
            # assignemts to global variabels). It is well enough for this optimization.
            if edge.get('return') == func_id or 'enter' in edge or 'condition' in edge or\
                    (func_id != -1 and '=' in edge['source']):
                break

            m = re.search(r'(tmp\w*);$', edge['source'])
            if m:
                edges_map[id(edge)] = edge
                tmp_var_names[m.group(1)] = id(edge)

            edge = self.error_trace.next_edge(edge)

        # Remember what temporary varibles aren't used after all.
        unused_tmp_var_decl_ids = set(list(tmp_var_names.values()))

        # Scan other statements to find function calls which results are stored into temporary variables.
        while True:
            # Reach error trace end.
            if not edge:
                break

            # Reach end of function.
            if edge.get('return') == func_id:
                break

            # Reach some function call which result is stored into temporary variable.
            m = re.search(r'^(tmp\w*)\s+=\s+(.+);$', edge['source'])
            if m:
                func_call_edge = edge

            # Remain all edges belonging to a given function as is in any case.
            if 'enter' in edge:
                removed_tmp_vars_num_tmp, edge = self.__remove_tmp_vars(edge)
                removed_tmp_vars_num += removed_tmp_vars_num_tmp

                # Replace
                #    tmp func(...);
                # with:
                #    func(...);
                if m:
                    # Detrmine that there is no retun from the function
                    # Keep in mind that each pair enter-return has an identifier, but such identifier is not unique
                    # across the trace, so we need to go through the whole trace and guarantee that for particular enter
                    # there is no pair.
                    level_under_concideration = None
                    level = 0
                    for e in self.error_trace.trace_iterator(begin=func_call_edge):
                        if 'enter' in e and e['enter'] == func_call_edge['enter']:
                            level += 1
                            if e == func_call_edge:
                                level_under_concideration = level
                        if 'return' in e and e['return'] == func_call_edge['enter']:
                            if level_under_concideration and level_under_concideration == level:
                                level = -1
                                break
                            else:
                                level = -1

                    # Do replacement
                    if level >= level_under_concideration:
                        func_call_edge['source'] = m.group(2) + ';'

                if not edge:
                    break

            # Try to find temorary variable usages on edges following corresponding function calls.
            if m:
                tmp_var_name = m.group(1)
                func_call = m.group(2)
                if tmp_var_name in tmp_var_names:
                    tmp_var_decl_id = tmp_var_names[tmp_var_name]
                    tmp_var_use_edge = self.error_trace.next_edge(edge)

                    # Skip simplification of the following sequence:
                    #   ... tmp...;
                    #   ...
                    #   tmp... = func(...);
                    #   ... gunc(... tmp... ...);
                    # since it requires two entered functions from one edge.
                    if 'enter' in tmp_var_use_edge:
                        unused_tmp_var_decl_ids.remove(tmp_var_decl_id)
                    else:
                        m = re.search(r'^(.*){0}(.*)$'.format(tmp_var_name), tmp_var_use_edge['source'])
                        if m:
                            func_call_edge['source'] = m.group(1) + func_call + m.group(2)

                            for attr in ('condition', 'return'):
                                if attr in tmp_var_use_edge:
                                    func_call_edge[attr] = tmp_var_use_edge[attr]

                            # Remove edge corresponding to temporary variable usage.
                            self.error_trace.remove_edge_and_target_node(tmp_var_use_edge)

                            removed_tmp_vars_num += 1

                            # Do not increase edges counter since we could merge edge corresponding to call to some
                            # function and edge corresponding to return from current function.
                            if func_call_edge.get('return') == func_id:
                                break

            edge = self.error_trace.next_edge(edge)

        # Remove all temporary variable declarations in any case.
        for tmp_var_decl_id in reversed(list(unused_tmp_var_decl_ids)):
            self.error_trace.remove_edge_and_target_node(edges_map[tmp_var_decl_id])

        return removed_tmp_vars_num, edge

    def __remove_aux_deg_code(self):
        # Determine control functions and allowed intervals
        intervals = ['CONTROL_FUNCTION_INIT', 'CALL', 'DISPATCH', 'RECEIVE', 'SUBPROCESS', 'CONDITION']
        data = dict()
        for file in self._emg_comments.keys():
            data[file] = dict()
            # Set control function start point
            for line in (l for l in self._emg_comments[file]
                         if self._emg_comments[file][l]['type'] == 'CONTROL_FUNCTION_BEGIN'):
                data[file][self._emg_comments[file][line]['instance']] = {
                    'begin': line,
                    'actions': list(),
                    'comment': self._emg_comments[file][line]['comment'],
                    'file': file
                }

            # Set control function end point
            for line in (l for l in self._emg_comments[file]
                         if self._emg_comments[file][l]['type'] == 'CONTROL_FUNCTION_END'):
                data[file][self._emg_comments[file][line]['instance']]['end'] = line

            # Deterine actions and allowed intervals
            for function in data[file]:
                inside_action = False
                for line in range(data[file][function]['begin'], data[file][function]['end']):
                    if not inside_action and line in self._emg_comments[file] and \
                                    self._emg_comments[file][line]['type'] in {t + '_BEGIN' for t in intervals}:
                        data[file][function]['actions'].append({'begin': line,
                                                                'comment': self._emg_comments[file][line]['comment'],
                                                                'type': self._emg_comments[file][line]['type']})
                        inside_action = True
                    elif inside_action and line in self._emg_comments[file] and \
                         self._emg_comments[file][line]['type'] in {t + '_END' for t in intervals}:
                        data[file][function]['actions'][-1]['end'] = line
                        inside_action = False

        # Search in error trace for control function code and cut all code outside allowed intervals
        cf_stack = list()

        def inside_control_function(cf_data, file, line):
            """Determine action to which string belong."""
            if cf_data['file'] == file and cf_data['begin'] <= line <= cf_data['end']:
                return True
            else:
                return False

        def inside_action(cf_data, line):
            """Determine action to which string belong."""
            for act in cf_data['actions']:
                if act['begin'] <= line <= act['end']:
                    return act

            return False

        def if_exit_function(e, stack):
            """Exit function."""
            if len(stack) > 0:
                if stack[-1]['functions'] == 0 and stack['enter id'] == e['return']:
                    # Exit control function
                    stack.pop()
                else:
                    if len(stack[-1]['functions']) > 0 and stack[-1]['functions'][-1] == e['return']:
                        # We inside an aux function
                        stack[-1]['functions'].pop()
                    if_simple_state(e, stack)

            return

        def if_enter_function(e, stack):
            """Enter function."""
            # Stepping into a control function?
            for file in data:
                for function in data[file]:
                    match = re.search('{}\(.*\)'.format(function.lower()), e['source'])
                    if match:
                        # Aha, found a new control function
                        cf_data = {
                            'action': None,
                            'functions': list(),
                            'cf': data[file][function],
                            'enter id': e['enter'],
                            'in aux code': False
                        }
                        stack.append(cf_data)

                        # Add note on each control function entry
                        e['note'] = cf_data['cf']['comment']
                        return

            if len(stack) != 0:
                # todo: here we need actually should be sure that we are still withtin an action but it is hard to check
                if inside_control_function(stack[-1]['cf'], e['file'], e['start line']):
                    act = inside_action(stack[-1]['cf'], e['start line'])
                    if not act:
                        cf_stack[-1]['action'] = None
                        stack[-1]['in aux code'] = True
                        self.error_trace.remove_edge_and_target_node(e)
                    else:
                        cf_stack[-1]['action'] = act
                        stack[-1]['in aux code'] = False
                else:
                    cf_stack[-1]['functions'].append(e['enter'])

        def if_simple_state(e, stack):
            """Simple e."""
            if len(stack) > 0 and inside_control_function(stack[-1]['cf'], e['file'], e['start line']):
                stack[-1]['in aux code'] = False
                act = inside_action(stack[-1]['cf'], e['start line'])
                if (act and cf_stack[-1]['action'] and cf_stack[-1]['action'] != act) or \
                   (act and not cf_stack[-1]['action']):
                    # First action or another action
                    cf_stack[-1]['action'] = act
                elif not act:
                    # Not in action
                    cf_stack[-1]['action'] = None
                    self.error_trace.remove_edge_and_target_node(e)
            elif len(stack) > 0 and not inside_control_function(stack[-1]['cf'], e['file'], e['start line']) and \
                 not cf_stack[-1]['action']:
                self.error_trace.remove_edge_and_target_node(e)
            elif len(stack) > 0 and stack[-1]['in aux code']:
                self.error_trace.remove_edge_and_target_node(e)

            return

        for edge in self.error_trace.trace_iterator():
            # Dict changes its size, so keep it in mind
            if 'enter' in edge:
                if_enter_function(edge, cf_stack)
            elif 'return' in edge:
                if_exit_function(edge, cf_stack)
            else:
                if_simple_state(edge, cf_stack)

        # Replace implicit callback calls by explicit ones
        def replace_callback_call(edge, true_call):
            expected_ret = edge['enter']
            callback_ret = None
            in_callback = 0
            self.error_trace.remove_edge_and_target_node(edge)
            while True:
                edge = self.error_trace.next_edge(edge)
                if not edge:
                    break
                elif not callback_ret:
                    if 'enter' not in edge:
                        self.error_trace.remove_edge_and_target_node(edge)
                    else:
                        edge['source'] = true_call
                        callback_ret = edge['enter']
                        in_callback += 1
                elif in_callback:
                    if 'enter' in edge and edge['enter'] == callback_ret:
                        in_callback += 1
                    elif 'return' in edge and edge['return'] == callback_ret:
                        in_callback -= 1
                    elif 'enter' in edge and int(edge['start line'] - 1) in self._emg_comments[edge['file']] and \
                            self._emg_comments[edge['file']][int(edge['start line'] - 1)]['type'] == 'CALLBACK':
                        ntc = self._emg_comments[edge['file']][edge['start line'] - 1]['comment']
                        edge = replace_callback_call(edge, ntc)
                        if not edge:
                            break
                elif in_callback == 0:
                    self.error_trace.remove_edge_and_target_node(edge)
                    if 'return' in edge and edge['return'] == expected_ret:
                        break

            return edge

        # Go through trace
        edge = self.error_trace.entry_node['out'][0]
        while True:
            if 'enter' in edge and int(edge['start line'] - 1) in self._emg_comments[edge['file']] and \
                    self._emg_comments[edge['file']][int(edge['start line'] - 1)]['type'] == 'CALLBACK':
                true_call = self._emg_comments[edge['file']][edge['start line'] - 1]['comment']
                edge = replace_callback_call(edge, true_call)
                if not edge:
                    break
            edge = self.error_trace.next_edge(edge)
            if not edge:
                break

        return