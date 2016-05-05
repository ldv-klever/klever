#include <linux/types.h>

#include <linux/ldv/common.h>
#include <verifier/rcv.h>

static int ldv_filter_positive_int(int val)
{
    ldv_assume(val <= 0);
	return val;
}

/*
 * Implicitly filter positive integers for all undefined functions. See more
 * details at https://forge.ispras.ru/issues/7140.
 */
int ldv_post_init(int init_ret_val)
{
    return ldv_filter_positive_int(init_ret_val);
}

/* Like ldv_post_init(). */
int ldv_post_probe(int probe_ret_val)
{
    return ldv_filter_positive_int(probe_ret_val);
}

