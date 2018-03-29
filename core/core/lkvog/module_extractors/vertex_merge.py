import os
from core.lkvog.module_extractors import util


class Node():
    def __init__(self, name, elems = None):
        self.name = name
        self.parents = set()
        self.childs = set()
        if not elems:
            self.elems = [name]
        else:
            self.elems = elems

    def __str__(self):
        return str(self.elems)

    def __repr__(self):
        return str(self)

class VertexMerge():
    def __init__(self, logger, clade, conf):
        self._logger = logger
        self._clade = clade
        self._conf = conf
        self._file_sizes = {}
        self._cc_modules = util.extract_cc(self._clade)
        self._dependencies, self._root_files = util.build_dependencies(self._clade)
        self._graph = self._convert_graph()

    def _convert_graph(self):
        ret = {}
        processed = set()
        process = list(self._root_files)
        edges = set()
        while process:
            c = process.pop(0)
            if c in processed:
                continue
            processed.add(c)

            if c not in self._cc_modules:
                continue

            if c not in ret:
                ret[c] = Node(c)

            for child in self._dependencies[c]:
                if child not in self._cc_modules:
                    continue
                if child not in ret:
                    ret[child] = Node(child)

                ret[c].childs.add(ret[child])
                ret[child].parents.add(ret[c])

                process.append(child)

        return ret

    def _merge_nodes(self, n1, n2):
        new_node = Node(n1.name, n1.elems + n2.elems)
        new_node.parents = n1.parents.union(n2.parents).difference(set((n1, n2)))
        new_node.childs = n1.childs.union(n2.childs).difference(set((n1, n2)))
        for n in (n1, n2):
            for parent in n.parents:
                parent.childs.remove(n)
            for child in n.childs:
                child.parents.remove(n)
        for parent in new_node.parents:
            parent.childs.add(new_node)
        for child in new_node.childs:
            child.parents.add(new_node)

        del self._graph[n1.name]
        del self._graph[n2.name]
        self._graph[new_node.name] = new_node

        merged = True
        while merged:
            merged = False
            for child in new_node.childs:
                if self._same_subsystem(new_node, child) \
                        and len(child.parents) == 1:
                    new_node = self._merge_nodes(new_node, child)
                    break

        return new_node

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

    def _same_subsystem(self, node1, node2):
        return os.path.dirname(node1.name) == os.path.dirname(node2.name)

    def _get_locs(self, file):
        #TODO
        return 0


    def divide(self):

        merged = True
        count_merged = 0

        while merged:
            merged = False
            for node in self._graph.values():
                for child in node.childs:
                    if self._same_subsystem(node, child) \
                            and len(child.parents) == 1:
                        self._merge_nodes(node, child)
                        merged = True
                        count_merged += 1
                        break
                else:
                    continue
                break
        #print(count_merged)
        #return {i: node.elems for i, node in enumerate(graph.values())}, self._file_graph

        for i in range(200):
            print(i)
            candidates = None
            mdiff = 0
            for node in self._graph.values():
                for parent in node.parents:
                    for child in parent.childs:
                        if child != node \
                                and self._same_subsystem(node, child):
                            diff = len(child.parents.symmetric_difference(node.parents))
                            if not candidates and len(child.elems) + len(node.elems) < 4:
                                candidates = (child, node)
                            elif diff < mdiff and len(child.elems) + len(node.elems) < 4 and self._subsystem_nearest(node.name, child.name) > self._subsystem_nearest(candidates[0].name, candidates[1].name):
                                candidates = (child, node)
            if not candidates:
                break
            self._merge_nodes(candidates[0], candidates[1], graph)
        modules = {}
        for node in self._graph.values():
            module_desc_files = set([self._cc_modules[cur]['id'] for cur in node.elems])
            module_in_files = set()
            for elem in node.elems:
                module_in_files.update(self._cc_modules[elem]['in'])
            self._logger.debug('Create module with {0} in files'.format(list(module_in_files)))
            modules.update(util.create_module(module_desc_files, module_in_files))
        return modules

