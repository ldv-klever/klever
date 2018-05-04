import os
from core.lkvog.module_extractors import util


class Node:
    def __init__(self, name, locs, elems=None):
        self.name = name
        self.parents = set()
        self.childs = set()
        self.locs = locs
        if not elems:
            self.elems = [name]
        else:
            self.elems = elems

    def __str__(self):
        return str(self.elems)

    def __repr__(self):
        return str(self)

    def __lt__(self, rhs):
        return self.name < rhs.name


class VertexMerge:
    def __init__(self, logger, clade, conf):
        self._logger = logger
        self._clade = clade
        self._conf = conf
        self._max_iters = self._conf.get('max iters', 200)
        self._max_locs = self._conf.get('max locs')
        self._max_files = self._conf.get('max files')
        self._only_same_subsystems = self._conf.get('same subsystems')
        self._file_sizes = {}
        self._cc_modules = util.extract_cc(self._clade)
        self._dependencies, self._root_files = util.build_dependencies(self._clade)
        self._graph = self._convert_graph()

    def _convert_graph(self):
        ret = {}
        processed = set()
        process = self._root_files
        while process:
            c = process.pop(0)
            if c in processed:
                continue
            processed.add(c)

            if c not in self._cc_modules:
                continue

            if c not in ret:
                ret[c] = Node(c, self._get_locs(c))

            for child in sorted(self._dependencies.get(c, [])):
                if child not in self._cc_modules:
                    continue
                if child not in ret:
                    ret[child] = Node(child, self._get_locs(child))

                ret[c].childs.add(ret[child])
                ret[child].parents.add(ret[c])

                process.append(child)

        return ret

    def _merge_nodes(self, n1, n2):
        new_node = Node(n1.name, n1.locs + n2.locs, n1.elems + n2.elems)
        if new_node.locs >= self._max_locs:
            print(n1.elems, n2.elems)
        new_node.parents = n1.parents.union(n2.parents).difference({n1, n2})
        new_node.childs = n1.childs.union(n2.childs).difference({n1, n2})
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

        merged = False # True
        while merged:
            merged = False
            for child in sorted(new_node.childs):
                if len(child.parents) == 1 \
                        and self._is_mergeable(new_node, child):
                    new_node = self._merge_nodes(new_node, child)
                    merged = True

        return new_node

    @staticmethod
    def _subsystem_nearest(file1, file2):
        return 0
        file1 = file1.split(os.path.sep)
        file2 = file2.split(os.path.sep)
        r = 0
        for f1, f2 in zip(file1, file2):
            if f1 == f2:
                r += 1
            else:
                break
        return 1+r

    @staticmethod
    def _same_subsystem(node1, node2):
        return os.path.dirname(node1.name) == os.path.dirname(node2.name)

    def _get_locs(self, file):
        desc = self._clade.get_cc().load_json_by_in(file)
        try:
            for in_file in desc['in']:
                with open(self._clade.get_file(os.path.join(desc['cwd'], in_file))) as fp:
                    return sum(1 for _ in fp)
        except:
            return 0

    def _is_mergeable(self, node1, node2):
        if self._max_files and len(node1.elems) + len(node2.elems) > self._max_files:
            return False
        if self._max_locs and node1.locs + node2.locs > self._max_locs:
            return False
        if self._only_same_subsystems and not self._same_subsystem(node1, node2):
            return False
        return True

    def divide(self):
        merged = False # True
        count_merged = 0

        while merged:
            merged = False
            for node in sorted(self._graph.values()):
                if len(node.childs) != 1:
                    continue
                for child in sorted(node.childs):
                    if len(child.parents) == 1 \
                            and self._is_mergeable(node, child):
                        self._merge_nodes(node, child)
                        merged = True
                        count_merged += 1
                        break
                else:
                    continue
                break
        # print(count_merged)
        # return {i: node.elems for i, node in enumerate(graph.values())}, self._file_graph
        i = None
        for i in range(self._max_iters):
            candidates = None
            mdiff = 0
            for node in sorted(self._graph.values()):
                for parent in sorted(node.parents):
                    for child in sorted(parent.childs):
                        if child != node and self._is_mergeable(node, child):
                            diff = len(child.parents.symmetric_difference(node.parents))
                            if not candidates:
                                candidates = (child, node)
                            elif diff < mdiff \
                                    and self._subsystem_nearest(node.name, child.name) \
                                    > self._subsystem_nearest(candidates[0].name, candidates[1].name):
                                candidates = (child, node)
            if not candidates:
                break
            self._merge_nodes(candidates[0], candidates[1])
        self._logger.debug("Iterations {0}".format(i))
        modules = {}
        for node in sorted(self._graph.values()):
            module_desc_files = set([self._cc_modules[cur]['id'] for cur in node.elems])
            module_in_files = set()
            for elem in node.elems:
                module_in_files.update(self._cc_modules[elem]['in'])
            self._logger.debug('Create module with {0} in files'.format(list(module_in_files)))
            modules.update(util.create_module(module_desc_files, module_in_files))
        return modules
