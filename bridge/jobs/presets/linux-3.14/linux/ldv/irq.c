/*
 * Trivial model for interrupt context. Likely it is correct just in case of
 * single thread executed on single CPU core.
 */
#include <linux/ldv/irq.h>

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
