#include <linux/module.h>
#include <ldv/common/test.h>

struct stats {
        long long int size_minus_node;
        long long int size_plus_node;
        long long int node_minus_size;
};

static inline long long int __ldv_alloc(size_t size, int node) {
	void *p;
	p = vmalloc_node(size, node);
	vfree(p);

        struct stats size_node_stats = {size - node, size + node, node - size};
        long long int res = size_node_stats.size_plus_node - size_node_stats.size_minus_node - size_node_stats.node_minus_size;

        return res;
}
