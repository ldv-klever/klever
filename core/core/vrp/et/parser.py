#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
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

import xml.etree.ElementTree as ET

from core.vrp.et.error_trace import ErrorTrace


class ErrorTraceParser:
    WITNESS_NS = {'graphml': 'http://graphml.graphdrawing.org/xmlns'}

    def __init__(self, logger, witness):
        self._logger = logger

        # Start parsing
        self.error_trace = ErrorTrace(logger)
        self._parse_witness(witness)
        self._check_given_files()
        self.error_trace.sanity_checks()

    def _check_given_files(self):
        last_used_file = None
        for edge in self.error_trace.trace_iterator():
            if 'file' in edge and edge['file'] is not None:
                last_used_file = edge['file']
            elif ('file' not in edge or edge['file'] is None) and last_used_file is not None:
                edge['file'] = last_used_file
            else:
                self._logger.warning("Cannot determine file for edge: '{}: {}'".
                                     format(edge['start line'], edge['source']))
                # We cannot predict the file and have to delete it
                if 'enter' in edge or 'return' in edge:
                    raise ValueError("There should not be 'enter' or 'return' in the edge")
                self.error_trace.remove_edge_and_target_node(edge)

    def _parse_witness(self, witness):
        self._logger.info('Parse witness {!r}'.format(witness))

        with open(witness, encoding='utf8') as fp:
            tree = ET.parse(fp)

        root = tree.getroot()

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
        main_id = None

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
                    try:
                        identifier = self.error_trace.add_file(data.text)
                        _edge['file'] = identifier
                    except FileNotFoundError:
                        _edge['file'] = None
                elif data_key == 'startline':
                    _edge['start line'] = int(data.text)
                elif data_key == 'endline':
                    _edge['end line'] = int(data.text)
                elif data_key == 'sourcecode':
                    _edge['source'] = data.text
                elif data_key == 'enterFunction' or data_key == 'returnFrom' or data_key == 'assumption.scope':
                    self.error_trace.add_function(data.text)
                    if data.text == 'main':
                        main_id = self.error_trace.resolve_function_id(data.text)
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
                elif data_key == 'threadId':
                    _edge['thread'] = data.text
                elif data_key in ('startoffset', 'endoffset'):
                    pass
                elif data_key in ('note', 'warning'):
                    _edge[data_key if data_key == 'note' else 'warn'] = data.text
                elif data_key not in unsupported_edge_data_keys:
                    self._logger.warning('Edge data key {!r} is not supported'.format(data_key))
                    unsupported_edge_data_keys[data_key] = None

            if isinstance(main_id, int) and 'enter' in _edge and _edge['enter'] == main_id:
                if 'source' in _edge:
                    del _edge['enter']
                else:
                    _edge["source"] = "Begin program execution"

            edges_num += 1

        self._logger.debug('Parse {0} edges and {1} sink edges'.format(edges_num, sink_edges_num))

