class Module:
    def __init__(self, id):
        self.id = id
        self.predecessors = []
        self.successors = []
        self.deep = 0
        self.size = 1

    def add_predecessor(self, pred):
        if pred:
            self.predecessors.append(pred)
            pred.successors.append(self)
            return 1
        else:
            return 0


class Cluster:
    def __init__(self, root):
        self.root = root
        modules = {}
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

    def divide_cluster(self, size):

        # Get simple hash
        hash = {}
        for module in self.modules:
            for pred in module.predecessors:
                hash.setdefault(module.id, {}).setdefault(pred.id, 0)
                hash[module.id][pred.id] += 1

        # Use hash to keep only unque tasks
        task_list = {}
        rest_list = [{'root': self.root.id,
                      'hash': hash,
                      'size': 1,
                      'modules': [self.root.id]}]
        while rest_list:
            task = rest_list.pop(0)

            # Trying to add all children
            children = task['hash'][task['root']].keys()
            while children and task['size'] < size:
                # Add child to group
                child = children.pop(0)
                task['modules'].append(child)
                if child in task['hash'] and task['hash'][child] > 0:
                    new_task = {'root': child,
                                'hash': task['hash'],
                                'size': 1,
                                'modules': [child]}
                    rest_list.append(new_task)
            if task['size'] < size or children:

                # Reach limit, rebuild graph without selected edges
                new_hash = {}
                exclude = {x: 1 for x in task['modules']}
                for module in task['hash'].keys():
                    if module != task['root']:
                        for child in task['hash'][module]:
                            if child not in exclude:
                                new_hash.setdefault(module, {})
                                new_hash[module][child] = 1
                    else:
                        new_hash[module] = task['hash'][module]

                if children:

                    # Limit reached ? Proceed with same values but new hash
                    new_task = {'root': task['root'],
                                'hash': new_hash,
                                'size': 1,
                                'modules': [task['root']]}
                    rest_list.append(new_task)

                    id = " ".join(list(sorted(task['modules'])))
                    task_list[id] = task
                else:

                    # Limit wasn't reached ? Find new root
                    for m in task['modules']:
                        if m != task['root'] and m in task['hash'] and task['hash'][m].keys():
                            new_task = {'root': m,
                                        'hash': new_hash,
                                        'size': len(task['modules']),
                                        'modules': task['modules']}
                            if 'origin' in task:
                                new_task['origin'] = task['origin']
                            else:
                                new_task['origin'] = task['root']
                            rest_list.append(new_task)
            else:
                id = " ".join(list(sorted(task['modules'])))
                task_list[id] = task

        # Prepare Cluster objects
        ret = []
        for task in task_list.values():

            # Initialize module objects
            modules = {}
            for module in task['modules']:
                modules[module] = Module(module)

            # Add edges
            for obj in modules.values():
                for predecessor in hash[obj.id].keys():
                    if predecessor in hash[obj.id]:
                        obj.add_predecessor(modules[predecessor])
            # If root was shifted down during calculation - use original one
            if ('origin' in task):
                root = modules[task['origin']]
            else:
                root = modules[task['root']]
            cluster = Cluster(root)
            ret.append(cluster)

        return ret
