#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
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

from core.vog.strategies.strategy_utils import Module, Cluster
from core.vog.strategies.abstract_strategy import AbstractStrategy


class Closure(AbstractStrategy):
    def __init__(self, logger, strategy_params, params):
        super().__init__(logger)

        self.logger = logger
        self.cluster_size = params.get('cluster size', 0)
        self.modules = {}
        self.checked_clusters = set()
        self.checked_modules = set()

    def _set_dependencies(self, deps, sizes):
        self.logger.info('Calculate graph of all dependencies between modules')
        for pred, _, module in sorted(deps):
            if pred not in self.modules:
                self.modules[pred] = Module(pred)
            if module not in self.modules:
                self.modules[module] = Module(module)
            self.modules[module].add_predecessor(self.modules[pred])

    def _divide(self, module_name):
        """
        Auxiliary function for preparation groups of modules with
        its dependencies taking into account size restrictions of
        verification objects.
        """

        # Calculation
        if module_name in self.checked_modules:
            return []
        clusters = []
        if module_name == 'all':
            for module in [module for module in self.modules.values() if not module.successors]:
                clusters.extend(self._divide(module.id))
            return clusters
        elif self.is_subsystem(module_name):
            # This is subsystem
            for module in sorted(self.modules.keys()):
                if module.startswith(module_name):
                    clusters.extend(self._divide(module))
            return set(clusters)

        self.logger.info("Start verificaton multimodule task extraction based on closure partitioning")
        self.logger.debug("Calculate dependencies for these 'top' modules")
        root = self.modules.get(module_name, Module(module_name))

        # Will be created own graph
        cluster = Cluster(root)
        if self.cluster_size != 0:
            if cluster.size > self.cluster_size:
                self.logger.info(
                    'Module {0} has too much dependencies, going to divide this verificatoin object'.format(root.id))
                shatters = self.divide_cluster(cluster)
                clusters.extend(shatters)
            else:
                clusters.append(cluster)
        else:
            clusters.append(cluster)

        # Return only not checked clusters
        ret_clusters = []
        for cluster in clusters:
            if cluster not in self.checked_clusters:
                self.checked_clusters.add(cluster)
                ret_clusters.append(cluster)
                self.checked_modules.update([module.id for module in cluster.units])

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
                for module in sorted(task['task_hash'].keys()):
                    if module == task['root']:
                        for child in sorted(task['task_hash'][module]):
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
                    flag = False
                    for module in sorted(task['modules']):
                        if module != task['root'] and module in task['task_hash'] and task['task_hash'][module].keys():
                            flag = True
                            new_task = {'root': module,
                                        'task_hash': new_hash,
                                        'size': len(task['modules']),
                                        'modules': task['modules']}
                            if 'origin' in task:
                                new_task['origin'] = task['origin']
                            else:
                                new_task['origin'] = task['root']
                            rest_list.append(new_task)
                    if not flag:
                        task_id = " ".join(list(sorted(task['modules'])))
                        task_list[task_id] = task
            else:
                task_id = " ".join(list(sorted(task['modules'])))
                task_list[task_id] = task

        # Prepare Cluster objects
        ret = []
        for _, task in sorted(task_list.items()):
            # Initialize module objects
            modules = {}
            for module in sorted(task['modules']):
                modules[module] = Module(module)

            # Add edges
            for obj in sorted(modules.values()):
                for predecessor in sorted(task_hash.get(obj.id, {}).keys()):
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

    def get_modules_to_build(self, modules):
        if not self.is_deps:
            return [], True
        else:
            return self._collect_modules_to_build(modules), False

    def need_dependencies(self):
        return True
