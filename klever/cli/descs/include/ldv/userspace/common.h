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

#ifndef __LDV_USERSPACE_COMMON_H
#define __LDV_USERSPACE_COMMON_H

/**
 * ldv_initialize() - explicitly initialize requirement model states.
 *
 * ldv_initialize() can be defined by requirement models if they use
 * model states and do not either use explicit or rely upon implicit
 * initialization of global variables that are usually used as model states.
 *
 * ldv_initialize() should be always called by generated environment models
 * just before calling all module initialization functions.
 */
extern void ldv_initialize(void);

/**
 * ldv_check_final_state() - perform some checks of final state specific for
 *                           requirement models.
 *
 * ldv_check_final_state() can be defined by requirement models if they
 * use model states and need to check it at the end.
 *
 * ldv_check_final_state() should be always called by generated environment
 * models just after calling all module exit functions. Nothing should be
 * performed after calling ldv_check_final_state() since this can lead to
 * unexpected false alarms.
 */
extern void ldv_check_final_state(void);

/**
 * ldv_filter_err_code() - filter positive return values after a call of module callbacks.
 * @ret_val:	           Return value of module callback.
 *
 * ldv_filter_err_code() is very like ldv_post_init().
 */
extern int ldv_filter_err_code(int ret_val);

#endif /* __LDV_USERSPACE_COMMON_H */
