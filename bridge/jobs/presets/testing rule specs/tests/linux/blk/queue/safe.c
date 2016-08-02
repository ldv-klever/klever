#include <linux/module.h>
#include <linux/blkdev.h>
#include <linux/types.h>

int __init my_init(void)
{
	request_fn_proc *r;
	spinlock_t *spin;
	gfp_t flags;
	struct request_queue *queue = blk_init_queue(r, spin);
	if (queue)
	{
		blk_cleanup_queue(queue);
	}
	queue = blk_alloc_queue(flags);
	if (queue)
	{
		blk_cleanup_queue(queue);
	}

	return 0;
}

module_init(my_init);
