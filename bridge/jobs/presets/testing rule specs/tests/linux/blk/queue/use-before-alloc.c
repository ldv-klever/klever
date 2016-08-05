#include <linux/module.h>
#include <linux/blkdev.h>
#include <linux/types.h>

int __init my_init(void)
{
	struct request_queue *queue;
	blk_cleanup_queue(queue);

	return 0;
}

module_init(my_init);
