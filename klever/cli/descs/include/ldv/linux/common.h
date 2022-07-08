/*
 * Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
 * Ivannikov Institute for System Programming of the Russian Academy of Sciences
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#ifndef __LDV_LINUX_COMMON_H
#define __LDV_LINUX_COMMON_H

#include <linux/types.h>
#include <ldv/common/model.h>

/**
 * ldv_switch_to_interrupt_context() - switch to interrupt context.
 *
 * ldv_switch_to_interrupt_context() can be defined by requirement
 * models.
 *
 * ldv_switch_to_interrupt_context() should be always called by generated
 * environment models just before calling interrupt callbacks.
 */
extern void ldv_switch_to_interrupt_context(void);
/**
 * ldv_switch_to_process_context() - switch to process context.
 *
 * ldv_switch_to_process_context() can be defined by requirement
 * models.
 *
 * ldv_switch_to_process_context() should be always called by generated
 * environment models just after calling interrupt callbacks.
 */
extern void ldv_switch_to_process_context(void);
/**
 * ldv_in_interrupt_context() - is execution in interrupt context.
 *
 * ldv_in_interrupt_context() can be defined by requirement models.
 *
 * Return: True in case of execution in interrupt context and false otherwise.
 */
extern bool ldv_in_interrupt_context(void);

/**
 * ldv_failed_usb_register_driver() - do specific for requirement actions if
 *                                    USB callbacks registration failed.
 *
 * ldv_failed_usb_register_driver() can be defined by requirement models.
 *
 * ldv_failed_usb_register_driver() should be always called by generated
 * environment models in a failing branch of usb_register model function.
 */
extern void ldv_failed_usb_register_driver(void);

/**
 * ldv_failed_register_netdev() - perform some actions and checks specific for
 *                                requirements after failed call of register_netdev.
 *
 * ldv_failed_register_netdev() can be defined by requirement models.
 *
 * ldv_failed_register_netdev() should be always called by generated environment.
 */
extern void ldv_failed_register_netdev(void);

/**
 * ldv_post_init() - perform some actions and checks specific for requirement
 *                   after calling module initialization functions.
 * @init_ret_val:	Return value of module initialization function.
 *
 * ldv_post_init() can be weaved by requirement models.
 *
 * ldv_post_init() should be always called by generated environment models just
 * after calling module initialization functions.
 *
 * Return: Filtered out return value of module initialization function. Callers
 *         should use this returned value rather than @init_ret_val.
 */
extern int ldv_post_init(int init_ret_val);

/**
 * ldv_pre_probe() - perform some actions and checks specific for requirement
 *                   before calling module probe callbacks.
 *
 * ldv_pre_probe() can be weaved by requirement models.
 *
 * ldv_pre_probe() should be always called by generated environment models just
 * before calling module probe callbacks.
 */
extern void ldv_pre_probe(void);

/**
 * ldv_post_probe() - perform some actions and checks specific for requirement
 *                    after calling module probe callbacks.
 * @probe_ret_val:	Return value of module probe callback.
 *
 * ldv_post_probe() is very like ldv_post_init().
 */
extern int ldv_post_probe(int probe_ret_val);
extern void ldv_check_return_value_probe(int probe_ret_val);

/**
 * ldv_filter_err_code() - filter positive return values after a call of module callbacks.
 * @ret_val:	           Return value of module callback.
 *
 * ldv_filter_err_code() is very like ldv_post_init().
 */
extern int ldv_filter_err_code(int ret_val);

/**
 * ldv_add_disk() - add partitioning information to kernel list.
 */
extern void ldv_add_disk(void);

/**
 * ldv_add_disk() - remove partitioning information from kernel list.
 */
extern void ldv_del_gendisk(void);

/**
 * ldv_check_alloc_flags() - check flags of a memory allocating function.
 */
extern void ldv_check_alloc_flags(gfp_t flags);

/**
 * ldv_check_alloc_nonatomic() - check that a memory allocating function is
 *                               called in the non-atomic context.
 */
extern void ldv_check_alloc_nonatomic(void);

#endif /* __LDV_LINUX_COMMON_H */
