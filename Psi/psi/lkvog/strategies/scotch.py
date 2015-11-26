from psi.lkvog.strategies.module import Module
from psi.lkvog.strategies.module import Cluster
from psi.lkvog.strategies.module import Graph
import os

class Scotch:
    #TODO: graph_file, scotch_out, scotch_log from parameters
    def __init__(self, logger, module_deps, task_size, balance_tolerance, graph_file, scotch_path, scotch_log, scotch_out):
        self.logger = logger
        self.graph_file = graph_file
        self.scotch_path = scotch_path
        self.scotch_log = scotch_log
        self.scotch_out = scotch_out
        self.module_deps = module_deps
        self.edge_to_id = {}
        self.id_to_edge = []
        self.task_size = task_size
        self.logger.debug('Going to get verification verification objects of size less than ' + str(self.task_size))
        self.balance_tolerance = balance_tolerance
        self.logger.debug('Going to keep balance tolerance equal to ' + str(self.balance_tolerance))
        self.logger.debug('Calculate graph of all dependencies between modules')
        self.modules = {}
        self.checked_clusters = set()


    def divide(self, module_name):
        self.logger.debug('Start verificaton multimodule task extraction based on scotch partitioning')

        dual_graph, dual_edges_num = self.get_dual_graph(module_name)

        self.logger.debug('Going to print dual graph to file:')
        self.print_and_check_dual_graph(dual_graph, dual_edges_num)

        #Determine how much partitions we are going to obtain
        partitions = 2 * (1 + self.balance_tolerance) * (len(dual_graph) / (self.task_size + 1))

        self.logger.debug('Going to obtain ' + str(partitions) + ' verification object in total')

        #Going to run scotch partitioner
        result = os.system(os.path.join(self.scotch_path, "gpart") + ' ' + ' '.join([str(partitions), self.graph_file,
                                                self.scotch_out, self.scotch_log, '-vm', "-b" + str(self.balance_tolerance)]))

        #Import results
        self.logger.debug("Import partitioning results from the file")

        partitioning = {}
        with open(self.scotch_out) as fp:
            lines = fp.readlines()
            for line in lines[1:]:
                line = line.rstrip("\n")
                parts = line.split('\t')
                for module in self.id_to_edge[int(parts[0])].split(' '):
                    partitioning.setdefault(parts[1], {})
                    partitioning[parts[1]][module] = 1

        #Prepare module groups
        self.logger.debug('Extract groups for verification objects')
        clusters = []
        for group_id in partitioning:

            #Create group with Module
            group_dict = {}
            for module in partitioning[group_id]:
                if module not in group_dict:
                    group_dict[module] = Module(module)

                #Add edges between the groups
                for predecessor in self.module_deps.get(module, []):
                    if predecessor in partitioning[group_id]:
                        if predecessor not in group_dict:
                            group_dict[predecessor] = Module(predecessor)

                        group_dict[module].add_predecessor(group_dict[predecessor])

            if group_dict:
                graph = Graph(group_dict.values())
                clusters.append(graph)

        if len(clusters) != partitions:
            self.logger.debug('Number of yielded partitions is less than expected: ' + str(len(clusters)) + ' expected: ' + str(partitions))

        ret_clusters = []
        for cluster in clusters:
            hash_num = hash(cluster)
            if hash_num not in self.checked_clusters:
                self.checked_clusters.add(hash_num)
                ret_clusters.append(cluster)

        return ret_clusters



    def get_dual_graph(self, module_name):
        self.logger.debug('Going to extract connective graph')
        connective_graph = self.extract_connective_graph(module_name)

        self.logger.debug('Going to prepare dual graph for extracted connective one')
        return self.prepare_dual_graph(connective_graph)

    def extract_connective_graph(self, module_name):
        self.logger.debug('Going to prepare undirected graph of dependencies')
        undirected_graph = self.collect_undirected_graph(module_name)
        connective_graph = {}

        #Hash to get internal numercal ds by module id
        vert_to_id = {}

        #List where num - internal id and value - module id
        id_to_vert = []

        #number of edges
        edges_num = 0

        vertex_key = 0
        edge_key = 0

        #Check all nodes
        for module in undirected_graph:

            #Keep only modules with dependencies
            #Maybe it's redundant
            if undirected_graph[module]:
                vert_to_id[module] = vertex_key
                id_to_vert.append(module)
                vertex_key += 1

                #Add edges
                for connected in undirected_graph[module]:
                    #Add new vertex
                    if module not in connective_graph or connected not in connective_graph[module]:
                        edges_num += 1
                    if connected not in connective_graph or module not in connective_graph[connected]:
                        edges_num += 1

                    if ' '.join((module, connected)) not in self.edge_to_id \
                        and ' '.join((connected, module)) not in self.edge_to_id:
                        #Get verticles
                        self.edge_to_id[' '.join((module, connected))] = edge_key
                        self.id_to_edge.append(' '.join((module, connected)))
                        edge_key += 1
                    connective_graph.setdefault(connected, {})
                    connective_graph[connected][module] = 1

                    connective_graph.setdefault(module, {})
                    connective_graph[module][connected] = 1

        self.logger.debug('Connective graph contains: ' + str(len(connective_graph)) + ' verticles')
        self.logger.debug('Connective graph contains: ' + str(edges_num) + ' edges')

        return connective_graph

    def collect_undirected_graph(self, module_name):
        undirected_graph = {}
        process_modules = [module_name]
        while process_modules:
            module = process_modules.pop(0)
            for predecessor in self.module_deps.get(module, []):
                undirected_graph.setdefault(module, {})
                undirected_graph[module][predecessor] = 1

                undirected_graph.setdefault(predecessor, {})
                undirected_graph[predecessor][module] = 1

            process_modules.extend(self.module_deps.get(module, []))

        self.logger.debug('Undirected graph contains: ' + str(len(undirected_graph)) + ' verticles')
        return undirected_graph

    def prepare_dual_graph(self, connective_graph):
        #Prepare graph
        dual_edges_num = 0
        dual_graph = {}
        for v1 in connective_graph:
            for v2 in connective_graph[v1]:
                #Get id
                if ' '.join((v1, v2)) in self.edge_to_id:
                    edge = self.edge_to_id[' '.join((v1, v2))]
                else:
                    edge = self.edge_to_id[' '.join((v2, v1))]

                for v3 in connective_graph[v1]:
                    #Get id
                    if ' '.join((v1, v3)) in self.edge_to_id:
                        e = self.edge_to_id[' '.join((v1, v3))]
                    else:
                        e = self.edge_to_id[' '.join((v3, v1))]

                    if e != edge:
                        if edge not in dual_graph or e not in dual_graph[edge]:
                            dual_edges_num += 1
                        if e not in dual_graph or edge not in dual_graph[e]:
                            dual_edges_num += 1
                        dual_graph.setdefault(edge, {})
                        dual_graph[edge][e] = 1

                        dual_graph.setdefault(e, {})
                        dual_graph[e][edge] = 1

        #Print stats
        self.logger.debug('Dual graph contains: ' + str(len(dual_graph)) + ' verticles')
        self.logger.debug('Dual graph contains: ' + str(dual_edges_num) + ' edges')

        return (dual_graph, dual_edges_num)

    def print_and_check_dual_graph(self, dual_graph, dual_edges_num):
        edges_num_check = 0

        #Prin header
        text_to_print = ['0\n', str(len(dual_graph)) + ' ' + str(dual_edges_num) + '\n', '0 000\n']
        #Prepare rows with info about nodes and edges
        ids = len(self.edge_to_id)
        for i in range(ids):

            #Get list of child verticles
            text_to_print.append(str(len(dual_graph[i])) + ' ' + ' '.join([str(x) for x in dual_graph[i]]) + '\n')
            edges_num_check += len(dual_graph[i])

        #Write them
        with open(self.graph_file, 'w') as fp:
            fp.write(''.join(text_to_print))

        #Check that number of edges was determined correctly
            if edges_num_check == dual_edges_num:
                self.logger.debug('Number of edges in dual graph was determied correctly: ' + str(dual_edges_num))
            else:
                self.logger.debug('Number of edges in dual graph was determined incorrectly. Correct number is ' + str(edges_num_check))

        return