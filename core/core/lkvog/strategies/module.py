from hashlib import md5

class Module:
    def __init__(self, id):
        self.id = id
        self.predecessors = []
        self.successors = []
        self.deep = 0
        self.size = 0
        self.export_functions = {}
        self.call_functions = {}

    def __lt__(self, other):
        return self.id < other.id

    def add_predecessor(self, predecessor):
        if predecessor:
            self.predecessors.append(predecessor)
            predecessor.successors.append(self)

    def add_successor(self, successor):
        if successor:
            self.successors.append(successor)
            successor.predecessors.append(self)

    def __hash__(self):
        return hash(self.id)

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
            for predecessor in module.predecessors:
                if module.deep + 1 < predecessor.deep or module.deep == 0:
                    predecessor.deep = module.deep + 1
                check.append(predecessor)
            modules[module.id] = module
        self.modules = list(modules.values())
        self.size = len(self.modules)

    def __hash__(self):
        return hash(frozenset(self.modules))

    def md5_hash(self):
        return md5("".join([module.id for module in self.modules]).encode('utf-8')).hexdigest()


class Graph:
    def __init__(self, modules):
        self.modules = modules
        self.root = self.modules[0]
        self.size = len(self.modules)

    def __hash__(self):
        return hash(frozenset(self.modules))

    def md5_hash(self):
        return md5("".join([module.id for module in self.modules]).encode('utf-8')).hexdigest()

