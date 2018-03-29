import subprocess
import os
from core.lkvog.module_extractors import util
from core.utils import execute

class GraphPartitioner():
    def __init__(self, logger, clade, conf):
        self._logger = logger
        self._clade = clade
        self._bin_path = conf['bin path']
        self._partitions = conf['partitions']
        self._tool = conf['tool']
        if self._tool not in ('scotch', 'metis'):
            raise NotImplementedError("Tool {0} is not supported".format(self._tool))
        #self._root_node = root_node
        #self._params = params

        self._graph_file = "graph.grf"
        self._scotch_out = "partitioner.out"
        self._scotch_log = "partitioner.log"
        self._vertex_to_file = {}
        self._file_to_vertex = {}
        self._file_size = {}
        self._graph = {}
        self._edge_strength = {}
        self._must_module = [["lib/string.c", "kernel/user_namespace.c"]]

        self._cc_modules = util.extract_cc(self._clade)
        self._dependencies, self._root_files = util.build_dependencies(self._clade)
        self._deps_to_graph()
        #self._additional_edges(graph)

    def divide(self):
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
                util.create_module(current_module_desc_files, current_module_in_files)
        return modules


    def _additional_edges(self, graph):
        for mm in self._must_module:
            for i in range(1, len(mm)):
                for j in range(0, i):
                    v1 = self._files[mm[i]]
                    v2 = self._files[mm[j]]
                    if v2 not in graph[v1]:
                        graph[v1].append(v2)
                        graph[v2].append(v1)
        self._dump_graph_metis(graph)

    def _deps_to_graph(self):
        for file, childs in self._dependencies.items():
            if file not in self._cc_modules:
                continue
            if file not in self._file_to_vertex:
                self._file_to_vertex[file] = len(self._file_to_vertex)
                self._vertex_to_file[self._file_to_vertex[file]] = file
                self._graph[self._file_to_vertex[file]] = set()
            for child, s in childs.items():
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

    """
    def _convert_graph(self, root_node):
        ret = {}
        processed = set()
        process = [root_node]
        files = {}
        while process:
            c = process.pop(0)
            if c in processed:
                continue
            processed.add(c)

            if c.file_name() not in files:
                files[c.file_name()] = len(files)
                ret[files[c.file_name()]] = []
                self._vertex_to_file[files[c.file_name()]] = c.file_name()
                self._file_graph[c.file_name()] = []
                self._file_size[c.file_name()] = self._get_locs(c.file_name())

            for child in c.childs():
                if child.file_name() not in files:
                    files[child.file_name()] = len(files)
                    ret[files[child.file_name()]] = []
                    self._vertex_to_file[files[child.file_name()]] = child.file_name()
                    self._file_graph[child.file_name()] = []
                    self._file_size[child.file_name()] = self._get_locs(child.file_name())

                if c.file_name() != child.file_name() and files[child.file_name()] not in ret[files[c.file_name()]]:
                    ret[files[c.file_name()]].append(files[child.file_name()])
                    self._file_graph[c.file_name()].append(child.file_name())
                    #For metis
                    ret[files[child.file_name()]].append(files[c.file_name()])
                    self._file_graph[child.file_name()].append(c.file_name())
                    edge = tuple(sorted((files[child.file_name()], files[c.file_name()])))
                    self._edge_strength.setdefault(edge, 0)
                    self._edge_strength[edge] += 1
                process.append(child)

        self._files = files

        return ret
    """

    def _dump_graph_scotch(self):
        count_v = len(self._file_to_vertex)
        count_e = len(self._edge_strength) * 2
        with open(self._graph_file, 'w', encoding='utf8') as fp:
            fp.write('0\n{0} {1}\n0 000\n'.format(count_v, count_e))
            for key, value in sorted(self._graph.items()):
                fp.write('{0} {1}\n'.format(len(value), ' '.join([str(v) for v in sorted(value)])))

    def _dump_graph_metis(self):
        count_v = len(self._file_to_vertex)
        count_e = len(self._edge_strength) * 2
        with open(self._graph_file, 'w', encoding='utf8') as fp:
            fp.write('{0} {1} 001\n'.format(count_v, int(count_e/2)))
            for key, value in sorted(self._graph.items()):
                fp.write('{0}\n'.format(' '.join(['{0} {1}'.format(str(v+1), self._weight_edge(key, v)) for v in sorted(value)])))

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

        return strength + nearest * 10;


    def _subsystem_nearest(self, file1, file2):
        file1 = file1.split(os.sep)
        file2 = file2.split(os.sep)
        max_res = max(len(file1), len(file2))
        r = 0
        for f1, f2 in zip(file1, file2):
            if f1 == f2:
                r += 1
            else:
                break
        return 1+r# - max_res

    def _get_locs(self, file):
        DIR = "/home/alexey/kernels/linux-3.14"
        with open(os.path.join(DIR, file)) as fp:
            return len(fp.readlines())



