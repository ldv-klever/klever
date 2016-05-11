#ifndef __LINUX_LDV_IRQ_H
#define __LINUX_LDV_IRQ_H

#include <linux/types.h>

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

#endif /* __LINUX_LDV_IRQ_H */
