import os
import re
import xml.etree.ElementTree as ET


class ErrorTrace:
    WITNESS_NS = {'graphml': 'http://graphml.graphdrawing.org/xmlns'}
    MODEL_COMMENT_TYPES = 'AUX_FUNC|MODEL_FUNC|NOTE|ASSERT'
    EMG_COMMENTS = 'CONTROL_FUNCTION_BEGIN|CONTROL_FUNCTION_END|CALLBACK|CONTROL_FUNCTION_INIT_BEGIN|' \
                   'CONTROL_FUNCTION_INIT_END|CALL_BEGIN|CALL_END|DISPATCH_BEGIN|DISPATCH_END|RECEIVE_BEGIN|' \
                   'RECEIVE_END|SUBPROCESS_BEGIN|SUBPROCESS_END|CONDITION_BEGIN|CONDITION_END'

    def __init__(self, logger, witness):
        self.logger = logger
        self.witness = witness
        self.nodes = []
        self.entry_node_id = None
        self.violation_node_ids = []
        self.edges = []
        self.files = []
        self.funcs = []
        self.__violation_edge_ids = []
        self.__aux_funcs = {}
        self.__model_funcs = {}
        self.__notes = {}
        self.__emg_comments = dict()
        self.__asserts = {}

    def process(self):
        self.__parse_witness()
        self.__get_violation_path()
        self.__parse_model_comments()
        self.__mark_witness()
        self.__simplify()

    def __get_input_edge_id(self, node_id):
        if node_id < 0 or node_id >= len(self.nodes):
            raise KeyError('Node {!r} does not exist'.format(node_id))

        node = self.nodes[node_id]

        if node[0] is None:
            raise ValueError('There are not input edges for node {!r}'.format(node_id))

        if isinstance(node[0], list):
            if len(node[0]) > 1:
                raise ValueError('There are more than one input edges for node {!r}'.format(node_id))

            return node[0][0]

        return node[0]

    def __get_violation_node_id(self):
        if len(self.violation_node_ids) > 1:
            raise NotImplementedError('Several violation nodes are not supported')

        return self.violation_node_ids[0]

    def __get_violation_path(self):
        self.logger.info('Get violation path')

        ignore_edges_of_func_id = None
        cur_edge_id = self.__get_input_edge_id(self.__get_violation_node_id())
        self.__violation_edge_ids.append(cur_edge_id)

        while True:
            cur_edge_id = self.__get_input_edge_id(self.edges[cur_edge_id]['source node'])
            cur_edge = self.edges[cur_edge_id]

            if not ignore_edges_of_func_id and 'return' in cur_edge:
                ignore_edges_of_func_id = cur_edge['return']

            if 'enter' in cur_edge and cur_edge['enter'] == ignore_edges_of_func_id:
                ignore_edges_of_func_id = None

            if not ignore_edges_of_func_id:
                self.__violation_edge_ids.append(cur_edge_id)

            if cur_edge['source node'] == self.entry_node_id:
                break

    def __mark_witness(self):
        self.logger.info('Mark witness with model comments')

        # Two stages are required since for marking edges with warnings we need to know whether there notes at violation
        # path below.
        warn_edges = []
        for stage in ('notes', 'warns'):
            for edge_id, edge in enumerate(self.edges):
                file_id = edge['file']
                file = self.files[file_id]
                start_line = edge['start line']

                if stage == 'notes':
                    if 'enter' in edge:
                        func_id = edge['enter']
                        if func_id in self.__model_funcs:
                            note = self.__model_funcs[func_id]
                            self.logger.debug("Add note {!r} for call of model function {!r} from '{2}:{3}'".
                                              format(note, self.funcs[func_id], file, start_line))
                            edge['note'] = note

                    if file_id in self.__notes and start_line in self.__notes[file_id]:
                        note = self.__notes[file_id][start_line]
                        self.logger.debug("Add note {!r} for statement from '{1}:{2}'".format(note, file, start_line))
                        edge['note'] = note

                if stage == 'warns':
                    if file_id in self.__asserts and start_line in self.__asserts[file_id]:
                        # Add warning just if there are no more edges with notes at violation path below.
                        track_notes = False
                        note_found = False
                        for violation_edge_id in reversed(self.__violation_edge_ids):
                            if track_notes:
                                if 'note' in self.edges[violation_edge_id]:
                                    note_found = True
                                    break
                            if violation_edge_id == edge_id:
                                track_notes = True

                        if not note_found:
                            warn = self.__asserts[file_id][start_line]
                            self.logger.debug(
                                "Add warning {!r} for statement from '{1}:{2}'".format(warn, file, start_line))
                            # Add warning either to edge itself or to first edge that enters function and has note at
                            # violation path. If don't do the latter warning will be hidden by error trace visualizer.
                            warn_edge = edge
                            for violation_edge_id in self.__violation_edge_ids:
                                violation_edge = self.edges[violation_edge_id]
                                if 'enter' in violation_edge and 'note' in violation_edge:
                                    warn_edge = violation_edge
                            warn_edge['warn'] = warn
                            warn_edges.append(warn_edge)

                            # Remove added warning to avoid its addition one more time.
                            del self.__asserts[file_id][start_line]

        # Remove notes from edges marked with warnings. Otherwise error trace visualizer will be confused.
        for warn_edge in warn_edges:
            if 'note' in warn_edge:
                del warn_edge['note']

        del self.__violation_edge_ids, self.__model_funcs, self.__notes, self.__asserts

    def __parse_model_comments(self):
        self.logger.info('Parse model comments from source files referred by witness')

        for file_id, file in enumerate(self.files):
            if not os.path.isfile(file):
                raise FileNotFoundError('File {!r} referred by witness does not exist'.format(file))

            self.logger.debug('Parse model comments from {!r}'.format(file))

            with open(file, encoding='utf8') as fp:
                line = 0
                for text in fp:
                    line += 1

                    # Try match EMG comment
                    # Expect comment like /* TYPE Instance Text */
                    if file_id not in self.__emg_comments:
                        self.__emg_comments[file_id] = dict()
                    match = re.search(r'/\*\s({0})\s(\w+)\s(.*)\s\*/'.format(self.EMG_COMMENTS), text)
                    if match:
                        self.__emg_comments[file_id][line] = {
                            'type': match.group(1),
                            'instance': match.group(2),
                            'comment': match.group(3),
                        }
                    else:
                        # Expect comment like /* TYPE Text */
                        match = re.search(r'/\*\s({0})\s(.*)\s\*/'.format(self.EMG_COMMENTS), text)
                        if match:
                            self.__emg_comments[file_id][line] = {
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
                            for func_id, ref_func_name in enumerate(self.funcs):
                                if ref_func_name == func_name:
                                    if kind == 'AUX_FUNC':
                                        self.__aux_funcs[func_id] = None
                                        self.logger.debug("Get auxiliary function '{0}' from '{1}:{2}'".
                                                          format(func_name, file, line))
                                    else:
                                        self.__model_funcs[func_id] = comment
                                        self.logger.debug("Get note '{}' for model function '{1}' from '{2}:{3}'".
                                                          format(comment, func_name, file, line))

                                    break
                        else:
                            if file_id not in self.__notes:
                                self.__notes[file_id] = {}
                            self.__notes[file_id][line + 1] = comment
                            self.logger.debug(
                                "Get note '{0}' for statement from '{1}:{2}'".format(comment, file, line + 1))
                            # Some assertions will become warnings.
                            if kind == 'ASSERT':
                                if file_id not in self.__asserts:
                                    self.__asserts[file_id] = {}
                                self.__asserts[file_id][line + 1] = comment
                                self.logger.debug("Get assertiom '{0}' for statement from '{1}:{2}'".
                                                  format(comment, file, line + 1))

    def __parse_witness(self):
        self.logger.info('Parse witness {!r}'.format(self.witness))

        with open(self.witness, encoding='utf8') as fp:
            tree = ET.parse(fp)

        root = tree.getroot()

        # Parse default file.
        for key in root.findall('graphml:key', self.WITNESS_NS):
            if key.attrib['id'] == 'originfile':
                self.files.append(key.find('graphml:default', self.WITNESS_NS).text)

        graph = root.find('graphml:graph', self.WITNESS_NS)

        nodes_map, sink_nodes_map = self.__parse_witness_nodes(graph)
        self.__parse_witness_edges(graph, nodes_map, sink_nodes_map)

    def __parse_witness_nodes(self, graph):
        node_id = 0
        nodes_map = {}
        sink_nodes_map = {}
        unsupported_node_data_keys = {}

        for node in graph.findall('graphml:node', self.WITNESS_NS):
            is_sink = False

            for data in node.findall('graphml:data', self.WITNESS_NS):
                data_key = data.attrib['key']
                if data_key == 'entry':
                    self.entry_node_id = node_id
                    self.logger.debug('Parse entry node {!r}'.format(node_id))
                elif data_key == 'sink':
                    is_sink = True
                    self.logger.debug('Parse sink node {!r}'.format(node_id))
                elif data_key == 'violation':
                    if self.violation_node_ids:
                        raise NotImplementedError('Several violation nodes are not supported')
                    self.violation_node_ids.append(node_id)
                    self.logger.debug('Parse violation node {!r}'.format(node_id))
                elif data_key not in unsupported_node_data_keys:
                    self.logger.warning('Node data key {!r} is not supported'.format(data_key))
                    unsupported_node_data_keys[data_key] = None

            # Do not track sink nodes as all other nodes. All edges leading to sink nodes will be excluded as well.
            if is_sink:
                sink_nodes_map[node.attrib['id']] = None
            else:
                # Use small integers instead of large string to uniquely identify nodes.
                nodes_map[node.attrib['id']] = node_id
                node_id += 1

                # Inialize lists of input and output edge ids.
                self.nodes.append([[], []])

        # Sanity checks.
        if self.entry_node_id is None:
            raise KeyError('Entry node was not found')
        if not self.violation_node_ids:
            raise KeyError('Violation nodes were not found')

        self.logger.debug('Parse {0} nodes and {1} sink nodes'.format(node_id, len(sink_nodes_map)))

        return nodes_map, sink_nodes_map

    def __parse_witness_edges(self, graph, nodes_map, sink_nodes_map):
        unsupported_edge_data_keys = {}

        # Use maps for source files and functions as for nodes. Add artificial map to 0 for default file without
        # explicitly specifying its path.
        files_map = {None: 0}
        funcs_map = {}

        # The number of edges leading to sink nodes. Such edges will be completely removed.
        sink_edges_num = 0
        edge_id = 0
        for edge in graph.findall('graphml:edge', self.WITNESS_NS):
            # Sanity checks.
            if 'source' not in edge.attrib:
                raise KeyError('Source node was not found')
            if 'target' not in edge.attrib:
                raise KeyError('Destination node was not found')

            source_node_id = nodes_map[edge.attrib['source']]

            if edge.attrib['target'] in sink_nodes_map:
                sink_edges_num += 1
                continue

            target_node_id = nodes_map[edge.attrib['target']]

            # Update lists of input and output edges for source and target nodes.
            self.nodes[source_node_id][1].append(edge_id)
            self.nodes[target_node_id][0].append(edge_id)

            _edge = {'source node': source_node_id, 'target node': target_node_id}

            for data in edge.findall('graphml:data', self.WITNESS_NS):
                data_key = data.attrib['key']
                if data_key == 'originfile':
                    if data.text not in files_map:
                        files_map[data.text] = len(files_map)
                        self.files.append(data.text)
                    _edge['file'] = files_map[data.text]
                elif data_key == 'startline':
                    _edge['start line'] = int(data.text)
                elif data_key == 'endline':
                    _edge['end line'] = int(data.text)
                elif data_key == 'sourcecode':
                    _edge['source'] = data.text
                elif data_key == 'enterFunction' or data_key == 'returnFrom' or data_key == 'assumption.scope':
                    if data.text not in funcs_map:
                        funcs_map[data.text] = len(funcs_map)
                        self.funcs.append(data.text)
                    if data_key == 'enterFunction':
                        _edge['enter'] = funcs_map[data.text]
                    elif data_key == 'returnFrom':
                        _edge['return'] = funcs_map[data.text]
                    else:
                        _edge['assumption scope'] = funcs_map[data.text]
                elif data_key == 'control':
                    _edge['condition'] = True
                elif data_key == 'assumption':
                    _edge['assumption'] = data.text
                elif data_key in ('startoffset', 'endoffset'):
                    pass
                elif data_key not in unsupported_edge_data_keys:
                    self.logger.warning('Edge data key {!r} is not supported'.format(data_key))
                    unsupported_edge_data_keys[data_key] = None

            if 'file' not in _edge:
                _edge['file'] = files_map[None]

            self.edges.append(_edge)
            edge_id += 1

        self.logger.debug('Parse {0} edges and {1} sink edges'.format(len(self.edges), sink_edges_num))

        # Now we know all input and ouptut edges for all nodes.
        # Optimize input and output edges lists if they contain less than 2 elements.
        for node in self.nodes:
            for i in (0, 1):
                if len(node[i]) < 2:
                    if not node[i]:
                        node[i] = None
                    else:
                        node[i] = node[i][0]

    def __remove_edge_and_target_node(self, removed_edge_id):
        removed_edge = self.edges[removed_edge_id]

        if not isinstance(self.nodes[removed_edge['source node']][1], int):
            raise ValueError(
                'Can not remove edge {!r} because of its source node {!r} has more than one output edges'.format(
                    removed_edge_id, removed_edge['source node']))

        if not isinstance(self.nodes[removed_edge['target node']][0], int):
            raise ValueError(
                'Can not remove edge {!r} because of its target node {!r} has more than one input edges'.format(
                    removed_edge_id, removed_edge['target node']))

        # Make all output edges of target node of removed edge output edges of its source node.
        self.__remove_node(removed_edge['target node'], removed_edge['source node'])

        # Shift by one all references to edges following removed one.
        for node in self.nodes:
            for i in (0, 1):
                if isinstance(node[i], int):
                    if node[i] > removed_edge_id:
                        node[i] -= 1
                elif isinstance(node[i], list):
                    for edge_id_i, edge_id in enumerate(node[i]):
                        if edge_id > removed_edge_id:
                            node[i][edge_id_i] -= 1

        # Remove edge at last.
        del self.edges[removed_edge_id]

    def __remove_node(self, removed_node_id, new_source_node_id=None):
        removed_node = self.nodes[removed_node_id]

        # Reset target node for input edges of removed node.
        if isinstance(removed_node[0], int):
            self.edges[removed_node[0]]['target node'] = None
        elif isinstance(removed_node[0], list):
            for input_edge_id in removed_node[0]:
                self.edges[input_edge_id]['target node'] = None

        # Specify new source node for output edges of removed node.
        if isinstance(removed_node[1], int):
            self.edges[removed_node[1]]['source node'] = new_source_node_id
        elif isinstance(removed_node[1], list):
            for input_edge_id in removed_node[1]:
                self.edges[input_edge_id]['source node'] = new_source_node_id

        # Shift by one all references to nodes following removed one.
        if self.entry_node_id > removed_node_id:
            self.entry_node_id -= 1
        for i, violation_node_id in enumerate(self.violation_node_ids):
            if violation_node_id > removed_node_id:
                self.violation_node_ids[i] -= 1
        for edge in self.edges:
            if edge['source node'] > removed_node_id:
                edge['source node'] -= 1

            if edge['target node'] and edge['target node'] > removed_node_id:
                edge['target node'] -= 1

        # Remove node at last.
        del self.nodes[removed_node_id]

    def __remove_tmp_vars(self, edge_id):
        removed_tmp_vars_num = 0
        edge = self.edges[edge_id]

        # Normal function scope.
        if 'enter' in edge:
            func_id = edge['enter']
            # Move forward to declarations or statements.
            edge_id += 1
        # -1 is global and entry point scopes that we can't distinguish.
        else:
            func_id = -1

        # Scan variable declarations to find temporary variable names and corresponding edge ids.
        tmp_var_names = {}
        while True:
            edge = self.edges[edge_id]

            # Declarations are considered to finish when returning from current function, some function is entered, some
            # condition is checked or some assigment is performed (except for entry point which "contains" many
            # assignemts to global variabels). It is well enough for this optimization.
            if edge.get('return') == func_id or 'enter' in edge or 'condition' in edge or\
                    (func_id != -1 and '=' in edge['source']):
                break

            m = re.search(r'(tmp\w*);$', edge['source'])
            if m:
                tmp_var_names[m.group(1)] = edge_id

            edge_id += 1

        # Remember what temporary varibles aren't used after all.
        unused_tmp_var_decl_ids = set(list(tmp_var_names.values()))

        # Scan other statements to find function calls which results are stored into temporary variables.
        while True:
            # Reach error trace end.
            if edge_id == len(self.edges):
                break

            edge = self.edges[edge_id]

            # Reach end of function.
            if edge.get('return') == func_id:
                break

            # Reach some function call which result is stored into temporary variable.
            m = re.search(r'^(tmp\w*)\s+=\s+(.+);$', edge['source'])
            if m:
                func_call_edge_id = edge_id

            # Remain all edges belonging to a given function as is in any case.
            if 'enter' in edge:
                removed_tmp_vars_num_tmp, edge_id = self.__remove_tmp_vars(edge_id)
                removed_tmp_vars_num += removed_tmp_vars_num_tmp

                # Replace
                #    tmp func(...);
                # with:
                #    func(...);
                if m:
                    # Detrmine that there is no retun from the function
                    level = 0
                    # Keep in mind that each pair enter-return has an identifier, but such identifier is not unique
                    # across the trace, so we need to go through the whole trace and guarantee that for particular enter
                    # there is no pair.
                    entrance_identifier = self.edges[func_call_edge_id]['enter']
                    level_under_concideration = None
                    level = 0
                    for e_id in range(func_call_edge_id, len(self.edges)):
                        if len(self.edges) > e_id:
                            e = self.edges[e_id]
                            if 'enter' in e and e['enter'] == entrance_identifier:
                                level += 1
                                if e_id == func_call_edge_id:
                                    level_under_concideration = level
                            if 'return' in e and e['return'] == entrance_identifier:
                                if level_under_concideration and level_under_concideration == level:
                                    level = -1
                                    break
                                else:
                                    level = -1

                    # Do replacement
                    if level >= level_under_concideration:
                        self.edges[func_call_edge_id]['source'] = m.group(2) + ';'

                # Reach error trace end.
                if edge_id == len(self.edges):
                    break

            # Try to find temorary variable usages on edges following corresponding function calls.
            if m:
                tmp_var_name = m.group(1)
                func_call = m.group(2)
                if tmp_var_name in tmp_var_names:
                    tmp_var_decl_id = tmp_var_names[tmp_var_name]
                    tmp_var_use_edge_id = edge_id + 1
                    tmp_var_use_edge = self.edges[tmp_var_use_edge_id]

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
                            self.edges[func_call_edge_id]['source'] = m.group(1) + func_call + m.group(2)

                            for attr in ('condition', 'return'):
                                if attr in tmp_var_use_edge:
                                    self.edges[func_call_edge_id][attr] = tmp_var_use_edge[attr]

                            # Remove edge corresponding to temporary variable usage.
                            self.__remove_edge_and_target_node(tmp_var_use_edge_id)

                            removed_tmp_vars_num += 1

                            # Do not increase edges counter since we could merge edge corresponding to call to some
                            # function and edge corresponding to return from current function.
                            if self.edges[func_call_edge_id].get('return') == func_id:
                                break

            edge_id += 1

        # Remove all temporary variable declarations in any case.
        for tmp_var_decl_id in reversed(list(unused_tmp_var_decl_ids)):
            self.__remove_edge_and_target_node(tmp_var_decl_id)
            # Move edges counter back since we removed edge corresponding to temporary variable declaration that
            # preceeds current one.
            edge_id -= 1

        return removed_tmp_vars_num, edge_id

    def __remove_aux_deg_code(self):
        # Determine control functions and allowed intervals
        intervals = ['CONTROL_FUNCTION_INIT', 'CALL', 'DISPATCH', 'RECEIVE', 'SUBPROCESS', 'CONDITION']
        data = dict()
        for file in self.__emg_comments.keys():
            data[file] = dict()
            # Set control function start point
            for line in (l for l in self.__emg_comments[file]
                         if self.__emg_comments[file][l]['type'] == 'CONTROL_FUNCTION_BEGIN'):
                data[file][self.__emg_comments[file][line]['instance']] = {
                    'begin': line,
                    'actions': list(),
                    'comment': self.__emg_comments[file][line]['comment']
                }

            # Set control function end point
            for line in (l for l in self.__emg_comments[file]
                         if self.__emg_comments[file][l]['type'] == 'CONTROL_FUNCTION_END'):
                data[file][self.__emg_comments[file][line]['instance']]['end'] = line

            # Deterine actions and allowed intervals
            for function in data[file]:
                inside_action = False
                for line in range(data[file][function]['begin'], data[file][function]['end']):
                    if not inside_action and line in self.__emg_comments[file] and \
                                    self.__emg_comments[file][line]['type'] in {t + '_BEGIN' for t in intervals}:
                        data[file][function]['actions'].append({'begin': line,
                                                                'comment': self.__emg_comments[file][line]['comment'],
                                                                'type': self.__emg_comments[file][line]['type']})
                        inside_action = True
                    elif inside_action and line in self.__emg_comments[file] and \
                                    self.__emg_comments[file][line]['type'] in {t + '_END' for t in intervals}:
                        data[file][function]['actions'][-1]['end'] = line
                        inside_action = False

        # Search in error trace for control function code and cut all code outside allowed intervals
        cf_stack = list()
        in_ext_aux_code = False

        def inside_control_function(cf_data, line):
            """Determine action to which string belong."""
            if cf_data['begin'] <= line <= cf_data['end']:
                return True
            else:
                return False

        def inside_action(cf_data, line):
            """Determine action to which string belong."""
            for act in cf_data['actions']:
                if act['begin'] <= line <= act['end']:
                    return act

            return False

        def if_exit_function(e_id, e, stack):
            """Exit function."""
            removed = 0

            if len(stack) > 0:
                if stack[-1]['functions'] == 0 and stack['enter id'] == e['return']:
                    # Exit control function
                    stack.pop()
                else:
                    if len(stack[-1]['functions']) > 0 and stack[-1]['functions'][-1] == e['return']:
                        # We inside an aux function
                        stack[-1]['functions'].pop()
                    removed = if_simple_state(e_id, e, stack)

            return removed

        def if_enter_function(e_id, e, stack):
            """Enter function."""
            removed = 0

            # Stepping into a control function?
            for function in data[e['file']]:
                match = re.search('{}\(.*\)'.format(function.lower()), e['source'])
                if match:
                    # Aha, found new control function
                    cf_data = {
                        'action': None,
                        'functions': list(),
                        'cf': data[e['file']][function],
                        'enter id': e['enter'],
                        'in aux code': False
                    }
                    stack.append(cf_data)

                    # Add note on each control function entry
                    e['note'] = cf_data['cf']['comment']
                    return removed

            if len(stack) != 0:
                # todo: here we need actually should be sure that we are still withtin an action but it is hard to check
                if inside_control_function(stack[-1]['cf'], e['start line']):
                    if not inside_action(stack[-1]['cf'], e['start line']):
                        cf_stack[-1]['action'] = None
                        stack[-1]['in aux code'] = True
                        self.__remove_edge_and_target_node(e_id)
                        removed += 1
                else:
                    cf_stack[-1]['functions'].append(e['enter'])

            return removed

        def if_simple_state(e_id, e, stack):
            """Simple e."""
            removed = 0

            if len(stack) > 0 and inside_control_function(stack[-1]['cf'], e['start line']):
                stack[-1]['in aux code'] = False
                act = inside_action(stack[-1]['cf'], e['start line'])
                if (act and cf_stack[-1]['action'] and cf_stack[-1]['action'] != act) or \
                   (act and not cf_stack[-1]['action']):
                    # First action or another action
                    cf_stack[-1]['action'] = act
                elif not act:
                    # Not in action
                    cf_stack[-1]['action'] = None
                    self.__remove_edge_and_target_node(e_id)
                    removed += 1
            elif len(stack) > 0 and not inside_control_function(stack[-1]['cf'], e['start line']) and \
                 not cf_stack[-1]['action']:
                self.__remove_edge_and_target_node(e_id)
                removed += 1
            elif len(stack) > 0 and stack[-1]['in aux code']:
                self.__remove_edge_and_target_node(e_id)
                removed += 1

            return removed

        e_id = 0
        while True:
            # Dict changes its size, so keep it in mind
            if len(self.edges) > e_id:
                edge = self.edges[e_id]
                if 'enter' in edge:
                    removed = if_enter_function(e_id, edge, cf_stack)
                elif 'return' in edge:
                    removed = if_exit_function(e_id, edge, cf_stack)
                else:
                    removed = if_simple_state(e_id, edge, cf_stack)
                e_id -= removed
                e_id += 1
            else:
                break
        return

    def __simplify(self):
        self.logger.info('Simplify witness')

        # Simple transformations.
        for edge in self.edges:
            # Make source code more human readable.
            if 'source' in edge:
                # Remove "[...]" around conditions.
                if 'condition' in edge:
                    edge['source'] = edge['source'].strip('[]')

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
        edge_id = 0
        removed_edges_num = 0
        while True:
            if edge_id == len(self.edges):
                break

            if 'return' in self.edges[edge_id]:
                self.__remove_edge_and_target_node(edge_id + 1)
                removed_edges_num += 1

            edge_id += 1
        if removed_edges_num:
            self.logger.debug('{0} useless edges were removed'.format(removed_edges_num))

        # Get rid of temporary variables. Replace:
        #   ... tmp...;
        #   ...
        #   tmp... = func(...);
        #   ... tmp... ...;
        # with (removing first and last statements):
        #   ...
        #   ... func(...) ...;
        removed_tmp_vars_num = self.__remove_tmp_vars(0)[0]

        if removed_tmp_vars_num:
            self.logger.debug('{0} temporary variables were removed'.format(removed_tmp_vars_num))

        # Get rid of auxiliary functions if possible. Replace:
        #   ... = aux_func(...)
        #     return func(...)
        # with:
        #   ... = func(...)
        # accurately replacing arguments if required.
        edge_id = 0
        removed_aux_funcs_num = 0
        while True:
            if edge_id == len(self.edges):
                break

            enter_edge = self.edges[edge_id]

            if 'enter' in enter_edge:
                func_id = enter_edge['enter']
                if func_id in self.__aux_funcs:
                    return_edge = self.edges[edge_id + 1]
                    if return_edge.get('return') == func_id and 'enter' in return_edge:
                        # Get lhs and actual arguments of called auxiliary function.
                        m = re.search(r'^(.*){0}\s*\((.+)\);$'.format(self.funcs[func_id]),
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

                                        self.__remove_edge_and_target_node(edge_id + 1)

                                        removed_aux_funcs_num += 1
            edge_id += 1

        if removed_aux_funcs_num:
            self.logger.debug('{0} auxiliary functions were removed'.format(removed_aux_funcs_num))

        # Remove non-action code from control functions
        self.__remove_aux_deg_code()
