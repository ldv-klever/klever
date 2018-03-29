
from core.lkvog.module_extractors.linux_kernel import LinuxKernel
from core.lkvog.module_extractors.breadth import Breadth
from core.lkvog.module_extractors.graph_partitioner import GraphPartitioner
from core.lkvog.module_extractors.vertex_merge import VertexMerge

module_extractors_list = {
    'Linux kernel': LinuxKernel,
    'Breadth': Breadth,
    'Graph Partitioner': GraphPartitioner,
    'Vertex Merge': VertexMerge
}
