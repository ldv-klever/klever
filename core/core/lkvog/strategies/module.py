from hashlib import md5
from graphviz import Digraph
import os.path


class Module:

    def __init__(self, module_id):
        self.id = module_id
        self.predecessors = []
        self.successors = []
        self.size = 0
        self.export_functions = {}
        self.call_functions = {}

    def __lt__(self, other):
        return self.id < other.id

    def __hash__(self):
        return hash(self.id)

    def add_predecessor(self, predecessor):
        if predecessor:
            self.predecessors.append(predecessor)
            predecessor.successors.append(self)

    def add_successor(self, successor):
        if successor:
            self.successors.append(successor)
            successor.predecessors.append(self)

    @property
    def md5_hash(self):
        return md5(self.id.encode('utf-8').hexdigest())


class Cluster:

    def __init__(self, root):
        self.root = root
        modules = {}
        self.hash = None
        check = [self.root]

        while check:
            module = check.pop(0)
            check.extend(module.predecessors)
            modules[module.id] = module

        self.modules = list(modules.values())

    def draw(self, dir):
        g = Digraph(name=str(self.root.id),
                    format="png")
        for module in self.modules:
            g.node(module.id, module.id)
        for module in self.modules:
            for pred in module.predecessors:
                g.edge(module.id, pred.id)
        g.save(os.path.join(dir, self.root.id + self.md5_hash))
        g.render()

    def __hash__(self):
        return hash(frozenset(self.modules))

    @property
    def md5_hash(self):
        return md5("".join([module.id for module in self.modules]).encode('utf-8')).hexdigest()

    @property
    def size(self):
        return len(self.modules)


class Graph:

    def __init__(self, modules):
        self.modules = modules
        self.root = self.modules[0]

    def __hash__(self):
        return hash(frozenset(self.modules))

    def draw(self, dir):
        g = Digraph(name=str(self.root.id),
                    format="png")
        for module in self.modules:
            g.node(module.id, module.id)
        for module in self.modules:
            for pred in module.predecessors:
                g.edge(module.id, pred.id)
        g.save(os.path.join(dir, self.root.id + self.md5_hash))
        g.render()

    @property
    def md5_hash(self):
        return md5("".join([module.id for module in self.modules]).encode('utf-8')).hexdigest()

    @property
    def size(self):
        return len(self.modules)


def order_build(modules, function_deps):
    deps = {}
    for module1, func, module2 in function_deps:
        deps.setdefault(module2, [])
        deps[module2].append(module1)

    ret = []
    unmarked = list(sorted(list(modules)))
    marked = {}
    while unmarked:
        selected = unmarked.pop(0)
        if selected not in marked:
            visit(selected, marked, ret, modules, deps)

    return ret


def visit(selected, marked, sorted_list, modules, deps):
    if selected not in marked:
        marked[selected] = 0

        if selected in modules:
            for m in set(deps.get(selected, [])).intersection(modules):
                visit(m, marked, sorted_list, modules, deps)

        marked[selected] = 1
        sorted_list.append(selected)
