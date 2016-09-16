import os
import re
import xml.etree.ElementTree as ET


class Witness:
    NS = {'graphml': 'http://graphml.graphdrawing.org/xmlns'}
    MODEL_COMMENT_TYPES = 'AUX_FUNC|MODEL_FUNC|NOTE|ASSERT'

    def __init__(self, logger, witness):
        self.logger = logger
        self.witness = witness
        self.__graph = None
        self.__nodes_map = {}
        self.nodes = []
        self.entry_node_id = None
        self.sink_node_ids = []
        self.violation_node_ids = []
        self.edges = []
        self.files = []
        self.funcs = []
        self.__violation_edge_ids = []
        self.__aux_funcs = {}
        self.__model_funcs = {}
        self.__notes = {}
        self.__asserts = {}

    def process(self):
        self.__parse()
        self.__get_violation_path()
        self.__parse_model_comments()
        self.__mark_witness()
        self.__simplify()

    def __get_input_edge_id(self, node_id):
        if node_id < 0 or node_id >= len(self.nodes):
            raise KeyError('Node "{0}" does not exist'.format(node_id))

        node = self.nodes[node_id]

        if node[0] is None:
            raise ValueError('There are not input edges for node "{0}"'.format(node_id))

        if isinstance(node[0], list):
            if len(node[0]) > 1:
                raise ValueError('There are more than one input edges for node "{0}"'.format(node_id))

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
                            self.logger.debug('Add note "{0}" for call of model function "{1}" from "{2}:{3}"'.
                                              format(note, self.funcs[func_id], file, start_line))
                            edge['note'] = note

                    if file_id in self.__notes and start_line in self.__notes[file_id]:
                        note = self.__notes[file_id][start_line]
                        self.logger.debug('Add note "{0}" for statement from "{1}:{2}"'.format(note, file, start_line))
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
                                'Add warning "{0}" for statement from "{1}:{2}"'.format(warn, file, start_line))
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

    def __parse(self):
        self.logger.info('Parse witness "{0}"'.format(self.witness))

        with open(self.witness, encoding='utf8') as fp:
            tree = ET.parse(fp)

        root = tree.getroot()

        # Parse default file.
        for key in root.findall('graphml:key', self.NS):
            if key.attrib['id'] == 'originfile':
                self.files.append(key.find('graphml:default', self.NS).text)

        self.__graph = root.find('graphml:graph', self.NS)

        self.__parse_nodes()
        self.__parse_edges()

        del self.__graph, self.__nodes_map

    def __parse_model_comments(self):
        self.logger.info('Parse model comments from source files referred by witness')

        for file_id, file in enumerate(self.files):
            if not os.path.isfile(file):
                raise FileNotFoundError('File "{0}" referred by witness does not exist'.format(file))

            self.logger.debug('Parse model comments from "{0}"'.format(file))

            with open(file, encoding='utf8') as fp:
                line = 0
                for text in fp:
                    line += 1
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
                                        'Auxiliary/model function definition is not specified in "{0}"'.format(text))
                            except StopIteration:
                                raise ValueError('Auxiliary/model function definition does not exist')

                            # Deal with functions referenced by witness.
                            for func_id, ref_func_name in enumerate(self.funcs):
                                if ref_func_name == func_name:
                                    if kind == 'AUX_FUNC':
                                        self.__aux_funcs[func_id] = None
                                        self.logger.debug('Get auxiliary function "{0}" from "{1}:{2}"'.
                                                          format(func_name, file, line))
                                    else:
                                        self.__model_funcs[func_id] = comment
                                        self.logger.debug('Get note "{0}" for model function "{1}" from "{2}:{3}"'.
                                                          format(comment, func_name, file, line))

                                    break
                        else:
                            if file_id not in self.__notes:
                                self.__notes[file_id] = {}
                            self.__notes[file_id][line + 1] = comment
                            self.logger.debug(
                                'Get note "{0}" for statement from "{1}:{2}"'.format(comment, file, line + 1))
                            # Some assertions will become warnings.
                            if kind == 'ASSERT':
                                if file_id not in self.__asserts:
                                    self.__asserts[file_id] = {}
                                self.__asserts[file_id][line + 1] = comment
                                self.logger.debug('Get assertiom "{0}" for statement from "{1}:{2}"'.
                                                  format(comment, file, line + 1))

    def __parse_nodes(self):
        unsupported_node_data_keys = {}

        for node_id, node in enumerate(self.__graph.findall('graphml:node', self.NS)):
            # Use small integers instead of large string to uniquely identify nodes.
            self.__nodes_map[node.attrib['id']] = node_id
            self.nodes.append([[], []])

            for data in node.findall('graphml:data', self.NS):
                data_key = data.attrib['key']
                if data_key == 'entry':
                    self.entry_node_id = node_id
                    self.logger.debug('Parse entry node "{0}"'.format(node_id))
                elif data_key == 'sink':
                    if self.sink_node_ids:
                        raise NotImplementedError('Several sink nodes are not supported')
                    self.sink_node_ids.append(node_id)
                    self.logger.debug('Parse sink node "{0}"'.format(node_id))
                elif data_key == 'violation':
                    if self.violation_node_ids:
                        raise NotImplementedError('Several violation nodes are not supported')
                    self.violation_node_ids.append(node_id)
                    self.logger.debug('Parse violation node "{0}"'.format(node_id))
                elif data_key not in unsupported_node_data_keys:
                    self.logger.warning('Node data key "{0}" is not supported'.format(data_key))
                    unsupported_node_data_keys[data_key] = None

        # Sanity checks.
        if self.entry_node_id is None:
            raise KeyError('Entry node was not found')
        if not self.violation_node_ids:
            raise KeyError('Violation nodes were not found')

        self.logger.debug('Parse "{0}" nodes'.format(len(self.nodes)))

    def __parse_edges(self):
        unsupported_edge_data_keys = {}

        # Use maps for source files and functions as for nodes. Add artificial map to 0 for default file without
        # explicitly specifying its path.
        files_map = {None: 0}
        funcs_map = {}

        for edge_id, edge in enumerate(self.__graph.findall('graphml:edge', self.NS)):
            # Sanity checks.
            if 'source' not in edge.attrib:
                raise KeyError('Source node was not found')
            if 'target' not in edge.attrib:
                raise KeyError('Destination node was not found')

            source_node_id = self.__nodes_map[edge.attrib['source']]
            target_node_id = self.__nodes_map[edge.attrib['target']]

            # Update lists of input and output edges for source and target nodes.
            self.nodes[source_node_id][1].append(edge_id)
            self.nodes[target_node_id][0].append(edge_id)

            _edge = {'source node': source_node_id, 'target node': target_node_id}

            for data in edge.findall('graphml:data', self.NS):
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
                    self.logger.warning('Edge data key "{0}" is not supported'.format(data_key))
                    unsupported_edge_data_keys[data_key] = None

            if 'file' not in _edge:
                _edge['file'] = files_map[None]

            self.edges.append(_edge)

        self.logger.debug('Parse "{0}" edges'.format(len(self.edges)))

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
                'Can not remove edge "{0}" because of its source node "{1}" has more than one output edges'.format(
                    removed_edge_id, removed_edge['source node']))

        if not isinstance(self.nodes[removed_edge['target node']][0], int):
            raise ValueError(
                'Can not remove edge "{0}" because of its target node "{1}" has more than one input edges'.format(
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
        for i, sink_node_id in enumerate(self.sink_node_ids):
            if sink_node_id > removed_node_id:
                self.sink_node_ids[i] -= 1
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

    def __simplify(self):
        self.logger.info('Simplify witness')

        # Simple transformations.
        for edge in self.edges:
            # Make source code more human readable.
            if 'source' in edge:
                # Remove "[...]" around conditions.
                if 'condition' in edge:
                    edge['source'] = edge['source'].strip('[]')

                # Replace white spaces before trailing ";".
                edge['source'] = re.sub(r'\s+;$', ';', edge['source'])

                # Replace unnessary "(...)" around integers and identifiers.
                edge['source'] = re.sub(r' \((-?\w+)\)', ' \g<1>', edge['source'])

                # Replace "!(... ==/!= ...)" with "... !=/== ...".
                edge['source'] = re.sub(r'^!\((.+)==(.+)\)$', '\g<1>!=\g<2>', edge['source'])
                edge['source'] = re.sub(r'^!\((.+)!=(.+)\)$', '\g<1>==\g<2>', edge['source'])

            # Make assumptions more human readable.
            if 'assumption' in edge:
                # Like for source code.
                edge['assumption'] = re.sub(r' \((-?\w+)\)', ' \g<1>', edge['assumption'])

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

        # Get rid of "simple" temporary variables. Replace:
        #   int tmp;
        #   tmp = func(...);
        #   return tmp;
        # with:
        #   return func(...);
        edge_id = 0
        removed_tmp_vars_num = 0
        while True:
            if edge_id == len(self.edges):
                break

            if 'enter' in self.edges[edge_id]:
                tmp_var_decl_edge = self.edges[edge_id + 1]
                if tmp_var_decl_edge.get('source') == 'int tmp;':
                    tmp_var_decl_assumption = tmp_var_decl_edge.get('assumption')
                    func_call_edge = self.edges[edge_id + 2]
                    if func_call_edge.get('source').startswith('tmp = '):
                        i = 3

                        # Remain all edges before returning from a given function as is in any case.
                        if 'enter' in func_call_edge:
                            while True:
                                if self.edges[edge_id + i].get('return') == func_call_edge['enter']:
                                    i += 1
                                    break
                                i += 1

                        return_edge = self.edges[edge_id + i]
                        if 'return' in return_edge and return_edge.get('source') == 'return tmp;':
                            func_call_edge['source'] = re.sub(r'^tmp = ', 'return ', func_call_edge['source'])
                            func_call_edge['return'] = return_edge['return']
                            if 'assumption' not in func_call_edge and tmp_var_decl_assumption:
                                func_call_edge['assumption'] = tmp_var_decl_assumption
                            for i in (i, 1):
                                self.__remove_edge_and_target_node(edge_id + i)
                            removed_tmp_vars_num += 1

            edge_id += 1

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
                    if return_edge.get('return') == func_id:
                        # Get lhs and actual arguments of called auxiliary function.
                        m = re.search(r'^(.*){0}\s*\((.+)\);$'.format(self.funcs[func_id]),
                                      enter_edge['source'].replace('\n', ' '))
                        if m:
                            lhs = m.group(1)
                            aux_actual_args = [aux_actual_arg.strip() for aux_actual_arg in m.group(2).split(',')]

                            # Get actual arguments of called function.
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

                                        self.__remove_edge_and_target_node(edge_id + 1)

                                        removed_aux_funcs_num += 1

            edge_id += 1

        if removed_aux_funcs_num:
            self.logger.debug('{0} auxiliary functions were removed'.format(removed_aux_funcs_num))
