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
from core.lkvog.module_extractors import util
from core.utils import execute


class GraphPartitioner:
    def __init__(self, logger, clade, conf, specified_modules):
        self._logger = logger
        self._clade = clade
        self._bin_path = conf['bin path']
        self._partitions = conf.get('partitions')
        self._tool = conf['tool']
        if self._tool not in ('scotch', 'metis'):
            raise NotImplementedError("Tool {0} is not supported".format(self._tool))

        self._graph_file = "graph.grf"
        self._scotch_out = "partitioner.out"
        self._scotch_log = "partitioner.log"
        self._vertex_to_file = {}
        self._file_to_vertex = {}
        self._file_size = {}
        self._graph = {}
        self._edge_strength = {}
        self._must_module = conf.get("must module", [])

        self._cc_modules = util.extract_cc(self._clade)
        self._dependencies, self._root_files = util.build_dependencies(self._clade)
        self._deps_to_graph()
        if not self._partitions:
            self._partitions = int(len(self._vertex_to_file) / conf['module size'])

    def divide(self):
        splited = None
        if self._tool == 'scotch':
            self._dump_graph_scotch()
            self._run_scotch()
            splited = self._parse_result_scotch()
        elif self._tool == 'metis':
            self._dump_graph_metis()
            self._run_metis()
            splited = self._parse_result_metis()
        modules = {}
        for elems in splited.values():
            current_module_desc_files = set()
            current_module_in_files = set()
            for elem in elems:
                current_module_desc_files.add(self._cc_modules[elem]['id'])
                current_module_in_files.update(self._cc_modules[elem]['in'])
            if current_module_in_files:
                self._logger.debug('Create module with {0} in files'.format(list(current_module_in_files)))
                modules.update(util.create_module_by_desc(current_module_desc_files, current_module_in_files))
        return modules

    def _deps_to_graph(self):
        for file, childs in sorted(self._dependencies.items()):
            if file not in self._cc_modules:
                continue
            if file not in self._file_to_vertex:
                self._file_to_vertex[file] = len(self._file_to_vertex)
                self._vertex_to_file[self._file_to_vertex[file]] = file
                self._graph[self._file_to_vertex[file]] = set()
            for child, s in sorted(childs.items()):
                if child not in self._cc_modules:
                    continue
                if child not in self._file_to_vertex:
                    self._file_to_vertex[child] = len(self._file_to_vertex)
                    self._vertex_to_file[self._file_to_vertex[child]] = child
                    self._graph[self._file_to_vertex[child]] = set()
                edge = tuple(sorted((self._file_to_vertex[file], self._file_to_vertex[child])))
                self._edge_strength[edge] = s
                self._graph[self._file_to_vertex[file]].add(self._file_to_vertex[child])
                self._graph[self._file_to_vertex[child]].add(self._file_to_vertex[file])

    def _dump_graph_scotch(self):
        count_v = len(self._file_to_vertex)
        count_e = len(self._edge_strength) * 2
        with open(self._graph_file, 'w', encoding='utf8') as fp:
            fp.write('0\n{0} {1}\n0 011\n'.format(count_v, count_e))
            for key, value in sorted(self._graph.items()):
                fp.write('{0} {1} {2}\n'.format(self._get_locs(self._vertex_to_file[key]), len(value),
                                                ' '.join(['{0} {1}'.format(self._weight_edge(key, v), v)
                                                         for v in sorted(value)])))

    def _dump_graph_metis(self):
        count_v = len(self._file_to_vertex)
        count_e = len(self._edge_strength) * 2
        with open(self._graph_file, 'w', encoding='utf8') as fp:
            fp.write('{0} {1} 011\n'.format(count_v, int(count_e/2)))
            for key, value in sorted(self._graph.items()):
                fp.write('{0} {1}\n'.format(self._get_locs(self._vertex_to_file[key]),
                                            ' '.join(['{0} {1}'.format(str(v+1), self._weight_edge(key, v))
                                                  for v in sorted(value)])))

    def _run_scotch(self):
        execute(self._logger, [self._bin_path, str(self._partitions), self._graph_file,
                               self._scotch_out, self._scotch_log, "-vm", "-b0.05"])

    def _run_metis(self):
        execute(self._logger, [self._bin_path, self._graph_file, str(self._partitions),
                               "-ufactor={0}".format(500), "-ptype=rb"])

    def _parse_result_scotch(self):
        res = {}
        with open(self._scotch_out, encoding='utf8') as fp:
            lines = fp.readlines()[1:]
            for line in lines:
                line = line.rstrip('\n')
                splts = line.split('\t')
                vertex_no, cluster_no = int(splts[0]), int(splts[1])
                res.setdefault(cluster_no, [])
                res[cluster_no].append(self._vertex_to_file[vertex_no])
        return res

    def _parse_result_metis(self):
        res = {}
        with open("{0}.part.{1}".format(self._graph_file, self._partitions), encoding='utf8') as fp:
            lines = fp.readlines()
            for vertex_no, line in enumerate(lines):
                line = line.rstrip('\n')
                cluster_no = int(line)
                res.setdefault(cluster_no, [])
                res[cluster_no].append(self._vertex_to_file[vertex_no])
        return res

    def _weight_edge(self, e1, e2):
        f1 = self._vertex_to_file[e1]
        f2 = self._vertex_to_file[e2]
        for mm in self._must_module:
            if f1 in mm and f2 in mm:
                return 1000

        strength = self._edge_strength[tuple(sorted((e1, e2)))]
        nearest = self._subsystem_nearest(self._vertex_to_file[e1], self._vertex_to_file[e2])

        return strength + nearest * 10

    @staticmethod
    def _subsystem_nearest(file1, file2):
        file1 = file1.split(os.sep)
        file2 = file2.split(os.sep)
        r = 0
        for f1, f2 in zip(file1, file2):
            if f1 == f2:
                r += 1
            else:
                break
        return 1+r

    def _get_locs(self, file):
        json_desc = self._clade.get_cc().load_json_by_in(file)
        try:
            with open(self._clade.get_file(os.path.join(json_desc['cwd'], file)), encoding='utf-8') as fp:
                return len(fp.readlines())
        except FileNotFoundError:
            self._logger.warning("File {0} not found in {1}".format(file, json_desc['cwd']))
            return 0
        except UnicodeDecodeError:
            return 0

