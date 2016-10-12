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
import os
import re
import xml.etree.ElementTree as ET
from core.vtg.et.error_trace import ErrorTrace


class ErrorTraceParser:
    WITNESS_NS = {'graphml': 'http://graphml.graphdrawing.org/xmlns'}
    MODEL_COMMENT_TYPES = 'AUX_FUNC|MODEL_FUNC|NOTE|ASSERT'
    EMG_COMMENTS = 'CONTROL_FUNCTION_BEGIN|CONTROL_FUNCTION_END|CALLBACK|CONTROL_FUNCTION_INIT_BEGIN|' \
                   'CONTROL_FUNCTION_INIT_END|CALL_BEGIN|CALL_END|DISPATCH_BEGIN|DISPATCH_END|RECEIVE_BEGIN|' \
                   'RECEIVE_END|SUBPROCESS_BEGIN|SUBPROCESS_END|CONDITION_BEGIN|CONDITION_END'

    def __init__(self, logger, witness):
        self._logger = logger
        self._violation_edges = list()
        self._model_funcs = dict()
        self._notes = dict()
        self._asserts = dict()

        # Start parsing
        self.error_trace = ErrorTrace()
        self._parse_witness(witness)
        # Do processing
        self._find_violation_path()
        self._parse_model_comments()
        self._mark_witness()

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
                    match = re.search(r'/\*\s({0})\s(\w+)\s(.*)\s\*/'.format(self.EMG_COMMENTS), text)
                    if match:
                        self.error_trace.add_emg_comment(file_id, line, match.group(1), match.group(2), match.group(3))
                    else:
                        match = re.search(r'/\*\s({0})\s(.*)\s\*/'.format(self.EMG_COMMENTS), text)
                        if match:
                            self.error_trace.add_emg_comment(file_id, line, match.group(1), None, match.group(2))

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
                                        self.error_trace.add_aux_func(func_id, None)
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
                        self._logger.debug("Add note {!r} for statement from '{}:{}'".format(note, file, start_line))
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
                                "Add warning {!r} for statement from '{}:{}'".format(warn, file, start_line))
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
