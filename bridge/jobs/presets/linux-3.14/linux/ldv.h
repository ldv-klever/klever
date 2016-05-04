#ifndef __LINUX_LDV_H
#define __LINUX_LDV_H

#include <linux/types.h>

/**
 * ldv_initialize() - explicitly initialize rule specification model states.
 *
 * ldv_initialize() can be defined by rule specification models if they use
 * model states and do not either use explicit or rely upon implicit
 * initialization of global variables that are usually used as model states.
 *
 * ldv_initialize() should be always called by generated environment models
 * just before calling all module initialization functions.
 */
extern void ldv_initialize(void);

/**
 * ldv_post_init() - perform some actions and checks specific for rule
 *                   specifications after calling module initialization
 *                   functions.
 * @init_ret_val:	Return value of module initialization function.
 *
 * ldv_post_init() can be defined by rule specification models.
 *
 * ldv_post_init() should be always called by generated environment models just
 * after calling module initialization functions.
 *
 * Return: Filtered out return value of module initialization function. Callers
 *         should use this returned value rather than @init_ret_val.
 */
extern int ldv_post_init(int init_ret_val);

/**
 * ldv_pre_probe() - perform some actions and checks specific for rule
 *                   specifications before calling module probe callbacks.
 *
 * ldv_pre_probe() can be defined by rule specification models.
 *
 * ldv_pre_probe() should be always called by generated environment models just
 * before calling module probe callbacks.
 */
extern void ldv_pre_probe(void);
/**
 * ldv_post_probe() - perform some actions and checks specific for rule
 *                    specifications after calling module probe callbacks.
 * @probe_ret_val:	Return value of module probe callback.
 *
 * ldv_post_probe() is very like ldv_post_init().
 */
extern int ldv_post_probe(int probe_ret_val);

/**
 * ldv_switch_to_interrupt_context() - switch to interrupt context.
 *
 * ldv_switch_to_interrupt_context() can be defined by rule specification
 * models.
 *
 * ldv_switch_to_interrupt_context() should be always called by generated
 * environment models just before calling interrupt callbacks.
 */
extern void ldv_switch_to_interrupt_context(void);
/**
 * ldv_switch_to_process_context() - switch to process context.
 *
 * ldv_switch_to_process_context() can be defined by rule specification
 * models.
 *
 * ldv_switch_to_process_context() should be always called by generated
 * environment models just after calling interrupt callbacks.
 */
extern void ldv_switch_to_process_context(void);
/**
 * ldv_in_interrupt_context() - is execution in interrupt context.
 *
 * ldv_in_interrupt_context() can be defined by rule specification models.
 *
 * Return: True in case of execution in interrupt context and false otherwise.
 */
extern bool ldv_in_interrupt_context(void);

/**
 * ldv_check_final_state() - perform some checks of final state specific for
 *                           rule specification models
 *
 * ldv_check_final_state() can be defined by rule specification models if they
 * use model states and need to check it at the end.
 *
 * ldv_check_final_state() should be always called by generated environment
 * models just after calling all module exit functions. Nothing should be
 * performed after calling ldv_check_final_state() since this can lead to
 * unexpected false alarms.
 */
extern void ldv_check_final_state(void);

#endif /* __LINUX_LDV_H */
