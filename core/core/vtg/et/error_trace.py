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


class ErrorTrace:

    def __init__(self):
        self._nodes = dict()
        self._files = list()
        self._funcs = list()
        self._entry_node_id = None
        self._violation_node_ids = set()
        self.aux_funcs = dict()
        self.emg_comments = dict()

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

    def add_aux_func(self, identifier, name):
        self.aux_funcs[identifier] = name

    def add_emg_comment(self, file, line, tp, instance, comment):
        if file not in self.emg_comments:
            self.emg_comments[file] = dict()
        self.emg_comments[file][line] = {
            'type': tp,
            'instance': instance,
            'comment': comment,
        }

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
        if not end and len(list(self.violation_nodes)) > 0:
            nodes = [node for identifier, node in self.violation_nodes if len(node['in']) > 0]
            if len(nodes) > 0:
                end = nodes[0]['in'][0]
        if backward:
            getter = self.previous_edge
        else:
            getter = self.next_edge

        current = None
        while True:
            if not current:
                current = begin
                yield current
            if end and current is end:
                raise StopIteration
            else:
                current = getter(current)
                if not current:
                    raise StopIteration
                else:
                    yield current

    def insert_edge_and_target_node(self, edge):
        new_edge = {
            'target node': None,
            'source node': None,
            'file': 0
        }
        new_node = self.add_node(int(len(self._nodes)))

        edge['target node']['in'].remove(edge)
        edge['target node']['in'].append(new_edge)
        new_edge['target node'] = edge['target node']
        edge['target node'] = new_node
        new_node['in'] = [edge]
        new_node['out'] = [new_edge]
        new_edge['source node'] = new_node

        return new_edge

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
