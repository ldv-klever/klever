/*
 * Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
 * Institute for System Programming of the Russian Academy of Sciences
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * ee the License for the specific language governing permissions and
 * limitations under the License.
 */

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
