#include <linux/module.h>
#include <linux/blkdev.h>
#include <linux/types.h>

int __init my_init(void)
{
	struct request_queue *r;
	int x;
	gfp_t flags;
	struct request *request_1 = blk_get_request(r, x, flags);
	return 0;
}

module_init(my_init);
