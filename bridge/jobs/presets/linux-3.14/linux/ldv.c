#include <linux/types.h>

#include <linux/ldv.h>
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

/*
 * Trivial model for interrupt context. Likely it is correct just in case of
 * single thread executed on single CPU core.
 */
static bool __ldv_in_interrupt_context = false;
void ldv_switch_to_interrupt_context(void)
{
    __ldv_in_interrupt_context = true;
}
void ldv_switch_to_process_context(void)
{
    __ldv_in_interrupt_context = false;
}
bool ldv_in_interrupt_context(void)
{
    return __ldv_in_interrupt_context;
}
