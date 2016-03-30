from core.lkvog.strategies.module import Module
from core.lkvog.strategies.module import Cluster


class Closure:
    def __init__(self, logger, module_deps, params={}):
        self.logger = logger
        self.cluster_size = params.get('cluster size', 0)
        self.logger.info('Calculate graph of all dependencies between modules')
        self.modules = {}
        self.checked_clusters = set()

        for module in module_deps:
            if module not in self.modules:
                self.modules[module] = Module(module)
            for pred in module_deps[module]:
                if pred not in self.modules:
                    self.modules[pred] = Module(pred)
                self.modules[module].add_predecessor(self.modules[pred])

    def divide(self, module_name):
        """Auxiliary function for preparation groups of modules with
        its dependencies taking into account size restrictions of
        verification objects"""

        # Calculation
        clusters = []
        self.logger.info("Start verificaton multimodule task extraction based on closure partitioning")
        self.logger.debug('Calculate dependencies for these "top" modules')
        root = self.modules.get(module_name, Module(module_name))
        # Will be created own graph
        cluster = Cluster(root)
        if self.cluster_size != 0:
            if cluster.size > self.cluster_size:
                self.logger.info('Module {0} has too much dependencies, going to divide this verificatoin object'.format(root.id))
                shatters = self.divide_cluster(cluster)
                clusters.extend(shatters)
            else:

                clusters.append(cluster)
        else:
            clusters.append(cluster)

        # Return only not checked clusters
        ret_clusters = []
        for cluster in clusters:
            hash_num = hash(cluster)
            if hash_num not in self.checked_clusters:
                self.checked_clusters.add(hash_num)
                ret_clusters.append(cluster)

        return ret_clusters

    def divide_cluster(self, input_cluster):

        # Get simple task_hash
        task_hash = {}
        for module in input_cluster.modules:
            for pred in module.predecessors:
                task_hash.setdefault(module.id, {}).setdefault(pred.id, 0)
                task_hash[module.id][pred.id] += 1

        # Use task_hash to keep only unque tasks
        task_list = {}
        rest_list = [{'root': input_cluster.root.id,
                      'task_hash': task_hash,
                      'size': 1,
                      'modules': [input_cluster.root.id]}]
        while rest_list:
            task = rest_list.pop(0)

            # Trying to add all children
            children = list(task['task_hash'].get(task['root'], {}).keys())
            while children and task['size'] < self.cluster_size:
                # Add child to group
                child = children.pop(0)
                task['modules'].append(child)
                task['size'] += 1
                if child in task['task_hash'] and len(task['task_hash'][child]) > 0:
                    new_task = {'root': child,
                                'task_hash': task['task_hash'],
                                'size': 1,
                                'modules': [child]}
                    rest_list.append(new_task)
            if task['size'] < self.cluster_size or children:

                # Reach limit, rebuild graph without selected edges
                new_hash = {}
                exclude = {module: 1 for module in task['modules']}
                for module in task['task_hash'].keys():
                    if module == task['root']:
                        for child in task['task_hash'][module]:
                            if child not in exclude:
                                new_hash.setdefault(module, {})
                                new_hash[module][child] = 1
                    else:
                        new_hash[module] = task['task_hash'][module]

                if children:

                    # Limit reached ? Proceed with same values but new task_hash
                    new_task = {'root': task['root'],
                                'task_hash': new_hash,
                                'size': 1,
                                'modules': [task['root']]}
                    rest_list.append(new_task)

                    task_id = " ".join(list(sorted(task['modules'])))
                    task_list[task_id] = task
                else:

                    # Limit wasn't reached ? Find new root
                    for module in task['modules']:
                        if module != task['root'] and module in task['task_hash'] and task['task_hash'][module].keys():
                            new_task = {'root': module,
                                        'task_hash': new_hash,
                                        'size': len(task['modules']),
                                        'modules': task['modules']}
                            if 'origin' in task:
                                new_task['origin'] = task['origin']
                            else:
                                new_task['origin'] = task['root']
                            rest_list.append(new_task)
            else:
                task_id = " ".join(list(sorted(task['modules'])))
                task_list[task_id] = task

        # Prepare Cluster objects
        ret = []
        for task in task_list.values():

            # Initialize module objects
            modules = {}
            for module in task['modules']:
                modules[module] = Module(module)

            # Add edges
            for obj in modules.values():
                for predecessor in task_hash.get(obj.id, {}).keys():
                    if predecessor in modules:
                        obj.add_predecessor(modules[predecessor])
            # If root was shifted down during calculation - use original one
            if 'origin' in task:
                root = modules[task['origin']]
            else:
                root = modules[task['root']]
            cluster = Cluster(root)
            ret.append(cluster)

        self.logger.info("The nuber of clusters is {0}".format(len(ret)))
        return ret
