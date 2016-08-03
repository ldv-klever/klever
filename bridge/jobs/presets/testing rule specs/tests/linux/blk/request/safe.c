#include <linux/module.h>
#include <linux/blkdev.h>
#include <linux/types.h>

int __init my_init(void)
{
	struct request_queue *r;
	struct bio *bio;
	int x;
	gfp_t flags = __GFP_WAIT;
	struct request_queue *queue;
	struct request *request_1, *request_2;

	request_1 = blk_get_request(r, x, flags);
	if (request_1)
		blk_put_request(request_1);
	else
		return -1;
	request_2 = blk_make_request(r, bio, flags);
	if (!IS_ERR(request_2))
		__blk_put_request(queue, request_2);
	return 0;
}

module_init(my_init);
