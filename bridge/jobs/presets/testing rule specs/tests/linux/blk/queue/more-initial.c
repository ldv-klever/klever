#include <linux/module.h>
#include <linux/blkdev.h>
#include <linux/types.h>

int __init my_init(void)
{
	gfp_t flags;
	struct request_queue *queue = blk_alloc_queue(flags);

	return 0;
}

module_init(my_init);
