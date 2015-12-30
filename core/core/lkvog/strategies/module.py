

class Module:
    def __init__(self, id):
        self.id = id
        self.predecessors = []
        self.successors = []
        self.deep = 0
        self.size = 1

    def add_predecessor(self, predecessor):
        if predecessor:
            self.predecessors.append(predecessor)
            predecessor.successors.append(self)
            return 1
        else:
            return 0

    def __hash__(self):
        return hash(self.id)


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


class Graph:
    def __init__(self, modules):
        self.modules = modules
        self.root = self.modules[0]
        self.size = len(self.modules)

    def __hash__(self):
        return hash(frozenset(self.modules))
