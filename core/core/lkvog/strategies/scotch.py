import os

from core.lkvog.strategies.module import Module
from core.lkvog.strategies.module import Graph


class Scotch:
    # TODO: graph_file, scotch_out, scotch_log from parameters
    def __init__(self, logger, module_deps, graph_file, scotch_log,
                 scotch_out, params={}):
        self.logger = logger
        self.scotch_path = params['scotch path']
        self.graph_file = graph_file
        self.scotch_log = scotch_log
        self.scotch_out = scotch_out
        self.module_deps = module_deps
        self.task_size = params['cluster size']
        self.logger.debug('Going to get verification verification objects of size less than ' + str(self.task_size))
        self.balance_tolerance = params.get('balance tolerance', 0.05)
        self.logger.debug('Going to keep balance tolerance equal to ' + str(self.balance_tolerance))
        self.logger.debug('Calculate graph of all dependencies between modules')
        self.clusters = set()

        all_dep_modules = set()
        count_e = 0
        for key, value in self.module_deps.items():
            count_e += len(value)
            all_dep_modules.add(key)
            all_dep_modules.update(value)

        self.logger.debug('There is {0} modules and {1} deps'.format(len(all_dep_modules), count_e))

        unordered_graph = {}
        for key, value in self.module_deps.items():
            if value:
                unordered_graph.setdefault(key, set())
                unordered_graph[key].update(value)

                for v in value:
                    unordered_graph.setdefault(v, set())
                    unordered_graph[v].add(key)

        count_e = sum([len(x) for x in unordered_graph.values()])
        self.logger.debug('Unordered graph contains {0} vertex and {1} edges'.format(len(unordered_graph), count_e))

        dual_graph = {}
        vertex2int = {}
        int2vertex = {}

        i = 0

        for v1 in unordered_graph:

            for v2 in unordered_graph[v1]:
                v12 = v1 + ' ' + v2 if v1 < v2 else v2 + ' ' + v1

                if v12 not in vertex2int:
                    vertex2int[v12] = i
                    int2vertex[i] = v12
                    i += 1

                dual_graph.setdefault(vertex2int[v12], set())
                for v3 in unordered_graph[v1]:
                    if v2 == v3:
                        continue

                    v13 = v1 + ' ' + v3 if v1 < v3 else v3 + ' ' + v1

                    if v13 not in vertex2int:
                        vertex2int[v13] = i
                        int2vertex[i] = v13
                        i += 1

                    dual_graph.setdefault(vertex2int[v13], set())
                    dual_graph[vertex2int[v12]].add(vertex2int[v13])
                    dual_graph[vertex2int[v13]].add(vertex2int[v12])

        count_v = len(dual_graph)
        count_e = int(sum(len(e) for e in dual_graph.values()))

        self.logger.debug('Dual graph contains {0} vertex and {1} edges'.format(count_v, count_e))
        with open(self.graph_file, 'w') as gf:
            gf.write('0\n{0} {1}\n0 000\n'.format(count_v, count_e))
            for key, value in sorted(dual_graph.items()):
                gf.write('{0} {1}\n'.format(len(value), ' '.join([str(v) for v in value])))

        partitions = int(2 * (1 + self.balance_tolerance) * (len(dual_graph) / (self.task_size + 1)))

        self.logger.debug('Going to obtain ' + str(int(partitions)) + ' verification object in total')

        # Going to run scotch partitioner
        result = os.system(os.path.join(self.scotch_path, "gpart") + ' ' + ' '.join([str(partitions), self.graph_file,
                                                                                     self.scotch_out, self.scotch_log,
                                                                                     '-vm', "-b" + str(
                self.balance_tolerance)]))
        if result != 0:
            raise ValueError("Scotch gpart error {}".format(result))
        # Import results
        self.logger.debug("Import partitioning results from the file")

        partitioning = {}
        with open(self.scotch_out, encoding='ascii') as fp:
            lines = fp.readlines()
            for line in lines[1:]:
                line = line.rstrip("\n")
                parts = line.split('\t')
                partitioning.setdefault(parts[1], set())
                partitioning[parts[1]].update(int2vertex[int(parts[0])].split(' '))

        # Prepare module groups
        self.logger.debug('Extract groups for verification objects')
        for group_id in partitioning:
            # Create group with Module
            group_dict = {}
            for module in partitioning[group_id]:
                if module not in group_dict:
                    group_dict[module] = Module(module)

                # Add edges between the groups
                for predecessor in self.module_deps.get(module, []):
                    if predecessor in partitioning[group_id]:
                        if predecessor not in group_dict:
                            group_dict[predecessor] = Module(predecessor)

                        group_dict[module].add_predecessor(group_dict[predecessor])

            if group_dict:
                graph = Graph(sorted(list(group_dict.values())))
                self.clusters.add(graph)

        #if len(clusters) != partitions:
        #    raise ValueError('Number of yielded partitions is less than expected: {0}. Expected: {1}'
        #                     .format(str(len(clusters)), str(partitions)))

        self.logger.info("Number of clusters is {0}".format(len(self.clusters)))

    def divide(self, module_name):
        if module_name == "all":
            return self.clusters

        ret_clusters = [cluster for cluster in self.clusters if module_name in
                        [module.id for module in cluster.modules]]
        self.clusters.difference_update(ret_clusters)
        for ret_cluster in ret_clusters:
            ret_cluster.root = [module for module in ret_cluster.modules if module.id == module_name][0]
        if not ret_clusters:
            ret_clusters = Graph([Module(module_name)])
        return ret_clusters
