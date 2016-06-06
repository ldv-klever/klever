from hashlib import md5


class Module:

    def __init__(self, module_id):
        self.id = module_id
        self.predecessors = []
        self.successors = []
        self.deep = 0
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
        self._root = root
        modules = {}
        self.hash = None
        check = [self.root]

        while check:
            module = check.pop(0)
            for predecessor in module.predecessors:
                # todo: Is it a correct comparison?
                if module.deep + 1 < predecessor.deep or module.deep == 0:
                    predecessor.deep = module.deep + 1
                check.append(predecessor)
            modules[module.id] = module
        self.modules = list(modules.values())

    def __hash__(self):
        return hash(frozenset(self.modules))

    @property
    def md5_hash(self):
        return md5("".join([module.id for module in self.modules]).encode('utf-8')).hexdigest()

    @property
    def size(self):
        return len(self.modules)

    @property
    def root(self):
        return self._root


class Graph:

    def __init__(self, modules):
        self.modules = modules
        self._root = self.modules[0]

    def __hash__(self):
        return hash(frozenset(self.modules))

    @property
    def md5_hash(self):
        return md5("".join([module.id for module in self.modules]).encode('utf-8')).hexdigest()

    @property
    def root(self):
        return self._root

    @property
    def size(self):
        return len(self.modules)
