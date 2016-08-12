#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

struct request_queue;

enum {
/* There are 2 possible states of queue. */
  LDV_NO_QUEUE = 0,     /* There is no queue or queue was cleaned. */
  LDV_INITIALIZED_QUEUE /* Queue was created. */
};

static int ldv_queue_state = LDV_NO_QUEUE;

/* MODEL_FUNC_DEF Allocate queue. */
struct request_queue *ldv_request_queue(void *dummy)
{
	/* ASSERT Queue should not be allocated twice. */
	ldv_assert("linux:blk:queue::double allocation", ldv_queue_state == LDV_NO_QUEUE);
	/* OTHER Choose an arbitrary return value. */
	struct request_queue *res = (struct request_queue *)ldv_undef_ptr();
	/* OTHER If memory is not available. */
	if (res) {
		/* CHANGE_STATE Allocate gendisk. */
		ldv_queue_state = LDV_INITIALIZED_QUEUE;
		/* RETURN Queue was successfully created. */
		return res;
	}
	/* RETURN There was an error during queue creation. */
	return res;
}

/* MODEL_FUNC_DEF Free queue. */
void ldv_blk_cleanup_queue(void)
{
	/* ASSERT Queue should be allocated . */
	ldv_assert("linux:blk:queue::use before allocation", ldv_queue_state == LDV_INITIALIZED_QUEUE);
	/* CHANGE_STATE Free queue. */
	ldv_queue_state = LDV_NO_QUEUE;
}

/* MODEL_FUNC_DEF Check that queue are not allocated at the end */
void ldv_check_final_state(void)
{
	/* ASSERT Queue must be freed at the end. */
	ldv_assert("linux:blk:queue::more initial at exit", ldv_queue_state == LDV_NO_QUEUE);
}
