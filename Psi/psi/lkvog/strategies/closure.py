from psi.lkvog.strategies.module import Module
from psi.lkvog.strategies.module import Cluster

def divide(logger, module_name, module_deps):
     #Auxiliary function for preparation groups of modules with
     #its dependencies taking into account size restrictions of
     #verification objects

     #Wait for module dependencies

     logger.debug('Calculate graph of all dependencies between modules')

     modules = {}

     process_modules = [module_name]

     while module_deps:
         module = process_modules.pop(0)
         if module not in modules:
             modules[module] = Module(module)
         for predecessor in module_deps[module]:
             if predecessor not in modules:
                 modules[predecessor] = Module(predecessor)
                 process_modules.append(predecessor)
             modules[module].add_predecessor(modules[predecessor])

     #TODO: check that graph has not checked

     top_modules = []
     for module in modules:
         #Add only root vertexes to the new list
         if not module.successors:
             top_modules.append(module)

     #Calculation
     clusters = []
     logger.debug('Calculate dependencies for these "top" modules')
     for root in top_modules:
         #Will be created own graph
         cluster = Cluster(root)

         #TODO verification obj size from file
         verification_obj_size = 3
         if verification_obj_size:
             if cluster.size > verification_obj_size:
                 logger.debug('Module' + root.id + 'has too much dependencies, going to divide this verificatoin object')
                 shatters = cluster.divide_cluster(verification_obj_size)

                 clusters.extend(shatters)
             else:
                 clusters.append(cluster)
         else:
             clusters.append(cluster)

     return clusters